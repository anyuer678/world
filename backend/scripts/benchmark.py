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

# 每个内置模型的基准步数。模型清单取自 registry.builtin_ids()——新模型若没有
# 这里的一行，基准脚本会直接报错而不是悄悄少测一个模型（R28/R31 的写死清单教训）。
BENCH_STEPS = {
    "queueing": 100_000,
    "cpu_scheduling": 50_000,
    "cache_sim": 100_000,
    "cellular_automaton": 500,
    "schelling": 500,
    "traffic_network": 500,
    "sir": 5_000,
    "predator_prey": 5_000,
}


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

    builtins = registry.builtin_ids()
    unbenchmarked = [mid for mid in builtins if mid not in BENCH_STEPS]
    if unbenchmarked:
        raise SystemExit(
            f"BENCH_STEPS 缺内置模型 {unbenchmarked}——新增模型必须同时加基准步数，"
            "否则基准表会静默少一行"
        )
    for model_id in builtins:
        results["engine"].append(
            benchmarks.bench_engine(
                build_spec(model_id, BENCH_STEPS[model_id]), registry, BENCH_STEPS[model_id]
            ).to_json()
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
        throughput = (
            f"{r['steps_per_second']:>12,.1f} steps/s"
            if r["measurable"]
            else " n/a（<1 ms，测不出）"
        )
        print(f"  {r['name']:<36} {r['steps']:>9,} steps in {r['seconds']:>10.4f}s = {throughput}")
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
