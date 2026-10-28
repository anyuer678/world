from pydantic import Field, model_validator
from typing import Literal, Optional

from ...core.engine.models_base import WorldLabParams


class JobSpec(WorldLabParams):
    arrival: float = Field(ge=0, title="到达时间")
    service: float = Field(gt=0, title="所需服务时长")
    priority: int = Field(default=0, title="优先级（数值越小越优先）")


class CpuSchedulingParams(WorldLabParams):
    strategy: Literal["fcfs", "sjf", "priority", "rr"] = Field(default="fcfs", title="调度策略")
    jobs: Optional[list[JobSpec]] = Field(
        default=None,
        title="显式作业列表",
        description="手工给出每条作业的到达/服务/优先级；留空则按下面的分布随机生成",
    )
    num_jobs: int = Field(default=200, ge=1, le=100_000, title="作业数量")
    arrival_rate: float = Field(default=1.0, gt=0, title="到达率")
    service_min: float = Field(default=0.2, gt=0, title="最短服务时长")
    service_max: float = Field(default=1.8, gt=0, title="最长服务时长")
    priority_low: int = Field(default=0, title="随机优先级下界")
    priority_high: int = Field(default=4, title="随机优先级上界")
    quantum: float = Field(
        default=1.0, gt=0, title="时间片长度", description="仅 RR 策略使用；作业每次最多连续运行这么久"
    )

    @model_validator(mode="after")
    def _check(self) -> "CpuSchedulingParams":
        if self.service_max < self.service_min:
            raise ValueError("service_max must be >= service_min")
        if self.priority_high < self.priority_low:
            raise ValueError("priority_high must be >= priority_low")
        if self.jobs is not None:
            if not self.jobs:
                raise ValueError("jobs must be non-empty when provided")
            if len(self.jobs) > 10_000:
                raise ValueError("at most 10000 explicit jobs")
        return self
