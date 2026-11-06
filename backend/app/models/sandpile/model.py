"""BTW sandpile: self-organized criticality on an open grid.

One step = drop one grain on a random cell, then topple every cell whose
height reaches the threshold (each toppling removes `threshold` grains and
gives one grain to each of the four neighbours inside the grid). Grains that
would fall past the edge are **lost** — that dissipation is what makes the
pile stabilize. A periodic (toroidal) boundary has no sink: at criticality a
single grain can cascade forever (observed while building this model), so
the boundary here is deliberately open. The number of topplings in one step
is that step's avalanche size.
"""
from __future__ import annotations

from typing import Any, ClassVar

from ...core.engine.models_base import TimeSteppedModel
from .params import SandpileParams

_HISTORY_CAP = 128
_NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class SandpileModel(TimeSteppedModel):
    model_id: ClassVar[str] = "sandpile"
    display_name: ClassVar[str] = "沙堆（自组织临界）"
    description: ClassVar[str] = (
        "BTW 沙堆模型：每次随机往一格加一粒沙，达到阈值就向四邻崩塌（边界外的沙子流失，"
        "正是这份耗散让沙堆稳定）。连锁反应形成大小不一的雪崩，规模没有固定尺度——"
        "这是自组织临界的标志。"
    )
    model_type: ClassVar[str] = "time_stepped"
    version: ClassVar[str] = "1.0.0"
    dt: ClassVar[float] = 1.0
    visualizer: ClassVar[dict[str, Any]] = {
        "kind": "sandpile",
        "series": ["topplings", "max_avalanche"],
    }
    param_model: ClassVar[type] = SandpileParams
    scenarios: ClassVar[list[dict[str, Any]]] = [
        {
            "id": "sandpile-critical",
            "title": "沙堆：加一粒沙也能引发雪崩",
            "description": (
                "从空沙堆开始逐粒落沙，堆到临界态后每次崩塌的规模都不可预测："
                "多数是一两格的小塌方，偶尔却会连锁整片沙堆——这就是自组织临界。"
            ),
            "params": {"width": 40, "height": 30, "threshold": 4},
            "seed": 1,
            "stop_condition": {"type": "steps", "value": 3000},
        },
        {
            "id": "sandpile-large",
            "title": "更大的沙堆：连锁范围更吓人",
            "description": (
                "把网格放大到 60×40：临界态来得更晚，但一旦进入临界，"
                "单次雪崩波及的格子数会明显变大——规模分布仍然没有特征尺度。"
            ),
            "params": {"width": 60, "height": 40, "threshold": 4},
            "seed": 2,
            "stop_condition": {"type": "steps", "value": 6000},
        },
    ]

    def initialize(self, ctx: Any = None) -> None:
        p = self.params
        self._s = {
            "grid": [[p.initial_grains] * p.width for _ in range(p.height)],
            "drops": 0,
            "topplings_total": 0,
            "lost_total": 0,
            "avalanches": 0,
            "max_avalanche": 0,
            "history": [],
        }

    def step(self) -> None:
        st = self._s
        p = self.params
        grid: list[list[int]] = st["grid"]
        h, w = len(grid), len(grid[0])
        i = self.rng.randrange(h)
        j = self.rng.randrange(w)
        grid[i][j] += 1
        st["drops"] += 1
        topplings, lost = self._topple(grid, i, j, p.threshold)
        st["topplings_total"] += topplings
        st["lost_total"] += lost
        if topplings:
            st["avalanches"] += 1
            if topplings > st["max_avalanche"]:
                st["max_avalanche"] = topplings
            st["history"].append(topplings)
            if len(st["history"]) > _HISTORY_CAP:
                # 只丢掉最老的几条；写成 del history[:CAP] 会在超限瞬间清空整段历史
                del st["history"][:-_HISTORY_CAP]

    @staticmethod
    def _topple(grid: list[list[int]], i: int, j: int, threshold: int) -> tuple[int, int]:
        """Cascade toppling from (i, j); returns (topplings, grains lost at the edge).

        Open boundary on purpose: with periodic wrapping there is no sink and a
        critical pile can cascade forever (a single grain never stabilises)."""
        h, w = len(grid), len(grid[0])
        stack = [(i, j)]
        topplings = lost = 0
        while stack:
            ci, cj = stack.pop()
            if grid[ci][cj] < threshold:
                continue
            grid[ci][cj] -= threshold
            topplings += 1
            for di, dj in _NEIGHBOURS:
                ni, nj = ci + di, cj + dj
                if 0 <= ni < h and 0 <= nj < w:
                    grid[ni][nj] += 1
                    stack.append((ni, nj))
                else:
                    lost += 1
        return topplings, lost

    def dump_state(self) -> dict[str, Any]:
        st = self._s
        return {
            "grid": [list(row) for row in st["grid"]],
            "drops": st["drops"],
            "topplings_total": st["topplings_total"],
            "lost_total": st["lost_total"],
            "avalanches": st["avalanches"],
            "max_avalanche": st["max_avalanche"],
            "history": list(st["history"]),
        }

    def load_state(self, state: dict[str, Any]) -> None:
        self._s = {
            "grid": [list(row) for row in state["grid"]],
            "drops": int(state["drops"]),
            "topplings_total": int(state["topplings_total"]),
            "lost_total": int(state.get("lost_total", 0)),
            "avalanches": int(state["avalanches"]),
            "max_avalanche": int(state["max_avalanche"]),
            "history": [int(v) for v in state.get("history", [])],
        }

    def snapshot(self) -> dict[str, Any]:
        st = self._s
        grid = st["grid"]
        h = len(grid)
        w = len(grid[0]) if h else 0
        return {
            "width": w,
            "height": h,
            "threshold": self.params.threshold,
            "heights": [list(row) for row in grid],
            "drops": st["drops"],
            "avalanches": st["avalanches"],
            "topplings": st["topplings_total"],
            "lost": st["lost_total"],
            "max_avalanche": st["max_avalanche"],
            "history": list(st["history"][-_HISTORY_CAP:]),
        }

    def finalize_metrics(self) -> dict[str, float]:
        st = self._s
        avalanches = st["avalanches"]
        return {
            "drops": float(st["drops"]),
            "avalanches": float(avalanches),
            "topplings": float(st["topplings_total"]),
            "lost": float(st["lost_total"]),
            "max_avalanche": float(st["max_avalanche"]),
            "mean_avalanche": (st["topplings_total"] / avalanches) if avalanches else 0.0,
        }
