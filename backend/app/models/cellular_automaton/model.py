"""2D cellular automaton as a time-stepped model.

One step = one generation. Rule given as a B/S rule string (e.g. B3/S23 =
Conway Life): a dead cell with n live neighbors is born if n in B, a live
cell survives if n in S. Boundary: toroidal or dead-outside.
"""
from __future__ import annotations

from typing import Any, ClassVar

from ...core.engine.models_base import TimeSteppedModel
from .params import CellularAutomatonParams

_HISTORY_CAP = 256


def _parse_rule(rule_string: str) -> tuple[frozenset[int], frozenset[int]]:
    birth_part, survive_part = rule_string[1:].split("/S")
    birth = frozenset(int(c) for c in birth_part)
    survive = frozenset(int(c) for c in survive_part)
    return birth, survive


def _blinker_grid() -> list[list[int]]:
    w, h = 16, 12
    grid = [[0] * w for _ in range(h)]
    y = h // 2
    for x in (w // 2 - 1, w // 2, w // 2 + 1):
        grid[y][x] = 1
    return grid


class CellularAutomatonModel(TimeSteppedModel):
    model_id: ClassVar[str] = "cellular_automaton"
    display_name: ClassVar[str] = "元胞自动机"
    description: ClassVar[str] = (
        "二维网格上的生命游戏类演化（B/S 规则串，如 B3/S23 即 Conway 生命游戏），"
        "可选环形边界或固定死边界，随机或手工指定初始状态；每代记录存活细胞数，"
        "观察图案如何生长、振荡或消亡。"
    )
    model_type: ClassVar[str] = "time_stepped"
    version: ClassVar[str] = "1.0.0"
    dt: ClassVar[float] = 1.0
    visualizer: ClassVar[dict[str, Any]] = {
        "kind": "ca",
        "series": ["population", "births", "deaths"],
    }
    param_model: ClassVar[type] = CellularAutomatonParams
    scenarios: ClassVar[list[dict[str, Any]]] = [
        {
            "id": "game-of-life",
            "title": "生命游戏：从噪声中长出结构",
            "description": (
                "最经典的规则 B3/S23，随机撒下 30% 的活细胞："
                "前几十代会剧烈变化，随后浮现稳定块与来回振荡的小图案。"
            ),
            "params": {"width": 48, "height": 32, "rule_string": "B3/S23", "initial_density": 0.3},
            "seed": 1,
            "stop_condition": {"type": "steps", "value": 300},
        },
        {
            "id": "overcrowded",
            "title": "太拥挤反而走向消亡",
            "description": (
                "同样的规则，初始密度提到 85%：到处都是邻居，"
                "过度拥挤规则（S23 之外都死）让种群急剧坍缩——先看它繁荣，再看它崩溃。"
            ),
            "params": {"width": 48, "height": 32, "rule_string": "B3/S23", "initial_density": 0.85},
            "seed": 1,
            "stop_condition": {"type": "steps", "value": 300},
        },
        {
            "id": "blinker",
            "title": "会眨眼的振荡器",
            "description": (
                "手工放 3 个横排活细胞（blinker）：它每两代在横竖之间翻转一次，"
                "永不停止——简单规则也能产生精确的周期行为。"
            ),
            "params": {"width": 16, "height": 12, "rule_string": "B3/S23", "initial_grid": _blinker_grid()},
            "seed": 1,
            "stop_condition": {"type": "steps", "value": 60},
        },
    ]

    def initialize(self, ctx: Any) -> None:
        p = self.params
        self._birth, self._survive = _parse_rule(p.rule_string)
        if p.initial_grid is not None:
            grid = [list(row) for row in p.initial_grid]
        else:
            grid = [
                [1 if self.rng.random() < p.initial_density else 0 for _ in range(p.width)]
                for _ in range(p.height)
            ]
        population = sum(sum(row) for row in grid)
        self._s = {
            "grid": grid,
            "generation": 0,
            "births_total": 0,
            "deaths_total": 0,
            "population": population,
            "history": [population],
        }

    def _row_sums(self, row: list[int]) -> list[int]:
        """Sum of each cell plus its horizontal neighbors."""
        w = len(row)
        if self.params.toroidal:
            pr = [row[-1], *row, row[0]]
        else:
            pr = [0, *row, 0]
        return [pr[j] + pr[j + 1] + pr[j + 2] for j in range(w)]

    def step(self) -> None:
        st = self._s
        p = self.params
        grid = st["grid"]
        h, w = len(grid), len(grid[0])
        hs = [self._row_sums(row) for row in grid]
        zeros = [0] * w
        new_grid: list[list[int]] = []
        births = deaths = 0
        for i in range(h):
            if p.toroidal:
                up = hs[(i - 1) % h]
                down = hs[(i + 1) % h]
            else:
                up = hs[i - 1] if i > 0 else zeros
                down = hs[i + 1] if i < h - 1 else zeros
            cur = grid[i]
            mid = hs[i]
            new_row = []
            for j in range(w):
                n = up[j] + mid[j] - cur[j] + down[j]
                if cur[j]:
                    alive = n in self._survive
                else:
                    alive = n in self._birth
                if alive != bool(cur[j]):
                    if alive:
                        births += 1
                    else:
                        deaths += 1
                new_row.append(1 if alive else 0)
            new_grid.append(new_row)
        st["grid"] = new_grid
        st["generation"] += 1
        st["births_total"] += births
        st["deaths_total"] += deaths
        population = sum(sum(row) for row in new_grid)
        st["population"] = population
        history = st["history"]
        history.append(population)
        if len(history) > _HISTORY_CAP:
            del history[: len(history) - _HISTORY_CAP]
        self.emit(float(st["generation"]), "generation",
                  f"gen {st['generation']}: population {population}",
                  {"population": population, "births": births, "deaths": deaths})

    def dump_state(self) -> dict[str, Any]:
        st = self._s
        return {
            "grid": [list(row) for row in st["grid"]],
            "generation": st["generation"],
            "births_total": st["births_total"],
            "deaths_total": st["deaths_total"],
            "population": st["population"],
            "history": list(st["history"]),
        }

    def load_state(self, state: dict[str, Any]) -> None:
        st = dict(state)
        st["grid"] = [list(row) for row in state["grid"]]
        st["history"] = list(state["history"])
        self._s = st
        self._birth, self._survive = _parse_rule(self.params.rule_string)

    def snapshot(self) -> dict[str, Any]:
        st = self._s
        h = len(st["grid"])
        w = len(st["grid"][0]) if h else 0
        return {
            "width": w,
            "height": h,
            "rule": self.params.rule_string,
            "toroidal": self.params.toroidal,
            "generation": st["generation"],
            "population": st["population"],
            "births_total": st["births_total"],
            "deaths_total": st["deaths_total"],
            "history": list(st["history"][-128:]),
            # rows as compact bitstrings for transfer; canvas renders from this
            "rows": ["".join("1" if c else "0" for c in row) for row in st["grid"]],
        }

    def finalize_metrics(self) -> dict[str, float]:
        st = self._s
        h, w = len(st["grid"]), len(st["grid"][0])
        return {
            "generation": float(st["generation"]),
            "population": float(st["population"]),
            "density": st["population"] / (h * w) if h * w else 0.0,
            "births_total": float(st["births_total"]),
            "deaths_total": float(st["deaths_total"]),
            "population_min": float(min(st["history"])),
            "population_max": float(max(st["history"])),
        }
