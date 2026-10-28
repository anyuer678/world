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
