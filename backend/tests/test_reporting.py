import csv
import io
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import APP_VERSION
from app.core.engine.base import ENGINE_VERSION
from app.main import create_app

QUEUE_SPEC = {
    "schema_version": 1,
    "model_id": "queueing",
    "params": {
        "arrival": {"kind": "poisson", "rate": 1.5},
        "service": {"kind": "exponential", "mean": 0.5},
        "servers": 1,
    },
    "stop_condition": {"type": "steps", "value": 1000},
    "seed": 42,
}


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def _run_experiment(client) -> int:
    r = client.post("/api/experiments", json={"name": "report-me", "spec": QUEUE_SPEC})
    assert r.status_code == 201
    exp_id = r.json()["id"]
    r = client.post(f"/api/experiments/{exp_id}/run", json={"wait": True})
    assert r.status_code == 200
    return exp_id


def test_report_json(client):
    exp_id = _run_experiment(client)
    r = client.get(f"/api/experiments/{exp_id}/report?format=json")
    assert r.status_code == 200
    body = r.json()
    assert body["report_version"] == 1
    assert body["software"]["app_version"] == APP_VERSION
    assert body["software"]["engine_version"] == ENGINE_VERSION
    assert body["software"]["python_version"]
    exp = body["experiment"]
    assert exp["id"] == exp_id
    assert exp["model_id"] == "queueing"
    assert exp["model_version"] == "1.0.0"
    assert exp["spec"]["seed"] == 42
    assert "runs" not in exp  # runs lifted to top level
    assert len(body["runs"]) == 1
    run = body["runs"][0]
    assert run["status"] == "completed"
    assert run["metrics"]
    assert len(run["result_sha256"]) == 64
    assert body["aggregate"]
    assert "model_version" in body["comparability_note"]


def test_report_markdown(client):
    exp_id = _run_experiment(client)
    r = client.get(f"/api/experiments/{exp_id}/report")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "attachment" in r.headers["content-disposition"]
    assert "worldlab-report-" in r.headers["content-disposition"]
    text = r.text
    assert "# WorldLab 实验报告" in text
    assert "queueing v1.0.0" in text
    assert f"WorldLab {APP_VERSION}" in text
    assert '"stop_condition"' in text  # spec embedded as JSON
    assert "| repeat | seed |" in text
    assert "result_sha256" in text
    assert "## 聚合指标" in text
    assert "model_version" in text  # comparability note rendered


def test_report_unknown_experiment(client):
    assert client.get("/api/experiments/99999/report").status_code == 404


def test_report_unrun_experiment(client):
    r = client.post("/api/experiments", json={"name": "empty", "spec": QUEUE_SPEC})
    exp_id = r.json()["id"]
    r = client.get(f"/api/experiments/{exp_id}/report?format=json")
    assert r.status_code == 200
    body = r.json()
    assert body["runs"] == []
    assert body["aggregate"] is None


def _wait_batch(client, batch_id: int) -> dict:
    for _ in range(200):
        b = client.get(f"/api/batches/{batch_id}").json()
        if b["status"] in ("completed", "failed", "cancelled"):
            return b
        time.sleep(0.05)
    raise AssertionError("batch did not reach terminal state")


def test_batch_csv_export(client):
    r = client.post(
        "/api/batches",
        json={
            "name": "csv-batch",
            "spec": QUEUE_SPEC,
            "grid": {"servers": [1, 2]},
            "repeats": 2,
            "seed_strategy": "unique",
        },
    )
    assert r.status_code == 201
    batch_id = r.json()["id"]
    b = _wait_batch(client, batch_id)
    assert b["status"] == "completed"

    r = client.get(f"/api/batches/{batch_id}/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert f"worldlab-batch-{batch_id}.csv" in r.headers["content-disposition"]

    assert r.text.startswith("\ufeff")  # BOM for Excel compatibility
    rows = list(csv.reader(io.StringIO(r.text.lstrip("\ufeff"))))
    assert rows[0] == ["# WorldLab 批量实验导出"]
    assert rows[3][0] == "item_index"
    header = rows[3]
    for col in ("seed", "status", "attempts", "result_sha256", "params", "metrics"):
        assert col in header
    data = rows[4:]
    assert len(data) == 4
    assert {row[header.index("status")] for row in data} == {"completed"}
    params = [json.loads(row[header.index("params")]) for row in data]
    assert {"servers": 1} in params and {"servers": 2} in params
    metrics = [json.loads(row[header.index("metrics")]) for row in data]
    assert all(m["arrived"] > 0 for m in metrics)
    shas = {row[header.index("result_sha256")] for row in data}
    assert all(len(s) == 64 for s in shas)
    seeds = {row[header.index("seed")] for row in data}
    assert len(seeds) == 4  # unique strategy → every item distinct seed


def test_batch_csv_unknown(client):
    assert client.get("/api/batches/99999/export.csv").status_code == 404
