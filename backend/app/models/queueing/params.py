from pydantic import Field, model_validator
from typing import Literal, Optional

from ...core.engine.models_base import WorldLabParams


class ArrivalProcess(WorldLabParams):
    kind: Literal["poisson", "deterministic"] = Field(default="poisson", title="到达类型")
    rate: float = Field(default=1.0, gt=0, title="到达率 λ", description="每单位时间到达的顾客数")


class ServiceProcess(WorldLabParams):
    kind: Literal["exponential", "deterministic", "uniform"] = Field(default="exponential", title="服务时间类型")
    mean: float = Field(default=1.0, gt=0, title="平均服务时间")
    half_spread: float = Field(default=0.0, ge=0, title="均匀分布半宽")

    @model_validator(mode="after")
    def _check_uniform(self) -> "ServiceProcess":
        if self.kind == "uniform" and self.half_spread <= 0:
            raise ValueError("uniform service requires half_spread > 0")
        if self.kind == "uniform" and self.half_spread >= self.mean:
            raise ValueError("uniform service requires half_spread < mean (service time must stay > 0)")
        if self.kind != "uniform" and self.half_spread != 0.0:
            raise ValueError("half_spread only applies to uniform service")
        return self


class QueueingParams(WorldLabParams):
    arrival: ArrivalProcess = Field(default_factory=ArrivalProcess, title="到达过程")
    service: ServiceProcess = Field(default_factory=ServiceProcess, title="服务过程")
    servers: int = Field(default=1, ge=1, le=1024, title="服务台数")
    capacity: Optional[int] = Field(
        default=None, ge=1, title="系统容量",
        description="系统内最大顾客数（含正在服务的）；留空 = 无限",
    )
    discipline: Literal["fifo", "lcfs"] = Field(default="fifo", title="排队规则")
    warmup_customers: int = Field(default=0, ge=0, title="预热人数", description="前 N 个到达不计入指标")
