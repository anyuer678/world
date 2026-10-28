import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.analysis_service import analyze_summary, find_dispersion, find_sweep_jumps
from app.services.batch_service import BatchService
from conftest import registry


def _combo(params: dict, metric_means: dict, n: int = 1, std: float = 0.0) -> dict:
    return {
        "params": params,
        "n": n,
        "metrics": {
            m: {"n": n, "mean": v, "std": std, "p50": v, "p90": v, "ci95_low": v, "ci95_high": v}
            for m, v in metric_means.items()
        },
    }


def test_jump_detected_in_single_param_sweep():
    grid = {"load": [0.5, 0.6, 0.7, 0.8, 0.9]}
    combos = [
        _combo({"load": 0.5}, {"avg_waiting_time": 2.0}),
        _combo({"load": 0.6}, {"avg_waiting_time": 2.2}),
        _combo({"load": 0.7}, {"avg_waiting_time": 2.4}),
        _combo({"load": 0.8}, {"avg_waiting_time": 2.6}),
        _combo({"load": 0.9}, {"avg_waiting_time": 26.0}),
    ]
    out = find_sweep_jumps(combos, grid)
    assert len(out) == 1
    f = out[0]
    assert f["param"] == "load" and f["metric"] == "avg_waiting_time"
    assert f["from"] == 0.8 and f["to"] == 0.9
    assert f["ratio"] >= 3.0


def test_flat_sweep_and_mixed_grid_produce_no_jumps():
    flat_grid = {"load": [0.5, 0.6, 0.7]}
    flat = [_combo({"load": v}, {"m": 1.0}) for v in flat_grid["load"]]
    assert find_sweep_jumps(flat, flat_grid) == []

    mixed_grid = {"a": [1, 2, 3], "b": [10, 20, 30]}
    mixed = [_combo({"a": a, "b": b}, {"m": 100.0}) for a in [1, 2, 3] for b in [10, 20, 30]]
    assert find_sweep_jumps(mixed, mixed_grid) == []


def test_jump_dedupe_keeps_max_per_param_metric():
    grid = {"load": [0.2, 0.4, 0.6, 0.8, 0.95]}
    combos = [
        _combo({"load": 0.2}, {"m": 1.0}),
        _combo({"load": 0.4}, {"m": 2.0}),
        _combo({"load": 0.6}, {"m": 4.0}),
        _combo({"load": 0.8}, {"m": 8.0}),
        _combo({"load": 0.95}, {"m": 80.0}),
    ]
    out = find_sweep_jumps(combos, grid)
    assert len(out) == 1
    assert out[0]["from"] == 0.8 and out[0]["to"] == 0.95
    assert out[0]["ratio"] == 10.0


def test_jump_to_zero_has_null_ratio():
    grid = {"load": [0.5, 0.6, 0.7]}
    combos = [
        _combo({"load": 0.5}, {"m": 100.0}),
        _combo({"load": 0.6}, {"m": 80.0}),
        _combo({"load": 0.7}, {"m": 0.0}),
    ]
    out = find_sweep_jumps(combos, grid)
    assert len(out) == 1
    assert out[0]["from"] == 0.6 and out[0]["to"] == 0.7
    assert out[0]["ratio"] is None
    assert out[0]["value_to"] == 0.0


def test_jump_from_zero_has_null_ratio():
    grid = {"load": [0.5, 0.6, 0.7]}
    combos = [
        _combo({"load": 0.5}, {"m": 0.0}),
        _combo({"load": 0.6}, {"m": 0.0}),
        _combo({"load": 0.7}, {"m": 12.0}),
    ]
    out = find_sweep_jumps(combos, grid)
    assert len(out) == 1
    assert out[0]["ratio"] is None
    assert out[0]["value_from"] == 0.0 and out[0]["value_to"] == 12.0


def test_zero_to_zero_pair_is_not_a_jump():
    grid = {"load": [0.5, 0.6, 0.7]}
    combos = [_combo({"load": v}, {"m": 0.0}) for v in grid["load"]]
    assert find_sweep_jumps(combos, grid) == []


def test_dispersion_flags_high_cv_only_with_enough_repeats():
    combos = [
        _combo({"load": 0.5}, {"m": 1.0}, n=4, std=0.8),
        _combo({"load": 0.7}, {"m": 1.0}, n=2, std=0.9),
        _combo({"load": 0.9}, {"m": 10.0}, n=4, std=0.1),
    ]
    out = find_dispersion(combos)
    assert len(out) == 1
    assert out[0]["params"] == {"load": 0.5} and out[0]["cv"] == 0.8 and out[0]["n"] == 4


def test_analyze_summary_shape_and_note():
    grid = {"load": [0.5, 0.9]}
    combos = [_combo({"load": 0.5}, {"m": 1.0}), _combo({"load": 0.9}, {"m": 2.0})]
    out = analyze_summary({"combos": combos}, grid)
    assert out["findings"] == []
    assert "不构成因果" in out["note"]


# ------------------------------------------------------------------ API
def _spec():
    return {
        "schema_version": 1,
        "model_id": "toy_des",
        "params": {"total_events": 200, "delay_mean": 1.0},
        "stop_condition": {"type": "until_empty"},
        "seed": 1000,
    }


def _wait_terminal(svc, batch_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        b = svc.get_batch(batch_id, include_summary=False)
        if b["status"] in ("completed", "failed", "cancelled"):
            return b
        time.sleep(0.05)
    raise AssertionError(f"batch {batch_id} did not finish in {timeout}s")


@pytest.fixture()
def batches(settings):
    b = BatchService(settings, registry)
    yield b
    b.shutdown()


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def test_findings_endpoint_on_real_batch(batches, client):
    b = batches.create("findings-api", _spec(), {"delay_mean": [0.5, 1.0, 2.0]}, repeats=2)
    _wait_terminal(batches, b["id"])
    resp = client.get(f"/api/batches/{b['id']}/findings")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["findings"], list)
    assert "不构成因果" in data["note"]


def test_findings_endpoint_unknown_batch(client):
    resp = client.get("/api/batches/999999/findings")
    assert resp.status_code == 404
