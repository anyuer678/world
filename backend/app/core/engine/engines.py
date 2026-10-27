"""Engines: time-stepped and discrete-event semantics, plus a unified facade
(SimulationEngine) providing run/step/reset/checkpoint/restore/cancel/limits.
Time semantics are strictly separated:
- time-stepped: clock advances exactly dt per step.
- discrete-event: clock jumps to the next event's time; ordering is
  (time, priority, seq); zero-delay chains bounded per timestamp.
"""
from __future__ import annotations

import time as _time
from dataclasses import dataclass
from typing import Any, Callable

from .base import (
    ENGINE_VERSION,
    ModelType,
    SimulationError,
    SimulationLimitExceeded,
)
from .event_queue import EventQueue
from .models_base import BaseWorldModel, DiscreteEventModel, StateSnapshot, TimeSteppedModel
from .rng import rng_state_from_json, rng_state_to_json


@dataclass(frozen=True)
class Limits:
    max_steps: int = 1_000_000
    max_wall_seconds: float = 120.0
    zero_delay_chain_limit: int = 10_000
    cancel_poll_interval: int = 256


@dataclass
class RunResult:
    status: str  # completed | step_limit | wall_timeout | cancelled | chunk_done
    stop_reason: str
    steps: int
    sim_time: float
    wall_seconds: float
    metrics: dict[str, float]
    snapshot: dict[str, Any]
    engine_version: str = ENGINE_VERSION

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "stop_reason": self.stop_reason,
            "steps": self.steps,
            "sim_time": self.sim_time,
            "wall_seconds": self.wall_seconds,
            "metrics": self.metrics,
            "snapshot": self.snapshot,
            "engine_version": self.engine_version,
        }


Checkpoint = dict[str, Any]


class EmptyQueueError(SimulationError):
    pass


class _BaseEngine:
    def __init__(
        self,
        model: BaseWorldModel,
        stop_condition: dict[str, Any],
        limits: Limits,
        cancel_check: Callable[[], bool] | None,
    ) -> None:
        self.model = model
        self.stop = stop_condition
        self.limits = limits
        self.cancel_check = cancel_check
        self.steps = 0
        self.clock = 0.0
        self.status = "ready"
        self._initialized = False

    def _ensure_init(self) -> None:
        if not self._initialized:
            self.model.initialize(self._ctx())
            self._initialized = True
            self.status = "running"

    def _ctx(self) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError

    def _wall_or_cancel(self, t0: float) -> str | None:
        if self.cancel_check is not None and self.cancel_check():
            return "cancelled"
        if _time.monotonic() - t0 > self.limits.max_wall_seconds:
            return "wall_timeout"
        return None

    def snapshot(self) -> StateSnapshot:
        if not self._initialized:
            return StateSnapshot(step=0, time=0.0, status=self.status, state={}, metrics={})
        return StateSnapshot(
            step=self.steps,
            time=self.clock,
            status=self.status,
            state=self.model.snapshot(),
            metrics=self.model.finalize_metrics(),
        )

    def checkpoint(self) -> Checkpoint:
        self._ensure_init()
        return {
            "engine_version": ENGINE_VERSION,
            "model_id": self.model.model_id,
            "model_type": self.model.model_type,
            "step": self.steps,
            "clock": self.clock,
            "status": self.status,
            "rng": rng_state_to_json(self.model.rng),
            "model_state": self.model.dump_state(),
            "engine": self._engine_state(),
        }

    def restore(self, cp: Checkpoint) -> None:
        if cp.get("model_id") != self.model.model_id:
            raise SimulationError(
                f"checkpoint model_id {cp.get('model_id')!r} != {self.model.model_id!r}"
            )
        if cp.get("engine_version") != ENGINE_VERSION:
            raise SimulationError("checkpoint engine version mismatch")
        self.steps = int(cp["step"])
        self.clock = float(cp["clock"])
        self.status = str(cp.get("status", "running"))
        rng_state_from_json(self.model.rng, cp["rng"])
        self.model.load_state(dict(cp["model_state"]))
        self._engine_restore(cp.get("engine", {}))
        self._initialized = True

    def _engine_state(self) -> dict[str, Any]:
        return {}

    def _engine_restore(self, state: dict[str, Any]) -> None:
        return None


class TimeSteppedEngine(_BaseEngine):
    def __init__(
        self,
        model: TimeSteppedModel,
        stop_condition: dict[str, Any],
        limits: Limits,
        cancel_check: Callable[[], bool] | None,
    ) -> None:
        super().__init__(model, stop_condition, limits, cancel_check)
        self.dt = float(model.dt)
        if self.dt <= 0:
            raise SimulationError("dt must be > 0")

    def _ctx(self) -> None:
        return None

    def step(self) -> None:
        self._ensure_init()
        self.model.step()
        self.steps += 1
        self.clock = self.steps * self.dt
        self.status = "running"

    def _stop_reason(self, t0: float) -> str | None:
        stop_type = self.stop.get("type")
        if stop_type == "steps" and self.steps >= int(self.stop["value"]):
            return "completed"
        if stop_type == "sim_time" and self.clock >= float(self.stop["value"]) - 1e-12:
            return "completed"
        if self.steps >= self.limits.max_steps:
            return "step_limit"
        if self.steps % self.limits.cancel_poll_interval == 0:
            return self._wall_or_cancel(t0)
        return None


class DesContext:
    """What a DiscreteEventModel receives while handling an event."""

    def __init__(self, engine: "DesEngine") -> None:
        self._engine = engine

    @property
    def now(self) -> float:
        return self._engine.clock

    @property
    def rng(self):  # noqa: ANN201 - model's own Random
        return self._engine.model.rng

    def schedule(
        self,
        delay: float,
        kind: str,
        payload: dict[str, Any] | None = None,
        priority: int = 0,
    ) -> None:
        if delay < 0:
            raise SimulationError(f"schedule delay must be >= 0, got {delay}")
        self._engine.queue.push(self._engine.clock + float(delay), kind, payload, priority)


class DesEngine(_BaseEngine):
    def __init__(
        self,
        model: DiscreteEventModel,
        stop_condition: dict[str, Any],
        limits: Limits,
        cancel_check: Callable[[], bool] | None,
    ) -> None:
        super().__init__(model, stop_condition, limits, cancel_check)
        self.queue = EventQueue()
        self._last_event_time: float | None = None
        self._chain_count = 0

    def _ctx(self) -> DesContext:
        return DesContext(self)

    def step(self) -> None:
        self._ensure_init()
        ev = self.queue.pop()
        if ev is None:
            self.status = "idle"
            raise EmptyQueueError("step() called with empty event queue")
        if ev.time < self.clock - 1e-12:
            raise SimulationError(f"event time {ev.time} earlier than clock {self.clock}")
        if self._last_event_time is not None and ev.time <= self._last_event_time + 1e-15:
            self._chain_count += 1
            if self._chain_count > self.limits.zero_delay_chain_limit:
                raise SimulationLimitExceeded(
                    f"more than {self.limits.zero_delay_chain_limit} events at t={self.clock}",
                    "zero_delay_chain",
                )
        else:
            self._chain_count = 0
        self.clock = ev.time
        self._last_event_time = ev.time
        self.model.handle_event(ev, DesContext(self))
        self.steps += 1
        self.status = "running"

    def _engine_state(self) -> dict[str, Any]:
        return {"queue": self.queue.to_json(), "seq": self.queue._seq}

    def _engine_restore(self, state: dict[str, Any]) -> None:
        self.queue = EventQueue()
        self.queue.load_json(state.get("queue", []))
        self._chain_count = 0
        self._last_event_time = self.clock if self.steps > 0 else None

    def _stop_reason(self, t0: float) -> str | None:
        if len(self.queue) == 0:
            return "completed"
        stop_type = self.stop.get("type")
        if stop_type == "sim_time":
            nxt = self.queue.peek()
            if nxt is not None and nxt.time > float(self.stop["value"]) + 1e-12:
                return "completed"
        if self.steps >= self.limits.max_steps:
            return "step_limit"
        if stop_type == "steps" and self.steps >= int(self.stop["value"]):
            return "completed"
        if self.steps % self.limits.cancel_poll_interval == 0:
            return self._wall_or_cancel(t0)
        return None


class SimulationEngine:
    """Unified facade over both time semantics.

    - run(n): advance up to n steps (n None = until stop condition/limits).
    - step(): single step; returns False when the simulation cannot advance.
    - pause/resume: implicit - the engine is a plain object; a "pause" is just
      not calling step() for a while; run()/step() resume exactly where they
      stopped. Checkpoints make that durable.
    """

    def __init__(
        self,
        model: BaseWorldModel,
        stop_condition: dict[str, Any] | None = None,
        *,
        limits: Limits | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        stop = stop_condition or {"type": "steps", "value": 1_000_000}
        limits = limits or Limits()
        if model.model_type == ModelType.DISCRETE_EVENT:
            self._inner: _BaseEngine = DesEngine(model, stop, limits, cancel_check)
        elif model.model_type == ModelType.TIME_STEPPED:
            self._inner = TimeSteppedEngine(model, stop, limits, cancel_check)
        else:
            raise SimulationError(f"unknown model_type {model.model_type!r}")
        self.model = model
        self.stop = stop

    @property
    def clock(self) -> float:
        return self._inner.clock

    @property
    def steps(self) -> int:
        return self._inner.steps

    @property
    def status(self) -> str:
        return self._inner.status

    def reset(self) -> None:
        old = self._inner
        fresh_model = type(self.model)(self.model.params, self.model.seed)
        kwargs = dict(
            stop_condition=self.stop,
            limits=old.limits,
            cancel_check=old.cancel_check,
        )
        if isinstance(fresh_model, DiscreteEventModel):
            self._inner = DesEngine(fresh_model, **kwargs)
        else:
            self._inner = TimeSteppedEngine(fresh_model, **kwargs)
        self.model = fresh_model

    def step(self) -> bool:
        try:
            self._inner.step()
            return True
        except EmptyQueueError:
            return False

    def run(self, max_steps: int | None = None) -> RunResult:
        t0 = _time.monotonic()
        self._inner._ensure_init()
        hard_cap = self._inner.limits.max_steps
        if max_steps is not None:
            hard_cap = min(hard_cap, self._inner.steps + max_steps)
        if self.stop.get("type") == "steps":
            hard_cap = min(hard_cap, int(self.stop["value"]))
        stop_reason: str | None = None
        while True:
            reason = self._inner._stop_reason(t0)
            if reason is not None:
                stop_reason = reason
                break
            if self._inner.steps >= hard_cap:
                stop_reason = "chunk_done"
                break
            self._inner.step()
        wall = _time.monotonic() - t0
        status = stop_reason or "completed"
        if status != "chunk_done":
            self._inner.status = status
        result = RunResult(
            status=status,
            stop_reason=stop_reason or "completed",
            steps=self._inner.steps,
            sim_time=self._inner.clock,
            wall_seconds=wall,
            metrics=self._inner.model.finalize_metrics(),
            snapshot=self._inner.snapshot().to_json(),
        )
        return result

    def checkpoint(self) -> Checkpoint:
        return self._inner.checkpoint()

    def restore(self, cp: Checkpoint) -> None:
        self._inner.restore(cp)

    def snapshot(self) -> StateSnapshot:
        return self._inner.snapshot()

    @property
    def event_log(self) -> list:
        return self._inner.model.event_log
