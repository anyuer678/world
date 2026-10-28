from pydantic import Field, model_validator
from typing import Literal, Optional

from ...core.engine.models_base import WorldLabParams


class CellularAutomatonParams(WorldLabParams):
    width: int = Field(default=32, ge=5, le=256, title="网格宽度")
    height: int = Field(default=32, ge=5, le=256, title="网格高度")
    rule_string: str = Field(
        default="B3/S23",
        pattern=r"^B[0-8]*/S[0-8]*$",
        title="演化规则（B/S 串）",
        description="B=出生所需邻居数，S=存活所需邻居数，如 B3/S23 即生命游戏",
    )
    toroidal: bool = Field(default=True, title="环形边界", description="开启后网格首尾相接；关闭则边界外视为死细胞")
    initial_density: float = Field(default=0.25, ge=0.0, le=1.0, title="初始随机密度")
    initial_grid: Optional[list[list[int]]] = Field(
        default=None,
        title="指定初始图案",
        description="给出 0/1 矩阵（行数=高度，列数=宽度）；留空则按随机密度生成",
    )

    @model_validator(mode="after")
    def _check(self) -> "CellularAutomatonParams":
        if self.initial_grid is not None:
            if len(self.initial_grid) != self.height or any(
                len(row) != self.width for row in self.initial_grid
            ):
                raise ValueError("initial_grid must be exactly height rows of width cells")
            if any(c not in (0, 1) for row in self.initial_grid for c in row):
                raise ValueError("initial_grid cells must be 0 or 1")
        return self
