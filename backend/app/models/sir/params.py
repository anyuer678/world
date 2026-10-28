from pydantic import Field, model_validator

from ...core.engine.models_base import WorldLabParams


class SirParams(WorldLabParams):
    population: int = Field(
        default=10000, ge=10, le=10_000_000, title="总人口",
        description="S+I+R 恒等于总人口（仓室模型，不追踪个体）",
    )
    initial_infected: int = Field(
        default=10, ge=1, le=10_000_000, title="初始感染数",
        description="t=0 时的感染者 I；其余全是易感者 S",
    )
    beta: float = Field(
        default=0.3, ge=0.0, le=10.0, title="传播率 β",
        description="每单位时间每个感染者对易感者的平均传播强度；β/γ>1 疫情才扩张",
    )
    gamma: float = Field(
        default=0.1, ge=0.0, le=5.0, title="康复率 γ",
        description="每单位时间感染者康复的比例（1/γ = 平均感染时长）",
    )

    @model_validator(mode="after")
    def _check(self) -> "SirParams":
        if self.initial_infected > self.population:
            raise ValueError("initial_infected cannot exceed population")
        return self
