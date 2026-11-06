"""Phase 4: batch experiments — grid building, seed strategies, retries,
cancellation, statistics and sensitivity, and the REST API surface."""
from __future__ import annotations

import math
import time

import pytest
from fastapi.testclient import TestClient

from app.core.schema.errors import SpecValidationError
from app.core.stats import mean, pearson, quantile, sample_std, summarize
from app.main import create_app
from app.services.batch_service import BatchService
from app.services.experiment_service import ConflictError, NotFoundError
from conftest import DiscreteEventModel, WorldLabParams, registry


# ------------------------------------------------------------------ helpers
def _spec(**overrides):
    spec = {
        "schema_version": 1,
        "model_id": "toy_des",
        "params": {"total_events": 200, "delay_mean": 1.0},
        "stop_condition": {"type": "until_empty"},
        "seed": 1000,
    }
    spec.update(overrides)
    return spec


def _wait_terminal(svc, batch_id, timeout=20):
    deadline = time.time() + timeout
    b = None
    while time.time() < deadline:
        b = svc.get_batch(batch_id, include_summary=False)
        if b["status"] in ("completed", "failed", "cancelled"):
            return b
        time.sleep(0.05)
    raise AssertionError(f"batch {batch_id} did not finish in {timeout}s: {b and b['status']}")


class AlwaysFailsParams(WorldLabParams):
    pass


class AlwaysFailsModel(DiscreteEventModel):
    model_id = "toy_always_fails"
    display_name = "Always fails"
    description = "Toy model whose initialize always raises, for retry tests."
    model_type = "discrete_event"
    version = "1.0.0"
    param_model = AlwaysFailsParams

    def initialize(self, ctx) -> None:
        raise RuntimeError("boom")

    def handle_event(self, event, ctx) -> None:  # pragma: no cover - never reached
        pass

    def dump_state(self):
        return {}

    def load_state(self, state):
        pass

    def snapshot(self):
        return {}

    def finalize_metrics(self):
        return {}


registry.register(AlwaysFailsModel)


class SlowDesParams(WorldLabParams):
    total_events: int = 100
    delay_mean: float = 1.0


class SlowDesModel(DiscreteEventModel):
    model_id = "toy_slow_des"
    display_name = "Slow toy DES"
    description = "Toy DES that sleeps per event; long-lived item for cancel tests."
    model_type = "discrete_event"
    version = "1.0.0"
    param_model = SlowDesParams

    def initialize(self, ctx) -> None:
        self.count = 0
        ctx.schedule(1.0, "tick")

    def handle_event(self, event, ctx) -> None:
        self.count += 1
        # 0.5ms/event: 100k steps (default_max_steps cap) ≈ 50s, and sleep
        # releases the GIL so the cancel request is never starved. A fast
        # item dies of step_limit in ~0.25s and races the cancel call.
        time.sleep(0.0005)
        if self.count < self.params.total_events:
            ctx.schedule(self.rng.expovariate(1.0 / self.params.delay_mean), "tick")

    def dump_state(self):
        return {"count": self.count}

    def load_state(self, state):
        self.count = state["count"]

    def snapshot(self):
        return {"count": self.count}

    def finalize_metrics(self):
        return {"count": float(self.count)}


registry.register(SlowDesModel)


class FailOnceParams(WorldLabParams):
    key: int = 0


class FailOnceModel(DiscreteEventModel):
    """Fails the first initialize for each key, succeeds afterwards (R97 retry test)."""

    model_id = "toy_fail_once"
    display_name = "Fail once"
    description = "Toy model that fails its first run per key, then succeeds."
    model_type = "discrete_event"
    version = "1.0.0"
    param_model = FailOnceParams
    _seen: set[int] = set()

    def initialize(self, ctx) -> None:
        key = int(self.params.key)
        if key not in FailOnceModel._seen:
            FailOnceModel._seen.add(key)
            raise RuntimeError(f"first attempt fails for key {key}")
        self._s = {"key": key}

    def handle_event(self, event, ctx) -> None:  # pragma: no cover - no events scheduled
        pass

    def dump_state(self):
        return dict(self._s)

    def load_state(self, state):
        self._s = dict(state)

    def snapshot(self):
        return dict(self._s)

    def finalize_metrics(self):
        return {"key": float(self.params.key)}


registry.register(FailOnceModel)


@pytest.fixture()
def batches(settings):
    b = BatchService(settings, registry)
    yield b
    b.shutdown()


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------- stats
def test_stats_basics():
    assert mean([1.0, 2.0, 3.0]) == 2.0
    assert sample_std([1.0, 2.0, 3.0]) == pytest.approx(1.0)
    assert sample_std([5.0]) == 0.0
    assert quantile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == 3.0
    assert quantile([1.0, 2.0, 3.0, 4.0, 5.0], 0.9) == pytest.approx(4.6)
    assert quantile([7.0], 0.9) == 7.0
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert pearson([1, 2, 3], [6, 4, 2]) == pytest.approx(-1.0)
    assert pearson([1, 1, 1], [1, 2, 3]) is None
    assert pearson([1], [2]) is None
    s = summarize([1.0, 2.0, 3.0, 4.0])
    assert s["n"] == 4
    assert s["mean"] == 2.5
    assert s["std"] == pytest.approx(math.sqrt(5 / 3))
    assert s["p50"] == 2.5
    assert s["p90"] == pytest.approx(3.7)
    half = 1.96 * math.sqrt(5 / 3) / 2
    assert s["ci95_low"] == pytest.approx(2.5 - half)
    assert s["ci95_high"] == pytest.approx(2.5 + half)
    assert summarize([]) == {"n": 0}


# ------------------------------------------------------------ grid + seeds
def test_grid_and_seed_strategies(batches):
    for strategy, expected in [
        ("fixed", [1000] * 6),
        ("per_repeat_increment", [1000, 1001, 1002, 1000, 1001, 1002]),
        ("unique", [1000, 1001, 1002, 1003, 1004, 1005]),
    ]:
        b = batches.create(
            f"grid-{strategy}",
            _spec(),
            {"delay_mean": [0.5, 2.0]},
            repeats=3,
            seed_strategy=strategy,
        )
        assert b["total_items"] == 6
        assert b["status"] in ("queued", "running")
        items = batches.list_items(b["id"], limit=100)["items"]
        assert [i["seed"] for i in items] == expected
        combos = [i["params"] for i in items]
        assert combos == [
            {"delay_mean": 0.5}, {"delay_mean": 0.5}, {"delay_mean": 0.5},
            {"delay_mean": 2.0}, {"delay_mean": 2.0}, {"delay_mean": 2.0},
        ]


def test_empty_grid_is_pure_repeats(batches):
    b = batches.create("repeats", _spec(), {}, repeats=4, seed_strategy="fixed")
    assert b["total_items"] == 4
    items = batches.list_items(b["id"], limit=100)["items"]
    assert len({i["seed"] for i in items}) == 1
    _wait_terminal(batches, b["id"])
    got = batches.list_items(b["id"], limit=100)["items"]
    assert all(i["status"] == "completed" for i in got)
    assert len({i["result_sha256"] for i in got}) == 1


def test_grid_validation_errors(batches):
    with pytest.raises(SpecValidationError):
        batches.create("bad-key", _spec(), {"no_such_param": [1]}, repeats=1)
    with pytest.raises(SpecValidationError):
        batches.create("bad-value", _spec(), {"total_events": [1.5]}, repeats=1)
    with pytest.raises(SpecValidationError):
        batches.create("bad-strategy", _spec(), {}, repeats=1, seed_strategy="nope")
    with pytest.raises(SpecValidationError):
        batches.create("too-big", _spec(), {"delay_mean": [0.1] * 21}, repeats=100)
    with pytest.raises(SpecValidationError):
        batches.create("", _spec(), {}, repeats=1)


# ----------------------------------------------------------- run + determinism
def test_batch_runs_and_determinism(batches):
    b1 = batches.create(
        "det-1", _spec(), {"delay_mean": [0.5, 2.0]}, repeats=2, seed_strategy="fixed"
    )
    b2 = batches.create(
        "det-2", _spec(), {"delay_mean": [0.5, 2.0]}, repeats=2, seed_strategy="fixed"
    )
    for b in (b1, b2):
        assert _wait_terminal(batches, b["id"])["status"] == "completed"
    items1 = batches.list_items(b1["id"], limit=100)["items"]
    items2 = batches.list_items(b2["id"], limit=100)["items"]
    assert [i["result_sha256"] for i in items1] == [i["result_sha256"] for i in items2]
    # fixed strategy: both repeats of a combo share one seed -> identical results
    assert items1[0]["result_sha256"] == items1[1]["result_sha256"]
    assert items1[2]["result_sha256"] == items1[3]["result_sha256"]
    # different delay_mean -> different results
    assert items1[0]["result_sha256"] != items1[2]["result_sha256"]


def test_per_repeat_increment_varies_repeats(batches):
    b = batches.create(
        "inc", _spec(), {"delay_mean": [1.0]}, repeats=3, seed_strategy="per_repeat_increment"
    )
    _wait_terminal(batches, b["id"])
    items = batches.list_items(b["id"], limit=100)["items"]
    assert items[0]["result_sha256"] != items[1]["result_sha256"]
    for i in items:
        assert i["metrics"]["count"] == 200.0


# ---------------------------------------------------------------- retry/fail
def test_retry_counts_attempts_then_fails(batches):
    b = batches.create(
        "retry", {"schema_version": 1, "model_id": "toy_always_fails", "seed": 1},
        {}, repeats=1, max_retries=2,
    )
    assert _wait_terminal(batches, b["id"])["status"] == "failed"
    item = batches.list_items(b["id"], limit=10)["items"][0]
    assert item["status"] == "failed"
    assert item["attempts"] == 3
    assert "boom" in item["error"]


# ------------------------------------------------------------------- cancel
def test_cancel_running_batch(batches):
    # toy_slow_des: 0.5ms/event means the item cannot hit step_limit (100k
    # steps ≈ 50s) within the test window, so cancel deterministically wins.
    b = batches.create(
        "slow",
        {
            "schema_version": 1,
            "model_id": "toy_slow_des",
            "params": {"total_events": 1_000_000, "delay_mean": 1.0},
            "stop_condition": {"type": "until_empty"},
            "seed": 1000,
        },
        {},
        repeats=1,
    )
    result = batches.cancel(b["id"])
    assert result["status"] in ("queued", "running", "cancelled")
    final = _wait_terminal(batches, b["id"])
    assert final["status"] == "cancelled"
    item = batches.list_items(b["id"], limit=10)["items"][0]
    assert item["status"] == "cancelled"


def test_cancel_finished_batch_conflicts(batches):
    b = batches.create("quick", _spec(params={"total_events": 10}), {}, repeats=1)
    _wait_terminal(batches, b["id"])
    with pytest.raises(ConflictError):
        batches.cancel(b["id"])
    with pytest.raises(NotFoundError):
        batches.cancel(99999)


# ------------------------------------------------------------------- delete
def test_delete_finished_batch_cascades_items(batches):
    b = batches.create("del", _spec(params={"total_events": 10}), {}, repeats=2)
    _wait_terminal(batches, b["id"])
    batches.delete(b["id"])
    with pytest.raises(NotFoundError):
        batches.get_batch(b["id"])
    with pytest.raises(NotFoundError):
        batches.list_items(b["id"])
    with pytest.raises(NotFoundError):
        batches.delete(b["id"])


def test_delete_running_batch_requires_cancel(batches):
    b = batches.create(
        "del-running",
        {
            "schema_version": 1,
            "model_id": "toy_slow_des",
            "params": {"total_events": 1_000_000, "delay_mean": 1.0},
            "stop_condition": {"type": "until_empty"},
            "seed": 1000,
        },
        {},
        repeats=1,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        if batches.get_batch(b["id"], include_summary=False)["status"] == "running":
            break
        time.sleep(0.02)
    with pytest.raises(ConflictError):
        batches.delete(b["id"])
    running = batches.list_batches(status="running")
    assert b["id"] in {x["id"] for x in running["batches"]}
    slow_model = batches.list_batches(model_id="toy_slow_des")
    assert b["id"] in {x["id"] for x in slow_model["batches"]}
    batches.cancel(b["id"])
    _wait_terminal(batches, b["id"])
    batches.delete(b["id"])
    with pytest.raises(NotFoundError):
        batches.get_batch(b["id"])


# ------------------------------------------------------------------- retry
def _flaky_spec():
    return {
        "schema_version": 1,
        "model_id": "toy_fail_once",
        "params": {},
        "stop_condition": {"type": "until_empty"},
        "seed": 1,
    }


def test_batch_status_is_failed_when_any_item_fails(batches):
    FailOnceModel._seen.clear()
    FailOnceModel._seen.add(1)  # key 1 succeeds, key 2 fails on its first run
    b = batches.create("mixed", _flaky_spec(), {"key": [1, 2]}, repeats=1, max_retries=0)
    final = _wait_terminal(batches, b["id"])
    assert final["status"] == "failed", "混有 completed 与 failed 的批量必须标为 failed"
    assert final["counts"] == {"completed": 1, "failed": 1}


def test_retry_failed_items_reruns_only_failed(batches):
    FailOnceModel._seen.clear()
    b = batches.create("retry", _flaky_spec(), {"key": [1, 2]}, repeats=1, max_retries=0)
    assert _wait_terminal(batches, b["id"])["status"] == "failed"
    listed = next(x for x in batches.list_batches(status="failed")["batches"] if x["id"] == b["id"])
    assert listed["failed_items"] == 2
    first = batches.list_items(b["id"])["items"]
    assert [i["status"] for i in first] == ["failed", "failed"]
    assert all(i["attempts"] == 1 for i in first)

    batches.retry_failed(b["id"])
    final = _wait_terminal(batches, b["id"])
    assert final["status"] == "completed"
    second = batches.list_items(b["id"])["items"]
    assert [i["status"] for i in second] == ["completed", "completed"]
    assert all(i["attempts"] == 2 for i in second), "重试应累计 attempts 而不是重置"
    assert all(i["error"] is None for i in second)

    with pytest.raises(ConflictError):
        batches.retry_failed(b["id"])  # 已完成，无可重试项
    with pytest.raises(NotFoundError):
        batches.retry_failed(99999)


def test_retry_keeps_completed_items_untouched(batches):
    FailOnceModel._seen.clear()
    FailOnceModel._seen.add(1)  # key 1 succeeds on first run, key 2 fails
    b = batches.create("partial", _flaky_spec(), {"key": [1, 2]}, repeats=1, max_retries=0)
    assert _wait_terminal(batches, b["id"])["status"] == "failed"
    before = {int(i["params"]["key"]): i for i in batches.list_items(b["id"])["items"]}
    assert before[1]["status"] == "completed" and before[2]["status"] == "failed"

    batches.retry_failed(b["id"])
    assert _wait_terminal(batches, b["id"])["status"] == "completed"
    after = {int(i["params"]["key"]): i for i in batches.list_items(b["id"])["items"]}
    assert after[1]["attempts"] == 1, "已完成的条目不应被重跑"
    assert after[1]["status"] == "completed"
    assert after[2]["attempts"] == 2 and after[2]["status"] == "completed"
    listed = next(x for x in batches.list_batches()["batches"] if x["id"] == b["id"])
    assert listed["failed_items"] == 0


# ---------------------------------------------------------------- sensitivity
def test_summary_and_sensitivity(batches):
    # total_time = delay_mean * sum(-log(1-u_i)) under a fixed seed: exactly linear
    b = batches.create(
        "sens", _spec(), {"delay_mean": [0.5, 2.0]}, repeats=3, seed_strategy="fixed"
    )
    _wait_terminal(batches, b["id"])
    summary = batches.get_batch(b["id"])["summary"]
    assert len(summary["combos"]) == 2
    assert "sensitivity_note" in summary and "ci_note" in summary
    sens = {(s["param"], s["metric"]): s["pearson_r"] for s in summary["sensitivity"]}
    assert sens[("delay_mean", "total_time")] == pytest.approx(1.0, abs=1e-4)
    by_delay = {c["params"]["delay_mean"]: c for c in summary["combos"]}
    assert by_delay[2.0]["metrics"]["total_time"]["mean"] > by_delay[0.5]["metrics"]["total_time"]["mean"]
    assert by_delay[2.0]["metrics"]["total_time"]["n"] == 3


# ----------------------------------------------------------------------- API
def test_batch_api_flow(client):
    r = client.post(
        "/api/batches",
        json={
            "name": "grid demo",
            "spec": _spec(),
            "grid": {"delay_mean": [0.5, 2.0]},
            "repeats": 3,
            "seed_strategy": "fixed",
        },
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    deadline = time.time() + 20
    g = None
    while time.time() < deadline:
        g = client.get(f"/api/batches/{bid}").json()
        if g["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.05)
    assert g["status"] == "completed"
    assert g["counts"].get("completed") == 6
    sens = {(s["param"], s["metric"]) for s in g["summary"]["sensitivity"]}
    assert ("delay_mean", "total_time") in sens
    items = client.get(f"/api/batches/{bid}/items?limit=2").json()
    assert items["total"] == 6 and len(items["items"]) == 2
    assert items["items"][0]["metrics"]["count"] == 200.0
    done = client.get(f"/api/batches/{bid}/items?status=completed").json()
    assert done["total"] == 6 and all(i["status"] == "completed" for i in done["items"])
    assert client.get(f"/api/batches/{bid}/items?status=failed").json()["total"] == 0
    assert client.get(f"/api/batches/{bid}/items?status=nope").status_code == 422
    listing = client.get("/api/batches").json()
    assert any(x["id"] == bid for x in listing["batches"])
    done = client.get("/api/batches?status=completed").json()
    assert bid in {x["id"] for x in done["batches"]}
    assert client.get("/api/batches?status=running").json()["total"] == 0
    assert client.get("/api/batches?model_id=toy_des").json()["total"] >= 1
    assert client.get("/api/batches?model_id=sir").json()["total"] == 0
    assert client.get("/api/batches?model_id=toy_des&status=completed").json()["total"] >= 1
    assert client.get("/api/batches?status=nope").status_code == 422
    # finished batch cannot be cancelled again
    assert client.post(f"/api/batches/{bid}/cancel").status_code == 409
    assert client.get("/api/batches/99999").status_code == 404


def test_item_status_filter(batches):
    b = batches.create("filter", _spec(params={"total_events": 10}), {}, repeats=2)
    _wait_terminal(batches, b["id"])
    assert batches.list_items(b["id"], status="completed")["total"] == 2
    assert batches.list_items(b["id"], status="failed")["total"] == 0
    assert batches.list_items(b["id"], status=None)["total"] == 2

    slow = batches.create(
        "filter-cancel",
        {
            "schema_version": 1,
            "model_id": "toy_slow_des",
            "params": {"total_events": 1_000_000, "delay_mean": 1.0},
            "stop_condition": {"type": "until_empty"},
            "seed": 1,
        },
        {},
        repeats=1,
    )
    batches.cancel(slow["id"])
    _wait_terminal(batches, slow["id"])
    assert batches.list_items(slow["id"], status="cancelled")["total"] == 1
    assert batches.list_items(slow["id"], status="completed")["total"] == 0


def test_batch_delete_api(client):
    r = client.post(
        "/api/batches",
        json={"name": "del api", "spec": _spec(params={"total_events": 10}), "grid": {}, "repeats": 1},
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    deadline = time.time() + 20
    while time.time() < deadline:
        g = client.get(f"/api/batches/{bid}").json()
        if g["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.05)
    assert client.delete(f"/api/batches/{bid}").status_code == 204
    assert client.get(f"/api/batches/{bid}").status_code == 404
    assert client.delete(f"/api/batches/{bid}").status_code == 404
    assert client.delete("/api/batches/99999").status_code == 404

    slow = client.post(
        "/api/batches",
        json={
            "name": "slow del",
            "spec": {
                "schema_version": 1,
                "model_id": "toy_slow_des",
                "params": {"total_events": 1_000_000, "delay_mean": 1.0},
                "stop_condition": {"type": "until_empty"},
                "seed": 1,
            },
            "grid": {},
            "repeats": 1,
        },
    ).json()["id"]
    deadline = time.time() + 10
    while time.time() < deadline and client.get(f"/api/batches/{slow}").json()["status"] != "running":
        time.sleep(0.05)
    assert client.delete(f"/api/batches/{slow}").status_code == 409
    assert client.post(f"/api/batches/{slow}/cancel").status_code == 200
    deadline = time.time() + 20
    while time.time() < deadline:
        if client.get(f"/api/batches/{slow}").json()["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.05)
    assert client.delete(f"/api/batches/{slow}").status_code == 204


def test_batch_retry_api(client):
    FailOnceModel._seen.clear()
    r = client.post(
        "/api/batches",
        json={"name": "retry api", "spec": _flaky_spec(), "grid": {"key": [1]}, "repeats": 1, "max_retries": 0},
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    deadline = time.time() + 20
    while time.time() < deadline and client.get(f"/api/batches/{bid}").json()["status"] != "failed":
        time.sleep(0.05)
    assert client.get(f"/api/batches/{bid}/items").json()["items"][0]["attempts"] == 1
    listed = client.get("/api/batches?status=failed").json()["batches"]
    assert next(x for x in listed if x["id"] == bid)["failed_items"] == 1

    assert client.post(f"/api/batches/{bid}/retry").status_code == 200
    deadline = time.time() + 20
    while time.time() < deadline:
        if client.get(f"/api/batches/{bid}").json()["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.05)
    item = client.get(f"/api/batches/{bid}/items").json()["items"][0]
    assert client.get(f"/api/batches/{bid}").json()["status"] == "completed"
    assert item["status"] == "completed" and item["attempts"] == 2

    assert client.post(f"/api/batches/{bid}/retry").status_code == 409
    assert client.post("/api/batches/99999/retry").status_code == 404


def test_batch_api_validation(client):
    r = client.post("/api/batches", json={"name": "x", "spec": _spec(), "grid": {"nope": [1]}})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "spec_invalid"
    r = client.post("/api/batches", json={"name": "x", "spec": _spec(), "grid": {"total_events": [1.5]}})
    assert r.status_code == 422
    r = client.post(
        "/api/batches",
        json={"name": "x", "spec": _spec(), "grid": {"delay_mean": [0.1] * 21}, "repeats": 100},
    )
    assert r.status_code == 422
    r = client.post("/api/batches", json={"spec": _spec(), "grid": {}})
    assert r.status_code == 422  # missing name -> pydantic


def test_grid_keys_must_be_top_level_param_names(client):
    """R34：网格只能扫顶层参数名。嵌套点号键 / 空列表必须在**建批时**说清楚——
    静默接受会让「所有组合结果相同」被当成真的无敏感性（假结论比报错更坏）。"""
    nested = client.post(
        "/api/batches", json={"name": "nested", "spec": _spec(), "grid": {"params.delay_mean": [0.5, 1.0]}}
    )
    assert nested.status_code == 422
    err = nested.json()["detail"]["errors"][0]
    assert err["code"] == "grid" and "params.delay_mean" in err["message"], err

    empty = client.post("/api/batches", json={"name": "empty", "spec": _spec(), "grid": {"delay_mean": []}})
    assert empty.status_code == 422
    assert "non-empty" in empty.json()["detail"]["errors"][0]["message"]


def test_batch_items_offset_pages_are_stable_and_ordered(client):
    """R34：前端靠 total 交代「显示前 N / 共 M」，因此 offset 续读必须给同序不重不漏。"""
    bid = client.post(
        "/api/batches", json={"name": "paging", "spec": _spec(), "grid": {"delay_mean": [0.5, 1.0]},
                              "repeats": 2, "seed_strategy": "fixed"}
    ).json()["id"]
    deadline = time.time() + 20
    g = None
    while time.time() < deadline:
        g = client.get(f"/api/batches/{bid}").json()
        if g["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.05)
    assert g["status"] == "completed", g

    first = client.get(f"/api/batches/{bid}/items?limit=3&offset=0").json()
    second = client.get(f"/api/batches/{bid}/items?limit=3&offset=3").json()
    assert first["total"] == second["total"] == 4
    assert [it["item_index"] for it in first["items"]] == [0, 1, 2]
    assert [it["item_index"] for it in second["items"]] == [3]


def test_batch_records_effective_limits_not_requested(batches, settings):
    """R43：concurrency / per_run_wall_seconds 被服务端上限钳制后再落库。

    契约已按此写明；这条测试绑定「报告的是生效值」，避免以后改成存请求值却没人
    发现——那会让响应里的并发与实际在途上限脱钩，正是 R34 记录过的那类透明度病。"""
    b = batches.create("clamp", _spec(), {}, repeats=1, concurrency=64,
                       per_run_wall_seconds=3600.0)
    assert settings.max_workers == 2 and settings.max_wall_seconds == 60.0
    assert b["concurrency"] == 2, b["concurrency"]
    assert b["per_run_wall_seconds"] == 60.0, b["per_run_wall_seconds"]
    got = batches.get_batch(b["id"], include_summary=False)
    assert (got["concurrency"], got["per_run_wall_seconds"]) == (2, 60.0)
    _wait_terminal(batches, b["id"])

