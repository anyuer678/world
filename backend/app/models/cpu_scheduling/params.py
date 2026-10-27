from pydantic import Field, model_validator
from typing import Literal, Optional

from ...core.engine.models_base import WorldLabParams


class JobSpec(WorldLabParams):
    arrival: float = Field(ge=0, description="job arrival time")
    service: float = Field(gt=0, description="total CPU service demand")
    priority: int = Field(default=0, description="smaller value = higher priority")


class CpuSchedulingParams(WorldLabParams):
    strategy: Literal["fcfs", "sjf", "priority", "rr"] = "fcfs"
    jobs: Optional[list[JobSpec]] = Field(
        default=None,
        description="explicit workload; None generates a random workload",
    )
    num_jobs: int = Field(default=200, ge=1, le=100_000)
    arrival_rate: float = Field(default=1.0, gt=0)
    service_min: float = Field(default=0.2, gt=0)
    service_max: float = Field(default=1.8, gt=0)
    priority_low: int = Field(default=0)
    priority_high: int = Field(default=4)
    quantum: float = Field(default=1.0, gt=0, description="time slice for rr strategy")

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
