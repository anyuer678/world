import pytest
from pydantic import ValidationError

from app.core.engine.engines import SimulationEngine
from app.models.cache_sim.model import CacheModel
from app.models.cache_sim.params import CacheParams


def _run(params: dict, steps: int, seed=42):
    model = CacheModel(params, rng_seed=seed)
    engine = SimulationEngine(model, {"type": "steps", "value": steps})
    return engine.run()


_SEQ = [1, 2, 1, 3, 1, 2]


def test_lru_known_sequence():
    result = _run({"accesses": _SEQ, "capacity": 2, "policy": "lru"}, 6)
    m = result.metrics
    assert m["accesses"] == 6.0
    assert m["hits"] == 2.0
    assert m["misses"] == 4.0
    assert m["hit_rate"] == pytest.approx(2 / 6)
    assert m["total_cost"] == pytest.approx(2 * 1.0 + 4 * 10.0)


def test_fifo_same_sequence_fewer_hits():
    """FIFO evicts key 1 (oldest) despite its recent hit; LRU keeps it."""
    result = _run({"accesses": _SEQ, "capacity": 2, "policy": "fifo"}, 6)
    m = result.metrics
    assert m["hits"] == 1.0
    assert m["misses"] == 5.0


def test_lfu_evicts_least_frequently_used():
    result = _run({"accesses": [1, 1, 2, 3, 1], "capacity": 2, "policy": "lfu"}, 5)
    m = result.metrics
    # miss 1, hit 1 (freq 2), miss 2, miss 3 (evict 2, freq 1), hit 1
    assert m["hits"] == 2.0
    assert m["misses"] == 3.0


def test_capacity_one_boundary():
    result = _run({"accesses": [7, 7, 8, 8, 7], "capacity": 1, "policy": "lru"}, 5)
    m = result.metrics
    assert m["hits"] == 2.0
    assert m["misses"] == 3.0
    assert m["hit_rate"] == pytest.approx(0.4)


def test_access_sequence_cycles_when_exhausted():
    result = _run({"accesses": [5, 5, 6], "capacity": 4, "policy": "lru"}, 9)
    m = result.metrics
    assert m["accesses"] == 9.0
    # cycle 1: miss 5, hit 5, miss 6; both keys stay cached (capacity 4)
    assert m["misses"] == 2.0
    assert m["hits"] == 7.0


def test_zipf_locality_raises_hit_rate():
    alpha = _run(
        {"num_keys": 50, "zipf_exponent": 1.2, "capacity": 5, "policy": "lru"}, 4000, seed=7
    ).metrics["hit_rate"]
    uniform = _run(
        {"num_keys": 100, "zipf_exponent": 0.0, "capacity": 5, "policy": "lru"}, 4000, seed=7
    ).metrics["hit_rate"]
    # locality keeps the hot top-5 keys resident; the uniform stream thrashes.
    assert alpha > 0.3, alpha
    assert uniform < 0.2, uniform
    assert alpha > uniform * 3, (alpha, uniform)


def test_determinism_same_seed_generated_stream():
    params = {"num_keys": 30, "zipf_exponent": 1.0, "capacity": 6, "policy": "random"}
    a = _run(params, 1500, seed=99)
    b = _run(params, 1500, seed=99)
    assert a.metrics == b.metrics
    c = _run(params, 1500, seed=100)
    assert c.metrics != a.metrics


def test_checkpoint_restore_equivalence():
    params = {"num_keys": 40, "zipf_exponent": 1.0, "capacity": 6, "policy": "lru"}
    stop = {"type": "steps", "value": 3000}
    a = SimulationEngine(CacheModel(params, rng_seed=11), stop)
    a.run(max_steps=1234)
    cp = a.checkpoint()
    a.run()
    b = SimulationEngine(CacheModel(params, rng_seed=11), stop)
    b.restore(cp)
    b.run()
    assert a.model.finalize_metrics() == b.model.finalize_metrics()
    assert a.model.snapshot() == b.model.snapshot()


def test_param_validation_boundaries():
    with pytest.raises(ValidationError):
        CacheParams(capacity=0)
    with pytest.raises(ValidationError):
        CacheParams(policy="mru")
    with pytest.raises(ValidationError):
        CacheParams(accesses=[])
    with pytest.raises(ValidationError):
        CacheParams(accesses=[1, -2])
    with pytest.raises(ValidationError):
        CacheParams(zipf_exponent=-0.5)
    with pytest.raises(ValidationError):
        CacheParams(cost_miss=0)
    with pytest.raises(ValidationError):
        CacheParams(num_keys=1)
    with pytest.raises(ValidationError):
        CacheParams(unknown_param=1)
    ok = CacheParams()
    assert ok.capacity == 8 and ok.policy == "lru" and ok.zipf_exponent == 0.0
