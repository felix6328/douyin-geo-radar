"""GeoLab controlled experiment: strategies × questions × models × seeds."""

from __future__ import annotations

import asyncio
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import yaml

from geo_common.llm import LLMClient, cumulative_spend_cny
from geo_common.progress import gather_progress
from geo_common.paths import ANSWERS, CONFIGS, EVAL, GOLD, INSIGHTS, ensure_data_dirs
from geolab.corpus import (
    STRATEGY_NOTES,
    STRATEGY_ORDER,
    TARGET_ID,
    all_target_variants,
    corpus_for,
    fixed_documents,
    load_specs,
)
from geolab.factcheck import factcheck_all_variants, factcheck_target_text
from geolab.generate import messages_for
from geolab.pawc import impressions
from geolab.retrieve import Retriever
from geolab.statsutil import bootstrap_ci, question_means
from geolab.report import build_eval_payload, write_badcases, write_results_md


def load_settings() -> dict:
    return yaml.safe_load((CONFIGS / "settings.yaml").read_text(encoding="utf-8"))


def load_queries() -> list[dict]:
    raw = yaml.safe_load((CONFIGS / "queries" / "geolab_queries.yaml").read_text(encoding="utf-8"))
    return list(raw["queries"])


def _dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def train_test_split(queries: list[dict], ratio: float, seed: int) -> tuple[list[dict], list[dict]]:
    """Stratified by qtype, deterministic."""
    rng = random.Random(seed)
    by = defaultdict(list)
    for q in queries:
        by[q["qtype"]].append(q)
    train, test = [], []
    for qt, items in by.items():
        items = items[:]
        rng.shuffle(items)
        n_train = max(1, int(round(len(items) * ratio)))
        n_train = min(n_train, len(items) - 1) if len(items) > 1 else len(items)
        train.extend(items[:n_train])
        test.extend(items[n_train:])
    train.sort(key=lambda q: q["id"])
    test.sort(key=lambda q: q["id"])
    return train, test


def retrieve_pack(
    query: str,
    strategy: str,
    top_k: int,
    frozen_from_baseline: bool,
) -> tuple[list, list[str], Optional[int], Optional[int], float]:
    """Return retrieved docs, numbered ids, target rank (live), target rank (baseline), score."""
    live_docs = corpus_for(strategy)
    live = Retriever(live_docs)
    live_rank, live_score = live.rank_of(query, TARGET_ID)
    base = Retriever(corpus_for("baseline"))
    base_rank, _ = base.rank_of(query, TARGET_ID)
    if frozen_from_baseline:
        packed = base.search(query, top_k=top_k)
        # replace target body with the strategy variant, keep order
        variant = {d.doc_id: d for d in live_docs}[TARGET_ID]
        docs = []
        for d, score, rank in packed:
            docs.append(variant if d.doc_id == TARGET_ID else d)
        numbered = [d.doc_id for d in docs]
        return docs, numbered, live_rank, base_rank, live_score
    packed = live.search(query, top_k=top_k)
    docs = [d for d, _, _ in packed]
    numbered = [d.doc_id for d in docs]
    return docs, numbered, live_rank, base_rank, live_score


async def generate_all(
    client: LLMClient,
    queries: list[dict],
    models: list[str],
    seeds: list[int],
    strategies: list[str],
    top_k: int,
    temperature: float,
    max_tokens: int,
    frozen: bool = False,
    purpose: str = "geolab_answer",
) -> list[dict]:
    jobs = []
    meta = []
    for q in queries:
        for st in strategies:
            for model in models:
                for seed in seeds:
                    docs, numbered, live_rank, base_rank, live_score = retrieve_pack(
                        q["text"], st, top_k, frozen_from_baseline=frozen
                    )
                    msgs, ids = messages_for(q["text"], docs)
                    assert ids == numbered
                    meta.append(
                        {
                            "query_id": q["id"],
                            "query_text": q["text"],
                            "qtype": q["qtype"],
                            "strategy": st,
                            "model": model,
                            "seed": seed,
                            "frozen_retrieval": frozen,
                            "retrieved_ids": numbered,
                            "target_in_topk": TARGET_ID in numbered,
                            "target_rank_live": live_rank,
                            "target_rank_baseline": base_rank,
                            "target_bm25_score": live_score,
                            "top_k": top_k,
                        }
                    )
                    jobs.append(
                        client.chat(
                            model,
                            msgs,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            seed=seed,
                            purpose=purpose,
                        )
                    )
    results = await gather_progress(jobs, purpose)
    rows = []
    specs = load_specs()
    all_docs_by_st = {st: corpus_for(st) for st in strategies}
    for info, res in zip(meta, results):
        if isinstance(res, Exception):
            content, pt, ct, cht, cost, lat, cached, error = "", 0, 0, 0, None, 0, False, type(res).__name__
        else:
            content = res.content
            pt, ct, cht = res.prompt_tokens, res.completion_tokens, res.cache_hit_tokens
            cost = res.cost_cny if not res.cached else 0.0
            lat, cached, error = res.latency_ms, res.cached, res.error
        docs = all_docs_by_st[info["strategy"]]
        imp = impressions(content, docs, numbered=info["retrieved_ids"], target_brand="北屿")
        t = imp[TARGET_ID]
        row = dict(info)
        row.update(
            {
                "answer": content,
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "cache_hit_tokens": cht,
                "cost_cny": cost,
                "latency_ms": lat,
                "cached": cached,
                "error": error,
                "cite_rate": 1.0 if t.n_cited_sentences > 0 else 0.0,
                "mention_rate": 1.0 if t.mentioned_brand else 0.0,
                "imp_wc": t.imp_wc,
                "imp_pwc": t.imp_pwc,
                "n_cited_sentences": t.n_cited_sentences,
                "first_cite_pos": t.first_cite_pos,
            }
        )
        rows.append(row)
    return rows


def _agg_table(rows: list[dict], filters: Optional[dict] = None) -> list[dict]:
    filters = filters or {}
    subset = [r for r in rows if all(r.get(k) == v for k, v in filters.items())]
    # group strategy × model (if model not filtered)
    keys = sorted({(r["strategy"], r["model"]) for r in subset})
    out = []
    for st, model in keys:
        sub = [r for r in subset if r["strategy"] == st and r["model"] == model]
        cite_q = question_means(sub, "cite_rate")
        pawc_q = question_means(sub, "imp_pwc")
        wc_q = question_means(sub, "imp_wc")
        men_q = question_means(sub, "mention_rate")
        in_top = question_means(sub, "target_in_topk")
        out.append(
            {
                "strategy": st,
                "model": model,
                "n_rows": len(sub),
                "n_questions": len(cite_q),
                "cite_rate": bootstrap_ci(cite_q),
                "mention_rate": bootstrap_ci(men_q),
                "imp_pwc": bootstrap_ci(pawc_q),
                "imp_wc": bootstrap_ci(wc_q),
                "target_in_topk": bootstrap_ci([float(x) for x in in_top]),
                "mean_target_rank_live": _mean_rank(sub),
            }
        )
    return out


def _mean_rank(rows: list[dict]) -> Optional[float]:
    ranks = [r["target_rank_live"] for r in rows if r.get("target_rank_live") is not None]
    return (sum(ranks) / len(ranks)) if ranks else None


def relative_improvement(table: list[dict], metric: str = "imp_pwc") -> list[dict]:
    """(strategy - baseline) / baseline, per model. Uses question-mean of metric."""
    out = []
    models = sorted({r["model"] for r in table})
    for model in models:
        base = next((r for r in table if r["strategy"] == "baseline" and r["model"] == model), None)
        if not base or not base[metric]["mean"]:
            bmean = base[metric]["mean"] if base else None
        else:
            bmean = base[metric]["mean"]
        for r in table:
            if r["model"] != model:
                continue
            m = r[metric]["mean"]
            rel = None
            if bmean not in (None, 0) and m is not None:
                rel = (m - bmean) / bmean * 100
            pp = None
            if bmean is not None and m is not None:
                pp = (m - bmean) * (100 if metric in {"cite_rate", "mention_rate", "target_in_topk"} else 1)
            out.append(
                {
                    "strategy": r["strategy"],
                    "model": model,
                    "metric": metric,
                    "mean": m,
                    "baseline_mean": bmean,
                    "relative_pct": rel,
                    "delta": (m - bmean) if (m is not None and bmean is not None) else None,
                    "delta_pp": pp,
                    "ci_low": r[metric]["ci_low"],
                    "ci_high": r[metric]["ci_high"],
                }
            )
    return out


def policy_from_train(train_rows: list[dict], metric: str = "cite_rate") -> dict[str, str]:
    """For each qtype, pick the strategy with highest mean metric on train (not baseline-forced)."""
    policy = {}
    qtypes = sorted({r["qtype"] for r in train_rows})
    strategies = sorted({r["strategy"] for r in train_rows})
    for qt in qtypes:
        best, best_v = "baseline", -1.0
        for st in strategies:
            vals = question_means(train_rows, metric, {"qtype": qt, "strategy": st})
            v = sum(vals) / len(vals) if vals else -1.0
            if v > best_v:
                best, best_v = st, v
        policy[qt] = best
    return policy


def global_best(train_rows: list[dict], metric: str = "cite_rate") -> str:
    best, best_v = "baseline", -1.0
    for st in sorted({r["strategy"] for r in train_rows}):
        vals = question_means(train_rows, metric, {"strategy": st})
        v = sum(vals) / len(vals) if vals else -1.0
        if v > best_v:
            best, best_v = st, v
    return best


def apply_policy(test_rows: list[dict], policy: dict[str, str]) -> list[dict]:
    """Keep only the (query, model, seed) rows whose strategy matches the policy for that qtype."""
    return [r for r in test_rows if r["strategy"] == policy.get(r["qtype"], "baseline")]


def policy_score(rows: list[dict], metric: str) -> dict:
    vals = question_means(rows, metric)
    return bootstrap_ci(vals)


def _fmt(x, nd=4):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def _ci(d: dict, nd=4) -> str:
    if not d or d.get("mean") is None:
        return "n/a"
    return f"{d['mean']:.{nd}f} [{d['ci_low']:.{nd}f}, {d['ci_high']:.{nd}f}]"



def cost_block(rows: list[dict]) -> str:
    from collections import defaultdict
    from geo_common.envload import estimate_cost_cny

    by = defaultdict(lambda: {"p": 0, "c": 0, "h": 0, "session": 0.0, "n": 0, "fresh": 0})
    for r in rows:
        m = r["model"]
        by[m]["p"] += int(r.get("prompt_tokens") or 0)
        by[m]["c"] += int(r.get("completion_tokens") or 0)
        by[m]["h"] += int(r.get("cache_hit_tokens") or 0)
        by[m]["n"] += 1
        if not r.get("cached"):
            by[m]["fresh"] += 1
            by[m]["session"] += float(r.get("cost_cny") or 0)
    lines = ["按模型 token（缓存条目计入历史用量，本次会话费用只计新调用）："]
    for m, v in by.items():
        est, note = estimate_cost_cny(m, v["p"], v["c"], v["h"])
        est_s = f"{est:.6f}" if est is not None else "n/a"
        lines.append(
            f"- `{m}`：n={v['n']}（新调用 {v['fresh']}），prompt={v['p']}，completion={v['c']}，"
            f"按标价计全部 token 约 ¥{est_s}；本次会话 ¥{v['session']:.6f}。"
        )
        lines.append(f"  {note}")
    lines.append(f"进程内累计估算 {cumulative_spend_cny():.6f} 元。此为标价估算，不是账单原件。")
    return "\n".join(lines)


async def run_geolab() -> dict:
    ensure_data_dirs()
    settings = load_settings()
    gl = settings["geolab"]
    queries = load_queries()
    models = list(settings["models"]["geolab"])
    seeds = list(gl["seeds"])
    top_k = int(gl["top_k"])
    fact_raw = factcheck_all_variants()
    fact = {k: {"ok": v.ok, "violations": v.violations} for k, v in fact_raw.items()}
    if not all(v["ok"] for v in fact.values()):
        raise RuntimeError(f"authored variants failed factcheck: {fact}")

    train, test = train_test_split(queries, float(gl["train_ratio"]), int(gl["split_seed"]))
    split = {
        "seed": int(gl["split_seed"]),
        "ratio": float(gl["train_ratio"]),
        "train_ids": [q["id"] for q in train],
        "test_ids": [q["id"] for q in test],
    }

    client = LLMClient(
        concurrency=int(settings["api"].get("concurrency") or 6),
        spend_cap=float(settings["api"]["spend_cap_cny"]),
    )
    try:
        main_rows = await generate_all(
            client,
            queries,
            models,
            seeds,
            STRATEGY_ORDER,
            top_k,
            float(gl["temperature"]),
            int(gl["max_tokens"]),
            frozen=False,
            purpose="geolab_answer",
        )
        # frozen ablation
        fr = gl.get("frozen_retrieval_ablation") or {}
        frozen_rows: list[dict] = []
        if fr:
            frozen_rows = await generate_all(
                client,
                queries,
                list(fr.get("models") or models[:1]),
                list(fr.get("seeds") or seeds[:1]),
                STRATEGY_ORDER,
                top_k,
                float(gl["temperature"]),
                int(gl["max_tokens"]),
                frozen=True,
                purpose="geolab_frozen",
            )
        table = _agg_table(main_rows)
        # policy: pool models on train
        train_ids = set(split["train_ids"])
        test_ids = set(split["test_ids"])
        train_rows = [r for r in main_rows if r["query_id"] in train_ids]
        test_rows = [r for r in main_rows if r["query_id"] in test_ids]
        policy = policy_from_train(train_rows, "cite_rate")
        gbest = global_best(train_rows, "cite_rate")
        baseline_policy = {qt: "baseline" for qt in policy}
        global_policy = {qt: gbest for qt in policy}
        scores = {
            "测试集-基线": {
                "cite_rate": policy_score(apply_policy(test_rows, baseline_policy), "cite_rate"),
                "imp_pwc": policy_score(apply_policy(test_rows, baseline_policy), "imp_pwc"),
            },
            f"测试集-全局最优({gbest})": {
                "cite_rate": policy_score(apply_policy(test_rows, global_policy), "cite_rate"),
                "imp_pwc": policy_score(apply_policy(test_rows, global_policy), "imp_pwc"),
            },
            "测试集-按类型分配": {
                "cite_rate": policy_score(apply_policy(test_rows, policy), "cite_rate"),
                "imp_pwc": policy_score(apply_policy(test_rows, policy), "imp_pwc"),
            },
        }
        policy_report = {
            "by_qtype": policy,
            "global_best": gbest,
            "n_train": len(train_ids),
            "n_test": len(test_ids),
            "scores": scores,
        }
        cb = cost_block(main_rows + frozen_rows)
        _dump(ANSWERS / "geolab_rows.json", main_rows)
        _dump(ANSWERS / "geolab_frozen_rows.json", frozen_rows)
        _dump(GOLD / "geolab_split.json", split)
        payload = build_eval_payload(main_rows, frozen_rows, table, fact, split, policy_report)
        _dump(EVAL / "results_geolab.json", payload)
        write_results_md(
            EVAL / "results_geolab.md",
            main_rows,
            frozen_rows,
            table,
            fact,
            split,
            policy_report,
            settings,
            cb,
        )
        write_badcases(EVAL / "badcases_geolab.md", main_rows, frozen_rows)
        return {"table": table, "policy": policy_report, "n": len(main_rows), "fact": fact}
    finally:
        await client.aclose()
