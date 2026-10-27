"""阶段 6：端到端测试 — 单一全生命周期 API 链路。

覆盖验收口径中的关键用户路径：健康检查 → 模型目录 → 规格校验 →
交互会话（单步/运行/重置/检查点/恢复/冲突映射）→ 实验保存与种子复现 →
报告导出 → 批量实验与 CSV 导出 → 清理。全部走 HTTP 层（TestClient），
不直接调用服务内部方法，保证测的是真实 API 契约。
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import app.models  # noqa: F401 - register built-ins
from app.core.registry import registry
from app.core.schema.spec import example_spec_for
from app.main import create_app

BUILTIN_MODELS = {"queueing", "cpu_scheduling", "cache_sim", "cellular_automaton"}


def _spec(model_id: str, steps: int, seed: int | None = 42) -> dict:
    spec = example_spec_for(registry.get(model_id))
    spec["stop_condition"] = {"type": "steps", "value": steps}
    if seed is not None:
        spec["seed"] = seed
    return spec


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def _poll_batch(client: TestClient, batch_id: int, deadline_s: float = 60.0) -> dict:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        r = client.get(f"/api/batches/{batch_id}")
        assert r.status_code == 200
        body = r.json()
        if body["status"] in ("completed", "failed", "cancelled"):
            return body
        time.sleep(0.2)
    raise AssertionError(f"batch {batch_id} did not finish within {deadline_s}s")


def _poll_session(client: TestClient, sid: str, deadline_s: float = 30.0) -> dict:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        r = client.get(f"/api/sessions/{sid}")
        assert r.status_code == 200
        body = r.json()
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError(f"session {sid} did not finish within {deadline_s}s")


def _poll_experiment(client: TestClient, exp_id: int, deadline_s: float = 30.0) -> dict:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        r = client.get(f"/api/experiments/{exp_id}")
        assert r.status_code == 200
        body = r.json()
        if body["status"] not in ("created", "queued", "running"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"experiment {exp_id} did not finish within {deadline_s}s")


def test_full_api_lifecycle(client):
    # 1. health
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["engine_version"]

    # 2. model catalog: four built-ins discoverable via API
    r = client.get("/api/models")
    assert r.status_code == 200
    ids = {m["model_id"] for m in r.json()["models"]}
    assert BUILTIN_MODELS <= ids

    # 3. spec validation endpoint: valid and invalid paths
    spec = _spec("queueing", 2000)
    r = client.post("/api/models/queueing/validate", json=spec)
    assert r.status_code == 200 and r.json()["valid"] is True
    bad = dict(spec, stop_condition={"type": "steps", "value": -5})
    r = client.post("/api/models/queueing/validate", json=bad)
    assert r.status_code == 200 and r.json()["valid"] is False
    assert r.json()["errors"]

    # 4. interactive session: create / step / run / reset / checkpoint / restore
    r = client.post("/api/sessions", json={"spec": spec})
    assert r.status_code == 201
    sid = r.json()["session_id"]

    r = client.post(f"/api/sessions/{sid}/step", json={"n": 5})
    assert r.status_code == 200
    assert r.json()["snapshot"]["step"] == 5

    # run is asynchronous: returns "running", completes in the background
    r = client.post(f"/api/sessions/{sid}/run")
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    final = _poll_session(client, sid)
    assert final["status"] == "completed"
    assert final["snapshot"]["step"] == 2000

    # pause/resume through the API on a run slow enough that the pause
    # reliably lands mid-run (CA ~4k steps/s => ~2.5s; queueing would finish
    # in ~0.25s on a fast machine and win the race)
    long_spec = _spec("cellular_automaton", 10_000)
    r = client.post("/api/sessions", json={"spec": long_spec})
    assert r.status_code == 201
    sid2 = r.json()["session_id"]
    r = client.post(f"/api/sessions/{sid2}/run")
    assert r.status_code == 200 and r.json()["status"] == "running"
    r = client.post(f"/api/sessions/{sid2}/pause")
    assert r.status_code == 200
    paused = r.json()
    assert paused["status"] == "paused"
    assert 0 < paused["snapshot"]["step"] < 10_000
    r = client.post(f"/api/sessions/{sid2}/resume")
    assert r.status_code == 200
    final2 = _poll_session(client, sid2)
    assert final2["status"] == "completed"
    assert final2["snapshot"]["step"] == 10_000

    r = client.post(f"/api/sessions/{sid}/reset")
    assert r.status_code == 200 and r.json()["snapshot"]["step"] == 0

    client.post(f"/api/sessions/{sid}/step", json={"n": 3})
    r = client.post(f"/api/sessions/{sid}/checkpoint")
    assert r.status_code == 200
    checkpoint = r.json()["checkpoint"]

    client.post(f"/api/sessions/{sid}/step", json={"n": 4})
    r = client.post(f"/api/sessions/{sid}/restore", json={"checkpoint": checkpoint})
    assert r.status_code == 200
    assert r.json()["snapshot"]["step"] == 3

    r = client.delete(f"/api/sessions/{sid}")
    assert r.status_code == 204
    assert client.get(f"/api/sessions/{sid}").status_code == 404

    # 5. experiment: save / tag / run / seeded reproducibility / clone
    r = client.post("/api/experiments", json={"name": "e2e-lifecycle", "spec": spec})
    assert r.status_code == 201
    exp_id = r.json()["id"]

    r = client.put(f"/api/experiments/{exp_id}/tags", json={"tags": ["e2e", "phase6"]})
    assert r.status_code == 200
    assert sorted(r.json()["tags"]) == ["e2e", "phase6"]

    # run returns "queued" (async worker); wait=True blocks the worker only
    r = client.post(f"/api/experiments/{exp_id}/run", json={"wait": True})
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    exp = _poll_experiment(client, exp_id)
    assert exp["status"] == "completed"

    r = client.get(f"/api/experiments/{exp_id}/result")
    assert r.status_code == 200
    result = r.json()
    assert result["runs"], "run rows must exist"
    sha_first = result["runs"][0]["result_sha256"]
    assert sha_first
    assert result["runs"][0]["metrics"] is not None

    # same model + params + seed through a full rerun => identical checksum
    r = client.post(f"/api/experiments/{exp_id}/rerun")
    assert r.status_code == 200 and r.json()["status"] == "queued"
    _poll_experiment(client, exp_id)
    r = client.get(f"/api/experiments/{exp_id}/result")
    sha_second = r.json()["runs"][-1]["result_sha256"]
    assert sha_second == sha_first, "seeded run must reproduce the same result"

    r = client.post(
        f"/api/experiments/{exp_id}/clone",
        json={"name": "e2e-clone", "spec_overrides": {"seed": 43}},
    )
    assert r.status_code == 200
    clone_id = r.json()["id"]
    assert clone_id != exp_id

    r = client.get("/api/experiments", params={"tag": "e2e"})
    assert r.status_code == 200
    assert any(e["id"] == exp_id for e in r.json()["experiments"])

    # 6. report export: markdown attachment + json structure
    r = client.get(f"/api/experiments/{exp_id}/report", params={"format": "markdown"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "queueing" in r.text

    r = client.get(f"/api/experiments/{exp_id}/report", params={"format": "json"})
    assert r.status_code == 200
    report = r.json()
    assert report["experiment"]["id"] == exp_id
    assert report["runs"] and report["aggregate"]

    # 7. batch experiment: grid x repeats, poll to completion, summary, CSV
    r = client.post(
        "/api/batches",
        json={
            "name": "e2e-batch",
            "spec": spec,
            "grid": {"capacity": [4, 8]},
            "repeats": 2,
            "seed_strategy": "per_repeat_increment",
        },
    )
    assert r.status_code == 201
    batch_id = r.json()["id"]
    assert r.json()["total_items"] == 4

    batch = _poll_batch(client, batch_id)
    assert batch["status"] == "completed", batch.get("error")
    assert batch["counts"].get("completed") == 4

    r = client.get(f"/api/batches/{batch_id}/items")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 4
    assert all(i["status"] == "completed" and i["metrics"] for i in items)

    r = client.get(f"/api/batches/{batch_id}")
    summary = r.json()["summary"]
    assert len(summary["combos"]) == 2
    assert all(c["n"] == 2 for c in summary["combos"])

    r = client.get(f"/api/batches/{batch_id}/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = [ln for ln in r.text.lstrip("\ufeff").strip().splitlines() if ln]
    # format: BOM + 3 "# ..." comment lines + column header + one row per item
    data_rows = [ln for ln in lines if not ln.startswith("#")]
    assert len(lines) == 8 and len(data_rows) == 5
    assert all(ln.split(",")[0].isdigit() for ln in data_rows[1:])

    # 8. cleanup: delete experiments, verify gone
    for eid in (exp_id, clone_id):
        assert client.delete(f"/api/experiments/{eid}").status_code == 204
    remaining = client.get("/api/experiments").json()["experiments"]
    assert all(e["id"] not in (exp_id, clone_id) for e in remaining)
