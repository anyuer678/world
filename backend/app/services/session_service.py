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
        # True while a stop was requested but the worker thread has not yet
        # left its in-flight chunk: the engine is still owned by that thread, so
        # step/reset/checkpoint must not touch it (R39 race fix).
        self.stopping = False
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
        # 空闲回收时限取自配置（R39）：以前硬编码 3600 秒，既不可调也无文档，
        # 用户离开一小时后回来只会拿到一个没有解释的 404。
        self._ttl_seconds = float(settings.session_ttl_seconds)
        # How long stop/pause/reset waits for the worker to leave its chunk.
        self._join_timeout = 5.0

    # ------------------------------------------------------------- lifecycle
    def session_limits(self) -> Limits:
        """会话引擎的资源上限一律取自 Settings。

        以前只传了 max_steps/max_wall_seconds，其余两项落进 `Limits` 的 dataclass
        默认值（256/10000），于是 `WORLDLAB_CANCEL_POLL_INTERVAL`、
        `WORLDLAB_ZERO_DELAY_CHAIN_LIMIT` 对交互会话静默无效——而 `GET /api/limits`
        报的却是 Settings 里的值（ advertise 与行为不一致，R37）。"""
        return Limits(
            max_steps=self._settings.default_max_steps,
            max_wall_seconds=self._settings.max_wall_seconds,
            zero_delay_chain_limit=self._settings.zero_delay_chain_limit,
            cancel_poll_interval=self._settings.cancel_poll_interval,
        )

    def create(self, spec_raw: dict[str, Any]) -> dict[str, Any]:
        spec, model_cls = validate_spec(spec_raw, self._registry)
        model = model_cls(spec.params, spec.seed)
        engine = SimulationEngine(
            model,
            spec.stop_condition.model_dump(),
            limits=self.session_limits(),
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
            self._stop_thread(s, cancel=True)
        with self._global_lock:
            self._sessions.pop(session_id, None)

    def shutdown(self) -> None:
        with self._global_lock:
            sessions = list(self._sessions.values())
        for s in sessions:
            with s.lock:
                self._stop_thread(s, cancel=True)

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if now - s.last_access > self._ttl_seconds]
        for sid in expired:
            s = self._sessions.pop(sid, None)
            if s is not None:
                with s.lock:
                    self._stop_thread(s, cancel=True)

    # ------------------------------------------------------------- stepping
    def step(self, session_id: str, n: int = 1) -> dict[str, Any]:
        s = self._get(session_id)
        with s.lock:
            if s.status == "running":
                raise ConflictError("session is running; pause it before stepping")
            if s.stopping:
                raise ConflictError("session is stopping; wait for the running chunk to finish")
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
            # `stopping` is cleared only by the exiting worker's finally block, so a
            # live flag means the old thread still owns the engine: starting a second
            # one would put two threads on the same engine object.
            if s.stopping:
                raise ConflictError("session is stopping; wait for the running chunk to finish")
            if s.status in ("completed", "cancelled"):
                raise ConflictError(f"session already finished ({s.status}); reset to run again")
            if s.status == "error":
                raise ConflictError("session is in error state; reset before running")
            s.pause_event.clear()
            s.cancel_event.clear()
            s.error = None
            s.status = "running"
            s.last_state = self._build_state(s)
            s.thread = threading.Thread(target=self._run_loop_guarded, args=(s,), daemon=True)
            s.thread.start()
        return self.state(session_id)

    def _run_loop(self, s: _Session) -> None:
        t0 = time.monotonic()
        last_push = 0.0
        while True:
            if s.cancel_event.is_set():
                self._finish_run(s, "cancelled")
                return
            if s.pause_event.is_set():
                self._finish_run(s, "paused")
                return
            # Continuous session runs are bounded by the wall clock, not the
            # engine's absolute step cap (that one guards unbounded run()
            # calls and manual step batches).
            if time.monotonic() - t0 > self._settings.max_wall_seconds:
                self._finish_run(s, "wall_timeout", reason="wall_timeout")
                return
            with s.lock:
                if s.status != "running":
                    self._finish_run(s, s.status)
                    return
            # Chunk runs WITHOUT the session lock so state() polls can always
            # acquire it; the engine is only touched by this thread while running.
            try:
                result = s.engine.run(max_steps=self.CHUNK_STEPS)
            except Exception as exc:  # noqa: BLE001
                with s.lock:
                    s.status = "error"
                    s.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                    s.stopping = False
                    s.thread = None
                return
            reason = result.status
            with s.lock:
                if reason in ("completed", "wall_timeout", "cancelled"):
                    self._finish_run(s, reason, reason=reason)
                    return
                now = time.monotonic()
                if now - last_push >= 0.1:
                    s.last_state = self._build_state(s)
                    last_push = now

    def _finish_run(self, s: _Session, status: str, reason: str | None = None) -> None:
        """Worker 交出引擎所有权：状态落定与 `stopping` 清零必须在同一次加锁里。

        分两次写会留一个窗口——status 已是 paused、stopping 还挂着，期间一次
        「单步」会吃到本可避免的 409。调用方都已持有或即将获取 s.lock。"""
        with s.lock:
            s.status = status
            if reason is not None:
                s.stop_reason = reason
            s.stopping = False
            s.thread = None

    def pause(self, session_id: str) -> dict[str, Any]:
        s = self._get(session_id)
        exited = self._stop_thread(s)
        with s.lock:
            if not exited:
                # 线程还在分片里跑：engine 归它所有。这里不改 status、不碰 engine，
                # 只留 stopping 标记；线程自己收尾时把状态写成 paused/cancelled。
                if s.status == "running":
                    s.stopping = True
                return self.state(session_id)
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
        if not self._stop_thread(s):
            raise ConflictError("session is still stopping; retry in a moment")
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
            if s.stopping:
                raise ConflictError("session is stopping; wait for the running chunk to finish")
            return {"session_id": s.id, "checkpoint": s.engine.checkpoint()}

    def restore(self, session_id: str, checkpoint: dict[str, Any]) -> dict[str, Any]:
        s = self._get(session_id)
        # Join BEFORE the lock, like reset(): until the worker leaves its chunk the
        # engine belongs to that thread, and restoring underneath it corrupts both
        # the in-flight run and the checkpoint being applied.
        if not self._stop_thread(s):
            raise ConflictError("session is still stopping; retry in a moment")
        with s.lock:
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

    def _stop_thread(self, s: _Session, *, cancel: bool = False) -> bool:
        """请求线程离开当前分片；返回线程是否真的退出。

        `cancel=False`（pause/reset/restore）只置 pause 标志：worker 会在分片边界
        落 `paused`，会话仍可「继续」。`cancel=True`（delete/purge/shutdown 这类
        丢弃路径）落 `cancelled` 终态。

        R39 前这里无条件同时置两个标志，而 `_run_loop` 先查 cancel——于是工作台上的
        「⏸ 暂停」实为「取消并终结会话」：前端继续按钮只在 status=paused 时点亮，
        用户按暂停后既不能继续也不能单步，只能重置丢掉进度。

        未退出时置 `s.stopping`：engine 此刻仍归那个线程所有，任何路径并发去碰
        它都是数据竞争（分片期间不加 s.lock，正是为了让轮询能进）。"""
        s.pause_event.set()
        if cancel:
            s.cancel_event.set()
        thread = s.thread
        exited = True
        if thread is not None and thread.is_alive():
            thread.join(timeout=self._join_timeout)
            exited = not thread.is_alive()
        if exited:
            s.thread = None
        else:
            with s.lock:
                s.stopping = True
        return exited

    def _run_loop_guarded(self, s: _Session) -> None:
        try:
            self._run_loop(s)
        finally:
            with s.lock:
                s.stopping = False
