"""R1 integrity regressions: recorded-seed provenance, aggregate
qualification, grid-cap ordering, per-batch concurrency bound, and
checkpoint compatibility binding."""
from __future__ import annotations

import json
import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.core.engine.base import SimulationError
from app.core.engine.engines import Limits, SimulationEngine
from app.core.engine.models_base import DiscreteEventModel, WorldLabParams
from app.core.schema.errors import SpecValidationError
from app.main import create_app
from app.services.batch_service import BatchService
from conftest import ToyDesModel, registry


class ProbeSlowParams(WorldLabParams):
    total_events: int = 100
    delay_mean: float = 1.0


class ProbeSlowModel(DiscreteEventModel):
    model_id = "toy_probe_slow"
    display_name = "Probe slow DES"
    description = "Slow toy DES for concurrency probing; sleeps per event."
    model_type = "discrete_event"
    version = "1.0.0"
    param_model = ProbeSlowParams

    def initialize(self, ctx) -> None:
        self.count = 0
        ctx.schedule(1.0, "tick")

    def handle_event(self, event, ctx) -> None:
        self.count += 1
        time.sleep(0.0005)
        if self.count < self.params.total_events:
            ctx.schedule(self.rng.expovariate(1.0 / self.params.delay_mean), "tick")

    def dump_state(self):
        return {"count": self.count}

    def load_state(self, state):
        self.count = state["count"]

    def snapshot(self):
        return {"count": self.count}

    def finalize_metrics(self):
        return {"count": float(self.count)}


registry.register(ProbeSlowModel)


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def batches(settings):
    b = BatchService(settings, registry)
    yield b
    b.shutdown()


def _toy_spec(**overrides):
    spec = {
        "schema_version": 1,
        "model_id": "toy_des",
        "params": {"total_events": 50, "delay_mean": 1.0},
        "stop_condition": {"type": "until_empty"},
        "seed": None,
    }
    spec.update(overrides)
    return spec


def _wait_terminal(svc, batch_id, timeout=20):
    deadline = time.time() + timeout
    b = None
    while time.time() < deadline:
        b = svc.get_batch(batch_id, include_summary=False)
        if b["status"] in ("completed", "failed", "cancelled"):
            return b
        time.sleep(0.05)
    raise AssertionError(f"batch {batch_id} did not finish in {timeout}s: {b and b['status']}")


# ------------------------------------------------------------ seed provenance
def test_recorded_seed_reproduces_run(client):
    r = client.post("/api/experiments", json={"name": "seed-a", "spec": _toy_spec()})
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    assert client.post(f"/api/experiments/{eid}/run", json={"wait": True}).status_code == 200
    run = client.get(f"/api/experiments/{eid}/result").json()["runs"][0]
    assert run["status"] == "completed"
    assert run["seed"] is not None

    replay = _toy_spec(seed=run["seed"])
    r2 = client.post("/api/experiments", json={"name": "seed-b", "spec": replay})
    eid2 = r2.json()["id"]
    client.post(f"/api/experiments/{eid2}/run", json={"wait": True})
    run2 = client.get(f"/api/experiments/{eid2}/result").json()["runs"][0]
    assert run2["seed"] == run["seed"]
    assert run2["metrics"] == run["metrics"]
    assert run2["result_sha256"] == run["result_sha256"]


# ------------------------------------------------------ aggregate qualification
def test_aggregate_excludes_truncated_runs(client, settings):
    r = client.post(
        "/api/experiments", json={"name": "agg", "spec": _toy_spec(seed=42)}
    )
    eid = r.json()["id"]
    client.post(f"/api/experiments/{eid}/run", json={"wait": True})
    run = client.get(f"/api/experiments/{eid}/result").json()["runs"][0]
    assert run["status"] == "completed"

    conn = sqlite3.connect(settings.db_path)
    try:
        conn.execute(
            "INSERT INTO experiment_runs(experiment_id, repeat_index, seed, status,"
            " steps, sim_time, metrics_json, result_sha256, finished_at)"
            " VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
            (eid, 1, 99, "step_limit", 1000, 1000.0,
             json.dumps({"count": 1000000.0, "total_time": 999.0}), "x" * 64),
        )
        conn.commit()
    finally:
        conn.close()

    result = client.get(f"/api/experiments/{eid}/result").json()
    assert len(result["runs"]) == 2
    assert result["runs"][1]["status"] == "step_limit"
    agg = result["aggregate"]
    assert agg is not None
    assert agg["count"] == run["metrics"]["count"]


# ------------------------------------------------------------- grid cap order
def test_grid_cap_rejected_before_expansion(batches):
    spec = {
        "schema_version": 1,
        "model_id": "queueing",
        "params": {"servers": 1},
        "stop_condition": {"type": "until_empty"},
        "seed": 1,
    }
    grid = {
        "servers": list(range(1000)),
        "capacity": list(range(1000)),
        "warmup_customers": list(range(1000)),
        "discipline": ["fifo", "lcfs"] * 500,
    }
    with pytest.raises(SpecValidationError) as ei:
        batches.create("cap", spec, grid, repeats=1)
    assert "exceeds cap" in str(ei.value)


# -------------------------------------------------------- concurrency bounding
class _TrackingExecutor:
    """Counts outstanding batch-item futures without mocking sim logic."""

    def __init__(self, inner):
        self._inner = inner
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def submit(self, fn, *args, **kwargs):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        fut = self._inner.submit(fn, *args, **kwargs)
        fut.add_done_callback(lambda _f: self._release())
        return fut

    def _release(self):
        with self._lock:
            self.active -= 1

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_batch_concurrency_bounded_per_batch(batches):
    slow_spec = {
        "schema_version": 1,
        "model_id": "toy_probe_slow",
        "params": {"total_events": 100, "delay_mean": 1.0},
        "stop_condition": {"type": "until_empty"},
        "seed": 7,
    }
    tracker = _TrackingExecutor(batches._executor)
    batches._executor = tracker

    b1 = batches.create("conc-1", slow_spec, {}, repeats=4, concurrency=1)
    assert _wait_terminal(batches, b1["id"])["status"] == "completed"
    assert tracker.max_active == 1

    # toy_slow_des items run >=50ms each, so the second in-flight submit lands
    # while the first is still running: max_active==2 is deterministic here.
    b2 = batches.create("conc-2", slow_spec, {}, repeats=4, concurrency=2)
    assert _wait_terminal(batches, b2["id"])["status"] == "completed"
    assert tracker.max_active == 2


# ---------------------------------------------------- checkpoint compatibility
def _engine(params: dict) -> SimulationEngine:
    return SimulationEngine(
        ToyDesModel(params, 42),
        {"type": "until_empty"},
        limits=Limits(max_steps=1000, max_wall_seconds=10),
        cancel_check=None,
    )


def test_checkpoint_binds_version_and_params():
    eng = _engine({"total_events": 10, "delay_mean": 1.0})
    eng.run(max_steps=5)
    cp = eng.checkpoint()
    assert cp["model_version"] == ToyDesModel.version

    same = _engine({"total_events": 10, "delay_mean": 1.0})
    same.restore(cp)

    diff = _engine({"total_events": 11, "delay_mean": 1.0})
    with pytest.raises(SimulationError):
        diff.restore(cp)

    class RenamedToy(ToyDesModel):
        version = "9.9.9"

    other = SimulationEngine(
        RenamedToy({"total_events": 10, "delay_mean": 1.0}, 42),
        {"type": "until_empty"},
        limits=Limits(max_steps=1000, max_wall_seconds=10),
        cancel_check=None,
    )
    with pytest.raises(SimulationError):
        other.restore(cp)


def test_soak_runs_and_sessions_leave_no_in_process_residue(settings):
    """R67：连续 run/会话循环后，进程内注册表与行数都不能泄漏。

    `_futures`/`_cancel_flags` 由 worker 的 finally 清理，`_sessions` 由 delete/TTL 清理；
    这里用真实服务跑 40 轮（run 等完成）+ 20 次会话建删，逐一断言为空/精确。"""
    import sqlite3

    from app.core.registry import registry
    from app.services.experiment_service import ExperimentService
    from app.services.session_service import SessionService

    exp_svc = ExperimentService(settings, registry)
    ses_svc = SessionService(settings, registry)
    spec = {
        "schema_version": 1,
        "model_id": "sir",
        "params": {},
        "stop_condition": {"type": "steps", "value": 5},
        "seed": 1,
    }
    try:
        exp = exp_svc.create_experiment("r67-soak", spec)
        for _ in range(40):
            body = exp_svc.run_experiment(exp["id"], wait=True)
            assert body["status"] == "queued"

        assert exp_svc._futures == {}, f"futures 泄漏：{len(exp_svc._futures)}"
        assert exp_svc._cancel_flags == {}, f"cancel flags 泄漏：{len(exp_svc._cancel_flags)}"

        conn = sqlite3.connect(settings.db_path)
        try:
            runs = conn.execute(
                "SELECT COUNT(*) FROM experiment_runs WHERE experiment_id=?", (exp["id"],)
            ).fetchone()[0]
        finally:
            conn.close()
        assert runs == 40, runs

        for _ in range(20):
            sid = ses_svc.create(spec)["session_id"]
            assert ses_svc.delete(sid) is None
        assert ses_svc._sessions == {}, f"会话泄漏：{len(ses_svc._sessions)}"
    finally:
        ses_svc.shutdown()
        exp_svc.shutdown()


def test_session_event_ring_honors_configured_size(settings):
    """R70：事件环必须按 `WORLDLAB_EVENT_LOG_SIZE` 截断，而不是硬编码 500。

    R67 的原版用 500 的默认值做上界断言，硬编码 500 也能通过——属于空断言。
    这里用 37 构造服务，既证「配置生效」也证「有界」。"""
    from dataclasses import replace

    from app.core.registry import registry
    from app.services.session_service import SessionService

    ses_svc = SessionService(replace(settings, event_log_size=37), registry)
    try:
        spec = {
            "schema_version": 1,
            "model_id": "queueing",
            "params": {},
            "stop_condition": {"type": "steps", "value": 5000},
            "seed": 1,
        }
        sid = ses_svc.create(spec)["session_id"]
        ses_svc.step(sid, 3000)
        st = ses_svc.state(sid, events_limit=500)
        assert len(st["events"]) == 37, len(st["events"])
    finally:
        ses_svc.shutdown()


def test_session_thread_churn_leaves_no_live_worker(settings):
    """R68：会话建/跑/删循环后，每个会话的 worker 线程都必须已退出。

    不依赖全局 `threading.active_count()`（其它测试的后台线程会干扰），而是保留
    `_Session` 引用逐个检查：删除后线程要么已被清空，要么不再存活。"""
    import time

    from app.core.registry import registry
    from app.services.session_service import SessionService

    svc = SessionService(settings, registry)
    try:
        spec = {
            "schema_version": 1,
            "model_id": "sir",
            "params": {},
            "stop_condition": {"type": "steps", "value": 50},
            "seed": 1,
        }
        sessions = []
        for _ in range(20):
            sid = svc.create(spec)["session_id"]
            sessions.append(svc._sessions[sid])  # noqa: SLF001 - 断言对象生命周期
            svc.run(sid)
            time.sleep(0.01)
            svc.delete(sid)
        deadline = time.time() + 10
        while time.time() < deadline and any(
            s.thread is not None and s.thread.is_alive() for s in sessions
        ):
            time.sleep(0.02)
        alive = [s.id for s in sessions if s.thread is not None and s.thread.is_alive()]
        assert not alive, f"会话 worker 线程未退出：{alive[:3]}"
        assert svc._sessions == {}, f"会话泄漏：{len(svc._sessions)}"
    finally:
        svc.shutdown()

