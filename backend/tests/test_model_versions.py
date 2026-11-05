"""多版本模型的解析与目录形状（R32）。

平台一直宣称「版本化模型 Schema」，但从没在**同一个 model_id 注册过两个版本**的场景下
验证过。探针实测出三处缺陷：① 版本号按字符串比较，`10.0.0` 排在 `2.0.0` 之前；
② `registry.get()` 的「最新版本」因此会选错；③ `/api/models` 同 id 出多条，
且 `/api/models/{id}` 返回**最旧**版本——用户看到的参数 Schema 与实际运行的版本不是一回事。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.models  # noqa: F401 - 内置模型先注册
from app.core.registry import ModelRegistry, registry, version_key
from app.main import create_app
from app.models.sir.model import SirModel

PROBE_ID = "version_probe"


def probe_class(version: str, model_id: str = PROBE_ID):
    """以 SIR 为模板造一个仅版本不同的探针模型（模型行为无关，本文件只测版本解析）。"""
    return type(
        f"VersionProbe{version.replace('.', '_')}",
        (SirModel,),
        {"model_id": model_id, "version": version, "display_name": f"版本探针模型 {version}"},
    )


def test_version_key_orders_by_numeric_components():
    assert version_key("10.0.0") > version_key("2.0.0") > version_key("1.9.9")
    assert sorted(["2.0.0", "10.0.0", "1.0.0"], key=version_key) == ["1.0.0", "2.0.0", "10.0.0"]
    assert version_key(" 1.2.3 ") == (1, 2, 3)
    assert version_key("beta") == (0,)  # 非数字段不炸，按 0 处理


def test_registry_picks_numerically_latest_version():
    reg = ModelRegistry()
    for v in ("2.0.0", "10.0.0", "1.0.0"):
        reg.register(probe_class(v))
    assert reg.versions_of(PROBE_ID) == ["1.0.0", "2.0.0", "10.0.0"]
    assert reg.get(PROBE_ID).version == "10.0.0", "「最新版本」不能按字符串 max 选"
    assert reg.get(PROBE_ID, "2.0.0").version == "2.0.0"
    listed = [(m["model_id"], m["version"]) for m in reg.list()]
    assert listed == [(PROBE_ID, "1.0.0"), (PROBE_ID, "2.0.0"), (PROBE_ID, "10.0.0")]


@pytest.fixture()
def multi_version_client():
    """往全局注册表临时挂三个版本，测完摘掉（注册表是模块级单例，不能留垃圾）。"""
    added = ("1.0.0", "2.0.0", "10.0.0")
    registry._by_id[PROBE_ID] = {v: probe_class(v) for v in added}
    try:
        with TestClient(create_app()) as c:
            yield c
    finally:
        registry._by_id.pop(PROBE_ID, None)


def test_catalog_shows_one_entry_per_model_with_version_list(multi_version_client):
    models = multi_version_client.get("/api/models").json()["models"]
    entries = [m for m in models if m["model_id"] == PROBE_ID]
    assert len(entries) == 1, f"目录里同一 model_id 出了 {len(entries)} 条（前端下拉会重复）"
    entry = entries[0]
    assert entry["version"] == "10.0.0"
    assert entry["versions"] == ["1.0.0", "2.0.0", "10.0.0"]
    assert entry["example_spec"]["model_version"] == "10.0.0", "示例 spec 必须跟着所列版本走"


def test_model_detail_defaults_to_latest_and_honors_version_query(multi_version_client):
    latest = multi_version_client.get(f"/api/models/{PROBE_ID}").json()
    assert latest["version"] == "10.0.0"
    assert latest["params_schema"]["type"] == "object"

    pinned = multi_version_client.get(f"/api/models/{PROBE_ID}?version=1.0.0").json()
    assert pinned["version"] == "1.0.0"
    assert pinned["example_spec"]["model_version"] == "1.0.0"

    missing = multi_version_client.get(f"/api/models/{PROBE_ID}?version=9.9.9")
    assert missing.status_code == 404
    assert "9.9.9" in missing.json()["detail"]["message"]
    assert "available" in missing.json()["detail"]["message"]


def test_unknown_model_id_still_404(multi_version_client):
    r = multi_version_client.get("/api/models/no_such_model")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"
