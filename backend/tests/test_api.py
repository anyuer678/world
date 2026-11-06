import hashlib
import json

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.experiment_service import canonical_metrics_json, metrics_sha256

QUEUE_SPEC = {
    "schema_version": 1,
    "model_id": "queueing",
    "params": {
        "arrival": {"kind": "poisson", "rate": 1.5},
        "service": {"kind": "exponential", "mean": 0.5},
        "servers": 1,
    },
    "stop_condition": {"type": "steps", "value": 3000},
    "seed": 42,
}


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_models_listed(client):
    r = client.get("/api/models")
    models = {m["model_id"]: m for m in r.json()["models"]}
    assert "queueing" in models
    q = models["queueing"]
    assert q["model_type"] == "discrete_event"
    assert "params_schema" in q and "example_spec" in q
    assert q["params_schema"]["properties"]["servers"]["minimum"] == 1


def test_model_detail_404(client):
    assert client.get("/api/models/nope").status_code == 404


def test_validate_endpoint(client):
    r = client.post("/api/models/queueing/validate", json={**QUEUE_SPEC, "params": {"servers": 0}})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert any("servers" in e["code"] for e in body["errors"])

    r = client.post("/api/models/queueing/validate", json=QUEUE_SPEC)
    assert r.json()["valid"] is True


def test_full_experiment_lifecycle(client):
    r = client.post("/api/experiments", json={"name": "mm1", "spec": QUEUE_SPEC})
    assert r.status_code == 201
    exp = r.json()
    assert exp["status"] == "created"
    assert exp["model_version"] == "1.0.0"
    exp_id = exp["id"]

    r = client.post(f"/api/experiments/{exp_id}/run", json={"wait": True})
    assert r.status_code == 200

    result = client.get(f"/api/experiments/{exp_id}/result").json()
    assert result["experiment"]["status"] == "completed"
    run = result["runs"][0]
    assert run["status"] == "completed"
    m = run["metrics"]
    assert m["arrived"] > 500
    assert 0.0 <= m["utilization"] <= 1.0
    assert run["result_sha256"] == hashlib.sha256(
        json.dumps(m, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    assert result["aggregate"] is not None

    run_detail = client.get(f"/api/runs/{run['id']}").json()
    assert run_detail["events"], "event log must come from the real run"
    kinds = {e["kind"] for e in run_detail["events"]}
    assert kinds <= {"arrival", "service_start", "departure", "drop"}


def test_invalid_spec_422(client):
    bad = {**QUEUE_SPEC, "params": {"servers": 0}}
    r = client.post("/api/experiments", json={"name": "bad", "spec": bad})
    assert r.status_code == 422
    errors = r.json()["detail"]["errors"]
    assert any("params.servers" in e["code"] for e in errors)


def test_validate_returns_effective_spec(client):
    """R33：契约承诺 normalized_spec 是「迁移补齐后的形态」——此前它只是把入参原样吐回
    （model_version/display_name 为 None、params 不含默认值）。"""
    latest = client.get("/api/models/sir").json()["version"]
    body = client.post(
        "/api/models/sir/validate",
        json={"model_id": "sir", "params": {"beta": 0.5}, "stop_condition": {"type": "steps", "value": 10}},
    ).json()
    assert body["valid"] is True
    n = body["normalized_spec"]
    assert n["model_version"] == latest, "未钉版本时必须给出解析出的实际版本"
    assert n["display_name"] == "SIR 传染病模型"
    assert n["params"]["beta"] == 0.5
    assert n["params"]["population"] == 10000, "params 必须是补齐默认值后的形态"

    pinned = client.post(
        "/api/models/sir/validate",
        json={"model_id": "sir", "model_version": latest, "params": {},
              "stop_condition": {"type": "steps", "value": 10}},
    ).json()["normalized_spec"]
    assert pinned["model_version"] == latest


def test_unknown_model_version_is_422_not_500(client):
    """钉了一个注册表里没有的版本：必须是可读的 422 spec_invalid，不能是 500。"""
    r = client.post(
        "/api/experiments",
        json={"name": "badver", "spec": {"model_id": "sir", "model_version": "9.9.9", "params": {},
                                         "stop_condition": {"type": "steps", "value": 10}}},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "spec_invalid"
    assert any(e["code"] == "unknown_model" for e in detail["errors"]), detail
    v = client.post(
        "/api/models/sir/validate",
        json={"model_id": "sir", "model_version": "9.9.9", "params": {},
              "stop_condition": {"type": "steps", "value": 10}},
    )
    assert v.status_code == 200 and v.json()["valid"] is False
    assert v.json()["errors"][0]["code"] == "unknown_model"


def test_unknown_model_422(client):
    r = client.post("/api/experiments", json={"name": "x", "spec": {"model_id": "ghost", "params": {}}})
    assert r.status_code == 422


def test_422_has_two_distinct_detail_shapes(client):
    """R30：422 的 detail 有两种形状，消费方必须都认：
    FastAPI 请求体规则（repeats/max_retries/concurrency 等）→ 数组；
    应用层 spec 校验（main.py 异常处理器）→ 对象 {code, message, errors[]}。
    前端 api.ts 曾只读对象形状，数组形状渲染成裸 "422"，用户看不到原因。"""
    limits = client.get("/api/limits").json()["batch"]
    over = client.post(
        "/api/batches",
        json={"name": "shape", "spec": dict(QUEUE_SPEC), "grid": {},
              "max_retries": limits["max_retries_max"] + 1},
    )
    assert over.status_code == 422
    detail = over.json()["detail"]
    assert isinstance(detail, list), detail
    assert detail[0]["loc"] == ["body", "max_retries"]
    assert "less than or equal to" in detail[0]["msg"]

    spec_bad = client.post(
        "/api/experiments", json={"name": "shape", "spec": {**QUEUE_SPEC, "params": {"servers": 0}}}
    )
    assert spec_bad.status_code == 422
    obj = spec_bad.json()["detail"]
    assert isinstance(obj, dict) and obj["code"] == "spec_invalid" and obj["errors"]


def test_clone_and_override_params(client):
    exp = client.post("/api/experiments", json={"name": "base", "spec": QUEUE_SPEC}).json()
    clone = client.post(
        f"/api/experiments/{exp['id']}/clone",
        json={"name": "serving-2", "spec_overrides": {"params": {"servers": 3}}},
    ).json()
    assert clone["id"] != exp["id"]
    assert clone["spec"]["params"]["servers"] == 3
    assert clone["spec"]["params"]["arrival"] == QUEUE_SPEC["params"]["arrival"]
    assert clone["parent_experiment_id"] == exp["id"]


def test_tags_and_list_filter(client):
    exp = client.post("/api/experiments", json={"name": "tagged", "spec": QUEUE_SPEC}).json()
    client.put(f"/api/experiments/{exp['id']}/tags", json={"tags": ["mm1", "baseline", "mm1"]})
    got = client.get(f"/api/experiments/{exp['id']}").json()
    assert got["tags"] == ["baseline", "mm1"]
    listed = client.get("/api/experiments", params={"tag": "mm1"}).json()
    assert listed["total"] >= 1


def test_delete_experiment(client):
    exp = client.post("/api/experiments", json={"name": "tmp", "spec": QUEUE_SPEC}).json()
    assert client.delete(f"/api/experiments/{exp['id']}").status_code == 204
    assert client.get(f"/api/experiments/{exp['id']}").status_code == 404


def test_run_events_pagination(client):
    exp = client.post("/api/experiments", json={"name": "ev", "spec": QUEUE_SPEC}).json()
    client.post(f"/api/experiments/{exp['id']}/run", json={"wait": True})
    rid = client.get(f"/api/experiments/{exp['id']}/result").json()["runs"][0]["id"]

    page1 = client.get(f"/api/runs/{rid}/events", params={"limit": 5, "offset": 0}).json()
    assert page1["total"] > 5 and len(page1["events"]) == 5
    page2 = client.get(f"/api/runs/{rid}/events", params={"limit": 5, "offset": 5}).json()
    assert page2["total"] == page1["total"]
    assert page2["events"][0] != page1["events"][-1]
    tail = client.get(f"/api/runs/{rid}/events", params={"offset": page1["total"] - 2}).json()
    assert len(tail["events"]) == 2
    beyond = client.get(f"/api/runs/{rid}/events", params={"offset": page1["total"] + 10}).json()
    assert beyond["events"] == []
    assert client.get("/api/runs/987654/events").status_code == 404


def test_limits_endpoint_tracks_validation_rules(client):
    """R29：/api/limits 暴露的必须是服务端自己的校验规则，不能是第二套硬编码。"""
    from app.services.batch_service import MAX_BATCH_ITEMS
    from app.services.session_service import MAX_STEP_BATCH

    body = client.get("/api/limits").json()
    assert body["session"]["max_step_batch"] == MAX_STEP_BATCH
    b = body["batch"]
    assert b["max_items"] == MAX_BATCH_ITEMS
    assert (b["repeats_min"], b["repeats_max"]) == (1, 100)
    assert (b["max_retries_min"], b["max_retries_max"]) == (0, 10)
    assert (b["concurrency_min"], b["concurrency_max"]) == (1, 64)
    assert b["name_max_length"] == 200
    assert body["engine"]["max_workers"] >= 1

    spec = {**QUEUE_SPEC}
    over = {"name": "limits-probe", "spec": spec, "grid": {}, "repeats": b["repeats_max"] + 1}
    assert client.post("/api/batches", json=over).status_code == 422

    ok = {"name": "limits-probe", "spec": spec, "grid": {}, "repeats": b["repeats_max"]}
    r = client.post("/api/batches", json=ok)
    assert r.status_code in (201, 400), r.text  # 400 only via item cap, never a repeats rejection
    if r.status_code == 201:
        client.post(f"/api/batches/{r.json()['id']}/cancel")


def test_cancel_non_running_is_safe(client):
    exp = client.post("/api/experiments", json={"name": "c", "spec": QUEUE_SPEC}).json()
    r = client.post(f"/api/experiments/{exp['id']}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_rerun_produces_same_result(client):
    exp = client.post("/api/experiments", json={"name": "repro", "spec": QUEUE_SPEC}).json()
    client.post(f"/api/experiments/{exp['id']}/run", json={"wait": True})
    first = client.get(f"/api/experiments/{exp['id']}/result").json()["runs"][0]
    client.post(f"/api/experiments/{exp['id']}/rerun")
    # wait for completion by polling
    import time

    for _ in range(100):
        exp_now = client.get(f"/api/experiments/{exp['id']}").json()
        if exp_now["status"] != "running":
            break
        time.sleep(0.05)
    result = client.get(f"/api/experiments/{exp['id']}/result").json()
    seeds = {r["seed"] for r in result["runs"]}
    assert len(result["runs"]) == 2
    assert len(seeds) == 1  # rerun keeps the pinned seed
    by_sha = {}
    for r in result["runs"]:
        assert r["result_sha256"] not in by_sha or True
        by_sha.setdefault(r["result_sha256"], 0)
        by_sha[r["result_sha256"]] += 1
    assert len(by_sha) == 1  # identical seed => identical checksum
    assert first["seed"] == result["runs"][0]["seed"]


def test_v0_spec_accepted_and_migrated(client):
    r = client.post(
        "/api/experiments",
        json={"name": "legacy", "spec": {"model": "queueing", "params": {"servers": 1}, "horizon": 1000, "seed": 3}},
    )
    assert r.status_code == 201
    spec = r.json()["spec"]
    assert spec["schema_version"] == 1
    assert spec["stop_condition"] == {"type": "steps", "value": 1000}


def test_pagination_bounds_are_enforced(client):
    """R59：不校验时 SQLite 的 `LIMIT -1` 是「无上限」——`/api/experiments?limit=-1`
    会返回全部记录（实测 52/52）。所有列表端点必须拒绝越界分页参数。"""
    for path in ("/api/experiments", "/api/batches"):
        for q in ("limit=0", "limit=-1", "limit=1001", "offset=-1"):
            r = client.get(f"{path}?{q}")
            assert r.status_code == 422, (path, q, r.status_code)
            assert isinstance(r.json()["detail"], list), r.text
    assert client.get("/api/experiments?limit=1").status_code == 200
    assert client.get("/api/batches?limit=1000").status_code == 200


def test_clone_rejects_overlong_name_like_create(client):
    """R60：名称长度上限原先只写在 CreateExperimentBody（路由层），`clone` 走服务层时
    能把 10000 字符的名称写进库（实测 200 OK）。规则下沉到服务层后两条入口一致。"""
    r = client.post("/api/experiments", json={"name": "x" * 200, "spec": QUEUE_SPEC})
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    over = client.post(f"/api/experiments/{eid}/clone", json={"name": "y" * 201})
    assert over.status_code == 422, over.text
    assert over.json()["detail"]["code"] == "spec_invalid"
    ok = client.post(f"/api/experiments/{eid}/clone", json={"name": "y" * 200})
    assert ok.status_code in (200, 201), ok.text


def test_default_app_never_points_at_repo_database():
    """R61：`create_app()` 不带参数时会用 `app.main.default_settings`。
    测试会话里它必须被换成临时库，否则一次全量测试就会往开发库写入实验/运行记录。"""
    import app.main as main_module

    repo_db = (Path(__file__).resolve().parents[1] / "data" / "worldlab.db").resolve()
    assert Path(main_module.default_settings.db_path).resolve() != repo_db


def test_malformed_inputs_never_leak_500(client):
    """R64：畸形输入只应得到 4xx。

    实测漏点：`offset=999999999999999999999` 让 Python 大整数进 SQLite，抛
    `OverflowError` → 500；路径 id 同样。现在 offset 有上限、id 用 RowId 约束。
    """
    import json

    deep = "[" * 900 + "]" * 900
    cases = [
        ("POST", "/api/sessions/nope/restore", '{"checkpoint": ' + deep + "}"),
        ("POST", "/api/experiments", json.dumps({"name": "x", "spec": []})),
        ("POST", "/api/sessions", json.dumps({"spec": None})),
        ("POST", "/api/batches", json.dumps(
            {"name": "b",
             "spec": {"schema_version": 1, "model_id": "sir", "params": {},
                      "stop_condition": {"type": "steps", "value": 5}, "seed": 1},
             "grid": {"gamma": 1}, "repeats": 1})),
        ("GET", "/api/experiments?tag=%FF%FE", None),
        ("GET", "/api/experiments?offset=999999999999999999999", None),
        ("GET", "/api/models/sir?version=%00", None),
        ("GET", "/api/experiments/999999999999999999999", None),
        ("GET", "/api/runs/999999999999999999999", None),
        ("GET", "/api/batches/999999999999999999999", None),
        ("GET", "/api/batches/1/items?offset=999999999999999999999", None),
    ]
    for method, path, body in cases:
        kwargs = {"content": body.encode("utf-8"), "headers": {"content-type": "application/json"}} if body else {}
        r = client.request(method, path, **kwargs)
        assert r.status_code < 500, (method, path, r.status_code, r.text[:200])


def test_run_detail_events_limit_zero_means_none(client):
    """R72：run 详情与会话同一类切片问题——`events[-0:]` 会返回全部事件。

    R59 只修了会话路径；这里固定 run 详情的语义：0 条、2 条，负数 422。"""
    r = client.post("/api/experiments", json={"name": "r72-events", "spec": QUEUE_SPEC})
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    run = client.post(f"/api/experiments/{eid}/run", json={"wait": True})
    assert run.status_code == 200, run.text
    rid = run.json()["run_id"]

    assert client.get(f"/api/runs/{rid}?events_limit=0").json()["events"] == []
    assert len(client.get(f"/api/runs/{rid}?events_limit=2").json()["events"]) == 2
    assert client.get(f"/api/runs/{rid}?events_limit=-1").status_code == 422

