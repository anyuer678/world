import pytest

from app.core.engine.engines import Limits, SimulationEngine
from app.core.engine.base import SimulationLimitExceeded
from conftest import ToyDesModel, ToyStepModel, ZeroDelayLoopModel


def _des_spec(n=100):
    return {"type": "steps", "value": n}


def test_time_stepped_basic():
    model = ToyStepModel({}, rng_seed=7)
    engine = SimulationEngine(model, {"type": "steps", "value": 10})
    result = engine.run()
    assert result.steps == 10
    assert result.sim_time == 10.0
    assert result.status == "completed"
    assert len(model.trace) == 10


def test_time_stepped_step_and_resume():
    model = ToyStepModel({}, rng_seed=7)
    engine = SimulationEngine(model, {"type": "steps", "value": 10})
    for _ in range(4):
        assert engine.step()
    assert engine.steps == 4
    assert engine.clock == 4.0


def test_time_stepped_checkpoint_restore_equivalence():
    seed = 99
    a = SimulationEngine(ToyStepModel({}, rng_seed=seed), {"type": "steps", "value": 20})
    a.run(max_steps=11)
    cp = a.checkpoint()
    a.run()

    b = SimulationEngine(ToyStepModel({}, rng_seed=seed), {"type": "steps", "value": 20})
    b.restore(cp)
    b.run()

    assert a.model.trace == b.model.trace
    assert a.model.trace[-1] == b.snapshot().state["value"]
    assert a.clock == b.clock


def test_time_stepped_reset():
    model = ToyStepModel({}, rng_seed=3)
    engine = SimulationEngine(model, {"type": "steps", "value": 5})
    engine.run()
    v1 = model.value
    engine.reset()
    engine.run()
    assert engine.model.value == v1


def test_des_basic_and_event_count():
    model = ToyDesModel({"total_events": 50}, rng_seed=1)
    engine = SimulationEngine(model, {"type": "steps", "value": 200})
    result = engine.run()
    assert result.metrics["count"] == 50.0
    assert result.status == "completed"
    assert result.sim_time > 0


def test_run_max_steps_bounds_per_call():
    """Regression: run(max_steps=N) must stop after N steps when no model stop
    condition is reached (chunk_done), and a follow-up run() continues."""
    model = ToyDesModel({"total_events": 1000}, rng_seed=5)
    engine = SimulationEngine(model, {"type": "steps", "value": 1000})
    r1 = engine.run(max_steps=100)
    assert r1.status == "chunk_done"
    assert engine.steps == 100
    assert engine.snapshot().status == "running"
    r2 = engine.run(max_steps=100)
    assert r2.status == "chunk_done"
    assert engine.steps == 200
    r3 = engine.run()
    assert r3.status == "completed"
    assert engine.steps == 1000
    assert engine.model.finalize_metrics()["count"] == 1000.0


def test_chunked_run_crosses_absolute_cap_des():
    """limits.max_steps caps unbounded run() calls, not chunked ones: a
    session worker chunking run(10) must be able to pass the cap."""
    model = ToyDesModel({"total_events": 300}, rng_seed=8)
    engine = SimulationEngine(
        model, {"type": "steps", "value": 300}, limits=Limits(max_steps=150)
    )
    for _ in range(40):
        r = engine.run(max_steps=10)
        if r.status == "completed":
            break
    assert r.status == "completed"
    assert engine.steps == 300


def test_chunked_run_crosses_absolute_cap_time_stepped():
    model = ToyStepModel({}, rng_seed=8)
    engine = SimulationEngine(
        model, {"type": "steps", "value": 300}, limits=Limits(max_steps=150)
    )
    for _ in range(40):
        r = engine.run(max_steps=10)
        if r.status == "completed":
            break
    assert r.status == "completed"
    assert engine.steps == 300
    assert engine.steps > 150


def test_des_checkpoint_restore_equivalence():
    spec = {"type": "steps", "value": 500}
    a = SimulationEngine(ToyDesModel({"total_events": 500}, rng_seed=11), spec)
    a.run(max_steps=123)
    cp = a.checkpoint()
    a.run()

    b = SimulationEngine(ToyDesModel({"total_events": 500}, rng_seed=11), spec)
    b.restore(cp)
    b.run()

    assert a.model.count == b.model.count
    assert a.model.total_time == b.model.total_time
    assert a.snapshot().metrics == b.snapshot().metrics


def test_des_rng_state_in_checkpoint():
    """Same seed + restored RNG stream => identical continuation."""
    spec = {"type": "steps", "value": 300}
    a = SimulationEngine(ToyDesModel({"total_events": 300}, rng_seed=5), spec)
    a.run(max_steps=57)
    cp = a.checkpoint()

    b = SimulationEngine(ToyDesModel({"total_events": 300}, rng_seed=5), spec)
    b.restore(cp)
    b.run()

    full = SimulationEngine(ToyDesModel({"total_events": 300}, rng_seed=5), spec)
    full.run()
    assert b.model.total_time == full.model.total_time


def test_des_step_on_empty_queue_returns_false():
    engine = SimulationEngine(ToyDesModel({"total_events": 1}, rng_seed=2), {"type": "steps", "value": 100})
    engine.run()
    assert engine.step() is False


def test_des_zero_delay_chain_limit():
    engine = SimulationEngine(
        ZeroDelayLoopModel({}, rng_seed=1),
        {"type": "steps", "value": 100000},
        limits=Limits(max_steps=1000000, zero_delay_chain_limit=100),
    )
    with pytest.raises(SimulationLimitExceeded):
        engine.run()


def test_des_max_steps_limit():
    engine = SimulationEngine(
        ToyDesModel({"total_events": 100000}, rng_seed=1),
        {"type": "steps", "value": 100000},
        limits=Limits(max_steps=50, cancel_poll_interval=1),
    )
    result = engine.run()
    assert result.status == "step_limit"
    assert result.steps == 50


def test_cancel_check():
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 0

    engine = SimulationEngine(
        ToyDesModel({"total_events": 100000}, rng_seed=1),
        {"type": "steps", "value": 100000},
        limits=Limits(max_steps=1000, cancel_poll_interval=1),
        cancel_check=cancel,
    )
    result = engine.run()
    assert result.status == "cancelled"


def test_wall_timeout():
    engine = SimulationEngine(
        ToyDesModel({"total_events": 100000}, rng_seed=1),
        {"type": "steps", "value": 100000},
        limits=Limits(max_steps=1000, max_wall_seconds=-1.0, cancel_poll_interval=1),
    )
    result = engine.run()
    assert result.status == "wall_timeout"


def test_des_sim_time_stop_does_not_process_beyond_horizon():
    model = ToyDesModel({"total_events": 100000}, rng_seed=4)
    engine = SimulationEngine(model, {"type": "sim_time", "value": 50.0})
    result = engine.run()
    assert result.status == "completed"
    assert result.metrics["total_time"] <= 50.0 + 1e-9


def test_des_until_empty():
    model = ToyDesModel({"total_events": 20}, rng_seed=8)
    engine = SimulationEngine(model, {"type": "until_empty"})
    result = engine.run()
    assert result.status == "completed"
    assert result.metrics["count"] == 20.0
