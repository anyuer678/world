"""Lotka-Volterra predator-prey model, deterministic RK4 integration.

One step = one time unit, integrated in fixed RK4 substeps. The classic
unbounded variant conserves the first integral H = delta*x - gamma*ln x
+ beta*y - alpha*ln y, so neutral cycles never decay; adding a logistic
carrying capacity for the prey turns the orbit into a damped spiral that
converges to the interior equilibrium (x* = gamma/(delta*beta), which is
independent of K — a nice analytic ground truth to assert against).
"""
from __future__ import annotations

import math
from typing import Any, ClassVar

from ...core.engine.models_base import TimeSteppedModel
from .params import PredatorPreyParams

_SUBSTEPS = 8
_H = 1.0 / _SUBSTEPS


class PredatorPreyModel(TimeSteppedModel):
    model_id: ClassVar[str] = "predator_prey"
    display_name: ClassVar[str] = "捕食者-猎物模型"
    description: ClassVar[str] = (
        "洛特卡-沃尔泰拉经典生态模型：猎物按 α 增长、被捕食者按 β 削减，"
        "捕食者靠吃到的猎物按 δ 繁殖、按 γ 衰减。两个种群此消彼长，"
        "相位互相领先四分之一周期——猎物先丰、捕食者后旺、猎物遭劫、捕食者断粮。"
        "经典版存在守恒量，循环永不衰减；给猎物加上环境容纳量 K，轨道会收敛到内平衡点。"
    )
    model_type: ClassVar[str] = "time_stepped"
    version: ClassVar[str] = "1.0.0"
    dt: ClassVar[float] = 1.0
    visualizer: ClassVar[dict[str, Any]] = {
        "kind": "predator_prey",
        "series": ["prey", "predator"],
    }
    param_model: ClassVar[type] = PredatorPreyParams
    scenarios: ClassVar[list[dict[str, Any]]] = [
        {
            "id": "neutral-cycles",
            "title": "经典循环：永不衰减的兴衰",
            "description": (
                "无环境限制的经典参数（α=1、β=0.4、δ=0.3、γ=0.6，x₀=2、y₀=1）："
                "围绕平衡点 (5, 2.5) 的中性循环，守恒量锁死轨道——"
                "生态系统自己就能产生周期性，不需要任何外部的季节 forcing。"
            ),
            "params": {
                "prey_growth": 1.0, "predation": 0.4, "conversion": 0.3,
                "predator_death": 0.6, "initial_prey": 2.0, "initial_predator": 1.0,
            },
            "seed": 3,
            "stop_condition": {"type": "steps", "value": 60},
        },
        {
            "id": "capacity-damped",
            "title": "资源有限：循环被压成收敛",
            "description": (
                "同样的物种，给猎物加上容纳量 K=8：食物受限后轨道变成阻尼螺旋，"
                "最终收敛到内平衡点——猎物平衡值 x*=γ/(δβ)=5 竟然与 K 无关，"
                "这是 Lotka-Volterra 的著名反直觉结论。"
            ),
            "params": {
                "prey_growth": 1.0, "predation": 0.4, "conversion": 0.3,
                "predator_death": 0.6, "initial_prey": 2.0, "initial_predator": 1.0,
                "prey_capacity": 8.0,
            },
            "seed": 3,
            "stop_condition": {"type": "steps", "value": 240},
        },
        {
            "id": "predator-boom-bust",
            "title": "捕食者过载：大起大落险致灭绝",
            "description": (
                "初始捕食者过多（y₀=6）：猎物被压到几乎灭绝，捕食者随之崩盘，"
                "轨道振幅巨大——现实中的猞猁-雪兔周期一旦振幅撞上 0，"
                "连续模型就救不回来了（离散世界里的灭绝）。"
            ),
            "params": {
                "prey_growth": 1.0, "predation": 0.4, "conversion": 0.3,
                "predator_death": 0.6, "initial_prey": 2.0, "initial_predator": 6.0,
            },
            "seed": 3,
            "stop_condition": {"type": "steps", "value": 80},
        },
    ]

    def _rates(self, x: float, y: float) -> tuple[float, float]:
        p = self.params
        growth = p.prey_growth * (1.0 - x / p.prey_capacity) if p.prey_capacity else p.prey_growth
        dx = growth * x - p.predation * x * y
        dy = p.conversion * p.predation * x * y - p.predator_death * y
        return dx, dy

    def initialize(self, ctx: Any) -> None:
        p = self.params
        x0, y0 = float(p.initial_prey), float(p.initial_predator)
        self._s = {
            "x": x0,
            "y": y0,
            "t": 0.0,
            "tick": 0,
            "prey_min": x0, "prey_max": x0,
            "pred_min": y0, "pred_max": y0,
            "prev_x": x0, "prev_rising": False,
            "prey_peaks": 0, "last_peak_t": None, "period_last": None,
            "area_x": 0.0, "area_y": 0.0,
            "history": [[0.0, x0, y0]],
            "hist_stride": 1,
            "hist_n": 0,
        }

    def step(self) -> None:
        st = self._s
        x, y = st["x"], st["y"]
        for _ in range(_SUBSTEPS):
            k1x, k1y = self._rates(x, y)
            k2x, k2y = self._rates(x + 0.5 * _H * k1x, y + 0.5 * _H * k1y)
            k3x, k3y = self._rates(x + 0.5 * _H * k2x, y + 0.5 * _H * k2y)
            k4x, k4y = self._rates(x + _H * k3x, y + _H * k3y)
            x += _H / 6.0 * (k1x + 2 * k2x + 2 * k3x + k4x)
            y += _H / 6.0 * (k1y + 2 * k2y + 2 * k3y + k4y)
        x = max(x, 0.0)
        y = max(y, 0.0)
        t_new = st["t"] + self.dt
        st["area_x"] += 0.5 * (st["x"] + x) * self.dt
        st["area_y"] += 0.5 * (st["y"] + y) * self.dt
        prey_rising = x > st["prev_x"]
        if st["prev_rising"] and not prey_rising:
            st["prey_peaks"] += 1
            if st["last_peak_t"] is not None:
                st["period_last"] = t_new - st["last_peak_t"]
            st["last_peak_t"] = t_new
        st["prev_x"], st["prev_rising"] = x, prey_rising
        st["x"], st["y"], st["t"] = x, y, t_new
        st["tick"] += 1
        st["prey_min"] = min(st["prey_min"], x)
        st["prey_max"] = max(st["prey_max"], x)
        st["pred_min"] = min(st["pred_min"], y)
        st["pred_max"] = max(st["pred_max"], y)
        self._sample()
        self.emit(
            float(st["tick"]),
            "populations",
            f"t={st['t']:.0f}: 猎物 {x:.2f} · 捕食者 {y:.2f}",
            {"prey": round(x, 3), "predator": round(y, 3)},
        )

    def _sample(self) -> None:
        st = self._s
        st["hist_n"] += 1
        if st["hist_n"] % st["hist_stride"]:
            return
        st["history"].append([st["t"], st["x"], st["y"]])
        if len(st["history"]) > 256:
            st["history"] = st["history"][::2]
            st["hist_stride"] *= 2

    def first_integral(self) -> float:
        """Conserved quantity of the classic (unbounded) Lotka-Volterra system."""
        st, p = self._s, self.params
        x, y = max(st["x"], 1e-300), max(st["y"], 1e-300)
        return (
            p.conversion * p.predation * x
            - p.predator_death * math.log(x)
            + p.predation * y
            - p.prey_growth * math.log(y)
        )

    def dump_state(self) -> dict[str, Any]:
        st = self._s
        return {
            "x": st["x"], "y": st["y"], "t": st["t"], "tick": st["tick"],
            "prey_min": st["prey_min"], "prey_max": st["prey_max"],
            "pred_min": st["pred_min"], "pred_max": st["pred_max"],
            "prev_x": st["prev_x"], "prev_rising": st["prev_rising"],
            "prey_peaks": st["prey_peaks"], "last_peak_t": st["last_peak_t"],
            "period_last": st["period_last"],
            "area_x": st["area_x"], "area_y": st["area_y"],
            "history": st["history"], "hist_stride": st["hist_stride"], "hist_n": st["hist_n"],
        }

    def load_state(self, state: dict[str, Any]) -> None:
        st = state
        self._s = {
            "x": st["x"], "y": st["y"], "t": st["t"], "tick": st["tick"],
            "prey_min": st["prey_min"], "prey_max": st["prey_max"],
            "pred_min": st["pred_min"], "pred_max": st["pred_max"],
            "prev_x": st["prev_x"], "prev_rising": st["prev_rising"],
            "prey_peaks": st["prey_peaks"], "last_peak_t": st["last_peak_t"],
            "period_last": st["period_last"],
            "area_x": st["area_x"], "area_y": st["area_y"],
            "history": list(st["history"]), "hist_stride": st["hist_stride"], "hist_n": st["hist_n"],
        }

    def snapshot(self) -> dict[str, Any]:
        st, p = self._s, self.params
        eq_x = p.predator_death / (p.conversion * p.predation)
        eq_y = (
            p.prey_growth / p.predation * (1.0 - eq_x / p.prey_capacity)
            if p.prey_capacity and eq_x < p.prey_capacity
            else p.prey_growth / p.predation
        )
        return {
            "tick": st["tick"],
            "day": st["t"],
            "prey": st["x"],
            "predator": st["y"],
            "prey_capacity": p.prey_capacity,
            "prey_peaks": st["prey_peaks"],
            "period_last": st["period_last"],
            "equilibrium_prey": eq_x,
            "equilibrium_predator": eq_y,
            "first_integral": self.first_integral(),
            "history": st["history"],
        }

    def finalize_metrics(self) -> dict[str, float]:
        st, p = self._s, self.params
        t_end = max(st["t"], 1e-12)
        eq_x = p.predator_death / (p.conversion * p.predation)
        eq_y = (
            p.prey_growth / p.predation * (1.0 - eq_x / p.prey_capacity)
            if p.prey_capacity and eq_x < p.prey_capacity
            else p.prey_growth / p.predation
        )
        dist = math.hypot((st["x"] - eq_x) / eq_x, (st["y"] - eq_y) / max(eq_y, 1e-12))
        return {
            "tick": float(st["tick"]),
            "prey_end": st["x"],
            "predator_end": st["y"],
            "prey_min": st["prey_min"],
            "prey_max": st["prey_max"],
            "predator_min": st["pred_min"],
            "predator_max": st["pred_max"],
            "mean_prey": st["area_x"] / t_end,
            "mean_predator": st["area_y"] / t_end,
            "prey_peaks": float(st["prey_peaks"]),
            "cycle_period": st["period_last"] if st["period_last"] else 0.0,
            "equilibrium_prey": eq_x,
            "equilibrium_predator": eq_y,
            "distance_to_equilibrium": dist,
        }
