import math

import pytest
from pydantic import ValidationError

from app.core.engine.engines import SimulationEngine
from app.models.predator_prey.model import PredatorPreyModel
from app.models.predator_prey.params import PredatorPreyParams

CLASSIC = {
    "prey_growth": 1.0, "predation": 0.4, "conversion": 0.3,
    "predator_death": 0.6, "initial_prey": 2.0, "initial_predator": 1.0,
}


def _model(params: dict, seed=1):
    return PredatorPreyModel(params, rng_seed=seed)


def _run_steps(params: dict, steps: int, seed=1):
    model = _model(params, seed)
    engine = SimulationEngine(model, {"type": "steps", "value": steps})
    engine.run()
    return model


def test_first_integral_conserved_in_classic_cycles():
    a, b, d, g = 1.0, 0.4, 0.3, 0.6
    x0, y0 = 2.0, 1.0
    h0 = d * b * x0 - g * math.log(x0) + b * y0 - a * math.log(y0)
    m = _run_steps(CLASSIC, steps=300)
    assert abs(m.first_integral() - h0) < 1e-3


def test_capacity_converges_to_interior_equilibrium():
    params = dict(CLASSIC, prey_capacity=8.0)
    m = _run_steps(params, steps=400)
    f = m.finalize_metrics()
    assert abs(f["prey_end"] - 5.0) < 0.01
    assert abs(f["predator_end"] - 0.9375) < 0.01
    assert f["distance_to_equilibrium"] < 0.01


def test_classic_cycles_keep_amplitude_and_period():
    m = _run_steps(CLASSIC, steps=600)
    f = m.finalize_metrics()
    assert f["prey_min"] > 0 and f["predator_min"] > 0
    # large-amplitude LV period is longer than the small-signal 2*pi/sqrt(alpha*gamma)
    small_signal = 2 * math.pi / math.sqrt(CLASSIC["prey_growth"] * CLASSIC["predator_death"])
    assert small_signal < f["cycle_period"] < 3 * small_signal
    # roughly 600/period cycles detected (±1 for edge effects)
    expected = 600 / f["cycle_period"]
    assert abs(f["prey_peaks"] - expected) <= 1


def test_no_predators_prey_follows_closed_form():
    exp = _run_steps(dict(CLASSIC, initial_predator=0.0), steps=10)
    fe = exp.finalize_metrics()
    assert fe["predator_end"] < 1e-12
    assert abs(fe["prey_end"] - 2.0 * math.e**10) / (2.0 * math.e**10) < 0.01

    log = _run_steps(dict(CLASSIC, initial_predator=0.0, prey_capacity=8.0), steps=10)
    fl = log.finalize_metrics()
    k, a, x0 = 8.0, 1.0, 2.0
    exact = k / (1.0 + (k / x0 - 1.0) * math.e ** (-a * 10))
    assert abs(fl["prey_end"] - exact) / exact < 0.01


def test_no_prey_predators_starve_exponentially():
    m = _run_steps(dict(CLASSIC, initial_prey=0.0, initial_predator=5.0), steps=10)
    f = m.finalize_metrics()
    assert f["prey_end"] == 0.0
    assert abs(f["predator_end"] - 5.0 * math.e ** (-0.6 * 10)) < 1e-6


def test_determinism_same_seed():
    a = _run_steps(CLASSIC, steps=80, seed=5)
    b = _run_steps(CLASSIC, steps=80, seed=5)
    assert a.finalize_metrics() == b.finalize_metrics()
    assert a.snapshot()["history"] == b.snapshot()["history"]


def test_checkpoint_restore_equivalence():
    stop = {"type": "steps", "value": 90}
    a = SimulationEngine(_model(CLASSIC, seed=11), stop)
    a.run(max_steps=25)
    cp = a.checkpoint()
    a.run()
    b = SimulationEngine(_model(CLASSIC, seed=11), stop)
    b.restore(cp)
    b.run()
    assert a.model.finalize_metrics() == b.model.finalize_metrics()
    assert a.model.snapshot() == b.model.snapshot()


def test_history_bounded_and_decimated():
    m = _run_steps(CLASSIC, steps=600)
    hist = m.snapshot()["history"]
    assert len(hist) <= 256
    assert len(hist) > 100
    assert hist[0][0] == 0 and hist[-1][0] == 600.0


def test_param_validation_boundaries():
    with pytest.raises(ValidationError):
        PredatorPreyParams(predation=0.0)
    with pytest.raises(ValidationError):
        PredatorPreyParams(conversion=-0.1)
    with pytest.raises(ValidationError):
        PredatorPreyParams(predator_death=0.0)
    with pytest.raises(ValidationError):
        PredatorPreyParams(prey_growth=-0.1)
    with pytest.raises(ValidationError):
        PredatorPreyParams(initial_prey=0.0, initial_predator=0.0)
    with pytest.raises(ValidationError):
        PredatorPreyParams(prey_capacity=0.0)
    with pytest.raises(ValidationError):
        PredatorPreyParams(initial_prey=-1.0)


def test_scenarios_run():
    assert len(PredatorPreyModel.scenarios) == 3
    for sc in PredatorPreyModel.scenarios:
        m = _run_steps(sc["params"], steps=sc["stop_condition"]["value"], seed=sc["seed"])
        f = m.finalize_metrics()
        assert f["prey_end"] >= 0 and f["predator_end"] >= 0
        assert all(math.isfinite(v) for v in f.values())
    classic = _run_steps(PredatorPreyModel.scenarios[0]["params"], steps=60, seed=3).finalize_metrics()
    damped = _run_steps(PredatorPreyModel.scenarios[1]["params"], steps=240, seed=3).finalize_metrics()
    assert classic["distance_to_equilibrium"] > 0.2  # neutral cycles never settle
    assert damped["distance_to_equilibrium"] < 0.01  # capacity case converges
