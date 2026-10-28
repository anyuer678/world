"""Schelling segregation as a synchronous-step agent model.

Agents (group 1 or 2) sit on a grid; an agent is happy when the fraction of
same-group agents among its occupied 8-neighbors reaches `tolerance`. One
step: all happiness is evaluated against the frozen t-grid, then every
unhappy agent (scan order) moves to a snapshot-empty cell (each empty used
at most once, no chaining) — the classic sync-step agent contract.
"""
from __future__ import annotations

from typing import Any, ClassVar

from ...core.engine.models_base import TimeSteppedModel
from .params import SchellingParams


def _neighbor_offsets() -> list[tuple[int, int]]:
    return [
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1), (0, 1),
        (1, -1), (1, 0), (1, 1),
    ]


_OFFSETS = _neighbor_offsets()


class SchellingModel(TimeSteppedModel):
    model_id: ClassVar[str] = "schelling"
    display_name: ClassVar[str] = "谢林隔离模型"
    description: ClassVar[str] = (
        "网格上的两类智能体（同步步移动）：每个智能体只要求相似邻居占比达到容忍阈值"
        "就满意，不满意的智能体每步搬去一个空格。谢林的著名结论：哪怕只要求"
        "「8 个邻居里有两三个跟自己同组」，整座城市也会自我隔离成清晰分区——"
        "个体温和的偏好聚合出集体极端的格局。"
    )
    model_type: ClassVar[str] = "time_stepped"
    version: ClassVar[str] = "1.0.0"
    dt: ClassVar[float] = 1.0
    visualizer: ClassVar[dict[str, Any]] = {
        "kind": "schelling",
        "series": ["unhappy_rate", "segregation_index"],
    }
    param_model: ClassVar[type] = SchellingParams
    scenarios: ClassVar[list[dict[str, Any]]] = [
        {
            "id": "no-preference",
            "title": "毫无偏好：不会自己隔离",
            "description": (
                "容忍阈值设为 0——每个智能体对邻居没有任何要求。"
                "结果一步也不挪、保持混居：隔离不会凭空出现，它需要偏好作为燃料。"
            ),
            "params": {"width": 40, "height": 30, "tolerance": 0.0},
            "seed": 4,
            "stop_condition": {"type": "steps", "value": 40},
        },
        {
            "id": "mild-preference",
            "title": "轻微偏好也足以隔离",
            "description": (
                "同样的初始布局（同种子），容忍阈值只要求约三成邻居同组："
                "如此温和的偏好，最终却涌现出大片同组聚集——谢林模型最著名的结论。"
            ),
            "params": {"width": 40, "height": 30, "tolerance": 0.3},
            "seed": 4,
            "stop_condition": {"type": "steps", "value": 60},
        },
        {
            "id": "demanding",
            "title": "苛刻偏好：更隔离也更动荡",
            "description": (
                "把要求提到七成邻居同组：分区确实更彻底，但永远有人不满足，"
                "城市变成持续的搬移动荡——更苛刻的偏好并不带来更安定的格局。"
            ),
            "params": {"width": 40, "height": 30, "tolerance": 0.7},
            "seed": 4,
            "stop_condition": {"type": "steps", "value": 120},
        },
    ]

    def initialize(self, ctx: Any) -> None:
        p = self.params
        if p.initial_grid is not None:
            grid = [row[:] for row in p.initial_grid]
        else:
            grid = [
                [
                    0
                    if self.rng.random() >= p.occupancy
                    else (1 if self.rng.random() < p.ratio_a else 2)
                    for _ in range(p.width)
                ]
                for _ in range(p.height)
            ]
        unhappy, seg = self._evaluate(grid)
        occ = self._occupied(grid)
        self._s = {
            "grid": grid,
            "tick": 0,
            "moves_total": 0,
            "unhappy_last": len(unhappy),
            "seg_last": seg,
            "history": [[0, len(unhappy) / occ if occ else 0.0, seg]],
            "hist_stride": 1,
            "hist_n": 0,
        }

    # --- geometry / evaluation -------------------------------------------
    def _neighbor_cells(self, i: int, j: int, h: int, w: int) -> list[tuple[int, int]]:
        out = []
        for di, dj in _OFFSETS:
            ni, nj = i + di, j + dj
            if self.params.toroidal:
                out.append((ni % h, nj % w))
            elif 0 <= ni < h and 0 <= nj < w:
                out.append((ni, nj))
        return out

    def _is_happy(self, grid: list[list[int]], i: int, j: int) -> bool:
        g = grid[i][j]
        same = occ = 0
        for ni, nj in self._neighbor_cells(i, j, len(grid), len(grid[0])):
            v = grid[ni][nj]
            if v:
                occ += 1
                same += v == g
        return occ == 0 or same / occ >= self.params.tolerance

    def _evaluate(self, grid: list[list[int]]) -> tuple[list[tuple[int, int]], float]:
        """Unhappy cells (scan order) and the mean same-fraction over cells
        that have at least one occupied neighbor (segregation index)."""
        unhappy: list[tuple[int, int]] = []
        seg_sum = 0.0
        seg_cells = 0
        h, w = len(grid), len(grid[0])
        tol = self.params.tolerance
        for i in range(h):
            for j in range(w):
                g = grid[i][j]
                if not g:
                    continue
                same = occ = 0
                for ni, nj in self._neighbor_cells(i, j, h, w):
                    v = grid[ni][nj]
                    if v:
                        occ += 1
                        same += v == g
                if occ == 0:
                    continue
                frac = same / occ
                seg_sum += frac
                seg_cells += 1
                if frac < tol:
                    unhappy.append((i, j))
        return unhappy, (seg_sum / seg_cells if seg_cells else 0.0)

    @staticmethod
    def _occupied(grid: list[list[int]]) -> int:
        return sum(1 for row in grid for c in row if c)

    # --- step --------------------------------------------------------------
    def step(self) -> None:
        st = self._s
        grid = st["grid"]
        h, w = len(grid), len(grid[0])
        unhappy, _ = self._evaluate(grid)
        empties = [(i, j) for i in range(h) for j in range(w) if grid[i][j] == 0]
        new_grid = [row[:] for row in grid]
        moves = 0
        for i, j in unhappy:
            if not empties:
                break
            k = self.rng.randrange(len(empties))
            ti, tj = empties[k]
            empties[k] = empties[-1]
            empties.pop()
            new_grid[ti][tj] = grid[i][j]
            new_grid[i][j] = 0
            moves += 1
        unhappy_after, seg = self._evaluate(new_grid)
        st["grid"] = new_grid
        st["tick"] += 1
        st["moves_total"] += moves
        st["unhappy_last"] = len(unhappy_after)
        st["seg_last"] = seg
        self._sample()
        self.emit(
            float(st["tick"]),
            "relocate",
            f"tick {st['tick']}: {moves} moves, {len(unhappy_after)} unhappy",
            {"moves": moves, "unhappy": len(unhappy_after)},
        )

    def _sample(self) -> None:
        st = self._s
        st["hist_n"] += 1
        if st["hist_n"] % st["hist_stride"]:
            return
        occ = self._occupied(st["grid"])
        rate = st["unhappy_last"] / occ if occ else 0.0
        st["history"].append([st["tick"], rate, st["seg_last"]])
        if len(st["history"]) > 256:
            st["history"] = st["history"][::2]
            st["hist_stride"] *= 2

    # --- state / snapshot / metrics ----------------------------------------
    def dump_state(self) -> dict[str, Any]:
        st = self._s
        return {
            "grid": [row[:] for row in st["grid"]],
            "tick": st["tick"],
            "moves_total": st["moves_total"],
            "unhappy_last": st["unhappy_last"],
            "seg_last": st["seg_last"],
            "history": st["history"],
            "hist_stride": st["hist_stride"],
            "hist_n": st["hist_n"],
        }

    def load_state(self, state: dict[str, Any]) -> None:
        self._s = {
            "grid": [row[:] for row in state["grid"]],
            "tick": state["tick"],
            "moves_total": state["moves_total"],
            "unhappy_last": state["unhappy_last"],
            "seg_last": state["seg_last"],
            "history": list(state["history"]),
            "hist_stride": state["hist_stride"],
            "hist_n": state["hist_n"],
        }

    def snapshot(self) -> dict[str, Any]:
        st = self._s
        grid = st["grid"]
        h, w = len(grid), len(grid[0])
        unhappy_now, seg_now = self._evaluate(grid)
        unhappy_set = set(unhappy_now)
        pop_a = sum(1 for row in grid for c in row if c == 1)
        pop_b = sum(1 for row in grid for c in row if c == 2)
        return {
            "width": w,
            "height": h,
            "tolerance": self.params.tolerance,
            "toroidal": self.params.toroidal,
            "tick": st["tick"],
            "population_a": pop_a,
            "population_b": pop_b,
            "unhappy": len(unhappy_now),
            "unhappy_rate": (len(unhappy_now) / (pop_a + pop_b)) if (pop_a + pop_b) else 0.0,
            "segregation_index": seg_now,
            "moves_total": st["moves_total"],
            "rows": ["".join(str(c) for c in row) for row in grid],
            "unhappy_rows": [
                "".join("1" if (i, j) in unhappy_set else "0" for j in range(w))
                for i in range(h)
            ],
            "history": st["history"],
        }

    def finalize_metrics(self) -> dict[str, float]:
        st = self._s
        grid = st["grid"]
        pop = self._occupied(grid)
        rates = [r[1] for r in st["history"]]
        segs = [r[2] for r in st["history"]]
        return {
            "tick": float(st["tick"]),
            "population": float(pop),
            "unhappy_rate": st["unhappy_last"] / pop if pop else 0.0,
            "unhappy_rate_min": min(rates) if rates else 0.0,
            "unhappy_rate_max": max(rates) if rates else 0.0,
            "segregation_index": st["seg_last"],
            "segregation_index_max": max(segs) if segs else 0.0,
            "moves_total": float(st["moves_total"]),
            "moves_per_tick": (st["moves_total"] / st["tick"]) if st["tick"] else 0.0,
        }
