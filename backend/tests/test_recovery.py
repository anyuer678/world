"""阶段 6：异常恢复测试。

覆盖三类真实故障的恢复语义：
1. 服务进程在运行中途崩溃/重启 —— 遗留的 running 行不能永远悬挂，
   也不能被冒充为成功；重启后必须被明确标记为失败/取消，且不破坏
   后续重跑。
2. 模型执行中途抛异常 —— 运行必须以 failed 收场并记录错误，
   不产生任何伪造的成功指标或校验和。
3. 损坏的检查点 —— restore 必须拒绝（409）且会话保持可用。
"""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

import app.models  # noqa: F401 - register built-ins
from app.core.engine.models_base import DiscreteEventModel, WorldLabParams
from app.core.registry import registry
from app.main import create_app
from app.services.batch_service import BatchService
from app.services.experiment_service import ExperimentService

QUEUE_SPEC = {
    "schema_version": 1,
    "model_id": "queueing",
    "params": {
        "arrival": {"kind": "poisson", "rate": 1.5},
        "service": {"kind": "exponential", "mean": 0.5},
        "servers": 1,
    },
    "stop_condition": {"type": "steps", "value": 1000},
    "seed": 42,
}

INTERRUPTED_RUN = "interrupted: service restarted while run was in progress"
INTERRUPTED_BATCH = "interrupted: service restarted while batch was in progress"


class BoomParams(WorldLabParams):
    total_events: int = 10
    delay_mean: float = 1.0


class BoomModel(DiscreteEventModel):
    model_id = "boom_des"
    display_name = "Boom"
    description = "Raises mid-run to verify failure recording."
    model_type = "discrete_event"
    version = "1.0.0"
    param_model = BoomParams

    def initialize(self, ctx) -> None:
        self.n = 0
        ctx.schedule(1.0, "boom")

    def handle_event(self, event, ctx) -> None:
        self.n += 1
        if self.n >= 3:
            raise RuntimeError("boom: simulated model crash")
        ctx.schedule(1.0, "boom")

    def dump_state(self):
        return {"n": self.n}

    def load_state(self, state):
        self.n = state["n"]

    def snapshot(self):
        return {"n": self.n}

    def finalize_metrics(self):
        return {"n": float(self.n)}


registry.register(BoomModel)


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def test_restart_recovers_running_experiment(settings):
    s1 = ExperimentService(settings, registry)
    exp_id = s1.create_experiment("crash-me", QUEUE_SPEC)["id"]
    # Simulate a crash after run_experiment() wrote 'running' rows.
    conn = sqlite3.connect(settings.db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE experiments SET status='running', started_at=datetime('now') WHERE id=?",
                (exp_id,),
            )
            conn.execute(
                "INSERT INTO experiment_runs(experiment_id, repeat_index, seed, status)"
                " VALUES (?,0,42,'running')",
                (exp_id,),
            )
    finally:
        conn.close()
    s1.shutdown()

    s2 = ExperimentService(settings, registry)  # restart triggers recovery
    try:
        res = s2.get_result(exp_id)
        assert res["experiment"]["status"] == "failed"
        assert INTERRUPTED_RUN in res["experiment"]["error"]
        run = res["runs"][0]
        assert run["status"] == "failed"
        assert INTERRUPTED_RUN in run["error"]
        assert run["metrics"] is None
        assert run["result_sha256"] is None

        # Recovery must not brick the experiment: a new run executes and
        # completes. The aggregate status stays 'failed' by design — it
        # reflects the whole run history, including the interrupted run.
        s2.run_experiment(exp_id, wait=True)
        res2 = s2.get_result(exp_id)
        assert res2["runs"][-1]["status"] == "completed"
        assert res2["runs"][-1]["result_sha256"]
        assert res2["runs"][0]["status"] == "failed"
    finally:
        s2.shutdown()


def test_restart_recovers_running_batch(settings):
    b1 = BatchService(settings, registry)  # applies migrations
    conn = sqlite3.connect(settings.db_path)
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO batch_runs(name, model_id, model_version, spec_json, grid_json,
                   repeats, seed_strategy, seed_base, max_retries, concurrency,
                   per_run_wall_seconds, status, total_items)
                   VALUES ('crash-batch','toy_des','1.0.0','{}','{}',2,'fixed',1,0,2,60.0,'running',2)"""
            )
            bid = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO batch_items(batch_id, item_index, combo_json, repeat_index, seed, status)"
                " VALUES (?,0,'{}',0,1,'running')",
                (bid,),
            )
            conn.execute(
                "INSERT INTO batch_items(batch_id, item_index, combo_json, repeat_index, seed, status)"
                " VALUES (?,1,'{}',1,1,'pending')",
                (bid,),
            )
    finally:
        conn.close()
    b1.shutdown()

    b2 = BatchService(settings, registry)  # restart triggers recovery
    try:
        batch = b2.get_batch(bid, include_summary=False)
        assert batch["status"] == "cancelled"
        assert INTERRUPTED_BATCH in batch["error"]
        items = b2.list_items(bid, limit=10)["items"]
        assert all(i["status"] == "cancelled" for i in items)
        assert all(INTERRUPTED_BATCH in (i["error"] or "") for i in items)
    finally:
        b2.shutdown()


def test_model_crash_records_error_no_fake_success(service):
    spec = {
        "schema_version": 1,
        "model_id": "boom_des",
        "params": {"total_events": 10, "delay_mean": 1.0},
        "stop_condition": {"type": "until_empty"},
        "seed": 7,
    }
    exp_id = service.create_experiment("boom", spec)["id"]
    service.run_experiment(exp_id, wait=True)
    res = service.get_result(exp_id)
    assert res["experiment"]["status"] == "failed"
    run = res["runs"][0]
    assert run["status"] == "failed"
    assert "boom" in (run["error"] or "")
    assert run["metrics"] is None
    assert run["result_sha256"] is None


def test_corrupted_checkpoint_rejected_session_stays_usable(client):
    r = client.post("/api/sessions", json={"spec": QUEUE_SPEC})
    assert r.status_code == 201
    sid = r.json()["session_id"]
    try:
        assert client.post(f"/api/sessions/{sid}/step", json={"n": 3}).status_code == 200

        r = client.post(f"/api/sessions/{sid}/restore", json={"checkpoint": {"garbage": True}})
        assert r.status_code == 409
        assert "restore failed" in r.json()["detail"]["message"]

        # The session must remain usable after a rejected restore.
        r = client.post(f"/api/sessions/{sid}/step", json={"n": 2})
        assert r.status_code == 200
        assert r.json()["snapshot"]["step"] == 5
    finally:
        client.delete(f"/api/sessions/{sid}")


def test_concurrent_run_claims_exactly_once(settings):
    """R62：并发 POST /run 只能有一个成功。

    旧实现先读 status 再无条件 UPDATE+INSERT——实测 8 线程同时发起时有 2 个成功、
    库里 2 条 run，同一实验被并发执行。现在占位是一条条件 UPDATE，rowcount 决定归属。"""
    import sqlite3
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from app.core.registry import registry
    from app.services.experiment_service import ConflictError, ExperimentService

    svc = ExperimentService(settings, registry)
    try:
        spec = {
            "schema_version": 1,
            "model_id": "toy_slow_step",
            "params": {},
            "stop_condition": {"type": "steps", "value": 200000},
            "seed": 3,
        }
        exp = svc.create_experiment("r62-race", spec)
        workers = 8
        barrier = threading.Barrier(workers)

        def fire(_i: int) -> str:
            barrier.wait(timeout=10)
            try:
                svc.run_experiment(exp["id"])
                return "ok"
            except ConflictError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(fire, range(workers)))

        assert outcomes.count("ok") == 1, outcomes
        runs = sqlite3.connect(settings.db_path).execute(
            "SELECT COUNT(*) FROM experiment_runs WHERE experiment_id=?", (exp["id"],)
        ).fetchone()[0]
        assert runs == 1, f"并发调用为同一实验插入了 {runs} 条 run"
        svc.cancel_experiment(exp["id"])
    finally:
        svc.shutdown()


def test_delete_refuses_when_a_run_claims_between_check_and_delete(settings, monkeypatch):
    """R63：`_assert_not_running` 与 DELETE 之间的窗口必须由条件 DELETE 兜住。

    这里把检查函数替换成 no-op 模拟「检查通过、随后被并发 claim」的时序：
    旧实现会直接删掉（级联删 run 行，worker 还在跑）；现在返回 409 且实验仍在。"""
    from app.core.registry import registry
    from app.services.experiment_service import ConflictError, ExperimentService

    svc = ExperimentService(settings, registry)
    try:
        spec = {
            "schema_version": 1,
            "model_id": "toy_slow_step",
            "params": {},
            "stop_condition": {"type": "steps", "value": 200000},
            "seed": 5,
        }
        exp = svc.create_experiment("r63-delete", spec)
        svc.run_experiment(exp["id"])
        monkeypatch.setattr(svc, "_assert_not_running", lambda _id: None)
        try:
            svc.delete_experiment(exp["id"])
            raise AssertionError("运行中的实验不应被删除")
        except ConflictError:
            pass
        assert svc.get_experiment(exp["id"])["status"] == "running"
        svc.cancel_experiment(exp["id"])
    finally:
        svc.shutdown()


def test_worker_exits_quietly_when_experiment_is_gone(settings):
    """R63：claim 后实验被删（级联删 run）时，worker 不能抛未观察的异常。"""
    from app.core.registry import registry
    from app.services.experiment_service import ExperimentService

    svc = ExperimentService(settings, registry)
    try:
        spec = {
            "schema_version": 1,
            "model_id": "toy_des",
            "params": {"total_events": 10, "delay_mean": 0.01},
            "stop_condition": {"type": "until_empty"},
            "seed": 5,
        }
        exp = svc.create_experiment("r63-gone", spec)
        conn = svc._conn()  # noqa: SLF001 - 直接造出「run 行存在但实验已不存在」的状态
        try:
            with conn:
                cur = conn.execute("INSERT INTO experiment_runs(experiment_id, repeat_index, seed, status) VALUES (?,?,?,'pending')", (exp["id"], 0, 5))
                run_id = int(cur.lastrowid)
                conn.execute("DELETE FROM experiments WHERE id=?", (exp["id"],))
        finally:
            conn.close()
        svc._execute_run(run_id, exp["id"])  # noqa: SLF001 - 不应抛异常
    finally:
        svc.shutdown()

