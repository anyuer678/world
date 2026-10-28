from pydantic import Field, model_validator
from typing import Literal, Optional

from ...core.engine.models_base import WorldLabParams


class CacheParams(WorldLabParams):
    capacity: int = Field(default=8, ge=1, le=1024, title="缓存容量（槽位数）")
    policy: Literal["lru", "fifo", "lfu", "random"] = Field(default="lru", title="替换策略")
    num_keys: int = Field(
        default=100,
        ge=2,
        le=100_000,
        title="键的种数",
        description="生成的访问序列中不同键的数量",
    )
    zipf_exponent: float = Field(
        default=0.0,
        ge=0,
        le=3.0,
        title="热门程度偏斜 α",
        description="0 = 所有键同样热门；越大越偏向少数热门键（真实网页/视频访问常在 1 附近）",
    )
    accesses: Optional[list[int]] = Field(
        default=None,
        title="显式访问序列",
        description="逐个给出要访问的键（非负整数），用完则从头循环；留空则按上面的分布随机生成",
    )
    cost_hit: float = Field(default=1.0, ge=0, title="命中成本")
    cost_miss: float = Field(default=10.0, gt=0, title="缺失成本")

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
