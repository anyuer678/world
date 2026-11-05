from pydantic import Field, model_validator
from typing import Optional

from ...core.engine.models_base import WorldLabParams


class PredatorPreyParams(WorldLabParams):
    prey_growth: float = Field(
        default=1.0, ge=0.0, le=10.0, title="猎物增长率 α",
        description="无捕食者时猎物每单位时间的指数增长率",
    )
    predation: float = Field(
        default=0.4, gt=0.0, le=10.0, title="捕食强度 β",
        description="单位时间单个捕食者与猎物相遇造成的捕食率",
    )
    conversion: float = Field(
        default=0.3, gt=0.0, le=10.0, title="转化效率 δ",
        description="吃到的猎物转化为新捕食者的比例（食物链能量传递）",
    )
    predator_death: float = Field(
        default=0.6, gt=0.0, le=10.0, title="捕食者死亡率 γ",
        description="捕食者断粮后每单位时间的衰减率",
    )
    initial_prey: float = Field(default=2.0, ge=0.0, le=1_000_000.0, title="初始猎物数量 x₀")
    initial_predator: float = Field(default=1.0, ge=0.0, le=1_000_000.0, title="初始捕食者数量 y₀")
    prey_capacity: Optional[float] = Field(
        default=None, gt=0.0, le=1_000_000.0, title="猎物环境容纳量 K",
        description="给猎物加上逻辑斯谛限制（资源有限）；留空 = 经典无界模型，循环永不衰减",
    )

    @model_validator(mode="after")
    def _check(self) -> "PredatorPreyParams":
        if self.initial_prey == 0 and self.initial_predator == 0:
            raise ValueError("at least one population must start above zero")
        return self
