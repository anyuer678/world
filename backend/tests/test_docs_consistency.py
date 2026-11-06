"""文档声称与代码现实的一致性锁。

R24–R30 每轮都在手工修同一类问题：README/BENCHMARKS 里的模型数、测试文件数、
端点清单与代码漂移（「四模型」错了二十几轮才被读出来）。本文件把这些声称绑到
注册表、路由表、磁盘与前端分发器上——再漂移就是红测试，而不是靠人记得去数。
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from app.core.registry import registry

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")
CONTRACT = (ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")
BENCHMARKS = (ROOT / "docs" / "BENCHMARKS.md").read_text(encoding="utf-8")
ARCH = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
PLUGINS = (ROOT / "docs" / "PLUGINS.md").read_text(encoding="utf-8")
DECISIONS = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
SIMVIEW = (ROOT / "frontend" / "src" / "SimView.tsx").read_text(encoding="utf-8")

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


def test_living_docs_model_count_phrases_match_registry():
    """README/ARCHITECTURE 是面向读者的现状文档（CHANGELOG/DECISIONS 有历史口径，不在此列）。
    R89：README 的测试说明与 ARCHITECTURE 的架构框图长期写「八模型」，而实际已九个。"""
    count = len(builtin_model_ids())
    numeral = CN_NUMERAL.get(count)
    assert numeral is not None, f"计数措辞测试未覆盖 {count} 个模型，请更新 CN_NUMERAL"
    for name, text in (("README.md", README), ("ARCHITECTURE.md", ARCH)):
        found = set(re.findall(r"([一二三四五六七八九十])个内置模型", text))
        found |= set(re.findall(r"内置([一二三四五六七八九十])个", text))
        assert found == {numeral}, (
            f"{name} 的模型数量措辞 {sorted(found)} 与注册表（{count} 个）不一致"
        )


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


# --------------------------------------------- R36：ARCHITECTURE / PLUGINS 与代码对账

SCOPE_PREFIXES = ("backend/app/", "backend/scripts/", "backend/migrations/", "frontend/src/")


def _shape(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "*", path.split("?")[0].rstrip("/"))


def _architecture_tree_paths() -> set[str]:
    """「文件清单」代码块里每行以两个空格开头的路径 token。"""
    block = ARCH.split("## 文件清单", 1)[1].split("```", 2)[1]
    found = set()
    for line in block.splitlines():
        m = re.match(r"\s\s((?:backend|frontend|docs|README\.md|LICENSE|docker-compose\.yml|\.gitignore)\S*)", line)
        if m:
            found.add(m.group(1))
    return found


def test_architecture_manifest_has_no_phantom_or_stale_paths():
    mentioned = _architecture_tree_paths()
    missing = sorted(p for p in mentioned if not (ROOT / p).exists())
    assert not missing, f"ARCHITECTURE 列了磁盘上不存在的文件：{missing}"


def test_architecture_manifest_covers_every_source_file():
    mentioned = _architecture_tree_paths()
    on_disk = set()
    for prefix in SCOPE_PREFIXES:
        for p in (ROOT / prefix).rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT).as_posix()
            if rel.endswith("__init__.py"):
                continue
            if rel.endswith((".py", ".sql", ".ts", ".tsx", ".toml", ".lock")):
                on_disk.add(rel)
    unlisted = sorted(on_disk - mentioned)
    assert not unlisted, f"磁盘上有、ARCHITECTURE 清单里没有的文件：{unlisted}"


def test_architecture_limits_claims_are_real_fields():
    from app.core.engine.engines import Limits

    fields = {f.name for f in dataclasses.fields(Limits)}
    anchor = ARCH.index("资源上限就是")
    segment = ARCH[anchor:anchor + 400].split("模拟时间上限")[0]
    listed = set(re.findall(r"`([a-z_]+)`", segment)) - {"Limits"}
    assert listed == fields, f"文档列的上限 {sorted(listed)} ≠ Limits 真实字段 {sorted(fields)}"
    assert "max_events" not in ARCH, "max_events 从来不是 Limits 的字段（旧文档的幻影）"


def test_architecture_table_section_matches_migrations_and_writers():
    sql = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "backend" / "migrations").glob("*.sql"))
    declared = set(re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?(\w+)", sql))
    code = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "backend" / "app").rglob("*.py"))
    written = set(re.findall(r"(?:INSERT INTO|INSERT OR IGNORE INTO|UPDATE|DELETE FROM)\s+(\w+)", code))

    doc_rows = set(re.findall(r"^\| `(\w+)` \|", ARCH, flags=re.M))
    assert doc_rows >= declared, f"ARCHITECTURE 漏表：{sorted(declared - doc_rows)}"
    ghost = sorted(t for t in doc_rows if t not in declared and t != "schema_migrations")
    assert not ghost, f"ARCHITECTURE 写了不存在的表：{ghost}"

    dead = sorted(t for t in declared - written)
    for t in dead:
        row = next(line for line in ARCH.splitlines() if line.startswith(f"| `{t}`"))
        assert "没有写入方" in row, f"死表 {t} 必须在文档里标明「已建表但当前没有写入方」，不得写成可用能力"


def test_plugins_documented_kinds_match_frontend_dispatcher():
    handled = set(re.findall(r"visualizer\.kind === '([a-z_]+)'", SIMVIEW))
    assert handled, "SimView 里找不到 kind 分发"
    assert "StateTable" in SIMVIEW, "未知 kind 必须有兜底视图"
    sentence = PLUGINS.split("对以下 kind 有专用视图：", 1)[1].split("；", 1)[0]
    documented = set(re.findall(r"`([a-z_]+)`", sentence))
    assert documented == handled, f"PLUGINS.md 的 kind 清单 {sorted(documented)} ≠ SimView 分发 {sorted(handled)}"
    assert "StateTable" in PLUGINS and "不读取它" in PLUGINS, "须写明兜底视图与 series 未被前端消费"


def test_architecture_endpoint_literals_exist_in_openapi():
    """架构文档里出现的 /api/ 路径（含不带方法名的裸写法）必须都是真实端点。
    前置断言排除 `backend/app/api/routes.py` 这类文件系统路径，结尾排除 .py。"""
    real = {_shape(p) for p in api_paths()}
    claimed = re.findall(r"(?:GET|POST|PUT|DELETE) (/api/[^\s`（)，。]+)", ARCH)
    claimed += [m for m in re.findall(r"(?<![\w./])/api/[A-Za-z0-9_/{}.-]*[A-Za-z0-9_/{}]", ARCH)
                if not m.endswith(".py")]
    ghost = sorted(c for c in set(claimed) if _shape(c) not in real)
    assert claimed, "架构文档里一个端点都没提，这条锁变成空锁"
    assert len(real) > 10 and len(set(claimed)) >= 3, f"匹配数异常少（{len(set(claimed))}），检查正则是否失效"
    assert not ghost, f"ARCHITECTURE 引用了不存在的端点：{ghost}"


def test_every_decision_reference_points_to_a_real_row():
    """R39：文档里到处是「（见 D53）」这类指针。写错一个数字，读者就顺着断链找不到依据，
    而这类错误肉眼很难发现——所以逐条解析并核对 DECISIONS 的行号。"""
    rows = set(re.findall(r"^\| (D\d+) \|", DECISIONS, flags=re.M))
    assert rows, "DECISIONS.md 里没解析到任何决策行，锁本身失效了"
    broken = []
    for name in ("README.md", "docs/ARCHITECTURE.md", "docs/API_CONTRACT.md", "docs/PLUGINS.md",
                 "docs/TESTING.md", "docs/CHANGELOG.md", "docs/BENCHMARKS.md", "docs/DECISIONS.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for ref in re.findall(r"(?:见|由|见 D|参见)\s*(D\d+)\b", text):
            if ref not in rows:
                broken.append(f"{name}→{ref}")
        for ref in re.findall(r"\bD\d+\b", text):
            if ref not in rows:
                broken.append(f"{name}~{ref}")
    assert not broken, f"指向不存在的决策行：{sorted(set(broken))}"


def test_benchmarks_are_internally_consistent_and_attributed():
    """R38：基准表的每个吞吐数字必须与同行「步数 ÷ 耗时」算得通。

    这不是形式检查：R22 曾把新模型的行插进另一台机位/另一轮的行里，R26 定下
    「整表来自同一次运行」的规矩却无人执行。算术一致性让改错一个数、
    混进别轮数字都变成红，而不是靠人记得核对。"""
    rows = re.findall(
        r"^\| (\w+)（[^）]*） \| ([\d,]+) \| ([\d.]+) s \| ≈([\d,]+) steps/s \|", BENCHMARKS, flags=re.M)
    assert len(rows) >= len(registry.builtin_ids()) - 2, f"引擎表行数异常少：{len(rows)}"
    for model, steps, secs, sps in rows:
        computed = int(steps.replace(",", "")) / float(secs)
        claimed = float(sps.replace(",", ""))
        # 3% 容差：够覆盖「3 位有效数字 + 耗时保留 3 位小数」的舍入，
        # 又能抓住把另一轮（哪怕只差 8%）的数字混进本表的情况。
        assert abs(computed - claimed) / claimed < 0.03, (
            f"{model} 表内不自洽：{steps}/{secs}s = {computed:,.0f}，却写 ≈{claimed:,.0f}")

    m = re.search(r"(\d+) items in ([\d.]+) s ≈ ([\d.]+) items/s", BENCHMARKS)
    assert m, "批量吞吐行格式变了，锁需要同步"
    assert abs(int(m.group(1)) / float(m.group(2)) - float(m.group(3))) / float(m.group(3)) < 0.03, m.groups()

    p50, p95, pmax = (float(x) for x in re.search(
        r"p50 = ([\d.]+) ms，p95 = ([\d.]+) ms，max = ([\d.]+) ms", BENCHMARKS).groups())
    assert p50 <= p95 <= pmax, (p50, p95, pmax)

    assert "解释器" in BENCHMARKS and re.search(r"Python \d+\.\d+\.\d+", BENCHMARKS), "缺解释器归属"
    assert "uv run python scripts/benchmark.py" in BENCHMARKS, "必须写明用哪条命令跑出的数（venv 与系统解释器不是同一机位）"


def test_comparability_guard_is_described_where_it_actually_lives():
    """R36：旧架构文档把「比较 API 返回 cross_version 警告字段」写成已完成能力，
    实际代码里根本没有该字段——不可比提示由前端 ComparePanel 判定、报告用 comparability_note 声明。"""
    assert "cross_version=true" not in ARCH and "cross_version" not in CONTRACT
    compare_src = (ROOT / "frontend" / "src" / "ComparePanel.tsx").read_text(encoding="utf-8")
    assert "不可直接比较" in compare_src, "不可比提示的实现位置变了，文档要跟着改"
    assert "ComparePanel" in ARCH and "comparability_note" in ARCH


# ------------------------------------------- R37：环境变量清单与 Limits 传参完整性

CONFIG = (ROOT / "backend" / "app" / "config.py").read_text(encoding="utf-8")
SERVICE_FILES = ("experiment_service.py", "session_service.py", "batch_service.py")


def test_readme_env_list_matches_config_completely():
    """README 的环境变量清单必须与 `Settings.from_env()` 读取的变量**双向**一致：
    少写一个＝特性没人知道（R30 就漏过 EVENT_LOG_SIZE 与 PLUGIN_MODULES）。"""
    read = set(re.findall(r'"(WORLDLAB_[A-Z_]+)"', CONFIG))
    documented = set(re.findall(r"`(WORLDLAB_[A-Z_]+)`", README))
    assert read, "config.py 里读不到任何环境变量？"
    assert documented == read, (f"README 多的：{sorted(documented - read)}；README 漏的：{sorted(read - documented)}")


def test_readme_env_defaults_match_code():
    """清单里写明的默认值必须等于代码里的真实默认值（数量级写错会误导容量规划，R29 案例）。"""
    for env, default in re.findall(r'environ\.get\(\s*"(WORLDLAB_[A-Z_]+)",\s*"([^"]+)"', CONFIG):
        segment = re.search(rf"`{env}`（([^）]*)）", README)
        assert segment, f"README 未给出 {env} 的默认值说明"
        text = segment.group(1)
        claimed = [n.replace(",", "") for n in re.findall(r"\d[\d,]*", text)]
        assert default in claimed, f"{env} 文档默认值 {text!r} 与代码 {default} 不符"


def test_every_service_passes_all_four_limits_fields():
    """三条执行路径（实验/会话/批量）构造 `Limits` 时都要显式给全四个字段，
    否则某个 Settings 项会静默退回 dataclass 默认值（R37 会话侧的真实缺陷）。"""
    for name in SERVICE_FILES:
        src = (ROOT / "backend/app/services" / name).read_text(encoding="utf-8")
        for m in re.finditer(r"Limits\(", src):
            block = src[m.start():m.start() + 400]
            missing = [f for f in ("max_steps", "max_wall_seconds", "zero_delay_chain_limit",
                                   "cancel_poll_interval") if f not in block]
            assert not missing, f"{name} 构造 Limits 时漏传 {missing}"


def test_every_setting_field_is_actually_consumed():
    """R70：`Settings` 的每个字段都必须有使用方。

    R37 修过「Limits 漏传两项」，R70 又发现 `event_log_size` 被读入后**从未使用**
    （事件环硬编码 500）——同一类「配置读了但不生效」。这条锁把这类问题从「靠人记得」
    变成 CI 红：字段名必须在 `backend/app/`（config.py 之外）出现。"""
    from app.config import Settings

    app_dir = ROOT / "backend" / "app"
    corpus = "\n".join(
        p.read_text(encoding="utf-8")
        for p in app_dir.rglob("*.py")
        if p.name != "config.py" and "__pycache__" not in p.parts
    )
    unused = [f for f in Settings.__dataclass_fields__ if f not in corpus]
    assert not unused, f"配置项无人使用（读了但不生效）：{unused}"

