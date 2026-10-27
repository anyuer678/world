"""Experiment report building and export rendering (markdown / JSON / CSV).

Reports contain only data recorded in the database — no derived or fabricated
numbers. Aggregate metrics are the plain mean over completed runs, matching
get_result().
"""
from __future__ import annotations

import csv
import io
import json
import platform
from datetime import datetime, timezone
from typing import Any

COMPARABILITY_NOTE = (
    "实验结果默认仅在相同 model_id 且相同 model_version 之间可比；"
    "跨模型版本的结果需明确声明后方能比较。"
)


def build_experiment_report(result: dict[str, Any], app_version: str, engine_version: str) -> dict[str, Any]:
    exp = dict(result["experiment"])
    exp_runs = exp.pop("runs", [])
    exp.pop("spec_json", None)
    return {
        "report_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "software": {
            "app_version": app_version,
            "engine_version": engine_version,
            "python_version": platform.python_version(),
        },
        "experiment": exp,
        "runs": result["runs"],
        "aggregate": result["aggregate"],
        "run_list_note": f"实验详情接口返回 {len(exp_runs)} 条运行摘要；本报告列出 {len(result['runs'])} 条完整运行记录。",
        "comparability_note": COMPARABILITY_NOTE,
    }


def render_report_markdown(report: dict[str, Any]) -> str:
    exp = report["experiment"]
    lines: list[str] = []
    lines.append(f"# WorldLab 实验报告 — {exp.get('name', '')} (#{exp.get('id')})")
    lines.append("")
    lines.append(f"- 模型：{exp.get('model_id')} v{exp.get('model_version')}")
    lines.append(f"- 实验状态：{exp.get('status')}")
    tags = exp.get("tags") or []
    lines.append(f"- 标签：{', '.join(tags) if tags else '（无）'}")
    lines.append(f"- 生成时间：{report['generated_at']}")
    sw = report["software"]
    lines.append(
        f"- 软件版本：WorldLab {sw['app_version']} · 引擎 {sw['engine_version']} · Python {sw['python_version']}"
    )
    lines.append("")
    lines.append("## 实验配置（spec）")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(exp.get("spec"), ensure_ascii=False, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## 运行记录")
    lines.append("")
    lines.append("| repeat | seed | steps | sim_time | 时长(ms) | 状态 | result_sha256 | 错误 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in report["runs"]:
        sha = r.get("result_sha256") or "—"
        err = (r.get("error") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {r.get('repeat_index', '—')} | {r.get('seed') if r.get('seed') is not None else '—'}"
            f" | {r.get('steps') if r.get('steps') is not None else '—'}"
            f" | {r.get('sim_time') if r.get('sim_time') is not None else '—'}"
            f" | {r.get('duration_ms') if r.get('duration_ms') is not None else '—'}"
            f" | {r.get('status', '—')} | {sha} | {err or '—'} |"
        )
    lines.append("")
    lines.append("### 各运行指标")
    lines.append("")
    any_metrics = False
    for r in report["runs"]:
        metrics = r.get("metrics")
        if not metrics:
            continue
        any_metrics = True
        lines.append(
            f"**运行 repeat={r.get('repeat_index', '—')}（seed={r.get('seed')}，result_sha256={r.get('result_sha256') or '—'}）**"
        )
        lines.append("")
        for k in sorted(metrics):
            lines.append(f"- {k}: {metrics[k]}")
        lines.append("")
    if not any_metrics:
        lines.append("（无已完成的运行指标）")
        lines.append("")
    aggregate = report.get("aggregate")
    lines.append("## 聚合指标（completed 运行的均值）")
    lines.append("")
    if aggregate:
        for k in sorted(aggregate):
            lines.append(f"- {k}: {aggregate[k]}")
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("## 说明")
    lines.append("")
    lines.append(f"- {report['comparability_note']}")
    lines.append("- result_sha256 为对 metrics 规范化 JSON（sorted keys）计算的 SHA-256，用于结果完整性校验。")
    return "\n".join(lines)


CSV_COLUMNS = [
    "item_index",
    "repeat_index",
    "seed",
    "status",
    "attempts",
    "steps",
    "sim_time",
    "duration_ms",
    "result_sha256",
    "error",
    "params",
    "metrics",
]


def render_batch_items_csv(batch: dict[str, Any], items: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["# WorldLab 批量实验导出"])
    writer.writerow(["# 批量", f"#{batch.get('id')} {batch.get('name', '')}"])
    writer.writerow(
        ["# 模型", f"{batch.get('model_id')} v{batch.get('model_version')}",
         "种子策略", batch.get("seed_strategy", "")]
    )
    writer.writerow(CSV_COLUMNS)
    for it in items:
        writer.writerow([
            it.get("item_index"),
            it.get("repeat_index"),
            it.get("seed"),
            it.get("status"),
            it.get("attempts"),
            it.get("steps") if it.get("steps") is not None else "",
            it.get("sim_time") if it.get("sim_time") is not None else "",
            it.get("duration_ms") if it.get("duration_ms") is not None else "",
            it.get("result_sha256") or "",
            it.get("error") or "",
            json.dumps(it.get("params"), ensure_ascii=False, sort_keys=True),
            json.dumps(it.get("metrics"), ensure_ascii=False, sort_keys=True) if it.get("metrics") else "",
        ])
    return buf.getvalue()
