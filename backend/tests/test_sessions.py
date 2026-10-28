"""Interactive session API tests: step, run/pause/resume, reset, checkpoint."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def _spec(**overrides):
    spec = {
        "schema_version": 1,
        "model_id": "toy_des",
        "params": {"total_events": 5000, "delay_mean": 0.01},
        "stop_condition": {"type": "steps", "value": 5000},
        "seed": 7,
    }
    spec.update(overrides)
    return spec


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def _create(client, spec=None):
    r = client.post("/api/sessions", json={"spec": spec or _spec()})
    assert r.status_code == 201, r.text
    return r.json()


def _wait_status(client, sid, statuses, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = client.get(f"/api/sessions/{sid}").json()["status"]
        if st in statuses:
            return st
        time.sleep(0.02)
    raise AssertionError(f"session did not reach {statuses}; last={st}")


def test_session_create_and_step(client):
    body = _create(client)
    sid = body["session_id"]
    assert body["status"] == "idle"
    assert body["snapshot"]["step"] == 0
    assert body["model_id"] == "toy_des"

    r = client.post(f"/api/sessions/{sid}/step", json={"n": 5})
    assert r.status_code == 200
    st = r.json()
    assert st["snapshot"]["step"] == 5
    assert st["snapshot"]["state"]["count"] == 5
    assert st["snapshot"]["metrics"]["count"] == 5.0
    assert len(st["events"]) > 0
    assert st["status"] == "paused"


def test_session_run_to_completion(client):
    sid = _create(client)["session_id"]
    r = client.post(f"/api/sessions/{sid}/run")
    assert r.status_code == 200
    status = _wait_status(client, sid, {"completed"}, timeout=15)
    assert status == "completed"
    final = client.get(f"/api/sessions/{sid}").json()
    assert final["snapshot"]["step"] == 5000
    assert final["stop_reason"] == "completed"


def test_session_run_polls_show_progress(client):
    """Regression: while a continuous run is in flight, state() polls must see
    increasing steps (worker refreshes the cached state between chunks)."""
    spec = _spec(
        params={"total_events": 5000000, "delay_mean": 0.0001},
        stop_condition={"type": "steps", "value": 5000000},
    )
    sid = _create(client, spec)["session_id"]
    assert client.post(f"/api/sessions/{sid}/run").status_code == 200
    # Consecutive polls can land inside one 0.1s cache-refresh window and read
    # the same cached step; only distinct steps count as observations.
    seen = []
    deadline = time.time() + 5
    while time.time() < deadline and len(seen) < 3:
        st = client.get(f"/api/sessions/{sid}").json()
        if st["status"] == "running":
            step = st["snapshot"]["step"]
            if not seen or step != seen[-1]:
                seen.append(step)
        time.sleep(0.05)
    client.post(f"/api/sessions/{sid}/pause")
    assert len(seen) >= 3, f"only {len(seen)} running polls: {seen}"
    assert all(b > a for a, b in zip(seen, seen[1:])), seen


def test_session_pause_and_resume(client):
    spec = _spec(params={"total_events": 60000, "delay_mean": 0.001}, stop_condition={"type": "steps", "value": 60000})
    sid = _create(client, spec)["session_id"]
    client.post(f"/api/sessions/{sid}/run")
    _wait_status(client, sid, {"running", "paused", "completed"}, timeout=5)
    client.post(f"/api/sessions/{sid}/pause")
    status = _wait_status(client, sid, {"paused", "completed"}, timeout=5)
    steps_at_pause = client.get(f"/api/sessions/{sid}").json()["snapshot"]["step"]
    if status == "paused":
        assert client.post(f"/api/sessions/{sid}/resume").status_code == 200
    status = _wait_status(client, sid, {"completed", "step_limit"}, timeout=30)
    final_steps = client.get(f"/api/sessions/{sid}").json()["snapshot"]["step"]
    assert final_steps >= steps_at_pause
    assert final_steps > 0


def test_session_checkpoint_restore_equivalence(client):
    sid_a = _create(client)["session_id"]
    client.post(f"/api/sessions/{sid_a}/step", json={"n": 50})
    cp = client.post(f"/api/sessions/{sid_a}/checkpoint").json()["checkpoint"]
    client.post(f"/api/sessions/{sid_a}/step", json={"n": 50})
    metrics_a = client.get(f"/api/sessions/{sid_a}").json()["snapshot"]["metrics"]

    sid_b = _create(client)["session_id"]
    client.post(f"/api/sessions/{sid_b}/step", json={"n": 50})
    r = client.post(f"/api/sessions/{sid_b}/restore", json={"checkpoint": cp})
    assert r.status_code == 200
    assert r.json()["snapshot"]["step"] == 50
    client.post(f"/api/sessions/{sid_b}/step", json={"n": 50})
    metrics_b = client.get(f"/api/sessions/{sid_b}").json()["snapshot"]["metrics"]
    assert metrics_a == metrics_b


def test_session_reset(client):
    sid = _create(client)["session_id"]
    client.post(f"/api/sessions/{sid}/step", json={"n": 10})
    r = client.post(f"/api/sessions/{sid}/reset")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "idle"
    assert body["snapshot"]["step"] == 0
    r = client.post(f"/api/sessions/{sid}/step", json={"n": 1})
    assert r.json()["snapshot"]["step"] == 1


def test_session_reset_while_running(client):
    # R13 regression: reset used to join the run thread while holding the
    # session lock; the thread's exit write ("cancelled") then landed after
    # reset's "idle", leaving the session stuck (run/step 409, reset twice
    # needed). toy_slow_step chunks (~0.5 ms/step) guarantee the thread is
    # mid-chunk when reset arrives.
    spec = _spec(
        model_id="toy_slow_step",
        params={},
        stop_condition={"type": "steps", "value": 200_000},
    )
    sid = _create(client, spec)["session_id"]
    client.post(f"/api/sessions/{sid}/run")
    _wait_status(client, sid, ["running"])
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if client.get(f"/api/sessions/{sid}").json()["snapshot"]["step"] >= 100:
            break
        time.sleep(0.02)
    r = client.post(f"/api/sessions/{sid}/reset")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "idle", body["status"]
    assert body["snapshot"]["step"] == 0
    r = client.post(f"/api/sessions/{sid}/run")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "running"
    client.delete(f"/api/sessions/{sid}")


def test_session_step_after_completion_conflict(client):
    spec = _spec(stop_condition={"type": "steps", "value": 5})
    sid = _create(client, spec)["session_id"]
    client.post(f"/api/sessions/{sid}/step", json={"n": 10})
    st = client.get(f"/api/sessions/{sid}").json()
    assert st["status"] == "completed"
    r = client.post(f"/api/sessions/{sid}/step", json={"n": 1})
    assert r.status_code == 409


def test_session_unknown_404(client):
    assert client.get("/api/sessions/nope").status_code == 404
    assert client.post("/api/sessions/nope/step", json={"n": 1}).status_code == 404
    assert client.delete("/api/sessions/nope").status_code == 404


def test_session_invalid_spec_422(client):
    bad = _spec(params={"total_events": 100, "bogus_key": 1})
    r = client.post("/api/sessions", json={"spec": bad})
    assert r.status_code == 422


def test_session_restore_wrong_model_409(client):
    sid = _create(client)["session_id"]
    client.post(f"/api/sessions/{sid}/step", json={"n": 5})
    cp = client.post(f"/api/sessions/{sid}/checkpoint").json()["checkpoint"]
    cp["model_id"] = "toy_step"
    r = client.post(f"/api/sessions/{sid}/restore", json={"checkpoint": cp})
    assert r.status_code == 409


def test_session_time_stepped_model(client):
    spec = {
        "schema_version": 1,
        "model_id": "toy_step",
        "params": {},
        "stop_condition": {"type": "steps", "value": 100},
        "seed": 3,
    }
    sid = _create(client, spec)["session_id"]
    r = client.post(f"/api/sessions/{sid}/step", json={"n": 4})
    body = r.json()
    assert body["snapshot"]["step"] == 4
    assert body["model_type"] == "time_stepped"
    assert body["snapshot"]["state"]["value"] > 0


def test_session_list_and_delete(client):
    sid = _create(client)["session_id"]
    listed = client.get("/api/sessions").json()["sessions"]
    assert any(s["session_id"] == sid for s in listed)
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get(f"/api/sessions/{sid}").status_code == 404
