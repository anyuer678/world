"""阶段 6：性能回归测试（宽松阈值）。

阈值相对 docs/BENCHMARKS.md 的实测值留 20-80 倍余量，
只用于捕获数量级劣化，避免 CI / 低配机器上的假失败。
精确数字请运行 scripts/benchmark.py。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.models  # noqa: F401 - register built-ins
from app.core.registry import registry
from app.core.schema.spec import example_spec_for
from app.main import create_app
from app.services.benchmarks import (
    bench_batch_throughput,
    bench_engine,
    bench_session_step_latency,
)


def _spec(model_id: str, steps: int) -> dict:
    spec = example_spec_for(registry.get(model_id))
    spec["stop_condition"] = {"type": "steps", "value": steps}
    spec["seed"] = 42
    return spec


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def test_engine_throughput_queueing():
    res = bench_engine(_spec("queueing", 50_000), registry, 50_000)
    assert res.steps == 50_000
    assert res.per_second > 10_000  # 实测 ~26.7 万 steps/s


def test_engine_throughput_cache():
    res = bench_engine(_spec("cache_sim", 50_000), registry, 50_000)
    assert res.steps == 50_000
    assert res.per_second > 10_000  # 实测 ~40 万 steps/s


def test_engine_cellular_automaton_speed():
    res = bench_engine(_spec("cellular_automaton", 500), registry, 500)
    assert res.steps == 500
    assert res.seconds < 10.0  # 实测 ~0.13s


def test_api_session_step_latency(client):
    res = bench_session_step_latency(client, _spec("queueing", 1_000_000), calls=20)
    assert res["p95_ms"] < 1000.0  # 实测 ~16ms（TestClient 进程内）


def test_batch_small_throughput(client):
    res = bench_batch_throughput(client.app.state.batches, _spec("cache_sim", 1000), 4)
    assert res["status"] == "completed"
    assert res["items"] == 4
    assert res["seconds"] < 60.0
