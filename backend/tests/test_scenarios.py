"""Scenario library regression: every built-in model ships 2+ scenarios, each
has Chinese title/description, passes spec validation, and actually runs."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.engine.engines import Limits, SimulationEngine
from app.core.registry import registry
from app.core.schema.spec import validate_spec
from app.main import create_app

BUILTIN_IDS = ["queueing", "cpu_scheduling", "cache_sim", "cellular_automaton", "traffic_network", "schelling"]

LIMITS = Limits(
    max_steps=1_000_000, max_wall_seconds=30, zero_delay_chain_limit=10_000, cancel_poll_interval=1000
)


def _has_chinese(text: str) -> bool:
    return any(ord(ch) > 0x2E80 for ch in text)


def _builtin_scenarios():
    out = []
    for m in registry.list():
        if m["model_id"] not in BUILTIN_IDS:
            continue
        for s in m["scenarios"]:
            out.append((m["model_id"], m["version"], s))
    return out


_SCENARIO_IDS = [f"{mid}:{s['id']}" for mid, _v, s in _builtin_scenarios()]


def test_every_builtin_model_has_scenarios():
    models = {m["model_id"]: m for m in registry.list()}
    for model_id in BUILTIN_IDS:
        assert model_id in models
        assert len(models[model_id]["scenarios"]) >= 2, model_id


def test_builtin_display_names_are_chinese():
    for m in registry.list():
        if m["model_id"] not in BUILTIN_IDS:
            continue
        assert m["display_name"] and _has_chinese(m["display_name"]), m["model_id"]
        assert _has_chinese(m["description"]), m["model_id"]


@pytest.mark.parametrize("model_id,version,scenario", _builtin_scenarios(), ids=_SCENARIO_IDS)
def test_scenario_shape_and_chinese(model_id: str, version: str, scenario: dict):
    assert set(scenario) == {"id", "title", "description", "params", "seed", "stop_condition"}
    assert isinstance(scenario["params"], dict) and scenario["params"]
    assert _has_chinese(scenario["title"]), scenario["id"]
    assert _has_chinese(scenario["description"]), scenario["id"]
    assert isinstance(scenario["seed"], int) and scenario["seed"] >= 0
    assert scenario["stop_condition"]["type"] == "steps"


@pytest.mark.parametrize("model_id,version,scenario", _builtin_scenarios(), ids=_SCENARIO_IDS)
def test_scenario_spec_valid_and_runs(model_id: str, version: str, scenario: dict):
    spec = {
        "model_id": model_id,
        "model_version": version,
        "params": scenario["params"],
        "seed": scenario["seed"],
        "stop_condition": scenario["stop_condition"],
    }
    parsed, model_cls = validate_spec(spec, registry)
    engine = SimulationEngine(
        model_cls(parsed.params, parsed.seed), {"type": "steps", "value": 200}, limits=LIMITS
    )
    result = engine.run()
    assert result.steps > 0
    assert result.metrics, scenario["id"]


def test_api_models_expose_scenarios(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        models = {m["model_id"]: m for m in client.get("/api/models").json()["models"]}
        for model_id in BUILTIN_IDS:
            assert model_id in models
            assert len(models[model_id]["scenarios"]) >= 2
            assert _has_chinese(models[model_id]["display_name"])
