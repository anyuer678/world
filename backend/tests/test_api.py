import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.experiment_service import canonical_metrics_json, metrics_sha256

QUEUE_SPEC = {
    "schema_version": 1,
    "model_id": "queueing",
    "params": {
        "arrival": {"kind": "poisson", "rate": 1.5},
        "service": {"kind": "exponential", "mean": 0.5},
        "servers": 1,
    },
    "stop_condition": {"type": "steps", "value": 3000},
    "seed": 42,
}


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_models_listed(client):
    r = client.get("/api/models")
    models = {m["model_id"]: m for m in r.json()["models"]}
    assert "queueing" in models
    q = models["queueing"]
    assert q["model_type"] == "discrete_event"
    assert "params_schema" in q and "example_spec" in q
    assert q["params_schema"]["properties"]["servers"]["minimum"] == 1


def test_model_detail_404(client):
    assert client.get("/api/models/nope").status_code == 404


def test_validate_endpoint(client):
    r = client.post("/api/models/queueing/validate", json={**QUEUE_SPEC, "params": {"servers": 0}})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert any("servers" in e["code"] for e in body["errors"])

    r = client.post("/api/models/queueing/validate", json=QUEUE_SPEC)
    assert r.json()["valid"] is True


def test_full_experiment_lifecycle(client):
    r = client.post("/api/experiments", json={"name": "mm1", "spec": QUEUE_SPEC})
    assert r.status_code == 201
    exp = r.json()
    assert exp["status"] == "created"
    assert exp["model_version"] == "1.0.0"
    exp_id = exp["id"]

    r = client.post(f"/api/experiments/{exp_id}/run", json={"wait": True})
    assert r.status_code == 200

    result = client.get(f"/api/experiments/{exp_id}/result").json()
    assert result["experiment"]["status"] == "completed"
    run = result["runs"][0]
    assert run["status"] == "completed"
    m = run["metrics"]
    assert m["arrived"] > 500
    assert 0.0 <= m["utilization"] <= 1.0
    assert run["result_sha256"] == hashlib.sha256(
        json.dumps(m, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    assert result["aggregate"] is not None

    run_detail = client.get(f"/api/runs/{run['id']}").json()
    assert run_detail["events"], "event log must come from the real run"
    kinds = {e["kind"] for e in run_detail["events"]}
    assert kinds <= {"arrival", "service_start", "departure", "drop"}


def test_invalid_spec_422(client):
    bad = {**QUEUE_SPEC, "params": {"servers": 0}}
    r = client.post("/api/experiments", json={"name": "bad", "spec": bad})
    assert r.status_code == 422
    errors = r.json()["detail"]["errors"]
    assert any("params.servers" in e["code"] for e in errors)


def test_unknown_model_422(client):
    r = client.post("/api/experiments", json={"name": "x", "spec": {"model_id": "ghost", "params": {}}})
    assert r.status_code == 422


def test_clone_and_override_params(client):
    exp = client.post("/api/experiments", json={"name": "base", "spec": QUEUE_SPEC}).json()
    clone = client.post(
        f"/api/experiments/{exp['id']}/clone",
        json={"name": "serving-2", "spec_overrides": {"params": {"servers": 3}}},
    ).json()
    assert clone["id"] != exp["id"]
    assert clone["spec"]["params"]["servers"] == 3
    assert clone["spec"]["params"]["arrival"] == QUEUE_SPEC["params"]["arrival"]
    assert clone["parent_experiment_id"] == exp["id"]


def test_tags_and_list_filter(client):
    exp = client.post("/api/experiments", json={"name": "tagged", "spec": QUEUE_SPEC}).json()
    client.put(f"/api/experiments/{exp['id']}/tags", json={"tags": ["mm1", "baseline", "mm1"]})
    got = client.get(f"/api/experiments/{exp['id']}").json()
    assert got["tags"] == ["baseline", "mm1"]
    listed = client.get("/api/experiments", params={"tag": "mm1"}).json()
    assert listed["total"] >= 1


def test_delete_experiment(client):
    exp = client.post("/api/experiments", json={"name": "tmp", "spec": QUEUE_SPEC}).json()
    assert client.delete(f"/api/experiments/{exp['id']}").status_code == 204
    assert client.get(f"/api/experiments/{exp['id']}").status_code == 404


def test_cancel_non_running_is_safe(client):
    exp = client.post("/api/experiments", json={"name": "c", "spec": QUEUE_SPEC}).json()
    r = client.post(f"/api/experiments/{exp['id']}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_rerun_produces_same_result(client):
    exp = client.post("/api/experiments", json={"name": "repro", "spec": QUEUE_SPEC}).json()
    client.post(f"/api/experiments/{exp['id']}/run", json={"wait": True})
    first = client.get(f"/api/experiments/{exp['id']}/result").json()["runs"][0]
    client.post(f"/api/experiments/{exp['id']}/rerun")
    # wait for completion by polling
    import time

    for _ in range(100):
        exp_now = client.get(f"/api/experiments/{exp['id']}").json()
        if exp_now["status"] != "running":
            break
        time.sleep(0.05)
    result = client.get(f"/api/experiments/{exp['id']}/result").json()
    seeds = {r["seed"] for r in result["runs"]}
    assert len(result["runs"]) == 2
    assert len(seeds) == 1  # rerun keeps the pinned seed
    by_sha = {}
    for r in result["runs"]:
        assert r["result_sha256"] not in by_sha or True
        by_sha.setdefault(r["result_sha256"], 0)
        by_sha[r["result_sha256"]] += 1
    assert len(by_sha) == 1  # identical seed => identical checksum
    assert first["seed"] == result["runs"][0]["seed"]


def test_v0_spec_accepted_and_migrated(client):
    r = client.post(
        "/api/experiments",
        json={"name": "legacy", "spec": {"model": "queueing", "params": {"servers": 1}, "horizon": 1000, "seed": 3}},
    )
    assert r.status_code == 201
    spec = r.json()["spec"]
    assert spec["schema_version"] == 1
    assert spec["stop_condition"] == {"type": "steps", "value": 1000}
