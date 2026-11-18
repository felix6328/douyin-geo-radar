"""End-to-end GeoRadar run: generate, extract, measure, insights."""

from __future__ import annotations

import asyncio
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

import yaml

from geo_common.llm import LLMClient, parse_json_object, cumulative_spend_cny
from geo_common.progress import gather_progress
from geo_common.paths import CONFIGS, DATA, EVAL, GOLD, INSIGHTS, ANSWERS, ensure_data_dirs
from georadar.brands import (
    Brand,
    brand_name_map,
    extract_mentions,
    first_brand,
    load_dictionary,
    mention_order,
)
from georadar.extract_llm import align_name, extractor_messages, normalize_extraction
from georadar.generate import messages_for
from georadar.insights import run_insight_agent
from georadar.metrics import (
    ORGANIC_EXCLUDE,
    answers_mentioning_any,
    cross_model_jaccard,
    first_position_rate,
    is_organic,
    mention_rate,
    share_of_voice,
    slice_metrics,
    source_type_distribution,
    stability_by_query_model,
    url_stats,
)
from georadar.sources import extract_sources


def load_settings() -> dict:
    return yaml.safe_load((CONFIGS / "settings.yaml").read_text(encoding="utf-8"))


def load_queries() -> list[dict]:
    raw = yaml.safe_load((CONFIGS / "queries" / "georadar_queries.yaml").read_text(encoding="utf-8"))
    return list(raw["queries"])


def _dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


async def generate_answers(
    client: LLMClient,
    queries: list[dict],
    platforms: list[dict],
    n_runs: int,
    seeds: list[int],
    temperature: float,
    max_tokens: int,
) -> list[dict]:
    tasks = []
    meta = []
    for q in queries:
        for p in platforms:
            for run in range(n_runs):
                seed = seeds[run] if run < len(seeds) else seeds[-1] + run
                meta.append((q, p, run, seed))
                tasks.append(
                    client.chat(
                        p["model"],
                        messages_for(q["text"]),
                        temperature=temperature,
                        max_tokens=max_tokens,
                        seed=seed,
                        purpose="georadar_answer",
                    )
                )
    results = await gather_progress(tasks, "georadar_answer")
    rows = []
    for (q, p, run, seed), res in zip(meta, results):
        if isinstance(res, Exception):
            err = f"{type(res).__name__}"
            content, pt, ct, cht, cost, lat, cached, error = "", 0, 0, 0, None, 0, False, err
        else:
            content = res.content
            pt, ct, cht = res.prompt_tokens, res.completion_tokens, res.cache_hit_tokens
            cost, lat, cached, error = res.cost_cny, res.latency_ms, res.cached, res.error
        rows.append(
            {
                "query_id": q["id"],
                "query_text": q["text"],
                "category": q["category"],
                "qtype": q["qtype"],
                "has_brand_in_query": q.get("has_brand_in_query", False),
                "brands_in_query": q.get("brands_in_query") or [],
                "model": p["model"],
                "family": p["family"],
                "platform_id": p["id"],
                "run": run,
                "seed": seed,
                "answer": content,
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "cache_hit_tokens": cht,
                "cost_cny": cost if not cached else 0.0,
                "latency_ms": lat,
                "cached": cached,
                "error": error,
            }
        )
    return rows


def apply_rules(rows: list[dict], dictionary: dict) -> list[dict]:
    for r in rows:
        brands: list[Brand] = dictionary.get(r["category"]) or []
        mentions = extract_mentions(r.get("answer") or "", brands, category=r["category"])
        r["rule_mentions"] = [
            {"brand_id": m.brand_id, "brand_name": m.brand_name, "alias": m.alias, "start": m.start, "end": m.end}
            for m in mentions
        ]
        r["rule_brand_ids"] = mention_order(mentions)
        fb = first_brand(mentions)
        r["rule_first_id"] = fb.brand_id if fb else None
        r["rule_first_name"] = fb.brand_name if fb else None
        srcs = extract_sources(r.get("answer") or "")
        r["rule_sources"] = [
            {
                "text": s.text,
                "url": s.url,
                "source_type": s.source_type,
                "well_formed_url": s.well_formed_url,
            }
            for s in srcs
        ]
    return rows


async def apply_llm_extract(
    client: LLMClient,
    rows: list[dict],
    dictionary: dict,
    model: str,
    temperature: float,
    max_tokens: int,
) -> list[dict]:
    tasks = []
    for r in rows:
        brands = dictionary.get(r["category"]) or []
        tasks.append(
            client.chat(
                model,
                extractor_messages(r["query_text"], r.get("answer") or "", brands),
                temperature=temperature,
                max_tokens=max_tokens,
                seed=0,
                json_mode=False,  # GLM-4.5-Air rejects response_format=json_object (code 20024)
                purpose="georadar_extract",
            )
        )
    results = await gather_progress(tasks, "georadar_extract")
    for r, res in zip(rows, results):
        brands = dictionary.get(r["category"]) or []
        if isinstance(res, Exception):
            r["llm_extract"] = normalize_extraction(None, r.get("answer") or "", brands)
            r["llm_extract"]["error"] = type(res).__name__
            r["llm_extract_tokens"] = {"prompt": 0, "completion": 0, "cost_cny": 0, "cached": False}
            continue
        obj = parse_json_object(res.content)
        r["llm_extract"] = normalize_extraction(obj, r.get("answer") or "", brands)
        r["llm_extract"]["error"] = res.error
        r["llm_extract_tokens"] = {
            "prompt": res.prompt_tokens,
            "completion": res.completion_tokens,
            "cost_cny": res.cost_cny if not res.cached else 0.0,
            "cached": res.cached,
        }
        # preferred first-recommended: LLM if grounded/aligned else rule
        r["llm_first_id"] = r["llm_extract"].get("first_recommended_id")
        r["llm_brand_ids"] = [
            b["brand_id"] for b in r["llm_extract"].get("brands") or [] if b.get("brand_id")
        ]
    return rows


def extractor_agreement(rows: list[dict]) -> dict[str, Any]:
    """Rule vs LLM brand-set agreement. Not a human gold standard."""
    n = 0
    inter = 0
    union = 0
    only_rule = 0
    only_llm = 0
    both_empty = 0
    jacs = []
    from georadar.metrics import jaccard

    for r in rows:
        if r.get("error") and not r.get("answer"):
            continue
        a = set(r.get("rule_brand_ids") or [])
        b = set(r.get("llm_brand_ids") or [])
        n += 1
        inter += len(a & b)
        union += len(a | b)
        only_rule += len(a - b)
        only_llm += len(b - a)
        if not a and not b:
            both_empty += 1
        jacs.append(jaccard(a, b))
    return {
        "n": n,
        "mean_jaccard": sum(jacs) / n if n else None,
        "micro_overlap": (inter / union) if union else None,
        "only_rule_mentions": only_rule,
        "only_llm_mentions": only_llm,
        "intersection_mentions": inter,
        "both_empty": both_empty,
        "note": "这是规则层与 LLM 抽取层的一致性，不是人工金标准确率。【未经人工审阅】",
    }


def draft_gold_subset(rows: list[dict], n: int, seed: int) -> list[dict]:
    import random

    rng = random.Random(seed)
    eligible = [r for r in rows if r.get("answer")]
    # stratified-ish: by category then organic vs branded
    buckets = defaultdict(list)
    for r in eligible:
        buckets[(r["category"], bool(r.get("has_brand_in_query")))].append(r)
    chosen = []
    # round-robin until n
    keys = list(buckets)
    rng.shuffle(keys)
    for k in keys:
        rng.shuffle(buckets[k])
    idx = {k: 0 for k in keys}
    while len(chosen) < min(n, len(eligible)):
        progress = False
        for k in keys:
            i = idx[k]
            if i < len(buckets[k]):
                chosen.append(buckets[k][i])
                idx[k] = i + 1
                progress = True
                if len(chosen) >= n:
                    break
        if not progress:
            break
    gold = []
    for r in chosen:
        gold.append(
            {
                "query_id": r["query_id"],
                "query_text": r["query_text"],
                "category": r["category"],
                "qtype": r["qtype"],
                "model": r["model"],
                "run": r["run"],
                "answer": r["answer"],
                "auto_brands_rule": r.get("rule_brand_ids") or [],
                "auto_brands_llm": r.get("llm_brand_ids") or [],
                "auto_first_rule": r.get("rule_first_id"),
                "auto_first_llm": r.get("llm_first_id"),
                "human_brands": None,
                "human_first": None,
                "reviewer": None,
                "review_notes": None,
                "status": "auto_draft_unreviewed",
            }
        )
    return gold


def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "n/a"
    return f"{x:.4f}"


def write_results_md(
    path: Path,
    rows: list[dict],
    name_map: dict[str, str],
    cat_names: dict[str, str],
    agreement: dict,
    insight: Optional[dict],
    settings: dict,
    extra: dict,
) -> None:
    organic = [r for r in rows if is_organic(r)]
    branded_q = [r for r in rows if not is_organic(r)]
    models = sorted({r["model"] for r in rows})
    cats = sorted({r["category"] for r in rows})
    ok = [r for r in rows if r.get("answer") and not (r.get("error") and not r.get("answer"))]
    failed = [r for r in rows if r.get("error") and not r.get("answer")]

    lines = []
    lines.append("# GeoRadar 评测结果")
    lines.append("")
    lines.append("评测日期：2026-11-14（Asia/Shanghai）。数字全部由 `scripts/run_georadar.py` 从本次运行的 JSON 汇总，未经手工改写。")
    lines.append("")
    lines.append("**必须一起读的局限：**")
    lines.append("")
    lines.append("- 调用的是硅基流动上的**裸模型**，没有实时搜索，**不是**豆包、元宝、通义或任何带检索的应用。跨模型差异反映的是参数知识和对齐，不能当成这些 App 的真实品牌露出。")
    lines.append("- 查询集和抽取金标由脚本起草，**【未经人工审阅】**。")
    lines.append("- 提及率、SOV 默认排除「品牌对比 / 品牌咨询」类问题，避免把问题里已经出现的品牌算成模型自发提及。")
    lines.append("")
    lines.append("## 规模")
    lines.append("")
    lines.append(f"- 查询 {len({r['query_id'] for r in rows})} 条，模型 {len(models)} 个（{', '.join(models)}），每查询采样 {settings['georadar']['n_runs']} 次。")
    lines.append(f"- 计划回答 {len(rows)} 条，成功 {len(ok)}，失败 {len(failed)}。")
    lines.append(f"- 自发提及分析集 {len(organic)} 条，问题已含品牌 {len(branded_q)} 条。")
    tok_p = sum(int(r.get("prompt_tokens") or 0) for r in rows)
    tok_c = sum(int(r.get("completion_tokens") or 0) for r in rows)
    # answer-generation costs only (cached=0 already)
    cost_ans = sum(float(r.get("cost_cny") or 0) for r in rows)
    lines.append(f"- 回答阶段 token：prompt {tok_p}，completion {tok_c}；本阶段估算费用见文末（磁盘缓存命中计 0）。")
    lines.append("")

    lines.append("## 整体可见度（自发提及分析集）")
    lines.append("")
    lines.append(f"- 至少提及一个词典品牌的回答占比：{_fmt_pct(answers_mentioning_any(organic))}")
    st = stability_by_query_model(organic)
    lines.append(
        f"- 跨采样稳定性（同题同模型，n_pairs={st['n_pairs']}）：品牌集合平均 Jaccard={_fmt_pct(st['mean_jaccard'])}，首位一致率={_fmt_pct(st['mean_first_agree'])}"
    )
    cm0 = cross_model_jaccard(organic, run=0)
    cm1 = cross_model_jaccard(organic, run=1) if settings["georadar"]["n_runs"] > 1 else None
    def _jac_fmt(d):
        if not d:
            return "n/a"
        parts = []
        for k, v in d.items():
            a, b = k.split("||")
            short = lambda m: m.split("/")[-1]
            parts.append(f"{short(a)} vs {short(b)}={_fmt_pct(v)}")
        return "；".join(parts)
    lines.append(f"- 跨模型品牌集合平均 Jaccard（run=0）：{_jac_fmt(cm0['pairwise_mean_jaccard'])}")
    if cm1:
        lines.append(f"- 跨模型品牌集合平均 Jaccard（run=1）：{_jac_fmt(cm1['pairwise_mean_jaccard'])}")
    lines.append("")
    lines.append("### 前 15 品牌（按 SOV）")
    lines.append("")
    lines.append("| 品牌 | SOV | 提及率 | 首位率 |")
    lines.append("| --- | --- | --- | --- |")
    for row in slice_metrics(organic, name_map, top_n=15):
        lines.append(
            f"| {row['brand_name']} | {_fmt_pct(row['sov'])} | {_fmt_pct(row['mention_rate'])} | {_fmt_pct(row['first_position_rate'])} |"
        )
    lines.append("")

    lines.append("## 分品类")
    lines.append("")
    for cat in cats:
        sub = [r for r in organic if r["category"] == cat]
        lines.append(f"### {cat_names.get(cat, cat)}（n={len(sub)}）")
        lines.append("")
        lines.append("| 品牌 | SOV | 提及率 | 首位率 |")
        lines.append("| --- | --- | --- | --- |")
        for row in slice_metrics(sub, name_map, top_n=8):
            lines.append(
                f"| {row['brand_name']} | {_fmt_pct(row['sov'])} | {_fmt_pct(row['mention_rate'])} | {_fmt_pct(row['first_position_rate'])} |"
            )
        lines.append("")

    lines.append("## 分模型")
    lines.append("")
    for m in models:
        sub = [r for r in organic if r["model"] == m]
        fam = next((r["family"] for r in rows if r["model"] == m), "")
        lines.append(f"### {fam} / `{m}`（n={len(sub)}）")
        lines.append("")
        lines.append(f"至少提及一品牌占比 {_fmt_pct(answers_mentioning_any(sub))}。前 8：")
        lines.append("")
        lines.append("| 品牌 | SOV | 提及率 | 首位率 |")
        lines.append("| --- | --- | --- | --- |")
        for row in slice_metrics(sub, name_map, top_n=8):
            lines.append(
                f"| {row['brand_name']} | {_fmt_pct(row['sov'])} | {_fmt_pct(row['mention_rate'])} | {_fmt_pct(row['first_position_rate'])} |"
            )
        lines.append("")

    lines.append("## 分问题类型")
    lines.append("")
    qtypes = sorted({r["qtype"] for r in organic})
    lines.append("| 问题类型 | n | 有品牌占比 | 跨采样 Jaccard |")
    lines.append("| --- | --- | --- | --- |")
    for qt in qtypes:
        sub = [r for r in organic if r["qtype"] == qt]
        stq = stability_by_query_model(sub)
        lines.append(
            f"| {qt} | {len(sub)} | {_fmt_pct(answers_mentioning_any(sub))} | {_fmt_pct(stq['mean_jaccard'])} |"
        )
    lines.append("")

    lines.append("## 引用来源")
    lines.append("")
    us = url_stats(rows)
    lines.append(
        f"- 含 URL 的回答 {us['answers_with_url']} / {us['n_answers']}（{_fmt_pct(us['url_rate'])}），"
        f"URL 总数 {us['n_urls']}，形式合法 {us['n_well_formed']}。"
    )
    dist = source_type_distribution(rows)
    if dist:
        lines.append("- 规则层来源类型分布（含非 URL 的「据…报道」等）：")
        for k, v in dist.items():
            lines.append(f"  - {k}: {_fmt_pct(v)}")
    else:
        lines.append("- 规则层几乎没有抽到来源表述。")
    if extra.get("url_probe"):
        lines.append("- 对去重后的形式合法 URL 做了一次短超时 HTTP 探测（不能单独证明「幻觉」，只记录可达性）：")
        for k, v in extra["url_probe"].items():
            lines.append(f"  - {k}: {v}")
    lines.append("")

    lines.append("## 抽取器一致性（规则 vs LLM，不是人工金标）")
    lines.append("")
    lines.append(agreement.get("note") or "")
    lines.append("")
    lines.append(f"- n={agreement['n']}，平均 Jaccard={_fmt_pct(agreement['mean_jaccard'])}，micro overlap={_fmt_pct(agreement.get('micro_overlap'))}")
    lines.append(
        f"- 仅规则命中 {agreement['only_rule_mentions']}，仅 LLM 命中 {agreement['only_llm_mentions']}，交集 {agreement['intersection_mentions']}，双方都空 {agreement['both_empty']}"
    )
    lines.append(f"- 自动起草的待审子集见 `data/gold/georadar_extractor_gold_draft.json`，状态均为 `auto_draft_unreviewed`。")
    lines.append("")

    if insight:
        lines.append("## 洞察 Agent（Skills：可见度审计）")
        lines.append("")
        lines.append("以下机会和假设由模型根据指标摘要和证据包生成，引用已做编号校验。引用失败的条目会标明 `citation_ok=false`，不得当结论用。")
        lines.append("")
        for o in insight.get("opportunities") or []:
            flag = "" if o.get("citation_ok") else "  **【引用未通过】**"
            lines.append(f"- **{o.get('id')} {o.get('title')}**{flag}：{o.get('observation')} 证据：{', '.join(o.get('evidence_ids') or [])}")
        lines.append("")
        for h in insight.get("hypotheses") or []:
            flag = "" if h.get("citation_ok") else "  **【引用未通过】**"
            lines.append(
                f"- **{h.get('id')}**{flag}：{h.get('statement')} "
                f"自变量：{h.get('independent_variable')}；证伪：{h.get('falsify_by')}；"
                f"建议策略：{h.get('suggested_geolab_strategy')}；证据：{', '.join(h.get('evidence_ids') or [])}"
            )
        if insight.get("caveats"):
            lines.append("")
            lines.append("Agent 自己列的局限：" + "；".join(str(c) for c in insight["caveats"]))
        if insight.get("invalid_citations"):
            lines.append(f"- 引用校验未通过 {len(insight['invalid_citations'])} 条，详见 insights JSON。")
        lines.append("")

    lines.append("## 费用（估算）")
    lines.append("")
    lines.append(extra.get("cost_block") or "见 docs/COST.md")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_badcases(path: Path, rows: list[dict], name_map: dict[str, str]) -> None:
    organic = [r for r in rows if is_organic(r)]
    lines = ["# GeoRadar 坏例与值得追问的样本", ""]
    lines.append("挑选原则：跨模型首位不一致、跨采样品牌集合变化、含 URL、规则与 LLM 抽取不一致、规则抽不到品牌。全部来自本次运行，未经人工润色。")
    lines.append("")

    def show(title: str, items: list[dict], n: int = 8) -> None:
        lines.append(f"## {title}")
        lines.append("")
        for r in items[:n]:
            brands = ",".join(name_map.get(b, b) for b in (r.get("rule_brand_ids") or [])) or "（无）"
            lines.append(
                f"- **{r['query_id']}** `{r['model']}` run={r['run']} ({r['category']}/{r['qtype']}) 规则品牌：{brands}"
            )
            lines.append(f"  - 问题：{r['query_text']}")
            ans = (r.get("answer") or r.get("error") or "")[:280].replace("\n", " ")
            lines.append(f"  - 回答片段：{ans}")
        lines.append("")

    # cross-model first disagreement
    by = defaultdict(list)
    for r in organic:
        if r.get("run") == 0:
            by[r["query_id"]].append(r)
    disagree = []
    for qid, items in by.items():
        firsts = {it.get("rule_first_id") for it in items}
        if len(firsts) >= 2:
            disagree.extend(items)
    show("跨模型首位不一致（run=0）", disagree, 12)

    byqm = defaultdict(list)
    for r in organic:
        byqm[(r["query_id"], r["model"])].append(r)
    unstable = []
    for items in byqm.values():
        sets = [tuple(it.get("rule_brand_ids") or []) for it in items]
        if len(set(sets)) >= 2:
            unstable.extend(sorted(items, key=lambda x: x.get("run", 0)))
    show("跨采样品牌集合变化", unstable, 12)

    urls = [r for r in rows if any(s.get("url") for s in (r.get("rule_sources") or []))]
    show("回答里出现了 URL（裸模型无搜索，值得追问是否编造）", urls, 10)

    mismatch = [
        r
        for r in organic
        if set(r.get("rule_brand_ids") or []) != set(r.get("llm_brand_ids") or [])
    ]
    show("规则层与 LLM 抽取不一致", mismatch, 10)

    empty = [r for r in organic if not r.get("rule_brand_ids") and r.get("answer")]
    show("自发提及题上规则层未抽出品牌", empty, 8)

    failed = [r for r in rows if r.get("error") and not r.get("answer")]
    if failed:
        show("生成失败", failed, 8)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def maybe_probe_urls(rows: list[dict], limit: int = 30) -> dict:
    """Optional reachability probe. Not proof of hallucination."""
    import httpx

    urls = []
    seen = set()
    for r in rows:
        for s in r.get("rule_sources") or []:
            u = s.get("url")
            if u and s.get("well_formed_url") and u not in seen:
                seen.add(u)
                urls.append(u)
    urls = urls[:limit]
    counts = Counter()
    if not urls:
        return {"n_unique_probed": 0}
    async with httpx.AsyncClient(follow_redirects=True, timeout=5.0) as client:
        for u in urls:
            try:
                resp = await client.head(u)
                bucket = f"http_{resp.status_code}"
                if resp.status_code == 405:
                    resp = await client.get(u)
                    bucket = f"http_{resp.status_code}"
                counts[bucket] += 1
            except httpx.TimeoutException:
                counts["timeout"] += 1
            except httpx.HTTPError:
                counts["http_error"] += 1
    return {"n_unique_probed": len(urls), **dict(counts)}


def cost_summary_from_rows(answer_rows: list[dict], extra_note: str = "") -> str:
    from geo_common.envload import estimate_cost_cny, SILICONFLOW_PRICES

    # Use token totals even for cached rows to report "if billed" vs "this session"
    by_model = defaultdict(lambda: {"p": 0, "c": 0, "h": 0, "session_cny": 0.0, "n": 0, "n_fresh": 0})
    for r in answer_rows:
        m = r["model"]
        by_model[m]["p"] += int(r.get("prompt_tokens") or 0)
        by_model[m]["c"] += int(r.get("completion_tokens") or 0)
        by_model[m]["h"] += int(r.get("cache_hit_tokens") or 0)
        by_model[m]["n"] += 1
        if not r.get("cached"):
            by_model[m]["n_fresh"] += 1
            by_model[m]["session_cny"] += float(r.get("cost_cny") or 0)
    lines = ["按模型 token（含缓存条目的历史用量；本次会话费用只计未缓存调用）："]
    total_session = 0.0
    for m, v in by_model.items():
        est, note = estimate_cost_cny(m, v["p"], v["c"], v["h"])
        lines.append(
            f"- `{m}`：n={v['n']}（本次新调用 {v['n_fresh']}），prompt={v['p']}，completion={v['c']}，"
            f"若按标价计全部 token 约 ¥{est if est is not None else 'n/a'}；本次会话估算 ¥{v['session_cny']:.6f}。"
        )
        if v["session_cny"]:
            total_session += v["session_cny"]
        if note:
            lines.append(f"  {note}")
    lines.append(f"累计估算（本进程已记录，见 docs/COST.md）进程内累计 {cumulative_spend_cny():.6f} 元。{extra_note}")
    return "\n".join(lines)


async def run_georadar(skip_llm_extract: bool = False, skip_insight: bool = False) -> dict:
    ensure_data_dirs()
    settings = load_settings()
    queries = load_queries()
    dictionary = load_dictionary()
    name_map = brand_name_map(dictionary)
    cat_names = {
        "skincare": "护肤",
        "headphones": "耳机",
        "nev": "新能源车",
        "coffee": "咖啡",
        "travel": "旅行",
    }
    platforms = settings["models"]["platforms"]
    gr = settings["georadar"]
    client = LLMClient(concurrency=int(settings["api"].get("concurrency") or 6), spend_cap=float(settings["api"]["spend_cap_cny"]))
    try:
        rows = await generate_answers(
            client,
            queries,
            platforms,
            n_runs=int(gr["n_runs"]),
            seeds=list(gr["run_seeds"]),
            temperature=float(gr["temperature"]),
            max_tokens=int(gr["max_tokens"]),
        )
        apply_rules(rows, dictionary)
        if not skip_llm_extract and client.enabled:
            await apply_llm_extract(
                client,
                rows,
                dictionary,
                model=settings["models"]["extractor"],
                temperature=float(gr["extractor_temperature"]),
                max_tokens=int(gr["extractor_max_tokens"]),
            )
        else:
            for r in rows:
                r["llm_extract"] = {}
                r["llm_brand_ids"] = []
                r["llm_first_id"] = None
        agreement = extractor_agreement(rows)
        gold = draft_gold_subset(rows, int(gr["gold_subset_size"]), int(gr["gold_seed"]))
        _dump(GOLD / "georadar_extractor_gold_draft.json", {
            "status": "auto_draft_unreviewed",
            "note": "自动起草，未经人工审阅。human_* 字段为空，审完之前不得把抽取器准确率写入简历。",
            "items": gold,
        })
        insight = None
        if not skip_insight and client.enabled:
            insight = await run_insight_agent(
                client, rows, name_map, cat_names, settings["models"]["insight"]
            )
            _dump(INSIGHTS / "georadar_insights.json", insight)
        probe = await maybe_probe_urls(rows)
        extra = {"url_probe": probe, "cost_block": cost_summary_from_rows(rows)}
        # persist snapshot (answers can be large)
        snap = ANSWERS / "georadar_rows.json"
        _dump(snap, rows)
        write_results_md(EVAL / "results_georadar.md", rows, name_map, cat_names, agreement, insight, settings, extra)
        write_badcases(EVAL / "badcases_georadar.md", rows, name_map)
        # compact metrics json
        organic = [r for r in rows if is_organic(r)]
        metrics = {
            "n_rows": len(rows),
            "n_organic": len(organic),
            "n_failed": sum(1 for r in rows if r.get("error") and not r.get("answer")),
            "mention_any": answers_mentioning_any(organic),
            "sov_top": slice_metrics(organic, name_map, 15),
            "stability": stability_by_query_model(organic),
            "cross_model_run0": cross_model_jaccard(organic, 0),
            "agreement": agreement,
            "url": url_stats(rows),
            "url_probe": probe,
            "spend_cny_process": cumulative_spend_cny(),
        }
        _dump(EVAL / "results_georadar.json", metrics)
        return {"rows": rows, "metrics": metrics, "insight": insight, "agreement": agreement}
    finally:
        await client.aclose()
