"""Reusable performance benchmarks. Real runs only — numbers come from
actually executing the engine/API, never from constants. Used by
scripts/benchmark.py (standalone report) and tests/test_performance.py
(loose regression bounds).
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from ..core.engine.base import ENGINE_VERSION
from ..core.engine.engines import Limits, SimulationEngine
from ..core.registry import ModelRegistry
from ..core.schema.spec import validate_spec

BENCH_SEED = 42


@dataclass
class BenchResult:
    name: str
    steps: int
    seconds: float

    @property
    def per_second(self) -> float:
        return self.steps / self.seconds if self.seconds > 0 else 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "steps": self.steps,
            "seconds": round(self.seconds, 4),
            "steps_per_second": round(self.per_second, 1),
        }


def bench_engine(spec_raw: dict[str, Any], registry: ModelRegistry, steps: int) -> BenchResult:
    """Run a spec in-process for `steps` engine steps and time it."""
    spec, model_cls = validate_spec(spec_raw, registry)
    model = model_cls(spec.params, spec.seed if spec.seed is not None else BENCH_SEED)
    engine = SimulationEngine(
        model,
        {"type": "steps", "value": steps},
        limits=Limits(max_steps=steps, max_wall_seconds=600),
    )
    t0 = time.monotonic()
    result = engine.run(None)
    elapsed = time.monotonic() - t0
    done = result.steps if result is not None else engine.steps
    return BenchResult(f"engine:{spec_raw['model_id']}", done, elapsed)


def bench_session_step_latency(
    client: TestClient, spec_raw: dict[str, Any], calls: int = 50
) -> dict[str, Any]:
    """Round-trip latency of POST /api/sessions/{id}/step (n=1)."""
    r = client.post("/api/sessions", json={"spec": spec_raw})
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    latencies: list[float] = []
    try:
        for _ in range(calls):
            t0 = time.monotonic()
            resp = client.post(f"/api/sessions/{sid}/step", json={"n": 1})
            latencies.append(time.monotonic() - t0)
            assert resp.status_code == 200, resp.text
    finally:
        client.delete(f"/api/sessions/{sid}")
    return {
        "name": "api:session_step",
        "calls": calls,
        "p50_ms": round(statistics.median(latencies) * 1000, 2),
        "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)] * 1000, 2),
        "max_ms": round(max(latencies) * 1000, 2),
    }


def bench_batch_throughput(service: Any, spec_raw: dict[str, Any], items: int) -> dict[str, Any]:
    """Wall time for a small fixed-seed batch with `items` cache_sim runs."""
    per_combo = 2
    combos = max(1, items // per_combo)
    capacities = [8 * (2**i) for i in range(combos)]
    t0 = time.monotonic()
    batch = service.create(
        "benchmark-batch",
        spec_raw,
        {"capacity": capacities},
        per_combo,
        "fixed",
        0,
        2,
        60.0,
    )
    batch_id = batch["id"]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        current = service.get_batch(batch_id, include_summary=False)
        if current["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.02)
    elapsed = time.monotonic() - t0
    counts = current["counts"]
    completed = counts.get("completed", 0)
    return {
        "name": "batch:cache_sim",
        "items": completed,
        "seconds": round(elapsed, 3),
        "items_per_second": round(completed / elapsed, 2) if elapsed > 0 else 0.0,
        "status": current["status"],
    }
