"""Bootstrap confidence intervals. Unit of resampling is the question."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Callable, Optional


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def bootstrap_ci(
    values: list[float],
    n_boot: int = 2000,
    seed: int = 42,
    alpha: float = 0.05,
) -> dict:
    if not values:
        return {"n": 0, "mean": None, "ci_low": None, "ci_high": None}
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(alpha / 2 * n_boot)]
    hi = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return {"n": n, "mean": sum(values) / n, "ci_low": lo, "ci_high": hi, "n_boot": n_boot}


def question_means(rows: list[dict], field: str, filters: Optional[dict] = None) -> list[float]:
    """Average `field` across seeds (and optionally models already filtered) per question."""
    filt = filters or {}
    groups: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if any(r.get(k) != v for k, v in filt.items()):
            continue
        val = r.get(field)
        if val is None:
            continue
        groups[r["query_id"]].append(float(val))
    return [sum(v) / len(v) for v in groups.values() if v]
