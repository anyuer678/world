import pytest

from app.core.engine.engines import SimulationEngine
from app.models.queueing.model import QueueingModel
from app.models.queueing.params import QueueingParams
from pydantic import ValidationError


def _run(params: dict, stop: dict, seed=42):
    model = QueueingModel(params, rng_seed=seed)
    engine = SimulationEngine(model, stop)
    return engine.run()


def test_determinism_same_seed():
    params = {"arrival": {"kind": "poisson", "rate": 1.2}, "service": {"kind": "exponential", "mean": 0.7}, "servers": 2}
    a = _run(params, {"type": "steps", "value": 5000}, seed=123)
    b = _run(params, {"type": "steps", "value": 5000}, seed=123)
    assert a.metrics == b.metrics
    assert a.sim_time == b.sim_time
    assert a.steps == b.steps


def test_different_seed_differs():
    params = {"arrival": {"kind": "poisson", "rate": 1.2}, "service": {"kind": "exponential", "mean": 0.7}, "servers": 2}
    a = _run(params, {"type": "steps", "value": 5000}, seed=1)
    b = _run(params, {"type": "steps", "value": 5000}, seed=2)
    assert a.metrics["arrived"] != b.metrics["arrived"] or a.sim_time != b.sim_time


def test_mm1_theoretical_values():
    """M/M/1 with rho=0.5: Wq = 0.5, W = 1.0, L = 1.0, utilization = 0.5."""
    params = {
        "arrival": {"kind": "poisson", "rate": 1.0},
        "service": {"kind": "exponential", "mean": 0.5},
        "servers": 1,
        "warmup_customers": 2000,
    }
    result = _run(params, {"type": "steps", "value": 120000}, seed=2026)
    m = result.metrics
    assert m["arrived"] > 10000
    assert abs(m["avg_waiting_time"] - 0.5) < 0.15, m["avg_waiting_time"]
    assert abs(m["avg_response_time"] - 1.0) < 0.2, m["avg_response_time"]
    assert abs(m["utilization"] - 0.5) < 0.05, m["utilization"]
    assert abs(m["throughput"] - 1.0) < 0.05, m["throughput"]


def test_mm1_1_erlang_loss():
    """M/M/1/1 blocking: P_B = rho / (1 + rho); lambda=2, mu=3 -> rho=2/3, P_B=0.4."""
    params = {
        "arrival": {"kind": "poisson", "rate": 2.0},
        "service": {"kind": "exponential", "mean": 1.0 / 3.0},
        "servers": 1,
        "capacity": 1,
        "warmup_customers": 2000,
    }
    result = _run(params, {"type": "steps", "value": 120000}, seed=777)
    m = result.metrics
    assert abs(m["drop_rate"] - 0.4) < 0.03, m["drop_rate"]
    assert 0.0 < m["drop_rate"] < 1.0
    assert m["final_queue_length"] <= 1


def test_deterministic_arrival_and_service_zero_wait():
    """Interarrival 1.0 > service 0.5 => nobody ever waits, no drops with capacity=1."""
    params = {
        "arrival": {"kind": "deterministic", "rate": 1.0},
        "service": {"kind": "deterministic", "mean": 0.5},
        "servers": 1,
        "capacity": 1,
    }
    result = _run(params, {"type": "steps", "value": 2000}, seed=5)
    m = result.metrics
    assert m["avg_waiting_time"] == 0.0
    assert m["drop_rate"] == 0.0
    assert m["arrived"] == 1000


def test_conservation_with_finite_capacity():
    params = {
        "arrival": {"kind": "poisson", "rate": 3.0},
        "service": {"kind": "exponential", "mean": 1.0},
        "servers": 1,
        "capacity": 3,
    }
    result = _run(params, {"type": "steps", "value": 20000}, seed=9)
    m = result.metrics
    assert m["served"] + m["dropped"] <= m["arrived"]
    assert m["served"] + m["dropped"] >= m["arrived"] - 3  # at most `capacity` customers remain in system
    assert 0.0 < m["drop_rate"] < 1.0


def test_lcfs_runs_and_is_deterministic():
    params = {
        "arrival": {"kind": "poisson", "rate": 2.0},
        "service": {"kind": "exponential", "mean": 0.6},
        "servers": 1,
        "discipline": "lcfs",
    }
    a = _run(params, {"type": "steps", "value": 8000}, seed=3)
    b = _run(params, {"type": "steps", "value": 8000}, seed=3)
    assert a.metrics == b.metrics
    assert a.metrics["served"] > 100


def test_warmup_excludes_early_metrics():
    params = {
        "arrival": {"kind": "poisson", "rate": 2.0},
        "service": {"kind": "exponential", "mean": 1.0},
        "servers": 1,
        "capacity": 1,
        "warmup_customers": 5000,
    }
    result = _run(params, {"type": "steps", "value": 2000}, seed=11)
    m = result.metrics
    assert m["drop_rate"] == 0.0
    assert m["avg_response_time"] == 0.0
    assert m["arrived"] < 5000  # run stopped before warmup finished


def test_checkpoint_restore_equivalence_mid_queue():
    params = {
        "arrival": {"kind": "poisson", "rate": 2.0},
        "service": {"kind": "exponential", "mean": 0.6},
        "servers": 2,
    }
    stop = {"type": "steps", "value": 20000}
    a = SimulationEngine(QueueingModel(params, rng_seed=64), stop)
    a.run(max_steps=777)
    cp = a.checkpoint()
    a.run()
    b = SimulationEngine(QueueingModel(params, rng_seed=64), stop)
    b.restore(cp)
    b.run()
    assert a.model.finalize_metrics() == b.model.finalize_metrics()


def test_param_validation_boundaries():
    with pytest.raises(ValidationError):
        QueueingParams(servers=0)
    with pytest.raises(ValidationError):
        QueueingParams(capacity=0)
    with pytest.raises(ValidationError):
        QueueingParams(arrival={"kind": "poisson", "rate": 0})
    with pytest.raises(ValidationError):
        QueueingParams(service={"kind": "exponential", "mean": -1})
    with pytest.raises(ValidationError):
        QueueingParams(service={"kind": "uniform", "mean": 1.0, "half_spread": 1.0})
    with pytest.raises(ValidationError):
        QueueingParams(discipline="sriot")
    with pytest.raises(ValidationError):
        QueueingParams(unknown_param=1)
    ok = QueueingParams(servers=4, capacity=10)
    assert ok.capacity == 10 and ok.warmup_customers == 0
