"""文档声称与代码现实的一致性锁。

R24–R30 每轮都在手工修同一类问题：README/BENCHMARKS 里的模型数、测试文件数、
端点清单与代码漂移（「四模型」错了二十几轮才被读出来）。本文件把这些声称绑到
注册表与路由表上——再漂移就是红测试，而不是靠人记得去数。
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.registry import registry

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")
CONTRACT = (ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")
BENCHMARKS = (ROOT / "docs" / "BENCHMARKS.md").read_text(encoding="utf-8")

CN_NUMERAL = {1: "一", 2: "两", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}


def builtin_model_ids() -> set[str]:
    """内置模型清单的唯一事实源在注册表（registry.builtin_ids）。"""
    return set(registry.builtin_ids())


def test_registry_builtin_set_is_non_empty_and_excludes_plugin_packages():
    ids = builtin_model_ids()
    assert ids, "注册表里应当有内置模型"
    assert {"queueing", "sir", "predator_prey"} <= ids


def test_readme_model_table_lists_exactly_the_builtin_models():
    table = README.split("## 内置模型", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in table.splitlines() if line.startswith("| `")]
    documented = {re.match(r"\| `([^`]+)`", row).group(1) for row in rows}
    assert documented == builtin_model_ids(), "README「内置模型」表与注册表不一致"


def test_readme_builtin_count_wording_matches_registry():
    count = len(builtin_model_ids())
    numeral = CN_NUMERAL.get(count)
    if numeral is None:  # 超过 10 个模型时改用阿拉伯数字表述，需同步更新本测试
        raise AssertionError(f"README 计数措辞测试未覆盖 {count} 个模型，请更新 CN_NUMERAL 与文案")
    assert f"{numeral}个内置模型" in README, f"README 应写「{numeral}个内置模型」"


def test_readme_backend_test_file_count_matches_disk():
    on_disk = len(list((ROOT / "backend" / "tests").glob("test_*.py")))
    claimed = {int(n) for n in re.findall(r"（(\d+) 个测试文件）", README)}
    assert claimed == {on_disk}, f"README 声称 {sorted(claimed)} 个测试文件，磁盘上 {on_disk} 个"


def test_benchmarks_cover_every_builtin_model():
    missing = [mid for mid in sorted(builtin_model_ids())
               if not re.search(rf"\b{re.escape(mid)}\b", BENCHMARKS)]
    assert not missing, f"BENCHMARKS 缺少模型吞吐行：{missing}"


def api_paths() -> list[str]:
    """真实对外端点取自 OpenAPI（FastAPI 新版把 include_router 的结果包在
    _IncludedRouter 里，app.routes 不再是扁平路径表）。"""
    from app.main import app

    return sorted(app.openapi()["paths"])


def _doc_pattern(route_path: str) -> re.Pattern:
    r"""把 /api/batches/{batch_id} 变成同时接受 `{任意}` 与真实值的正则——
    契约文档里的占位符命名（{id} / {exp_id}）不必与代码一致。"""
    parts = [re.escape(seg) if not seg.startswith("{") else r"(?:\{[^}]*\}|[^/]+)"
             for seg in route_path.strip("/").split("/")]
    return re.compile(r"(?<![\w/-])/" + "/".join(parts) + r"(?![\w/])")


def test_every_api_route_is_documented_in_the_contract():
    undocumented = [path for path in api_paths() if not _doc_pattern(path).search(CONTRACT)]
    assert not undocumented, f"API_CONTRACT.md 未记载的端点：{undocumented}"


def test_contract_promises_no_endpoint_that_does_not_exist():
    """反向锁：文档不能凭空承诺端点（R25 发现过「契约写了却没实现」的 events）。"""

    def shape(path: str) -> str:
        return re.sub(r"\{[^}]*\}", "*", path.split("?")[0].rstrip("/"))

    real = {shape(path) for path in api_paths()}
    claimed = {shape(match) for match in re.findall(r"(?:GET|POST|PUT|DELETE) (/api/[^\s`]+)", CONTRACT)}
    ghost = sorted(claimed - real)
    assert not ghost, f"契约承诺了 OpenAPI 里没有的端点：{ghost}"
