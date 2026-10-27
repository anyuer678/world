"""Versioned model description format (ModelSpec) + two-layer validation:
1) spec-level: schema fields, stop-condition/model-type compatibility
2) model-level: params against the registered model's pydantic schema
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..registry import ModelRegistry, RegistryError
from ..engine.base import ModelType
from .errors import SpecValidationError
from .evolution import SPEC_CURRENT_VERSION, upgrade_spec


class StopSteps(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["steps"]
    value: int = Field(gt=0, le=100_000_000)


class StopSimTime(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["sim_time"]
    value: float = Field(gt=0)


class StopUntilEmpty(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["until_empty"]


StopCondition = Annotated[
    Union[StopSteps, StopSimTime, StopUntilEmpty], Field(discriminator="type")
]


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SPEC_CURRENT_VERSION
    model_id: str = Field(min_length=1, max_length=100)
    model_version: Optional[str] = None
    display_name: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    stop_condition: StopCondition = Field(default_factory=lambda: StopSteps(type="steps", value=10_000))
    seed: Optional[int] = Field(default=None, ge=0)
    notes: str = ""


def parse_spec(raw: dict[str, Any]) -> ModelSpec:
    """Migrate raw spec dict to current schema version, then validate shape."""
    if not isinstance(raw, dict):
        raise SpecValidationError.single("type_error", "spec must be a JSON object")
    try:
        raw = upgrade_spec(raw)
    except SpecValidationError:
        raise
    try:
        return ModelSpec(**raw)
    except ValidationError as exc:
        errors = [
            {"code": ".".join(str(loc) for loc in e["loc"]) or "spec", "message": e["msg"]}
            for e in exc.errors()
        ]
        raise SpecValidationError(errors) from None


def validate_spec(raw: dict[str, Any], registry: ModelRegistry) -> tuple[ModelSpec, Any]:
    """Full validation: shape + registry lookup + stop/type compatibility +
    model params. Returns (spec, model_class). Raises SpecValidationError."""
    spec = parse_spec(raw)
    try:
        model_cls = registry.get(spec.model_id, spec.model_version)
    except RegistryError as exc:
        raise SpecValidationError.single("unknown_model", str(exc)) from None
    stop_type = spec.stop_condition.type
    if stop_type == "until_empty" and model_cls.model_type != ModelType.DISCRETE_EVENT:
        raise SpecValidationError.single(
            "stop_condition_incompatible",
            "until_empty is only valid for discrete-event models",
        )
    if stop_type == "sim_time" and model_cls.model_type == ModelType.TIME_STEPPED:
        pass  # allowed: horizon in simulated time units
    try:
        params_obj = model_cls.param_model(**spec.params)
    except ValidationError as exc:
        errors = [
            {"code": f"params.{'.'.join(str(loc) for loc in e['loc'])}", "message": e["msg"]}
            for e in exc.errors()
        ]
        raise SpecValidationError(errors) from None
    return spec, model_cls


def example_spec_for(model_cls: Any) -> dict[str, Any]:
    """Build a runnable example spec from a model class defaults."""
    return {
        "schema_version": SPEC_CURRENT_VERSION,
        "model_id": model_cls.model_id,
        "model_version": model_cls.version,
        "params": model_cls.param_model().model_dump(),
        "stop_condition": {"type": "steps", "value": 10_000},
        "seed": 42,
    }
