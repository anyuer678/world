import pytest
from pydantic import ValidationError

from app.core.engine.engines import SimulationEngine
from app.models.sir.model import SirModel
from app.models.sir.params import SirParams


def _model(params: dict, seed=1):
    return SirModel(params, rng_seed=seed)


def _run_steps(params: dict, steps: int, seed=1):
    model = _model(params, seed)
    engine = SimulationEngine(model, {"type": "steps", "value": steps})
    engine.run()
    return model


def test_conservation_sir_equals_population():
    m = _run_steps({"population": 5000, "initial_infected": 5, "beta": 0.4, "gamma": 0.1}, steps=80)
    snap = m.snapshot()
    total = snap["susceptible"] + snap["infected"] + snap["recovered"]
    assert abs(total - 5000) < 1e-6


def test_epidemic_threshold_below_one_burns_out():
    below = _run_steps({"population": 10000, "initial_infected": 10, "beta": 0.05, "gamma": 0.1}, steps=100)
    mb = below.finalize_metrics()
    assert mb["attack_rate"] < 0.05
    assert mb["peak_infected"] < 100


def test_epidemic_threshold_above_one_outbreak():
    above = _run_steps({"population": 10000, "initial_infected": 10, "beta": 0.5, "gamma": 0.1}, steps=100)
    ma = above.finalize_metrics()
    assert ma["attack_rate"] > 0.6
    assert ma["peak_infected"] > 0.1 * 10000
    # peak comes before the burnout tail; infection wave must have passed
    assert ma["peak_time"] < ma["tick"]


def test_sweep_finds_phase_transition_at_beta_gamma():
    """The textbook jump: attack rate explodes as beta crosses gamma."""
    metrics = []
    for beta in [0.05, 0.1, 0.15, 0.2, 0.3]:
        m = _run_steps({"population": 2000, "initial_infected": 5, "beta": beta, "gamma": 0.1}, steps=200)
        metrics.append(m.finalize_metrics()["attack_rate"])
    assert metrics[0] < 0.1
    assert metrics[-1] > 0.5
    # strictly increasing between the crossing points
    assert all(b > a for a, b in zip(metrics, metrics[1:]))


def test_determinism_same_seed():
    params = {"population": 3000, "initial_infected": 20, "beta": 0.3, "gamma": 0.1}
    a = _run_steps(params, steps=60, seed=5)
    b = _run_steps(params, steps=60, seed=5)
    assert a.finalize_metrics() == b.finalize_metrics()
    assert a.snapshot()["history"] == b.snapshot()["history"]


def test_checkpoint_restore_equivalence():
    params = {"population": 3000, "initial_infected": 20, "beta": 0.3, "gamma": 0.1}
    stop = {"type": "steps", "value": 80}
    a = SimulationEngine(_model(params, seed=11), stop)
    a.run(max_steps=25)
    cp = a.checkpoint()
    a.run()
    b = SimulationEngine(_model(params, seed=11), stop)
    b.restore(cp)
    b.run()
    assert a.model.finalize_metrics() == b.model.finalize_metrics()
    assert a.model.snapshot() == b.model.snapshot()


def test_history_bounded_and_decimated():
    m = _run_steps({"population": 5000, "initial_infected": 5, "beta": 0.4, "gamma": 0.1}, steps=600)
    hist = m.snapshot()["history"]
    assert len(hist) <= 256
    assert len(hist) > 100
    assert hist[0][0] == 0 and hist[-1][0] == 600.0


def test_zero_beta_no_infection():
    m = _run_steps({"population": 1000, "initial_infected": 5, "beta": 0.0, "gamma": 0.2}, steps=50)
    f = m.finalize_metrics()
    assert f["infected_end"] < 1e-3  # exponential decay, Euler never hits exact zero
    assert abs(f["total_infected"] - 5.0) < 1e-3


def test_param_validation_boundaries():
    with pytest.raises(ValidationError):
        SirParams(population=5)
    with pytest.raises(ValidationError):
        SirParams(population=1000, initial_infected=0)
    with pytest.raises(ValidationError):
        SirParams(population=1000, initial_infected=1001)
    with pytest.raises(ValidationError):
        SirParams(beta=-0.1)
    with pytest.raises(ValidationError):
        SirParams(gamma=-0.1)


def test_scenarios_run():
    for sc in SirModel.scenarios:
        m = _run_steps(sc["params"], steps=sc["stop_condition"]["value"], seed=sc["seed"])
        f = m.finalize_metrics()
        assert abs(f["susceptible_end"] + f["infected_end"] + f["recovered_end"] - sc["params"]["population"]) < 1e-6
    assert len(SirModel.scenarios) == 3
