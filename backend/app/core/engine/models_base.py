"""Model plugin contract. A model implements either TimeSteppedModel or
DiscreteEventModel; the engine owns clocks and scheduling, models own state."""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pydantic import BaseModel as PydanticModel
from pydantic import ConfigDict

from .base import ENGINE_VERSION, ModelType


class WorldLabParams(PydanticModel):
    """Base class for model parameter schemas; unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")


@dataclass
class EventRecord:
    seq: int
    time: float
    kind: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "time": self.time,
            "kind": self.kind,
            "message": self.message,
            "data": self.data,
        }


@dataclass
class StateSnapshot:
    step: int
    time: float
    status: str
    state: dict[str, Any]
    metrics: dict[str, float]

    def to_json(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "time": self.time,
            "status": self.status,
            "state": self.state,
            "metrics": self.metrics,
        }


class BaseWorldModel(ABC):
    """Contract every model plugin must satisfy.

    ClassVars declare identity and schema; instances hold params + one private
    RNG. All state must be JSON-serializable (snapshots and checkpoints travel
    through the API and the database).
    """

    model_id: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str] = ""
    model_type: ClassVar[str]
    version: ClassVar[str] = "1.0.0"
    visualizer: ClassVar[dict[str, Any]] = {"kind": "none"}
    param_model: ClassVar[type[WorldLabParams]]

    def __init__(self, params: dict[str, Any] | WorldLabParams, rng_seed: int | None):
        if isinstance(params, dict):
            params = self.param_model(**params)
        elif type(params) is not self.param_model:
            raise TypeError(f"params must be {self.param_model.__name__}")
        self.params = params
        self.rng = random.Random(rng_seed)
        self._log: deque[EventRecord] = deque(maxlen=500)
        self._log_seq = 0
        self.seed = rng_seed

    def emit(self, time: float, kind: str, message: str, data: dict[str, Any] | None = None) -> None:
        self._log_seq += 1
        self._log.append(EventRecord(self._log_seq, float(time), kind, message, data or {}))

    @property
    def event_log(self) -> list[EventRecord]:
        return list(self._log)

    @abstractmethod
    def initialize(self, ctx: Any) -> None: ...

    @abstractmethod
    def dump_state(self) -> dict[str, Any]: ...

    @abstractmethod
    def load_state(self, state: dict[str, Any]) -> None: ...

    @abstractmethod
    def snapshot(self) -> dict[str, Any]: ...

    @abstractmethod
    def finalize_metrics(self) -> dict[str, float]: ...


class DiscreteEventModel(BaseWorldModel):
    """DES contract: schedule future events via ctx, react in handle_event.

    Time semantics: event times strictly ordered by (time, priority, seq);
    delay=0 chains are processed in scheduling order at one timestamp.
    """

    model_type = ModelType.DISCRETE_EVENT

    @abstractmethod
    def handle_event(self, event: Any, ctx: Any) -> None: ...


class TimeSteppedModel(BaseWorldModel):
    """Fixed-delta-t contract: one step() call advances exactly dt."""

    model_type = ModelType.TIME_STEPPED
    dt: ClassVar[float] = 1.0

    def initialize(self, ctx: Any) -> None:
        """Optional setup; ctx is unused for time-stepped models."""

    @abstractmethod
    def step(self) -> None:
        """Advance state by exactly self.dt. Emit events via self.emit()."""

