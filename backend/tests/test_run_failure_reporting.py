"""R35：提交时校验的一致性、失败诊断的可读性、实验列表过滤×分页。

审计线取自「只在全新/单实例/正路径上验过」的声称：库里躺着注册表已无的模型
（插件模块没配、版本撤下）时，平台必须当场说清楚，而不是先答应再悄悄失败。
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app.models  # noqa: F401
from app.core.registry import registry
from app.main import create_app
from app.models.sir.model import SirModel
from app.services.experiment_service import describe_run_failure

GONE = "temporarily_registered"


def _probe_class(model_id: str = GONE):
    return type("TempModel", (SirModel,), {"model_id": model_id, "version": "1.0.0",
                                           "display_name": "临时注册模型"})


def _spec(model_id: str) -> dict:
    return {"schema_version": 1, "model_id": model_id, "params": {},
            "stop_condition": {"type": "steps", "value": 5}, "seed": 3}


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def orphan_experiment(client):
    """建一个「建时模型存在、之后模型消失」的实验——正是插件卸载后的库内状态。"""
    registry.register(_probe_class())
    try:
        exp = client.post("/api/experiments", json={"name": "orphan", "spec": _spec(GONE)}).json()
        eid = exp["id"]
    finally:
        registry._by_id.pop(GONE, None)
    assert client.get("/api/models").json()  # 注册表照常
    return eid


def test_run_rejects_unregistered_model_at_submit_time(client, orphan_experiment):
    eid = orphan_experiment
    for path in (f"/api/experiments/{eid}/run", f"/api/experiments/{eid}/rerun"):
        r = client.post(path, json={"wait": False})
        assert r.status_code == 422, (path, r.status_code, r.text[:200])
        detail = r.json()["detail"]
        assert detail["code"] == "spec_invalid"
        assert any(e["code"] == "unknown_model" for e in detail["errors"]), detail
        # 校验发生在状态改写之前：实验不能因此卡在 running
        assert client.get(f"/api/experiments/{eid}").json()["status"] == "created"


def test_orphan_experiment_is_still_readable(client, orphan_experiment):
    """读路径不能因为模型消失就 500——历史数据必须能查看与出报告。"""
    eid = orphan_experiment
    assert client.get(f"/api/experiments/{eid}").status_code == 200
    assert client.get(f"/api/experiments/{eid}/result").status_code == 200
    md = client.get(f"/api/experiments/{eid}/report")
    assert md.status_code == 200 and "text/markdown" in md.headers["content-type"]
    rep = client.get(f"/api/experiments/{eid}/report?format=json").json()
    assert rep["report_version"] == 1
    assert rep["experiment"]["model_id"] == GONE
    # 克隆要重新校验，因此必须拒（与 run 同口径）
    assert client.post(f"/api/experiments/{eid}/clone", json={}).status_code == 422


def test_describe_run_failure_keeps_expected_errors_one_line():
    from app.core.registry import RegistryError
    from app.core.schema.spec import SpecValidationError

    for exc_type in (SpecValidationError, RegistryError):
        try:
            raise exc_type([{"code": "unknown_model", "message": "boom"}]) if exc_type is SpecValidationError \
                else exc_type("boom")
        except (SpecValidationError, RegistryError) as exc:
            text = describe_run_failure(exc)
            assert "\n" not in text, text
            assert "Traceback" not in text and "site-packages" not in text

    class Unexpected(RuntimeError):
        pass

    try:
        raise Unexpected("engine bug")
    except Unexpected as exc:
        text = describe_run_failure(exc)
        assert text.startswith("Unexpected: engine bug")
        assert "Traceback" in text or "test_run_failure_reporting" in text  # 意外错误保留定位信息


def test_experiment_list_filters_combine_and_total_follows_filter(client):
    ids = []
    for model, tags in [("sir", ["alpha"]), ("sir", ["alpha", "keep"]), ("sir", []),
                        ("queueing", ["keep"])]:
        e = client.post("/api/experiments", json={"name": f"list-{model}-{len(ids)}", "spec": _spec(model)})
        eid = e.json()["id"]
        if tags:
            client.put(f"/api/experiments/{eid}/tags", json={"tags": tags})
        ids.append(eid)

    both = client.get("/api/experiments?model_id=sir&tag=alpha").json()
    assert {x["id"] for x in both["experiments"]} == {ids[0], ids[1]}
    assert both["total"] == 2, "total 必须是被过滤后的条数，不是全库计数"

    keep = client.get("/api/experiments?tag=keep").json()
    assert {x["id"] for x in keep["experiments"]} == {ids[1], ids[3]}

    page = client.get(f"/api/experiments?tag=keep&limit=1&offset=1").json()
    assert page["total"] == 2 and len(page["experiments"]) == 1

    none = client.get("/api/experiments?tag=%E4%B8%8D%E5%AD%98%E5%9C%A8").json()
    assert none["total"] == 0 and none["experiments"] == []

    # 过滤后仍可翻页：offset 不重叠
    a = client.get("/api/experiments?tag=keep&limit=1&offset=0").json()["experiments"]
    b = client.get("/api/experiments?tag=keep&limit=1&offset=1").json()["experiments"]
    assert a[0]["id"] != b[0]["id"]
