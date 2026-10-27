from pydantic import Field, model_validator
from typing import Literal, Optional

from ...core.engine.models_base import WorldLabParams


class ArrivalProcess(WorldLabParams):
    kind: Literal["poisson", "deterministic"] = "poisson"
    rate: float = Field(default=1.0, gt=0, description="arrivals per time unit")


class ServiceProcess(WorldLabParams):
    kind: Literal["exponential", "deterministic", "uniform"] = "exponential"
    mean: float = Field(default=1.0, gt=0)
    half_spread: float = Field(default=0.0, ge=0)

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
    arrival: ArrivalProcess = Field(default_factory=ArrivalProcess)
    service: ServiceProcess = Field(default_factory=ServiceProcess)
    servers: int = Field(default=1, ge=1, le=1024)
    capacity: Optional[int] = Field(default=None, ge=1, description="max customers in system (incl. in service); None = unlimited")
    discipline: Literal["fifo", "lcfs"] = "fifo"
    warmup_customers: int = Field(default=0, ge=0, description="arrivals before metrics are collected")
