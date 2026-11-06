"""Shared fixtures and toy models for engine tests."""
from __future__ import annotations

import sys
import time
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


class SlowStepParams(WorldLabParams):
    pass


class SlowStepModel(TimeSteppedModel):
    """Sleeps per step so a 256-step run chunk lasts ~130 ms — long-lived
    sessions for reset/pause-during-running tests."""

    model_id = "toy_slow_step"
    display_name = "Slow toy time-stepped"
    description = "Toy time-stepped model that sleeps per step."
    model_type = "time_stepped"
    version = "1.0.0"
    dt = 1.0
    param_model = SlowStepParams

    def initialize(self, ctx=None) -> None:
        self.value = 0.0

    def step(self) -> None:
        time.sleep(0.0005)
        self.value += 1.0

    def dump_state(self):
        return {"value": self.value}

    def load_state(self, state):
        self.value = state["value"]

    def snapshot(self):
        return {"value": self.value}

    def finalize_metrics(self):
        return {"value": float(self.value)}


registry.register(ToyDesModel)
registry.register(ToyStepModel)
registry.register(ZeroDelayLoopModel)
registry.register(SlowStepModel)


@pytest.fixture(scope="session", autouse=True)
def isolate_default_settings(tmp_path_factory):
    """R61：测试绝不允许写进仓库里的开发库 `backend/data/worldlab.db`。

    `create_app()` 不带参数时读 `app.main.default_settings`；此前
    `tests/test_model_versions.py` 的两处 `create_app()` 每跑一轮就往开发库塞 3 个实验
    （实测 58 → 61）。这里在会话级别把默认设置换成临时库，任何"忘了传 settings"的调用
    都写不到仓库数据。已修正的调用点仍然显式传 tmp 库。"""
    import app.main as main_module

    original = main_module.default_settings
    main_module.default_settings = Settings(
        db_path=str(tmp_path_factory.mktemp("default-db") / "worldlab.db"),
        max_workers=original.max_workers,
        default_max_steps=original.default_max_steps,
        max_wall_seconds=original.max_wall_seconds,
        event_log_size=original.event_log_size,
        zero_delay_chain_limit=original.zero_delay_chain_limit,
        cancel_poll_interval=original.cancel_poll_interval,
        session_ttl_seconds=original.session_ttl_seconds,
        plugin_modules=(),
    )
    yield
    main_module.default_settings = original


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
        session_ttl_seconds=3600.0,
        plugin_modules=(),
    )


@pytest.fixture()
def service(settings):
    s = ExperimentService(settings, registry)
    yield s
    s.shutdown()
