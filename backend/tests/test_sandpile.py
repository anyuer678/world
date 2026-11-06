"""BTW sandpile: conservation, stabilization, determinism and checkpoints."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.engine.engines import Limits, SimulationEngine
from app.models.sandpile.model import SandpileModel
from app.models.sandpile.params import SandpileParams


def _model(**overrides) -> SandpileModel:
    params = {"width": 20, "height": 20, "threshold": 4}
    params.update(overrides)
    m = SandpileModel(params, 7)
    m.initialize()
    return m


def test_params_reject_initial_grains_at_or_above_threshold():
    with pytest.raises(ValidationError):
        SandpileParams(threshold=4, initial_grains=4)
    with pytest.raises(ValidationError):
        SandpileParams(threshold=3, initial_grains=3)


def test_grains_are_conserved_except_at_open_edges():
    m = _model()
    for _ in range(500):
        m.step()
    st = m._s
    on_grid = sum(sum(row) for row in st["grid"])
    assert on_grid + st["lost_total"] == st["drops"] == 500


def test_pile_is_stable_after_every_step():
    m = _model()
    for _ in range(300):
        m.step()
        assert max(max(row) for row in m._s["grid"]) < m.params.threshold


def test_avalanches_happen_and_history_is_capped():
    m = _model()
    for _ in range(2000):
        m.step()
    metrics = m.finalize_metrics()
    assert metrics["avalanches"] > 0
    assert metrics["max_avalanche"] >= 1
    # 超过上限时保留最近 128 条（早期写法 del history[:128] 会一次删光，曲线只剩几条）
    assert len(m._s["history"]) == 128


def test_same_seed_is_deterministic():
    def run_once() -> tuple[dict, dict]:
        m = _model()
        for _ in range(300):
            m.step()
        return m.snapshot(), m.finalize_metrics()

    assert run_once() == run_once()


def test_checkpoint_restore_equivalence():
    """引擎级检查点（含 RNG）恢复后与不中断运行逐位一致。"""
    stop = {"type": "steps", "value": 25}
    a = SimulationEngine(SandpileModel({"width": 20, "height": 20, "threshold": 4}, 11), stop)
    a.run(max_steps=7)
    cp = a.checkpoint()
    a.run()
    b = SimulationEngine(SandpileModel({"width": 20, "height": 20, "threshold": 4}, 11), stop)
    b.restore(cp)
    b.run()
    assert a.model.finalize_metrics() == b.model.finalize_metrics()
    assert a.model.snapshot() == b.model.snapshot()


def test_engine_runs_sandpile_with_stop_condition():
    engine = SimulationEngine(
        SandpileModel({"width": 20, "height": 20, "threshold": 4}, 3),
        {"type": "steps", "value": 50},
        limits=Limits(max_steps=1000, max_wall_seconds=10),
    )
    result = engine.run()
    assert result.status == "completed"
    assert result.steps == 50
    assert result.metrics["drops"] == 50.0
