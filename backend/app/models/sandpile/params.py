from pydantic import Field, model_validator

from ...core.engine.models_base import WorldLabParams


class SandpileParams(WorldLabParams):
    width: int = Field(default=40, ge=10, le=120, title="网格宽度")
    height: int = Field(default=30, ge=10, le=120, title="网格高度")
    threshold: int = Field(
        default=4,
        ge=2,
        le=8,
        title="崩塌阈值",
        description="格子里的沙粒达到该值就向四邻各塌落 1 粒；阈值越低越容易连锁崩塌",
    )
    initial_grains: int = Field(
        default=0,
        ge=0,
        le=7,
        title="每格初始沙粒",
        description="开始运行时每个格子已有的沙粒数（必须小于阈值，否则开局就不稳定）",
    )

    @model_validator(mode="after")
    def _check(self) -> "SandpileParams":
        if self.initial_grains >= self.threshold:
            raise ValueError("initial_grains must be smaller than threshold")
        return self
