from pydantic import Field, model_validator
from typing import Literal, Optional

from ...core.engine.models_base import WorldLabParams


class CacheParams(WorldLabParams):
    capacity: int = Field(default=8, ge=1, le=1024, description="cache size in slots")
    policy: Literal["lru", "fifo", "lfu", "random"] = "lru"
    num_keys: int = Field(
        default=100,
        ge=2,
        le=100_000,
        description="distinct keys for the generated access stream",
    )
    zipf_exponent: float = Field(
        default=0.0,
        ge=0,
        le=3.0,
        description="key popularity skew; 0 = uniform, 1+ = strong locality",
    )
    accesses: Optional[list[int]] = Field(
        default=None,
        description="explicit access sequence (non-negative keys); cycled when exhausted",
    )
    cost_hit: float = Field(default=1.0, ge=0)
    cost_miss: float = Field(default=10.0, gt=0)

    @model_validator(mode="after")
    def _check(self) -> "CacheParams":
        if self.accesses is not None:
            if not self.accesses:
                raise ValueError("accesses must be non-empty when provided")
            if len(self.accesses) > 1_000_000:
                raise ValueError("at most 1000000 explicit accesses")
            if any(k < 0 for k in self.accesses):
                raise ValueError("access keys must be >= 0")
        return self
