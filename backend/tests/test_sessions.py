"""Interactive session API tests: step, run/pause/resume, reset, checkpoint."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def _spec(**overrides):
    spec = {
        "schema_version": 1,
        "model_id": "toy_des",
        "params": {"total_events": 5000, "delay_mean": 0.01},
        "stop_condition": {"type": "steps", "value": 5000},
        "seed": 7,
    }
    spec.update(overrides)
    return spec


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def _create(client, spec=None):
    r = client.post("/api/sessions", json={"spec": spec or _spec()})
    assert r.status_code == 201, r.text
    return r.json()


def _wait_status(client, sid, statuses, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = client.get(f"/api/sessions/{sid}").json()["status"]
        if st in statuses:
            return st
        time.sleep(0.02)
    raise AssertionError(f"session did not reach {statuses}; last={st}")


def test_session_create_and_step(client):
    body = _create(client)
    sid = body["session_id"]
    assert body["status"] == "idle"
    assert body["snapshot"]["step"] == 0
    assert body["model_id"] == "toy_des"

    r = client.post(f"/api/sessions/{sid}/step", json={"n": 5})
    assert r.status_code == 200
    st = r.json()
    assert st["snapshot"]["step"] == 5
    assert st["snapshot"]["state"]["count"] == 5
    assert st["snapshot"]["metrics"]["count"] == 5.0
    assert len(st["events"]) > 0
    assert st["status"] == "paused"


def test_session_run_to_completion(client):
    sid = _create(client)["session_id"]
    r = client.post(f"/api/sessions/{sid}/run")
    assert r.status_code == 200
    status = _wait_status(client, sid, {"completed"}, timeout=15)
    assert status == "completed"
    final = client.get(f"/api/sessions/{sid}").json()
    assert final["snapshot"]["step"] == 5000
    assert final["stop_reason"] == "completed"


def test_session_run_polls_show_progress(client):
    """Regression: while a continuous run is in flight, state() polls must see
    increasing steps (worker refreshes the cached state between chunks)."""
    spec = _spec(
        params={"total_events": 5000000, "delay_mean": 0.0001},
        stop_condition={"type": "steps", "value": 5000000},
    )
    sid = _create(client, spec)["session_id"]
    assert client.post(f"/api/sessions/{sid}/run").status_code == 200
    # Consecutive polls can land inside one 0.1s cache-refresh window and read
    # the same cached step; only distinct steps count as observations.
    seen = []
    deadline = time.time() + 5
    while time.time() < deadline and len(seen) < 3:
        st = client.get(f"/api/sessions/{sid}").json()
        if st["status"] == "running":
            step = st["snapshot"]["step"]
            if not seen or step != seen[-1]:
                seen.append(step)
        time.sleep(0.05)
    client.post(f"/api/sessions/{sid}/pause")
    assert len(seen) >= 3, f"only {len(seen)} running polls: {seen}"
    assert all(b > a for a, b in zip(seen, seen[1:])), seen


def test_session_pause_and_resume(client):
    spec = _spec(params={"total_events": 60000, "delay_mean": 0.001}, stop_condition={"type": "steps", "value": 60000})
    sid = _create(client, spec)["session_id"]
    client.post(f"/api/sessions/{sid}/run")
    _wait_status(client, sid, {"running", "paused", "completed"}, timeout=5)
    client.post(f"/api/sessions/{sid}/pause")
    status = _wait_status(client, sid, {"paused", "completed"}, timeout=5)
    steps_at_pause = client.get(f"/api/sessions/{sid}").json()["snapshot"]["step"]
    if status == "paused":
        assert client.post(f"/api/sessions/{sid}/resume").status_code == 200
    status = _wait_status(client, sid, {"completed", "step_limit"}, timeout=30)
    final_steps = client.get(f"/api/sessions/{sid}").json()["snapshot"]["step"]
    assert final_steps >= steps_at_pause
    assert final_steps > 0


def test_session_checkpoint_restore_equivalence(client):
    sid_a = _create(client)["session_id"]
    client.post(f"/api/sessions/{sid_a}/step", json={"n": 50})
    cp = client.post(f"/api/sessions/{sid_a}/checkpoint").json()["checkpoint"]
    client.post(f"/api/sessions/{sid_a}/step", json={"n": 50})
    metrics_a = client.get(f"/api/sessions/{sid_a}").json()["snapshot"]["metrics"]

    sid_b = _create(client)["session_id"]
    client.post(f"/api/sessions/{sid_b}/step", json={"n": 50})
    r = client.post(f"/api/sessions/{sid_b}/restore", json={"checkpoint": cp})
    assert r.status_code == 200
    assert r.json()["snapshot"]["step"] == 50
    client.post(f"/api/sessions/{sid_b}/step", json={"n": 50})
    metrics_b = client.get(f"/api/sessions/{sid_b}").json()["snapshot"]["metrics"]
    assert metrics_a == metrics_b


def test_session_reset(client):
    sid = _create(client)["session_id"]
    client.post(f"/api/sessions/{sid}/step", json={"n": 10})
    r = client.post(f"/api/sessions/{sid}/reset")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "idle"
    assert body["snapshot"]["step"] == 0
    r = client.post(f"/api/sessions/{sid}/step", json={"n": 1})
    assert r.json()["snapshot"]["step"] == 1


def test_session_reset_while_running(client):
    # R13 regression: reset used to join the run thread while holding the
    # session lock; the thread's exit write ("cancelled") then landed after
    # reset's "idle", leaving the session stuck (run/step 409, reset twice
    # needed). toy_slow_step chunks (~0.5 ms/step) guarantee the thread is
    # mid-chunk when reset arrives.
    spec = _spec(
        model_id="toy_slow_step",
        params={},
        stop_condition={"type": "steps", "value": 200_000},
    )
    sid = _create(client, spec)["session_id"]
    client.post(f"/api/sessions/{sid}/run")
    _wait_status(client, sid, ["running"])
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if client.get(f"/api/sessions/{sid}").json()["snapshot"]["step"] >= 100:
            break
        time.sleep(0.02)
    # R40：运行中点重置不再阻塞等待分片，而是排到边界由 worker 自己做。
    # 响应里仍是交接前的状态，但必须在极短时间内落 idle/step 0。
    t0 = time.time()
    r = client.post(f"/api/sessions/{sid}/reset")
    assert r.status_code == 200, r.text
    assert time.time() - t0 < 0.5, "reset 不该把请求阻塞到分片结束"
    _wait_status(client, sid, ["idle"], timeout=10)
    body = client.get(f"/api/sessions/{sid}").json()
    assert body["status"] == "idle" and body["snapshot"]["step"] == 0, body
    r = client.post(f"/api/sessions/{sid}/run")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "running"
    client.delete(f"/api/sessions/{sid}")


def test_session_step_after_completion_conflict(client):
    spec = _spec(stop_condition={"type": "steps", "value": 5})
    sid = _create(client, spec)["session_id"]
    client.post(f"/api/sessions/{sid}/step", json={"n": 10})
    st = client.get(f"/api/sessions/{sid}").json()
    assert st["status"] == "completed"
    r = client.post(f"/api/sessions/{sid}/step", json={"n": 1})
    assert r.status_code == 409


def test_session_unknown_404(client):
    assert client.get("/api/sessions/nope").status_code == 404
    assert client.post("/api/sessions/nope/step", json={"n": 1}).status_code == 404
    assert client.delete("/api/sessions/nope").status_code == 404


def test_session_invalid_spec_422(client):
    bad = _spec(params={"total_events": 100, "bogus_key": 1})
    r = client.post("/api/sessions", json={"spec": bad})
    assert r.status_code == 422


def test_session_restore_wrong_model_409(client):
    sid = _create(client)["session_id"]
    client.post(f"/api/sessions/{sid}/step", json={"n": 5})
    cp = client.post(f"/api/sessions/{sid}/checkpoint").json()["checkpoint"]
    cp["model_id"] = "toy_step"
    r = client.post(f"/api/sessions/{sid}/restore", json={"checkpoint": cp})
    assert r.status_code == 409


def test_session_time_stepped_model(client):
    spec = {
        "schema_version": 1,
        "model_id": "toy_step",
        "params": {},
        "stop_condition": {"type": "steps", "value": 100},
        "seed": 3,
    }
    sid = _create(client, spec)["session_id"]
    r = client.post(f"/api/sessions/{sid}/step", json={"n": 4})
    body = r.json()
    assert body["snapshot"]["step"] == 4
    assert body["model_type"] == "time_stepped"
    assert body["snapshot"]["state"]["value"] > 0


def test_session_list_and_delete(client):
    sid = _create(client)["session_id"]
    listed = client.get("/api/sessions").json()["sessions"]
    assert any(s["session_id"] == sid for s in listed)
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_pause_leaves_the_session_resumable(client):
    """R39 实跑发现的 P0：⏸ 暂停把会话写成了 cancelled 终态。

    `_stop_thread` 过去无条件同时置 cancel_event 与 pause_event，而 `_run_loop`
    先查 cancel——所以「暂停」= 取消。前端「继续」只在 status=paused 时点亮、
    单步/运行也只认 idle|paused，用户按暂停后既不能继续也不能单步，只能重置丢进度。

    用 toy_slow_step（0.5 ms/步，分片 ≈128 ms）确保暂停落在运行中间而非收尾。"""
    spec = _spec(model_id="toy_slow_step", params={}, stop_condition={"type": "steps", "value": 200000})
    sid = _create(client, spec)["session_id"]
    assert client.post(f"/api/sessions/{sid}/run").status_code == 200
    time.sleep(0.25)
    assert client.post(f"/api/sessions/{sid}/pause").status_code == 200

    status = _wait_status(client, sid, {"paused", "cancelled", "completed"}, timeout=10)
    body = client.get(f"/api/sessions/{sid}").json()
    assert status == "paused", f"暂停应当落 paused，实得 {status}（stop_reason={body.get('stop_reason')}）"
    assert body["stop_reason"] is None
    steps_at_pause = body["snapshot"]["step"]
    assert steps_at_pause > 0

    # paused 是可用态：单步与继续都必须放行（这正是旧实现坏掉的地方）
    assert client.post(f"/api/sessions/{sid}/step", json={"n": 3}).status_code == 200
    assert client.get(f"/api/sessions/{sid}").json()["snapshot"]["step"] == steps_at_pause + 3
    assert client.post(f"/api/sessions/{sid}/resume").status_code == 200
    _wait_status(client, sid, {"running"}, timeout=10)
    time.sleep(0.2)
    client.post(f"/api/sessions/{sid}/pause")
    _wait_status(client, sid, {"paused"}, timeout=10)
    assert client.get(f"/api/sessions/{sid}").json()["snapshot"]["step"] > steps_at_pause + 3


def test_pause_during_chunk_never_mutates_the_running_engine(tmp_path):
    """R39：join 超时后不许改 engine——它此刻仍归运行线程所有。

    旧实现 `join(timeout=5.0)` 失败后照样把状态写成 paused，然后 step/reset/checkpoint
    继续动同一个引擎，restore 更是在锁内 join；分片期间是不加 s.lock 的（为了让轮询
    能进），于是两个线程并发改同一个事件堆。

    用 gate 把 worker 卡在分片内部，而不是靠 sleep 赌时序。"""
    import threading
    import time

    from app.config import Settings
    from app.core.registry import registry
    from app.services.experiment_service import ConflictError
    from app.services.session_service import SessionService

    import app.models  # noqa: F401

    svc = SessionService(
        Settings(db_path=str(tmp_path / "race.db"), max_workers=1, default_max_steps=100000,
                 max_wall_seconds=60, event_log_size=50, zero_delay_chain_limit=10000,
                 cancel_poll_interval=256, session_ttl_seconds=3600.0, plugin_modules=()),
        registry,
    )
    svc._join_timeout = 0.05
    entered, release = threading.Event(), threading.Event()
    try:
        sid = svc.create({"model_id": "toy_slow_step", "params": {},
                          "stop_condition": {"type": "steps", "value": 100000}, "seed": 1})["session_id"]
        engine = svc._sessions[sid].engine
        real_run = engine.run

        def gated_run(max_steps=None):
            entered.set()
            assert release.wait(timeout=10), "测试未能放行 worker 线程"
            return real_run(max_steps=max_steps)

        engine.run = gated_run
        svc.run(sid)
        assert entered.wait(timeout=10), "worker 没有进入分片"

        st = svc.pause(sid)
        s = svc._sessions[sid]
        assert s.stopping is True, "join 超时必须标 stopping，而不是假装已经暂停"
        assert st["status"] == "running", "线程还在跑时对外仍应是 running（状态由它自己收尾）"
        for call in (lambda: svc.step(sid, 1), lambda: svc.checkpoint(sid), lambda: svc.run(sid)):
            with pytest.raises(ConflictError):
                call()
        # restore 仍拒绝（API-only，检查点校验失败必须回 409 给调用方）；
        # reset 改为排队：请求立刻返回，动作由 worker 在边界执行，engine 不被并发触碰。
        with pytest.raises(ConflictError, match="stopping"):
            svc.restore(sid, {"checkpoint": {}})
        st = svc.reset(sid)
        assert s.pending_action == ("reset", None), "运行中的重置必须排队而不是硬闯"
        assert st["status"] == "running", "排队期间对外仍是交接前的状态"
        assert s.engine.steps == 0, "被拒绝/排队的调用不能在分片结束前推动引擎"

        release.set()
        deadline = time.time() + 10
        while time.time() < deadline and svc._sessions[sid].stopping:
            time.sleep(0.02)
        assert svc._sessions[sid].stopping is False, "线程退出后必须清掉 stopping"
        # 排队的 reset 在边界被 worker 执行 → idle（而不是 paused）
        assert svc._sessions[sid].status == "idle", svc._sessions[sid].status
        assert svc._sessions[sid].engine.steps == 0
        assert svc.step(sid, 1)["snapshot"]["step"] >= 1
    finally:
        release.set()
        svc.shutdown()


def test_stopping_session_returns_conflict_over_http(settings):
    """R39：同一状态在 HTTP 层的对外形状——409 `conflict` + 可读 message。

    前端在暂停的瞬间仍可能把「单步/重置/检查点」请求发出去（按钮按 status 点亮，
    而 stopping 不体现在 status 里），所以用户必须拿到可解释的 409，而不是 500
    或把引擎改坏之后的错乱状态。"""
    import threading

    app = create_app(settings)
    with TestClient(app) as c:
        svc = app.state.sessions
        svc._join_timeout = 0.05
        entered, release = threading.Event(), threading.Event()
        try:
            sid = c.post("/api/sessions", json={"spec": _spec(model_id="toy_slow_step", params={})}).json()["session_id"]
            engine = svc._sessions[sid].engine
            real_run = engine.run
            engine.run = lambda max_steps=None: (entered.set(), release.wait(timeout=10), real_run(max_steps=max_steps))[-1]
            assert c.post(f"/api/sessions/{sid}/run").status_code == 200
            assert entered.wait(timeout=10)
            assert c.post(f"/api/sessions/{sid}/pause").status_code == 200

            for path in ("step", "checkpoint", "restore"):
                body = {"checkpoint": {"model_id": "toy_slow_step"}} if path == "restore" else {}
                r = c.post(f"/api/sessions/{sid}/{path}", json=body)
                assert r.status_code == 409, f"{path}: {r.status_code} {r.text}"
                assert r.json()["detail"]["code"] == "conflict"
                message = r.json()["detail"]["message"]
                # step/checkpoint 由既有守卫拦住；restore 由 R39 的 stopping 守卫拦住。
                # reset 不在这里：R40 起是 200 + 边界排队。
                if path == "restore":
                    assert "stopping" in message, r.text
                assert message, r.text
                assert engine.steps == 0, f"{path} 在分片结束前推动了引擎"
            assert c.get(f"/api/sessions/{sid}").json()["status"] == "running"

            t0 = time.time()
            r = c.post(f"/api/sessions/{sid}/reset")
            assert r.status_code == 200, r.text
            assert time.time() - t0 < 0.2, "reset 不该阻塞到分片结束"
            assert r.json()["status"] == "running", "排队期间仍是交接前状态"

            release.set()
            # pause 只置 pause 标志（R39）；排队的 reset 在边界执行 → idle
            _wait_status(c, sid, ("idle",), timeout=10)
            assert c.get(f"/api/sessions/{sid}").json()["snapshot"]["step"] == 0
            r = c.post(f"/api/sessions/{sid}/step", json={"n": 1})
            assert r.status_code == 200, r.text
            assert svc._sessions[sid].stopping is False
        finally:
            release.set()


def test_session_ttl_is_configurable_and_enforced(monkeypatch, tmp_path):
    """R39：会话空闲回收时限取自 Settings（此前硬编码 3600 秒且无任何文档，
    用户回来只见 404 无从解释）。"""
    from app.config import Settings
    from app.core.registry import registry
    from app.services.session_service import SessionService

    monkeypatch.delenv("WORLDLAB_SESSION_TTL_SECONDS", raising=False)
    assert Settings.from_env().session_ttl_seconds == 3600.0
    monkeypatch.setenv("WORLDLAB_SESSION_TTL_SECONDS", "12.5")
    assert Settings.from_env().session_ttl_seconds == 12.5

    def svc(ttl: float) -> SessionService:
        return SessionService(
            Settings(db_path=str(tmp_path / f"ttl{ttl}.db"), max_workers=1, default_max_steps=100000,
                     max_wall_seconds=60, event_log_size=50, zero_delay_chain_limit=10000,
                     cancel_poll_interval=256, session_ttl_seconds=ttl, plugin_modules=()),
            registry,
        )

    import app.models  # noqa: F401

    spec = {"model_id": "sir", "params": {}, "stop_condition": {"type": "steps", "value": 5}, "seed": 1}
    tight = svc(0.05)
    try:
        old = tight.create(spec)["session_id"]
        time.sleep(0.2)
        tight.create(spec)  # 任意会话操作会先回收过期会话
        assert old not in tight._sessions, "超过 TTL 的会话应被回收"
    finally:
        tight.shutdown()

    patient = svc(3600.0)
    try:
        sid = patient.create(spec)["session_id"]
        patient.create(spec)
        assert sid in patient._sessions, "未超时的会话不能被误回收"
    finally:
        patient.shutdown()


def test_session_limits_come_from_settings():
    """R37：会话引擎的四项资源上限必须全部取自 Settings。

    此前只传 max_steps/max_wall_seconds，另两项落进 `Limits` 的 dataclass 默认值，
    于是 `WORLDLAB_CANCEL_POLL_INTERVAL` / `WORLDLAB_ZERO_DELAY_CHAIN_LIMIT`
    对交互会话静默无效——而 `GET /api/limits` 报的却是 Settings 里的值。"""
    from app.config import Settings
    from app.core.registry import registry
    from app.services.session_service import SessionService

    import app.models  # noqa: F401

    settings = Settings(
        db_path=":memory:", max_workers=1, default_max_steps=4321, max_wall_seconds=11.0,
        event_log_size=77, zero_delay_chain_limit=1234, cancel_poll_interval=7,
        session_ttl_seconds=3600.0, plugin_modules=(),
    )
    svc = SessionService(settings, registry)
    try:
        limits = svc.session_limits()
        assert (limits.max_steps, limits.max_wall_seconds) == (4321, 11.0)
        assert limits.cancel_poll_interval == 7, "取消粒度必须跟随 Settings（会话侧曾漏传）"
        assert limits.zero_delay_chain_limit == 1234

        created = svc.create({"model_id": "sir", "params": {},
                              "stop_condition": {"type": "steps", "value": 5}})
        engine = svc._sessions[created["session_id"]].engine._inner
        assert engine.limits.cancel_poll_interval == 7
        assert engine.limits.zero_delay_chain_limit == 1234
    finally:
        svc.shutdown()
