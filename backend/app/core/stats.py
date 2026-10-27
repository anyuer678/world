"""Pure-Python statistics for batch experiments (no numpy dependency).

Sample std uses ddof=1; quantiles use linear interpolation (numpy default).
CI is a normal-approximation 95% interval - labelled as such at the API layer
because it is only appropriate for reasonably large n.
"""
from __future__ import annotations

import math


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def sample_std(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))


def quantile(values: list[float], q: float) -> float:
    """Linear-interpolation quantile, q in [0, 1] (numpy 'linear' method)."""
    if not values:
        raise ValueError("quantile of empty list")
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation; None when either side has zero variance."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx, my = mean(xs), mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0.0 or syy == 0.0:
        return None
    return sxy / math.sqrt(sxx * syy)


def summarize(values: list[float]) -> dict[str, float | int]:
    n = len(values)
    if n == 0:
        return {"n": 0}
    m = mean(values)
    s = sample_std(values)
    half = 1.96 * s / math.sqrt(n) if n > 0 else 0.0
    return {
        "n": n,
        "mean": m,
        "std": s,
        "p50": quantile(values, 0.5),
        "p90": quantile(values, 0.9),
        "ci95_low": m - half,
        "ci95_high": m + half,
    }
