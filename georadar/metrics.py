"""Visibility metrics: SOV, mention rate, first-position, stability, variance."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from statistics import mean
from typing import Any, Iterable, Optional


ORGANIC_EXCLUDE = {"品牌对比", "品牌咨询"}


def is_organic(row: dict, exclude: Optional[set[str]] = None) -> bool:
    exclude = exclude or ORGANIC_EXCLUDE
    if row.get("has_brand_in_query"):
        return False
    return row.get("qtype") not in exclude


def _brand_set(row: dict) -> set[str]:
    return set(row.get("rule_brand_ids") or [])


def mention_rate(rows: list[dict], brand_id: str) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if brand_id in _brand_set(r)) / len(rows)


def share_of_voice(rows: list[dict]) -> dict[str, float]:
    """Share of (answer, unique-brand) pairs."""
    counts: Counter[str] = Counter()
    for r in rows:
        for b in _brand_set(r):
            counts[b] += 1
    total = sum(counts.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in counts.items()}


def first_position_rate(rows: list[dict], brand_id: str, field: str = "rule_first_id") -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.get(field) == brand_id) / len(rows)


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    A, B = set(a), set(b)
    if not A and not B:
        return 1.0
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def stability_by_query_model(rows: list[dict]) -> dict[str, Any]:
    """Group by (query_id, model) and compare runs."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["query_id"], r["model"])].append(r)
    jacs, first_agree, n_pairs = [], [], 0
    empty_both = 0
    for key, items in groups.items():
        items = sorted(items, key=lambda x: x.get("run", 0))
        if len(items) < 2:
            continue
        # all pairs if more than 2 runs
        for x, y in combinations(items, 2):
            n_pairs += 1
            sx, sy = _brand_set(x), _brand_set(y)
            jacs.append(jaccard(sx, sy))
            if not sx and not sy:
                empty_both += 1
            first_agree.append(1.0 if x.get("rule_first_id") == y.get("rule_first_id") else 0.0)
    return {
        "n_groups_with_2plus": sum(1 for items in groups.values() if len(items) >= 2),
        "n_pairs": n_pairs,
        "mean_jaccard": mean(jacs) if jacs else None,
        "mean_first_agree": mean(first_agree) if first_agree else None,
        "empty_both_pairs": empty_both,
    }


def cross_model_jaccard(rows: list[dict], run: int = 0) -> dict[str, Any]:
    """Pairwise Jaccard of brand sets across models, same query and run."""
    by_qm: dict[tuple, dict] = {}
    for r in rows:
        if r.get("run") != run:
            continue
        by_qm[(r["query_id"], r["model"])] = r
    queries = sorted({q for q, _ in by_qm})
    models = sorted({m for _, m in by_qm})
    pair_scores: dict[str, list[float]] = defaultdict(list)
    for q in queries:
        sets = {m: _brand_set(by_qm[q, m]) for m in models if (q, m) in by_qm}
        for a, b in combinations(sorted(sets), 2):
            pair_scores[f"{a}||{b}"].append(jaccard(sets[a], sets[b]))
    return {
        "run": run,
        "models": models,
        "n_queries": len(queries),
        "pairwise_mean_jaccard": {k: mean(v) for k, v in pair_scores.items() if v},
    }


def source_type_distribution(rows: list[dict], key: str = "rule_sources") -> dict[str, float]:
    counts: Counter[str] = Counter()
    for r in rows:
        for s in r.get(key) or []:
            counts[s.get("source_type") or "unknown"] += 1
    total = sum(counts.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in counts.most_common()}


def url_stats(rows: list[dict]) -> dict[str, Any]:
    n_ans = len(rows)
    n_with = 0
    n_urls = 0
    n_well = 0
    for r in rows:
        urls = [s for s in (r.get("rule_sources") or []) if s.get("url")]
        if urls:
            n_with += 1
        n_urls += len(urls)
        n_well += sum(1 for s in urls if s.get("well_formed_url"))
    return {
        "n_answers": n_ans,
        "answers_with_url": n_with,
        "url_rate": n_with / n_ans if n_ans else 0.0,
        "n_urls": n_urls,
        "n_well_formed": n_well,
    }


def slice_metrics(
    rows: list[dict],
    name_map: dict[str, str],
    top_n: int = 15,
) -> list[dict]:
    sov = share_of_voice(rows)
    ranked = sorted(sov.items(), key=lambda kv: -kv[1])[:top_n]
    out = []
    for bid, share in ranked:
        out.append(
            {
                "brand_id": bid,
                "brand_name": name_map.get(bid, bid),
                "sov": share,
                "mention_rate": mention_rate(rows, bid),
                "first_position_rate": first_position_rate(rows, bid),
                "n_answers": len(rows),
            }
        )
    return out


def answers_mentioning_any(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if _brand_set(r)) / len(rows)
