"""Interactive simulation sessions for the workbench.

A session wraps one SimulationEngine instance in memory so the UI can
step / run / pause / reset / checkpoint it. Continuous runs execute in a
worker thread in bounded slices (run(chunk)) so pause takes effect quickly
and state polling never blocks behind an unbounded run.
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from typing import Any

from ..config import Settings
from ..core.engine.engines import Limits, SimulationEngine
from ..core.registry import ModelRegistry
from ..core.schema.spec import SpecValidationError, validate_spec
from .experiment_service import ConflictError, NotFoundError


class _Session:
    def __init__(self, session_id: str, spec: dict[str, Any], engine: SimulationEngine):
        self.id = session_id
        self.spec = spec
        self.engine = engine
        self.lock = threading.RLock()
        # Fresh state dict pushed by the worker between chunks; state() serves
        # this while status == "running" so polling never touches the engine
        # mid-chunk and never starves behind the worker's lock handoffs.
        self.last_state: dict[str, Any] | None = None
        self.pause_event = threading.Event()
        self.cancel_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.status = "idle"  # idle | running | paused | completed | cancelled | error
        self.stop_reason: str | None = None
        self.error: str | None = None
        self.created_at = time.time()
        self.last_access = self.created_at

    def meta(self) -> dict[str, Any]:
        return {
            "session_id": self.id,
            "status": self.status,
            "model_id": self.engine.model.model_id,
            "model_version": self.engine.model.version,
            "step": self.engine.steps,
            "clock": self.engine.clock,
            "created_at": self.created_at,
        }


class SessionService:
    CHUNK_STEPS = 256

    def __init__(self, settings: Settings, registry: ModelRegistry):
        self._settings = settings
        self._registry = registry
        self._sessions: dict[str, _Session] = {}
        self._global_lock = threading.Lock()
        self._ttl_seconds = 3600.0

    # ------------------------------------------------------------- lifecycle
    def create(self, spec_raw: dict[str, Any]) -> dict[str, Any]:
        spec, model_cls = validate_spec(spec_raw, self._registry)
        model = model_cls(spec.params, spec.seed)
        engine = SimulationEngine(
            model,
            spec.stop_condition.model_dump(),
            limits=Limits(
                max_steps=self._settings.default_max_steps,
                max_wall_seconds=self._settings.max_wall_seconds,
            ),
        )
        session = _Session(uuid.uuid4().hex, spec.model_dump(), engine)
        session.status = "idle"
        with self._global_lock:
            self._purge_expired()
            self._sessions[session.id] = session
        return self.state(session.id)

    def _get(self, session_id: str) -> _Session:
        with self._global_lock:
            s = self._sessions.get(session_id)
        if s is None:
            raise NotFoundError(f"session {session_id!r} not found")
        s.last_access = time.time()
        return s

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._global_lock:
            self._purge_expired()
            sessions = list(self._sessions.values())
        return sorted((s.meta() for s in sessions), key=lambda m: m["created_at"])

    def delete(self, session_id: str) -> None:
        s = self._get(session_id)
        with s.lock:
            self._stop_thread(s)
        with self._global_lock:
            self._sessions.pop(session_id, None)

    def shutdown(self) -> None:
        with self._global_lock:
            sessions = list(self._sessions.values())
        for s in sessions:
            with s.lock:
                self._stop_thread(s)

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if now - s.last_access > self._ttl_seconds]
        for sid in expired:
            s = self._sessions.pop(sid, None)
            if s is not None:
                with s.lock:
                    self._stop_thread(s)

    # ------------------------------------------------------------- stepping
    def step(self, session_id: str, n: int = 1) -> dict[str, Any]:
        s = self._get(session_id)
        with s.lock:
            if s.status == "running":
                raise ConflictError("session is running; pause it before stepping")
            if s.status in ("completed", "cancelled"):
                raise ConflictError(f"session already finished ({s.status})")
            if s.status == "error":
                raise ConflictError("session is in error state; reset before stepping")
            if n < 1 or n > 1_000_000:
                raise SpecValidationError.single("n", "n must be between 1 and 1000000")
            s.pause_event.clear()
            s.cancel_event.clear()
            s.error = None
            try:
                advanced = False
                for _ in range(n):
                    if not s.engine.step():
                        s.status = "completed"
                        s.stop_reason = "completed"
                        break
                    advanced = True
                else:
                    reason = self._check_stop(s)
                    if reason is None:
                        s.status = "paused"
                    else:
                        s.status = "completed" if reason == "completed" else reason
                        s.stop_reason = reason
                if not advanced and s.status not in ("completed", "cancelled"):
                    reason = self._check_stop(s)
                    if reason is not None:
                        s.status = "completed" if reason == "completed" else reason
                        s.stop_reason = reason
            except Exception as exc:  # noqa: BLE001 - surface model errors to the UI
                s.status = "error"
                s.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            return self.state(session_id)

    def run(self, session_id: str) -> dict[str, Any]:
        s = self._get(session_id)
        with s.lock:
            if s.status == "running":
                raise ConflictError("session is already running")
            if s.status in ("completed", "cancelled"):
                raise ConflictError(f"session already finished ({s.status}); reset to run again")
            if s.status == "error":
                raise ConflictError("session is in error state; reset before running")
            s.pause_event.clear()
            s.cancel_event.clear()
            s.error = None
            s.status = "running"
            s.last_state = self._build_state(s)
            s.thread = threading.Thread(target=self._run_loop, args=(s,), daemon=True)
            s.thread.start()
        return self.state(session_id)

    def _run_loop(self, s: _Session) -> None:
        t0 = time.monotonic()
        last_push = 0.0
        while True:
            if s.cancel_event.is_set():
                with s.lock:
                    s.status = "cancelled"
                return
            if s.pause_event.is_set():
                with s.lock:
                    s.status = "paused"
                return
            # Continuous session runs are bounded by the wall clock, not the
            # engine's absolute step cap (that one guards unbounded run()
            # calls and manual step batches).
            if time.monotonic() - t0 > self._settings.max_wall_seconds:
                with s.lock:
                    s.status = "wall_timeout"
                    s.stop_reason = "wall_timeout"
                return
            with s.lock:
                if s.status != "running":
                    return
            # Chunk runs WITHOUT the session lock so state() polls can always
            # acquire it; the engine is only touched by this thread while running.
            try:
                result = s.engine.run(max_steps=self.CHUNK_STEPS)
            except Exception as exc:  # noqa: BLE001
                with s.lock:
                    s.status = "error"
                    s.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                return
            reason = result.status
            with s.lock:
                if reason in ("completed", "wall_timeout", "cancelled"):
                    s.status = reason
                    s.stop_reason = reason
                    return
                now = time.monotonic()
                if now - last_push >= 0.1:
                    s.last_state = self._build_state(s)
                    last_push = now

    def pause(self, session_id: str) -> dict[str, Any]:
        s = self._get(session_id)
        s.pause_event.set()
        thread = s.thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        with s.lock:
            if s.status == "running":
                s.status = "paused"
            elif s.status in ("completed", "step_limit", "wall_timeout", "cancelled", "error", "paused"):
                pass
        return self.state(session_id)

    def resume(self, session_id: str) -> dict[str, Any]:
        return self.run(session_id)

    def reset(self, session_id: str) -> dict[str, Any]:
        s = self._get(session_id)
        # Join the run thread BEFORE taking the lock: the thread's exit path
        # writes s.status under s.lock, so holding the lock during join would
        # deadlock until the join timeout and let the thread's "cancelled"
        # write land after reset's "idle" (the stuck state seen in R13).
        self._stop_thread(s)
        with s.lock:
            s.engine.reset()
            s.status = "idle"
            s.stop_reason = None
            s.error = None
        return self.state(session_id)

    # ----------------------------------------------------------- checkpoint
    def checkpoint(self, session_id: str) -> dict[str, Any]:
        s = self._get(session_id)
        with s.lock:
            if s.status == "running":
                raise ConflictError("pause the session before checkpointing")
            return {"session_id": s.id, "checkpoint": s.engine.checkpoint()}

    def restore(self, session_id: str, checkpoint: dict[str, Any]) -> dict[str, Any]:
        s = self._get(session_id)
        with s.lock:
            self._stop_thread(s)
            try:
                s.engine.restore(checkpoint)
            except Exception as exc:  # noqa: BLE001 - restore failure keeps session usable
                raise ConflictError(f"checkpoint restore failed: {exc}") from exc
            s.status = "paused"
            s.stop_reason = None
            s.error = None
        return self.state(session_id)

    # ----------------------------------------------------------------- state
    def state(self, session_id: str, events_limit: int = 50) -> dict[str, Any]:
        s = self._get(session_id)
        with s.lock:
            if s.status == "running" and s.last_state is not None:
                return s.last_state
            return self._build_state(s, events_limit)

    def _build_state(self, s: _Session, events_limit: int = 50) -> dict[str, Any]:
        engine = s.engine
        snap = engine.snapshot()
        events = engine.event_log[-events_limit:]
        status = s.status
        if status == "running":
            display_status = "running"
        else:
            display_status = status
        return {
            "session_id": s.id,
            "status": display_status,
            "stop_reason": s.stop_reason,
            "error": s.error,
            "model_id": engine.model.model_id,
            "model_version": engine.model.version,
            "model_type": engine.model.model_type,
            "visualizer": engine.model.visualizer,
            "display_name": engine.model.display_name,
            "spec": s.spec,
            "snapshot": snap.to_json(),
            "events": [e.to_json() for e in events],
            "chunk_steps": self.CHUNK_STEPS,
        }

    # ---------------------------------------------------------------- helpers
    def _check_stop(self, s: _Session) -> str | None:
        inner = s.engine._inner  # noqa: SLF001 - service owns the engine lifecycle
        return inner._stop_reason(time.monotonic())

    def _stop_thread(self, s: _Session) -> None:
        s.cancel_event.set()
        s.pause_event.set()
        thread = s.thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        s.thread = None
