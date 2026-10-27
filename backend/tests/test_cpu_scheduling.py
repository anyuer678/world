import pytest
from pydantic import ValidationError

from app.core.engine.engines import SimulationEngine
from app.models.cpu_scheduling.model import CpuSchedulingModel
from app.models.cpu_scheduling.params import CpuSchedulingParams


def _run(params: dict, stop: dict, seed=42):
    model = CpuSchedulingModel(params, rng_seed=seed)
    engine = SimulationEngine(model, stop)
    return engine.run()


_JOBS = [
    {"arrival": 0.0, "service": 5.0},
    {"arrival": 1.0, "service": 2.0},
    {"arrival": 2.0, "service": 9.0},
    {"arrival": 3.0, "service": 4.0},
]


def test_single_job_exact_metrics():
    result = _run({"jobs": [{"arrival": 0.0, "service": 5.0}]}, {"type": "steps", "value": 10})
    m = result.metrics
    assert m["arrived"] == 1.0
    assert m["completed"] == 1.0
    assert m["avg_waiting_time"] == 0.0
    assert m["avg_turnaround_time"] == 5.0
    assert m["avg_response_time"] == 0.0
    assert m["cpu_utilization"] == 1.0
    assert m["sim_time_end"] == 5.0


def test_fcfs_explicit_workload_exact():
    """FCFS: jobs run in arrival order; waits = 0, 4, 5, 13."""
    result = _run({"jobs": _JOBS, "strategy": "fcfs"}, {"type": "steps", "value": 100})
    m = result.metrics
    assert m["completed"] == 4.0
    # completion times: 5, 7, 16, 20 -> turnarounds 5, 6, 14, 17 -> waits 0, 4, 5, 13
    assert m["avg_waiting_time"] == pytest.approx((0 + 4 + 5 + 13) / 4)
    assert m["avg_turnaround_time"] == pytest.approx((5 + 6 + 14 + 17) / 4)
    # response times (non-preemptive = waiting times): 0, 4, 5, 13
    assert m["avg_response_time"] == pytest.approx((0 + 4 + 5 + 13) / 4)
    # CPU busy [0, 20) without gaps: utilization 1.0
    assert m["cpu_utilization"] == pytest.approx(1.0)
    assert m["sim_time_end"] == pytest.approx(20.0)


def test_sjf_beats_fcfs_on_average_wait():
    """Same workload (same seed, generated): non-preemptive SJF minimizes avg wait."""
    base = {"num_jobs": 300, "arrival_rate": 0.8, "service_min": 0.1, "service_max": 4.0}
    fcfs = _run({**base, "strategy": "fcfs"}, {"type": "steps", "value": 200_000}, seed=88)
    sjf = _run({**base, "strategy": "sjf"}, {"type": "steps", "value": 200_000}, seed=88)
    assert fcfs.metrics["completed"] == sjf.metrics["completed"] == 300.0
    assert sjf.metrics["avg_waiting_time"] <= fcfs.metrics["avg_waiting_time"]
    assert sjf.metrics["completed"] > 0


def test_priority_prefers_small_priority_value():
    jobs = [
        {"arrival": 0.0, "service": 3.0, "priority": 5},
        {"arrival": 0.5, "service": 1.0, "priority": 1},
    ]
    result = _run({"jobs": jobs, "strategy": "priority"}, {"type": "steps", "value": 50})
    m = result.metrics
    # priority-5 job runs [0,3); priority-1 job runs [3,4)
    assert m["avg_response_time"] == pytest.approx((0 + 2.5) / 2)
    assert m["sim_time_end"] == pytest.approx(4.0)


def test_rr_quantum_slicing_exact():
    """A(service 5) arrives 0, B(service 2) arrives 1, quantum 2:
    A[0,2) B[2,4) A[4,6) A[6,7)."""
    result = _run(
        {"jobs": [{"arrival": 0.0, "service": 5.0}, {"arrival": 1.0, "service": 2.0}],
         "strategy": "rr", "quantum": 2.0},
        {"type": "steps", "value": 100},
    )
    m = result.metrics
    assert m["completed"] == 2.0
    assert m["avg_turnaround_time"] == pytest.approx((7.0 + 3.0) / 2)
    assert m["avg_waiting_time"] == pytest.approx((2.0 + 1.0) / 2)
    assert m["avg_response_time"] == pytest.approx((0.0 + 1.0) / 2)
    assert m["cpu_utilization"] == pytest.approx(1.0)
    assert m["sim_time_end"] == pytest.approx(7.0)


def test_rr_quantum_larger_than_service_behaves_like_fcfs():
    jobs = [
        {"arrival": 0.0, "service": 2.0},
        {"arrival": 1.0, "service": 3.0},
    ]
    rr = _run({"jobs": jobs, "strategy": "rr", "quantum": 100.0}, {"type": "steps", "value": 100})
    fcfs = _run({"jobs": jobs, "strategy": "fcfs"}, {"type": "steps", "value": 100})
    assert rr.metrics == fcfs.metrics


def test_idle_gap_utilization_below_one():
    jobs = [
        {"arrival": 0.0, "service": 1.0},
        {"arrival": 10.0, "service": 1.0},
    ]
    result = _run({"jobs": jobs, "strategy": "fcfs"}, {"type": "steps", "value": 50})
    m = result.metrics
    assert m["cpu_utilization"] == pytest.approx(2.0 / 11.0)


def test_determinism_generated_workload_same_seed():
    params = {"strategy": "rr", "quantum": 0.5, "num_jobs": 150, "arrival_rate": 1.5}
    a = _run(params, {"type": "steps", "value": 20_000}, seed=21)
    b = _run(params, {"type": "steps", "value": 20_000}, seed=21)
    assert a.metrics == b.metrics
    assert a.sim_time == b.sim_time
    c = _run(params, {"type": "steps", "value": 20_000}, seed=22)
    assert c.metrics != a.metrics


def test_checkpoint_restore_equivalence_mid_run():
    params = {"strategy": "rr", "quantum": 0.8, "num_jobs": 120, "arrival_rate": 1.2}
    stop = {"type": "steps", "value": 5_000}
    a = SimulationEngine(CpuSchedulingModel(params, rng_seed=64), stop)
    a.run(max_steps=97)
    cp = a.checkpoint()
    a.run()
    b = SimulationEngine(CpuSchedulingModel(params, rng_seed=64), stop)
    b.restore(cp)
    b.run()
    assert a.model.finalize_metrics() == b.model.finalize_metrics()
    assert a.model.snapshot() == b.model.snapshot()


def test_param_validation_boundaries():
    with pytest.raises(ValidationError):
        CpuSchedulingParams(jobs=[])
    with pytest.raises(ValidationError):
        CpuSchedulingParams(jobs=[{"arrival": -1.0, "service": 1.0}])
    with pytest.raises(ValidationError):
        CpuSchedulingParams(jobs=[{"arrival": 0.0, "service": 0.0}])
    with pytest.raises(ValidationError):
        CpuSchedulingParams(strategy="lottery")
    with pytest.raises(ValidationError):
        CpuSchedulingParams(quantum=0)
    with pytest.raises(ValidationError):
        CpuSchedulingParams(service_min=2.0, service_max=1.0)
    with pytest.raises(ValidationError):
        CpuSchedulingParams(priority_low=5, priority_high=1)
    with pytest.raises(ValidationError):
        CpuSchedulingParams(unknown_param=1)
    ok = CpuSchedulingParams(num_jobs=1)
    assert ok.strategy == "fcfs" and ok.quantum == 1.0
