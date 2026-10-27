from pydantic import Field, model_validator
from typing import Literal, Optional

from ...core.engine.models_base import WorldLabParams


class CellularAutomatonParams(WorldLabParams):
    width: int = Field(default=32, ge=5, le=256)
    height: int = Field(default=32, ge=5, le=256)
    rule_string: str = Field(
        default="B3/S23",
        pattern=r"^B[0-8]*/S[0-8]*$",
        description="birth/survival neighbor counts, e.g. B3/S23 (Conway Life)",
    )
    toroidal: bool = Field(default=True, description="wrap at edges; otherwise outside = dead")
    initial_density: float = Field(default=0.25, ge=0.0, le=1.0)
    initial_grid: Optional[list[list[int]]] = Field(
        default=None,
        description="explicit initial state (0/1 cells, exact width x height)",
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
