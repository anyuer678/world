"""Traffic network model: params validation, determinism, restore
equivalence, theoretical timing, signal effect, occupancy invariants, and
the API session roundtrip."""
from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.core.engine.engines import Limits, TimeSteppedEngine
from app.core.schema.spec import example_spec_for, validate_spec
from app.main import create_app
from app.models.traffic_network import TrafficNetworkModel
from app.models.traffic_network.params import TrafficParams
from app.core.registry import registry


LIMITS = Limits(max_steps=100000, max_wall_seconds=30, zero_delay_chain_limit=10000, cancel_poll_interval=1000)


def _engine(params, seed=42, stop_value=100000):
    m = TrafficNetworkModel(params, seed)
    e = TimeSteppedEngine(m, {"type": "steps", "value": stop_value}, LIMITS, None)
    return e


def _ring(scale=30.0):
    nodes = [
        {"id": f"n{i}", "x": scale * math.cos(2 * math.pi * i / 6), "y": scale * math.sin(2 * math.pi * i / 6)}
        for i in range(6)
    ]
    edges = [{"src": f"n{i}", "dst": f"n{(i + 1) % 6}"} for i in range(6)]
    return {"nodes": nodes, "edges": edges, "signals": []}


# ------------------------------------------------------------------ params
def test_params_validation_errors():
    with pytest.raises(ValueError, match="unique"):
        TrafficParams(nodes=[{"id": "a", "x": 0, "y": 0}, {"id": "a", "x": 1, "y": 1}],
                      edges=[{"src": "a", "dst": "a"}])
    base_nodes = [{"id": "a", "x": 0, "y": 0}, {"id": "b", "x": 10, "y": 0}]
    with pytest.raises(ValueError, match="not a declared node"):
        TrafficParams(nodes=base_nodes, edges=[{"src": "a", "dst": "zz"}])
    with pytest.raises(ValueError, match="self-loop"):
        TrafficParams(nodes=base_nodes, edges=[{"src": "a", "dst": "a"}])
    with pytest.raises(ValueError, match="duplicate directed edge"):
        TrafficParams(nodes=base_nodes, edges=[{"src": "a", "dst": "b"}, {"src": "a", "dst": "b"}])
    with pytest.raises(ValueError, match="exceeds cap"):
        TrafficParams(nodes=base_nodes, edges=[{"src": "a", "dst": "b", "length": 20000}])
    with pytest.raises(ValueError, match="not a declared node"):
        TrafficParams(nodes=base_nodes, edges=[{"src": "a", "dst": "b"}],
                      signals=[{"node": "zz", "cycle": 4, "group_a": ["a"], "group_b": ["b"]}])
    # signal groups must exactly cover incoming sources
    with pytest.raises(ValueError, match="exactly cover"):
        TrafficParams(nodes=base_nodes, edges=[{"src": "a", "dst": "b"}],
                      signals=[{"node": "b", "cycle": 4, "group_a": [], "group_b": ["b"]}])
    with pytest.raises(ValueError, match="overlap"):
        TrafficParams(nodes=base_nodes, edges=[{"src": "a", "dst": "b"}],
                      signals=[{"node": "b", "cycle": 4, "group_a": ["a"], "group_b": ["a", "b"]}])
    # coincident nodes without explicit length are rejected
    with pytest.raises(ValueError, match="coincident"):
        TrafficParams(nodes=[{"id": "a", "x": 0, "y": 0}, {"id": "b", "x": 0, "y": 0}],
                      edges=[{"src": "a", "dst": "b"}])
    with pytest.raises(ValueError, match="not declared"):
        TrafficParams(nodes=base_nodes, edges=[{"src": "a", "dst": "b"}], spawn_nodes=["zz"])


def test_example_spec_is_valid():
    spec, model_cls = validate_spec(example_spec_for(TrafficNetworkModel), registry)
    assert model_cls is TrafficNetworkModel
    assert spec.params["nodes"]


# ------------------------------------------------- determinism + restore
def test_determinism_same_seed():
    p = _ring()
    p.update(v_max=2, slow_prob=0.3, spawn_rate=0.5)
    e1 = _engine(p, seed=99)
    e2 = _engine(p, seed=99)
    for _ in range(80):
        e1.step()
        e2.step()
    assert e1.model.dump_state() == e2.model.dump_state()
    assert e1.model.finalize_metrics() == e2.model.finalize_metrics()


def test_seed_changes_outcome():
    p = _ring()
    p.update(slow_prob=0.5, spawn_rate=0.5)
    e1 = _engine(p, seed=1)
    e2 = _engine(p, seed=2)
    for _ in range(60):
        e1.step()
        e2.step()
    assert e1.model.dump_state() != e2.model.dump_state()


def test_restore_continuation_equivalence():
    p = _ring()
    p.update(slow_prob=0.2, spawn_rate=0.5)
    e1 = _engine(p, seed=7)
    e2 = _engine(p, seed=7)
    for _ in range(30):
        e1.step()
    cp = e1.checkpoint()
    e3 = _engine(p, seed=7)
    e3.restore(cp)
    for _ in range(25):
        e1.step()
        e3.step()
    assert e1.model.dump_state() == e3.model.dump_state()
    # untouched engine differs (different tick count)
    e2.step()
    assert e1.model.dump_state() != e2.model.dump_state()


# ------------------------------------------------------ theoretical check
def test_single_vehicle_corridor_travel_time():
    # 30-cell road, v_max=2, one vehicle: enters tick 1, moves ticks 2..16,
    # exits tick 16 -> travel time exactly 15 ticks.
    p = {"nodes": [{"id": "A", "x": 0, "y": 0}, {"id": "B", "x": 30, "y": 0}],
         "edges": [{"src": "A", "dst": "B"}],
         "signals": [],
         "v_max": 2, "slow_prob": 0, "spawn_rate": 1.0,
         "spawn_nodes": ["A"], "spawn_until": 1}
    e = _engine(p, seed=1)
    for _ in range(30):
        e.step()
    m = e.model.finalize_metrics()
    assert m["spawned"] == 1.0
    assert m["completed"] == 1.0
    assert m["active_vehicles"] == 0.0
    assert m["avg_travel_time"] == pytest.approx(15.0)


def test_ring_drains_completely():
    p = _ring()
    # slow_prob=0 keeps the stream deterministic. A fresh vehicle spawns at
    # v=0 right behind its predecessor (gap 0), cannot move on its spawn
    # tick, and holds the entry cell one extra tick — so at rate 1.0 the
    # entry admits one vehicle every other tick: 6 spawns in ticks 1..10.
    p.update(v_max=2, slow_prob=0, spawn_rate=1.0, spawn_nodes=["n0"], spawn_until=10)
    e = _engine(p, seed=5)
    for _ in range(140):
        e.step()
    m = e.model.finalize_metrics()
    assert m["spawned"] == 6.0
    assert m["completed"] == 6.0
    assert m["active_vehicles"] == 0.0
    assert m["avg_travel_time"] > 0


# ------------------------------------------------------------- signal test
_CROSSROAD = {
    "nodes": [
        {"id": "N", "x": 0, "y": -30}, {"id": "E", "x": 30, "y": 0},
        {"id": "S", "x": 0, "y": 30}, {"id": "W", "x": -30, "y": 0},
        {"id": "C", "x": 0, "y": 0},
    ],
    "edges": [
        {"src": "N", "dst": "C"}, {"src": "C", "dst": "S"},
        {"src": "S", "dst": "C"}, {"src": "C", "dst": "N"},
        {"src": "E", "dst": "C"}, {"src": "C", "dst": "W"},
        {"src": "W", "dst": "C"}, {"src": "C", "dst": "E"},
    ],
}


def test_signal_reduces_throughput():
    heavy = {"v_max": 2, "slow_prob": 0.15, "spawn_rate": 0.5}
    p_free = {**_CROSSROAD, "signals": [], **heavy}
    p_signal = {**_CROSSROAD,
                "signals": [{"node": "C", "cycle": 8, "offset": 0,
                             "group_a": ["N", "S"], "group_b": ["E", "W"]}],
                **heavy}
    e_free = _engine(p_free, seed=11)
    e_sig = _engine(p_signal, seed=11)
    for _ in range(150):
        e_free.step()
        e_sig.step()
    m_free = e_free.model.finalize_metrics()
    m_sig = e_sig.model.finalize_metrics()
    assert m_sig["completed"] < m_free["completed"]
    # signal forces waiting and drags down the average speed
    assert m_sig["avg_wait_ticks"] > m_free["avg_wait_ticks"]
    assert m_sig["mean_speed"] < m_free["mean_speed"]


# -------------------------------------------------------------- invariants
def test_no_double_occupancy_invariant():
    p = {**_CROSSROAD,
         "signals": [{"node": "C", "cycle": 8, "offset": 0,
                      "group_a": ["N", "S"], "group_b": ["E", "W"]}],
         "v_max": 2, "slow_prob": 0.3, "spawn_rate": 0.6, "max_vehicles": 120}
    e = _engine(p, seed=13)
    for _ in range(150):
        e.step()
        st = e.model._s
        occupied: dict[int, int] = {}
        for ei, cells in enumerate(st["cells"]):
            for ci, vid in enumerate(cells):
                if vid:
                    assert vid not in occupied, f"vehicle {vid} on two cells"
                    occupied[vid] = (ei << 16) | ci
        veh_cells = {v["id"]: (v["e"] << 16) | v["c"] for v in st["vehicles"]}
        assert occupied == veh_cells


def test_max_vehicles_cap():
    p = _ring()
    p.update(slow_prob=0.2, spawn_rate=1.0, max_vehicles=5)
    e = _engine(p, seed=3)
    for _ in range(200):
        e.step()
    st = e.model._s
    assert max(st["history"]) <= 5
    assert len(st["vehicles"]) <= 5


# --------------------------------------------------------------------- API
def test_traffic_api_session_roundtrip(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        models = client.get("/api/models").json()["models"]
        assert any(m["model_id"] == "traffic_network" for m in models)

        spec = {
            "schema_version": 1,
            "model_id": "traffic_network",
            "params": {**_CROSSROAD,
                       "signals": [{"node": "C", "cycle": 8, "offset": 0,
                                    "group_a": ["N", "S"], "group_b": ["E", "W"]}],
                       "v_max": 2, "slow_prob": 0.1, "spawn_rate": 0.6},
            "stop_condition": {"type": "steps", "value": 60},
            "seed": 21,
        }
        r = client.post("/api/sessions", json={"spec": spec})
        assert r.status_code == 201, r.text
        sid = r.json()["session_id"]
        r = client.post(f"/api/sessions/{sid}/step", json={"n": 5})
        assert r.status_code == 200, r.text
        state = r.json()["snapshot"]["state"]
        assert len(state["nodes"]) == 5
        assert len(state["edges"]) == 8
        assert state["signals"][0]["node"] == "C"
        assert isinstance(state["vehicles"], list)
        assert len(state["edge_load"]) == 8
        r = client.post(f"/api/sessions/{sid}/run")
        assert r.status_code == 200, r.text
        final = client.get(f"/api/sessions/{sid}").json()
        assert final["status"] in ("completed", "step_limit")
        metrics = final["snapshot"]["metrics"]
        assert metrics["ticks"] == 60.0
        assert metrics["spawned"] > 0
        assert "avg_travel_time" in metrics

        r = client.post("/api/experiments", json={"name": "traffic api", "spec": spec})
        assert r.status_code == 201, r.text
        exp_id = r.json()["id"]
        client.post(f"/api/experiments/{exp_id}/run")
        import time
        deadline = time.time() + 20
        while time.time() < deadline:
            res = client.get(f"/api/experiments/{exp_id}/result").json()
            if res["experiment"]["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)
        assert res["experiment"]["status"] == "completed"
        run = res["runs"][0]
        assert run["metrics"]["ticks"] == 60.0
        assert run["result_sha256"]
