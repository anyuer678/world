"""Shared fixtures and toy models for engine tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import app.models  # noqa: F401, E402 - register built-in plugins
from app.config import Settings  # noqa: E402
from app.core.engine.models_base import DiscreteEventModel, TimeSteppedModel, WorldLabParams  # noqa: E402
from app.core.registry import registry  # noqa: E402
from app.services.experiment_service import ExperimentService  # noqa: E402


class ToyDesParams(WorldLabParams):
    total_events: int = 100
    delay_mean: float = 1.0


class ToyDesModel(DiscreteEventModel):
    model_id = "toy_des"
    display_name = "Toy DES"
    description = "Toy discrete-event model for tests."
    model_type = "discrete_event"
    version = "1.0.0"
    param_model = ToyDesParams

    def initialize(self, ctx) -> None:
        self.count = 0
        self.total_time = 0.0
        ctx.schedule(1.0, "tick")

    def handle_event(self, event, ctx) -> None:
        self.count += 1
        self.total_time = event.time
        self.emit(event.time, event.kind, f"tick #{self.count}")
        if self.count < self.params.total_events:
            ctx.schedule(self.rng.expovariate(1.0 / self.params.delay_mean), "tick")

    def dump_state(self):
        return {"count": self.count, "total_time": self.total_time}

    def load_state(self, state):
        self.count = state["count"]
        self.total_time = state["total_time"]

    def snapshot(self):
        return {"count": self.count, "total_time": self.total_time}

    def finalize_metrics(self):
        return {"count": float(self.count), "total_time": float(self.total_time)}


class ToyStepParams(WorldLabParams):
    pass


class ToyStepModel(TimeSteppedModel):
    model_id = "toy_step"
    display_name = "Toy time-stepped"
    description = "Toy time-stepped model for tests."
    model_type = "time_stepped"
    version = "1.0.0"
    dt = 1.0
    param_model = ToyStepParams

    def initialize(self, ctx=None) -> None:
        self.value = 1.0
        self.trace = []

    def step(self) -> None:
        self.value = self.value * 2.0 + self.rng.random()
        self.trace.append(self.value)

    def dump_state(self):
        return {"value": self.value, "trace": list(self.trace)}

    def load_state(self, state):
        self.value = state["value"]
        self.trace = list(state["trace"])

    def snapshot(self):
        return {"value": self.value, "step_count": len(self.trace)}

    def finalize_metrics(self):
        return {"value": float(self.value)}


class ZeroDelayParams(WorldLabParams):
    pass


class ZeroDelayLoopModel(DiscreteEventModel):
    """Pathological model: never stops scheduling delay=0 events."""

    model_id = "toy_zero_delay"
    display_name = "Zero-delay loop"
    description = "Pathological zero-delay chain model for tests."
    model_type = "discrete_event"
    version = "1.0.0"
    param_model = ZeroDelayParams

    def initialize(self, ctx) -> None:
        ctx.schedule(0.0, "spin")

    def handle_event(self, event, ctx) -> None:
        ctx.schedule(0.0, "spin")

    def dump_state(self):
        return {}

    def load_state(self, state):
        pass

    def snapshot(self):
        return {}

    def finalize_metrics(self):
        return {}


registry.register(ToyDesModel)
registry.register(ToyStepModel)
registry.register(ZeroDelayLoopModel)


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        db_path=str(tmp_path / "worldlab.db"),
        max_workers=2,
        default_max_steps=100000,
        max_wall_seconds=60,
        event_log_size=500,
        zero_delay_chain_limit=10000,
        cancel_poll_interval=256,
        plugin_modules=(),
    )


@pytest.fixture()
def service(settings):
    s = ExperimentService(settings, registry)
    yield s
    s.shutdown()
