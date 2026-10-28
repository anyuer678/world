"""Compartmental SIR epidemic model, deterministic Euler integration.

One step = one time unit, integrated in fixed substeps for stability.
S+I+R is conserved; the classic epidemic threshold beta/gamma = 1 decides
whether an outbreak happens — which makes sweeps over beta the textbook
phase-transition demo for the batch findings / sweep-chart pipeline.
"""
from __future__ import annotations

from typing import Any, ClassVar

from ...core.engine.models_base import TimeSteppedModel
from .params import SirParams

_SUBSTEPS = 50
_H = 1.0 / _SUBSTEPS


class SirModel(TimeSteppedModel):
    model_id: ClassVar[str] = "sir"
    display_name: ClassVar[str] = "SIR 传染病模型"
    description: ClassVar[str] = (
        "仓室流行病模型：人口分为易感 S、感染 I、康复 R 三个仓室，"
        "按传播率 β 与康复率 γ 连续演化。疫情能否扩张由阈值 β/γ>1 决定——"
        "这是教科书级的相变：把 β 当扫描参数批量跑，总感染数会在阈值附近断崖。"
        "R₀=β/γ，1/γ 是平均感染时长。"
    )
    model_type: ClassVar[str] = "time_stepped"
    version: ClassVar[str] = "1.0.0"
    dt: ClassVar[float] = 1.0
    visualizer: ClassVar[dict[str, Any]] = {
        "kind": "sir",
        "series": ["susceptible", "infected", "recovered"],
    }
    param_model: ClassVar[type] = SirParams
    scenarios: ClassVar[list[dict[str, Any]]] = [
        {
            "id": "outbreak",
            "title": "疫情爆发：R₀=5",
            "description": (
                "β=0.5、γ=0.1，R₀=5：高传染性病原闯入万人社区，"
                "感染曲线先指数爬升、达峰后回落——绝大多数人会在峰值前后被感染。"
            ),
            "params": {"population": 10000, "initial_infected": 10, "beta": 0.5, "gamma": 0.1},
            "seed": 7,
            "stop_condition": {"type": "steps", "value": 120},
        },
        {
            "id": "flatten-curve",
            "title": "压平曲线：R₀=1.2",
            "description": (
                "同样的社区，把传播压到 β=0.12、γ=0.1，R₀=1.2：峰值显著更低、"
                "来得更晚——防疫措施未必阻止疫情，但能把峰值压到医疗可承受的范围。"
            ),
            "params": {"population": 10000, "initial_infected": 10, "beta": 0.12, "gamma": 0.1},
            "seed": 7,
            "stop_condition": {"type": "steps", "value": 300},
        },
        {
            "id": "die-out",
            "title": "自行熄灭：R₀=0.5",
            "description": (
                "传播压到阈值之下（β=0.05、γ=0.1，R₀=0.5）：疫情起不来，"
                "零星感染者康复后无人续传——低于 β/γ=1 这条线，世界自己恢复。"
            ),
            "params": {"population": 10000, "initial_infected": 10, "beta": 0.05, "gamma": 0.1},
            "seed": 7,
            "stop_condition": {"type": "steps", "value": 120},
        },
    ]

    def initialize(self, ctx: Any) -> None:
        p = self.params
        self._s = {
            "s": float(p.population - p.initial_infected),
            "i": float(p.initial_infected),
            "r": 0.0,
            "t": 0.0,
            "tick": 0,
            "peak_infected": float(p.initial_infected),
            "peak_time": 0.0,
            "history": [[0, float(p.population - p.initial_infected), float(p.initial_infected), 0.0]],
            "hist_stride": 1,
            "hist_n": 0,
        }

    def step(self) -> None:
        st = self._s
        p = self.params
        n = float(p.population)
        beta, gamma = p.beta, p.gamma
        s, i, r = st["s"], st["i"], st["r"]
        for _ in range(_SUBSTEPS):
            new_infections = beta * s * i / n * _H
            new_recoveries = gamma * i * _H
            s -= new_infections
            i += new_infections - new_recoveries
            r += new_recoveries
        # Euler drift guard: keep the compartments non-negative and conserved
        i = min(max(i, 0.0), n)
        s = min(max(s, 0.0), n)
        r = min(max(n - s - i, 0.0), n)
        st["s"], st["i"], st["r"] = s, i, r
        st["t"] += self.dt
        st["tick"] += 1
        if i > st["peak_infected"]:
            st["peak_infected"] = i
            st["peak_time"] = st["t"]
        self._sample()
        self.emit(
            float(st["tick"]),
            "epidemic",
            f"day {st['tick']}: S={s:.0f} I={i:.0f} R={r:.0f}",
            {"susceptible": round(s, 3), "infected": round(i, 3), "recovered": round(r, 3)},
        )

    def _sample(self) -> None:
        st = self._s
        st["hist_n"] += 1
        if st["hist_n"] % st["hist_stride"]:
            return
        st["history"].append([st["t"], st["s"], st["i"], st["r"]])
        if len(st["history"]) > 256:
            st["history"] = st["history"][::2]
            st["hist_stride"] *= 2

    def dump_state(self) -> dict[str, Any]:
        st = self._s
        return {
            "s": st["s"],
            "i": st["i"],
            "r": st["r"],
            "t": st["t"],
            "tick": st["tick"],
            "peak_infected": st["peak_infected"],
            "peak_time": st["peak_time"],
            "history": st["history"],
            "hist_stride": st["hist_stride"],
            "hist_n": st["hist_n"],
        }

    def load_state(self, state: dict[str, Any]) -> None:
        self._s = {
            "s": state["s"],
            "i": state["i"],
            "r": state["r"],
            "t": state["t"],
            "tick": state["tick"],
            "peak_infected": state["peak_infected"],
            "peak_time": state["peak_time"],
            "history": list(state["history"]),
            "hist_stride": state["hist_stride"],
            "hist_n": state["hist_n"],
        }

    def snapshot(self) -> dict[str, Any]:
        st = self._s
        p = self.params
        n = float(p.population)
        return {
            "tick": st["tick"],
            "day": st["t"],
            "population": p.population,
            "susceptible": st["s"],
            "infected": st["i"],
            "recovered": st["r"],
            "susceptible_frac": st["s"] / n,
            "infected_frac": st["i"] / n,
            "recovered_frac": st["r"] / n,
            "peak_infected": st["peak_infected"],
            "peak_time": st["peak_time"],
            "r0": p.beta / p.gamma if p.gamma > 0 else float("inf"),
            "history": st["history"],
        }

    def finalize_metrics(self) -> dict[str, float]:
        st = self._s
        p = self.params
        n = float(p.population)
        total_infected = st["r"] + st["i"]
        return {
            "tick": float(st["tick"]),
            "population": float(p.population),
            "susceptible_end": st["s"],
            "infected_end": st["i"],
            "recovered_end": st["r"],
            "total_infected": total_infected,
            "attack_rate": total_infected / n,
            "peak_infected": st["peak_infected"],
            "peak_time": st["peak_time"],
        }
