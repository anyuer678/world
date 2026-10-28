import pytest
from pydantic import ValidationError

from app.core.engine.engines import SimulationEngine
from app.models.schelling.model import SchellingModel
from app.models.schelling.params import SchellingParams


def _model(params: dict, seed=1):
    return SchellingModel(params, rng_seed=seed)


def _run_steps(params: dict, steps: int, seed=1):
    model = _model(params, seed)
    engine = SimulationEngine(model, {"type": "steps", "value": steps})
    engine.run()
    return model


def _checkerboard(h: int = 6, w: int = 6) -> list[list[int]]:
    return [[(1 if (i + j) % 2 == 0 else 2) for j in range(w)] for i in range(h)]


def test_zero_tolerance_never_moves():
    grid = _checkerboard()
    model = _run_steps(
        {"initial_grid": grid, "width": 6, "height": 6, "tolerance": 0.0},
        steps=10,
        seed=3,
    )
    snap = model.snapshot()
    assert snap["moves_total"] == 0
    assert snap["unhappy"] == 0
    assert snap["rows"] == ["".join(str(c) for c in row) for row in grid]


def test_uniform_grid_is_always_happy():
    grid = [[1] * 6 for _ in range(6)]
    model = _run_steps(
        {"initial_grid": grid, "width": 6, "height": 6, "tolerance": 1.0},
        steps=5,
        seed=3,
    )
    snap = model.snapshot()
    assert snap["moves_total"] == 0
    assert snap["unhappy"] == 0
    assert snap["segregation_index"] == 1.0


def test_single_mismatched_agent_moves_once_then_settles():
    grid = [[1] * 5 for _ in range(5)]
    grid[2][2] = 2
    grid[0][0] = 0
    model = _run_steps(
        {"initial_grid": grid, "width": 5, "height": 5, "tolerance": 0.5},
        steps=1,
        seed=7,
    )
    snap = model.snapshot()
    assert snap["moves_total"] == 1
    assert snap["rows"][2][2] == "0"
    assert sum(row.count("2") for row in snap["rows"]) == 1


def test_fully_occupied_unhappy_agent_cannot_move():
    grid = [[1] * 5 for _ in range(5)]
    grid[2][2] = 2
    model = _run_steps(
        {"initial_grid": grid, "width": 5, "height": 5, "tolerance": 0.5},
        steps=3,
        seed=7,
    )
    snap = model.snapshot()
    assert snap["moves_total"] == 0
    assert snap["unhappy"] == 1


def test_sync_step_invariants_hold_over_run():
    m1 = _run_steps({"width": 20, "height": 15, "tolerance": 0.4}, steps=1, seed=11)
    m50 = _run_steps({"width": 20, "height": 15, "tolerance": 0.4}, steps=50, seed=11)
    s1, s50 = m1.snapshot(), m50.snapshot()
    assert s1["population_a"] + s1["population_b"] == s50["population_a"] + s50["population_b"]
    assert s50["population_a"] == s1["population_a"]
    assert all(c in "012" for row in s50["rows"] for c in row)
    metrics = m50.finalize_metrics()
    assert metrics["tick"] == 50.0
    assert metrics["moves_per_tick"] >= 0.0


def test_determinism_same_seed():
    def run():
        m = _run_steps({"width": 20, "height": 15, "tolerance": 0.35}, steps=40, seed=5)
        return m.dump_state()

    assert run() == run()


def test_checkpoint_restore_equivalence():
    params = {"width": 18, "height": 12, "tolerance": 0.3}
    stop = {"type": "steps", "value": 16}
    a = SimulationEngine(_model(params, seed=9), stop)
    a.run(max_steps=7)
    cp = a.checkpoint()
    a.run()
    b = SimulationEngine(_model(params, seed=9), stop)
    b.restore(cp)
    b.run()
    assert a.model.dump_state() == b.model.dump_state()
    assert a.model.snapshot() == b.model.snapshot()


def test_segregation_rises_under_mild_preference():
    model = _run_steps({"width": 30, "height": 20, "tolerance": 0.4}, steps=60, seed=4)
    segs = [r[2] for r in model.snapshot()["history"]]
    assert segs[-1] > segs[0]
    metrics = model.finalize_metrics()
    assert metrics["moves_total"] > 0


def test_param_validation_boundaries():
    with pytest.raises(ValidationError):
        SchellingParams(width=4)
    with pytest.raises(ValidationError):
        SchellingParams(occupancy=0.99)
    with pytest.raises(ValidationError):
        SchellingParams(tolerance=-0.1)
    with pytest.raises(ValidationError):
        SchellingParams(initial_grid=[[0, 1], [2]])
    ok = SchellingParams(initial_grid=[[0, 1, 2, 1, 0]] * 5, width=5, height=5)
    assert ok.initial_grid[0] == [0, 1, 2, 1, 0]


def test_scenario_specs_run():
    for scenario in SchellingModel.scenarios:
        model = SchellingModel(scenario["params"], rng_seed=scenario["seed"])
        engine = SimulationEngine(model, scenario["stop_condition"])
        engine.run()
        metrics = model.finalize_metrics()
        assert metrics["tick"] > 0
        assert 0.0 <= metrics["segregation_index"] <= 1.0


def test_no_preference_scenario_has_zero_moves():
    scenario = next(s for s in SchellingModel.scenarios if s["id"] == "no-preference")
    model = _run_steps(scenario["params"], scenario["stop_condition"]["value"], scenario["seed"])
    assert model.finalize_metrics()["moves_total"] == 0.0
