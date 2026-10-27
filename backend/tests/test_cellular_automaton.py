import pytest
from pydantic import ValidationError

from app.core.engine.engines import SimulationEngine
from app.models.cellular_automaton.model import CellularAutomatonModel
from app.models.cellular_automaton.params import CellularAutomatonParams


def _model(params: dict, seed=1):
    return CellularAutomatonModel(params, rng_seed=seed)


def _run_steps(params: dict, steps: int, seed=1):
    model = _model(params, seed)
    engine = SimulationEngine(model, {"type": "steps", "value": steps})
    engine.run()
    return model


def _blinker_grid():
    return [
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
        [0, 1, 1, 1, 0],
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
    ]


def test_block_still_life_is_stable():
    grid = [[0] * 6 for _ in range(6)]
    for i in (2, 3):
        for j in (2, 3):
            grid[i][j] = 1
    model = _run_steps(
        {"initial_grid": grid, "width": 6, "height": 6}, steps=10, seed=3
    )
    m = model.finalize_metrics()
    assert m["generation"] == 10.0
    assert m["population"] == 4.0
    assert m["births_total"] == 0.0
    assert m["deaths_total"] == 0.0


def test_blinker_oscillates_with_period_two():
    params = {"initial_grid": _blinker_grid(), "width": 5, "height": 5}
    model = _model(params, seed=3)
    engine = SimulationEngine(model, {"type": "steps", "value": 2})
    engine.run()
    snap = model.snapshot()
    assert snap["population"] == 3
    assert snap["rows"] == ["".join(str(c) for c in row) for row in _blinker_grid()]


def test_blinker_vertical_intermediate_state():
    model = _run_steps(
        {"initial_grid": _blinker_grid(), "width": 5, "height": 5}, steps=1, seed=3
    )
    rows = model.snapshot()["rows"]
    assert rows[1] == "00100"
    assert rows[2] == "00100"
    assert rows[3] == "00100"


def test_empty_grid_stays_empty():
    grid = [[0] * 8 for _ in range(8)]
    model = _run_steps({"initial_grid": grid, "width": 8, "height": 8}, steps=15, seed=3)
    m = model.finalize_metrics()
    assert m["population"] == 0.0
    assert m["births_total"] == 0.0


def test_custom_rule_b3_s_decay_to_zero():
    """B3/S (empty survive set): nothing survives; blinker -> 2 births -> empty."""
    params = {
        "initial_grid": _blinker_grid(),
        "width": 5,
        "height": 5,
        "rule_string": "B3/S",
    }
    model = _run_steps(params, steps=2, seed=3)
    m = model.finalize_metrics()
    assert m["population"] == 0.0
    assert model.snapshot()["history"] == [3, 2, 0]


def _glider_grid():
    grid = [[0] * 6 for _ in range(6)]
    grid[0][1] = 1
    grid[1][2] = 1
    grid[2][0] = grid[2][1] = grid[2][2] = 1
    return grid


def test_toroidal_wrap_keeps_glider_alive_fixed_boundary_settles_to_block():
    toroidal = _run_steps(
        {"initial_grid": _glider_grid(), "width": 6, "height": 6, "toroidal": True},
        steps=20,
        seed=3,
    )
    fixed = _run_steps(
        {"initial_grid": _glider_grid(), "width": 6, "height": 6, "toroidal": False},
        steps=20,
        seed=3,
    )
    # Glider wraps the torus forever: population stays 5 at every generation.
    assert toroidal.finalize_metrics()["population"] == 5.0
    # On a fixed boundary the glider dies at the corner and the debris
    # settles into a 2x2 block still life in the bottom-right.
    assert fixed.finalize_metrics()["population"] == 4.0
    assert fixed.snapshot()["rows"][-2:] == ["000011", "000011"]
    assert all(set(r) == {"0"} for r in fixed.snapshot()["rows"][:-2])


def test_determinism_generated_grid_same_seed():
    params = {"width": 16, "height": 16, "initial_density": 0.3}
    a = _run_steps(params, steps=30, seed=5)
    b = _run_steps(params, steps=30, seed=5)
    assert a.finalize_metrics() == b.finalize_metrics()
    assert a.snapshot()["rows"] == b.snapshot()["rows"]
    c = _run_steps(params, steps=30, seed=6)
    assert c.snapshot()["rows"] != a.snapshot()["rows"]


def test_checkpoint_restore_equivalence():
    params = {"width": 16, "height": 16, "initial_density": 0.3}
    stop = {"type": "steps", "value": 25}
    a = SimulationEngine(_model(params, seed=11), stop)
    a.run(max_steps=7)
    cp = a.checkpoint()
    a.run()
    b = SimulationEngine(_model(params, seed=11), stop)
    b.restore(cp)
    b.run()
    assert a.model.finalize_metrics() == b.model.finalize_metrics()
    assert a.model.snapshot() == b.model.snapshot()


def test_param_validation_boundaries():
    with pytest.raises(ValidationError):
        CellularAutomatonParams(rule_string="B9/S23")
    with pytest.raises(ValidationError):
        CellularAutomatonParams(rule_string="b3/s23")
    with pytest.raises(ValidationError):
        CellularAutomatonParams(rule_string="B3S23")
    with pytest.raises(ValidationError):
        CellularAutomatonParams(width=4)
    with pytest.raises(ValidationError):
        CellularAutomatonParams(initial_density=1.5)
    with pytest.raises(ValidationError):
        CellularAutomatonParams(width=4, height=4, initial_grid=[[0, 1], [1, 0]])
    with pytest.raises(ValidationError):
        CellularAutomatonParams(width=2, height=2, initial_grid=[[0, 2], [1, 0]])
    with pytest.raises(ValidationError):
        CellularAutomatonParams(unknown_param=1)
    ok = CellularAutomatonParams(rule_string="B2/S", width=8, height=8)
    assert ok.toroidal is True and ok.initial_density == 0.25
