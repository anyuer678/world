from typing import Literal, Optional

from pydantic import Field, model_validator

from ...core.engine.models_base import WorldLabParams


class SchellingParams(WorldLabParams):
    width: int = Field(default=40, ge=5, le=120, title="网格宽度")
    height: int = Field(default=30, ge=5, le=120, title="网格高度")
    occupancy: float = Field(
        default=0.85, ge=0.1, le=0.98, title="格子占用率",
        description="随机初始化时被智能体占据的格子比例，其余留空",
    )
    ratio_a: float = Field(
        default=0.5, ge=0.05, le=0.95, title="A 组占比",
        description="被占用的格子里属于 A 组的比例，其余为 B 组",
    )
    tolerance: float = Field(
        default=0.3, ge=0.0, le=1.0, title="容忍阈值",
        description="相似邻居占已占用邻居的比例达到该值即满意；0=毫无偏好，1=要求全部同组",
    )
    toroidal: bool = Field(default=True, title="环形边界", description="开启后网格首尾相接；关闭则边界外不算邻居")
    initial_grid: Optional[list[list[int]]] = Field(
        default=None,
        title="指定初始布局",
        description="0=空格、1=A 组、2=B 组的矩阵（行数=高度，列数=宽度）；留空则随机生成",
    )

    @model_validator(mode="after")
    def _check(self) -> "SchellingParams":
        if self.initial_grid is not None:
            if len(self.initial_grid) != self.height or any(
                len(row) != self.width for row in self.initial_grid
            ):
                raise ValueError("initial_grid must be exactly height rows of width cells")
            if any(c not in (0, 1, 2) for row in self.initial_grid for c in row):
                raise ValueError("initial_grid cells must be 0, 1 or 2")
        return self
