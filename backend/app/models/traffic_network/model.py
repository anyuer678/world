"""Road-network traffic as a time-stepped cell-transmission model.

The directed graph comes from params: nodes carry layout coordinates, edges
are roads divided into unit cells (one vehicle per cell), and optional node
signals alternate between two explicit groups of incoming approaches
(group_a green first half-cycle, group_b second). Vehicles follow
Nagel-Schreckenberg-style rules (accelerate, brake on gap or red light,
randomize, move); routes are shortest paths picked at spawn. One step = one
tick (dt = 1). slow_prob=0 makes the whole model deterministic.
"""
from __future__ import annotations

import heapq
from typing import Any, ClassVar

from ...core.engine.models_base import TimeSteppedModel
from .params import TrafficParams

_HISTORY_CAP = 256
_INFINITE_ALLOWANCE = 1 << 30


class TrafficNetworkModel(TimeSteppedModel):
    model_id: ClassVar[str] = "traffic_network"
    display_name: ClassVar[str] = "交通路网"
    description: ClassVar[str] = (
        "有向路网上的车流模拟：道路按元胞划分（每格一辆车），车辆按 "
        "Nagel-Schreckenberg 规则加减速、避让与启停，可在节点上配置红绿灯相位，"
        "发车走最短路径。输出吞吐、平均行程时间与等待，适合观察拥堵的形成与消散。"
    )
    model_type: ClassVar[str] = "time_stepped"
    version: ClassVar[str] = "1.0.0"
    dt: ClassVar[float] = 1.0
    visualizer: ClassVar[dict[str, Any]] = {
        "kind": "traffic",
        "series": ["active_vehicles", "completed", "avg_travel_time"],
    }
    param_model: ClassVar[type] = TrafficParams
    scenarios: ClassVar[list[dict[str, Any]]] = [
        {
            "id": "no-signal",
            "title": "没有红绿灯的十字路口",
            "description": (
                "默认的十字路网（N/E/S/W 汇入中心 C），车流从四个方向持续汇入："
                "路口没有信号时，抢行的车在 C 点互相顶住，看拥堵如何从路口向上游蔓延。"
            ),
            "params": {"spawn_rate": 0.5, "slow_prob": 0.0},
            "seed": 9,
            "stop_condition": {"type": "steps", "value": 400},
        },
        {
            "id": "signal-crossroad",
            "title": "给路口装上红绿灯",
            "description": (
                "同样的车流（同种子），在 C 装信号灯：南北向与东西向每 4 拍轮换放行。"
                "对比上一个场景的完成数与平均等待，看信号如何用「轮流等」换「不堵死」。"
            ),
            "params": {
                "spawn_rate": 0.5,
                "slow_prob": 0.0,
                "signals": [{"node": "C", "cycle": 8, "group_a": ["N", "S"], "group_b": ["E", "W"]}],
            },
            "seed": 9,
            "stop_condition": {"type": "steps", "value": 400},
        },
        {
            "id": "rush-aftermath",
            "title": "高峰过后，堵车多久才散",
            "description": (
                "前 60 拍高密度发车（高峰），之后不再发车：观察路上积压的车辆"
                "如何逐渐排空，体会「停止输入」到「恢复畅通」之间的时间差。"
            ),
            "params": {
                "spawn_rate": 0.7,
                "spawn_until": 60,
                "slow_prob": 0.0,
                "signals": [{"node": "C", "cycle": 8, "group_a": ["N", "S"], "group_b": ["E", "W"]}],
            },
            "seed": 9,
            "stop_condition": {"type": "steps", "value": 400},
        },
    ]

    def __init__(self, params: dict[str, Any] | TrafficParams, rng_seed: int | None):
        super().__init__(params, rng_seed)
        self._build_static()

    def _build_static(self) -> None:
        p = self.params
        self._node_pos = {n.id: (n.x, n.y) for n in p.nodes}
        self._edges: list[dict[str, Any]] = []
        for e in p.edges:
            if e.length is not None:
                length = e.length
            else:
                x0, y0 = self._node_pos[e.src]
                x1, y1 = self._node_pos[e.dst]
                length = ((x0 - x1) ** 2 + (y0 - y1) ** 2) ** 0.5
            self._edges.append({"src": e.src, "dst": e.dst, "ncells": max(1, round(length)), "length": length})
        self._out: dict[str, list[int]] = {n.id: [] for n in p.nodes}
        self._in: dict[str, list[int]] = {n.id: [] for n in p.nodes}
        for i, e in enumerate(self._edges):
            self._out[e["src"]].append(i)
            self._in[e["dst"]].append(i)
        for lst in self._out.values():
            lst.sort()
        for lst in self._in.values():
            lst.sort()
        self._signals = {
            s.node: {"cycle": s.cycle, "offset": s.offset, "a": frozenset(s.group_a), "b": frozenset(s.group_b)}
            for s in p.signals
        }
        self._dist_cache: dict[str, tuple[dict[str, float], dict[str, int]]] = {}

    def _dijkstra(self, src: str) -> tuple[dict[str, float], dict[str, int]]:
        dist = {src: 0.0}
        parent: dict[str, int] = {}
        heap: list[tuple[float, str]] = [(0.0, src)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist.get(u, float("inf")) + 1e-12:
                continue
            for ei in self._out.get(u, []):
                v = self._edges[ei]["dst"]
                nd = d + self._edges[ei]["length"]
                if nd < dist.get(v, float("inf")) - 1e-12:
                    dist[v] = nd
                    parent[v] = ei
                    heapq.heappush(heap, (nd, v))
        return dist, parent

    def _route(self, src: str) -> list[int] | None:
        if src not in self._dist_cache:
            self._dist_cache[src] = self._dijkstra(src)
        dist, parent = self._dist_cache[src]
        dests = sorted(n for n in dist if n != src)
        if not dests:
            return None
        dest = self.rng.choice(dests)
        path: list[int] = []
        cur = dest
        while cur != src:
            ei = parent[cur]
            path.append(ei)
            cur = self._edges[ei]["src"]
        path.reverse()
        return path

    def _green_group(self, node: str, tick: int) -> int:
        sig = self._signals[node]
        half = sig["cycle"] // 2
        return 0 if (tick + sig["offset"]) % sig["cycle"] < half else 1

    def initialize(self, ctx: Any) -> None:
        self._s = self._fresh_state()

    def _fresh_state(self) -> dict[str, Any]:
        return {
            "tick": 0,
            "next_vid": 1,
            "vehicles": [],
            "cells": [[0] * e["ncells"] for e in self._edges],
            "spawned": 0,
            "completed": 0,
            "wait_ticks": 0,
            "speed_sum": 0.0,
            "active_sum": 0.0,
            "travel_sum": 0.0,
            "travel_n": 0,
            "history": [],
        }

    def _spawn(self, tick: int) -> None:
        st = self._s
        p = self.params
        if p.spawn_until is not None and tick > p.spawn_until:
            return
        sources = p.spawn_nodes or sorted(self._node_pos)
        for src in sources:
            if self.rng.random() >= p.spawn_rate:
                continue
            if len(st["vehicles"]) >= p.max_vehicles:
                return
            route = self._route(src)
            if route is None:
                continue
            first = route[0]
            if st["cells"][first][0] != 0:
                continue
            vid = st["next_vid"]
            st["next_vid"] += 1
            st["vehicles"].append({"id": vid, "e": first, "c": 0, "v": 0, "r": route[1:], "t0": tick})
            st["cells"][first][0] = vid
            st["spawned"] += 1

    def _plan(self, veh: dict[str, Any]) -> int:
        st = self._s
        p = self.params
        edge = self._edges[veh["e"]]
        cells = st["cells"][veh["e"]]
        pos = veh["c"]
        d = min(veh["v"] + 1, p.v_max)
        ahead = None
        for i in range(pos + 1, edge["ncells"]):
            if cells[i]:
                ahead = i
                break
        if ahead is not None:
            d = min(d, ahead - pos - 1)
        else:
            to_end = edge["ncells"] - 1 - pos
            if d > to_end:
                allow = self._cross_allowance(veh)
                d = min(d, to_end + allow)
        if p.slow_prob > 0 and self.rng.random() < p.slow_prob:
            d = max(0, d - 1)
        return d

    def _cross_allowance(self, veh: dict[str, Any]) -> int:
        st = self._s
        e = veh["e"]
        dst = self._edges[e]["dst"]
        sig = self._signals.get(dst)
        if sig is not None:
            src = self._edges[e]["src"]
            my_group = 0 if src in sig["a"] else 1
            if my_group != self._green_group(dst, st["tick"]):
                return 0
        route = veh["r"]
        if not route:
            return _INFINITE_ALLOWANCE
        nxt = route[0]
        ncells_next = self._edges[nxt]["ncells"]
        cells_next = st["cells"][nxt]
        free = 0
        while free < ncells_next and cells_next[free] == 0:
            free += 1
        return min(free, ncells_next - 1)

    def step(self) -> None:
        st = self._s
        st["tick"] += 1
        tick = st["tick"]
        self._spawn(tick)
        moves = {veh["id"]: self._plan(veh) for veh in st["vehicles"]}
        self._apply(moves)
        active = len(st["vehicles"])
        st["history"].append(active)
        if len(st["history"]) > _HISTORY_CAP:
            del st["history"][: len(st["history"]) - _HISTORY_CAP]
        st["active_sum"] += active
        st["speed_sum"] += sum(veh["v"] for veh in st["vehicles"])
        self.emit(
            float(tick),
            "traffic",
            f"tick {tick}: active {active}, completed {st['completed']}",
            {"active": active, "completed": st["completed"], "spawned": st["spawned"]},
        )

    def _apply(self, moves: dict[int, int]) -> None:
        st = self._s
        finished: list[dict[str, Any]] = []
        for veh in st["vehicles"]:
            d = moves[veh["id"]]
            edge = self._edges[veh["e"]]
            cells = st["cells"][veh["e"]]
            pos = veh["c"]
            new_pos = pos + d
            if new_pos < edge["ncells"]:
                cells[pos] = 0
                veh["c"] = new_pos
                cells[new_pos] = veh["id"]
            else:
                route = veh["r"]
                nxt = route[0] if route else None
                transferred = False
                if nxt is not None:
                    o = new_pos - edge["ncells"]
                    cells_next = st["cells"][nxt]
                    if 0 <= o < self._edges[nxt]["ncells"] and cells_next[o] == 0:
                        cells[pos] = 0
                        veh["e"] = nxt
                        veh["c"] = o
                        veh["r"] = route[1:]
                        cells_next[o] = veh["id"]
                        transferred = True
                if not transferred:
                    if nxt is None:
                        cells[pos] = 0
                        st["completed"] += 1
                        st["travel_sum"] += st["tick"] - veh["t0"]
                        st["travel_n"] += 1
                        finished.append(veh)
                    else:
                        boundary = edge["ncells"] - 1
                        if cells[boundary] == 0 and boundary != pos:
                            cells[pos] = 0
                            d = boundary - pos
                            veh["c"] = boundary
                            cells[boundary] = veh["id"]
                        else:
                            d = 0
            veh["v"] = d
            if d == 0:
                st["wait_ticks"] += 1
        if finished:
            done_ids = {v["id"] for v in finished}
            st["vehicles"] = [v for v in st["vehicles"] if v["id"] not in done_ids]

    def dump_state(self) -> dict[str, Any]:
        st = self._s
        return {
            "tick": st["tick"],
            "next_vid": st["next_vid"],
            "vehicles": [
                {"id": v["id"], "e": v["e"], "c": v["c"], "v": v["v"], "r": list(v["r"]), "t0": v["t0"]}
                for v in st["vehicles"]
            ],
            "cells": [list(c) for c in st["cells"]],
            "spawned": st["spawned"],
            "completed": st["completed"],
            "wait_ticks": st["wait_ticks"],
            "speed_sum": st["speed_sum"],
            "active_sum": st["active_sum"],
            "travel_sum": st["travel_sum"],
            "travel_n": st["travel_n"],
            "history": list(st["history"]),
        }

    def load_state(self, state: dict[str, Any]) -> None:
        st = dict(state)
        st["vehicles"] = [
            {"id": int(v["id"]), "e": int(v["e"]), "c": int(v["c"]), "v": int(v["v"]), "r": [int(x) for x in v["r"]], "t0": int(v["t0"])}
            for v in state["vehicles"]
        ]
        st["cells"] = [list(c) for c in state["cells"]]
        st["history"] = list(state["history"])
        self._s = st
        self._build_static()

    def snapshot(self) -> dict[str, Any]:
        st = self._s
        return {
            "tick": st["tick"],
            "nodes": [{"id": n.id, "x": n.x, "y": n.y} for n in self.params.nodes],
            "edges": [{"src": e["src"], "dst": e["dst"], "cells": e["ncells"]} for e in self._edges],
            "signals": [
                {"node": node, "cycle": sig["cycle"], "green_group": self._green_group(node, st["tick"])}
                for node, sig in self._signals.items()
            ],
            "vehicles": [[v["e"], v["c"], v["v"]] for v in st["vehicles"]],
            "edge_load": [sum(1 for c in cells if c) for cells in st["cells"]],
            "active": len(st["vehicles"]),
            "spawned": st["spawned"],
            "completed": st["completed"],
            "avg_travel_time": st["travel_sum"] / st["travel_n"] if st["travel_n"] else 0.0,
            "history": st["history"][-128:],
        }

    def finalize_metrics(self) -> dict[str, float]:
        st = self._s
        return {
            "ticks": float(st["tick"]),
            "spawned": float(st["spawned"]),
            "completed": float(st["completed"]),
            "active_vehicles": float(len(st["vehicles"])),
            "avg_travel_time": st["travel_sum"] / st["travel_n"] if st["travel_n"] else 0.0,
            "avg_wait_ticks": st["wait_ticks"] / st["spawned"] if st["spawned"] else 0.0,
            "mean_speed": st["speed_sum"] / st["active_sum"] if st["active_sum"] else 0.0,
        }
