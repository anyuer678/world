"""WorldLab performance benchmark. Run from backend/:
    uv run python scripts/benchmark.py [--json]

Every number is measured from a real run in this process. Environment is
recorded so results in docs/BENCHMARKS.md stay attributable.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.models  # noqa: F401 - register built-ins
from app.config import Settings
from app.core.engine.base import ENGINE_VERSION
from app.core.registry import registry
from app.core.schema.spec import example_spec_for
from app.services import benchmarks
from app.services.batch_service import BatchService
from app.services.experiment_service import ExperimentService
from app.services.session_service import SessionService

APP_VERSION = "0.1.0"

QUEUE_SPEC_STEPS = 100_000
CA_SPEC_STEPS = 500
CACHE_SPEC_STEPS = 100_000
CPU_SPEC_STEPS = 50_000
SCHELLING_SPEC_STEPS = 500
TRAFFIC_SPEC_STEPS = 500
SIR_SPEC_STEPS = 5_000


def build_spec(model_id: str, steps: int) -> dict:
    cls = registry.get(model_id)
    spec = example_spec_for(cls)
    spec["stop_condition"] = {"type": "steps", "value": steps}
    spec["seed"] = benchmarks.BENCH_SEED
    return spec


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print raw JSON only")
    args = parser.parse_args()

    results: dict = {
        "environment": {
            "app_version": APP_VERSION,
            "engine_version": ENGINE_VERSION,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "engine": [],
        "api": {},
        "batch": {},
    }

    for model_id, steps in (
        ("queueing", QUEUE_SPEC_STEPS),
        ("cpu_scheduling", CPU_SPEC_STEPS),
        ("cache_sim", CACHE_SPEC_STEPS),
        ("cellular_automaton", CA_SPEC_STEPS),
        ("schelling", SCHELLING_SPEC_STEPS),
        ("traffic_network", TRAFFIC_SPEC_STEPS),
        ("sir", SIR_SPEC_STEPS),
    ):
        results["engine"].append(
            benchmarks.bench_engine(build_spec(model_id, steps), registry, steps).to_json()
        )

    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = Settings.from_env()
    app = create_app(settings)
    with TestClient(app) as client:
        results["api"] = benchmarks.bench_session_step_latency(
            client, build_spec("queueing", 1_000_000), calls=50
        )

    with tempfile.TemporaryDirectory() as tmp:
        bench_settings = Settings(
            db_path=str(Path(tmp) / "bench.db"),
            max_workers=2,
            default_max_steps=1_000_000,
            max_wall_seconds=120,
            event_log_size=500,
            zero_delay_chain_limit=10000,
            cancel_poll_interval=256,
            plugin_modules=(),
        )
        service = ExperimentService(bench_settings, registry)
        sessions = SessionService(bench_settings, registry)
        batches = BatchService(bench_settings, registry)
        try:
            results["batch"] = benchmarks.bench_batch_throughput(
                batches, build_spec("cache_sim", 1000), items=8
            )
        finally:
            sessions.shutdown()
            batches.shutdown()
            service.shutdown()

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print("WorldLab 性能基准")
    print(f"  Python {results['environment']['python']} · 引擎 {ENGINE_VERSION} · {results['environment']['platform']}")
    print()
    print("引擎吞吐（真实运行）")
    for r in results["engine"]:
        print(f"  {r['name']:<36} {r['steps']:>9,} steps in {r['seconds']:>8.3f}s = {r['steps_per_second']:>12,.1f} steps/s")
    api = results["api"]
    print()
    print("API 延迟（TestClient 进程内）")
    print(f"  {api['name']:<36} {api['calls']} 次单步往返 p50={api['p50_ms']}ms p95={api['p95_ms']}ms max={api['max_ms']}ms")
    b = results["batch"]
    print()
    print("批量吞吐（2 工作线程）")
    print(f"  {b['name']:<36} {b['items']} items in {b['seconds']}s = {b['items_per_second']} items/s（status={b['status']}）")


if __name__ == "__main__":
    main()
