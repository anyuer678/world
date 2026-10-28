"""Automatic findings over a completed batch: 1-D sweep jumps (possible
phase transitions) and repeat-dispersion anomalies. Heuristics over the
already-aggregated summary — descriptive, never causal."""
from __future__ import annotations

from typing import Any

_RATIO_THRESHOLD = 3.0
_FLOOR = 1e-12
_CV_THRESHOLD = 0.5
_MIN_REPEATS = 3
_CAP = 5

NOTE = "自动发现只报告数据中的显著变化，不构成因果解释；单批结果不足以断言普遍规律。"


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _numeric_grid_params(grid: dict[str, list[Any]]) -> list[str]:
    return [
        k
        for k, vals in grid.items()
        if vals and all(_is_number(v) for v in vals)
    ]


def find_sweep_jumps(combos: list[dict[str, Any]], grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    numeric = _numeric_grid_params(grid)
    for param in numeric:
        if len(grid[param]) < 3:
            continue
        others = [p for p in numeric if p != param]
        base: dict[str, Any] = {}
        for p in others:
            counts: dict[Any, int] = {}
            for c in combos:
                v = c["params"].get(p)
                counts[v] = counts.get(v, 0) + 1
            base[p] = max(counts, key=counts.get)
        sweep = sorted(
            (c for c in combos if all(c["params"].get(p) == base[p] for p in others)),
            key=lambda c: c["params"][param],
        )
        if len({c["params"][param] for c in sweep}) < 3:
            continue
        for metric in sorted({m for c in sweep for m in c["metrics"]}):
            points = [
                (c["params"][param], c["metrics"][metric])
                for c in sweep
                if c["metrics"].get(metric, {}).get("n", 0) > 0
            ]
            best: dict[str, Any] | None = None
            best_score = 0.0
            for (v0, s0), (v1, s1) in zip(points, points[1:]):
                a, b = s0["mean"], s1["mean"]
                lo_real = min(abs(a), abs(b))
                hi_real = max(abs(a), abs(b))
                if hi_real == 0.0:
                    continue  # 0 -> 0: nothing changed
                if lo_real == 0.0:
                    # touching exact zero is the strongest jump; no finite factor
                    score = float("inf")
                    ratio = None
                else:
                    ratio = round(max(abs(a), abs(b)) / lo_real, 3)
                    score = ratio
                    if ratio < _RATIO_THRESHOLD:
                        continue
                if best is None or score > best_score:
                    best_score = score
                    best = {
                        "type": "jump",
                        "param": param,
                        "from": v0,
                        "to": v1,
                        "metric": metric,
                        "value_from": a,
                        "value_to": b,
                        "ratio": ratio,
                    }
            if best is not None:
                findings.append(best)
    findings.sort(key=lambda f: (-(f["ratio"] if f["ratio"] is not None else float("inf")), f["param"]))
    return findings[:_CAP]


def find_dispersion(combos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in combos:
        if c.get("n", 0) < _MIN_REPEATS:
            continue
        for metric in sorted(c["metrics"]):
            s = c["metrics"][metric]
            if s.get("n", 0) < _MIN_REPEATS:
                continue
            mean = s["mean"]
            std = s["std"]
            if not _is_number(mean) or not _is_number(std) or abs(mean) <= _FLOOR:
                continue
            cv = std / abs(mean)
            if cv >= _CV_THRESHOLD:
                out.append(
                    {
                        "type": "dispersion",
                        "params": c["params"],
                        "metric": metric,
                        "cv": round(cv, 3),
                        "n": s["n"],
                        "mean": mean,
                        "std": std,
                    }
                )
    out.sort(key=lambda f: -f["cv"])
    return out[:_CAP]


def analyze_summary(summary: dict[str, Any], grid: dict[str, list[Any]]) -> dict[str, Any]:
    combos = summary.get("combos", [])
    return {
        "findings": find_sweep_jumps(combos, grid) + find_dispersion(combos),
        "note": NOTE,
    }
