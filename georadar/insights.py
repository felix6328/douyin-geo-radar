"""Skills-style insight agent: evidence-backed opportunities and hypotheses."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from geo_common.llm import LLMClient, parse_json_object
from georadar.metrics import (
    ORGANIC_EXCLUDE,
    is_organic,
    mention_rate,
    share_of_voice,
    stability_by_query_model,
    cross_model_jaccard,
)

INSIGHT_SYSTEM = """你是一名增长投放方向的 AI 产品经理，正在做 GEO（生成式引擎优化）可见度审计。
你会收到已经算好的指标，以及若干带编号的证据片段。请输出可复核的机会和待验证假设。

硬性规则：
1. 每条机会和假设必须引用至少 2 个 evidence_id，且只能使用材料里出现的编号。
2. 不得把「模型更常提到某品牌」说成「该品牌市场份额更高」或「在豆包/抖音上效果更好」。这些是无搜索裸模型的参数知识，不是真实流量。
3. 不得编造材料里没有的数字、品牌或引用。
4. 假设必须写清：自变量、预期变化、可以用什么实验证伪。
5. 不要建议伪造评测、编造奖项或把关键词堆砌当正式策略。
6. 只输出 JSON：
{
  "opportunities": [
    {"id": "O1", "title": "短标题", "observation": "观测", "evidence_ids": ["E1","E2"], "why_it_matters": "为何可能值得干预"}
  ],
  "hypotheses": [
    {"id": "H1", "statement": "假设", "independent_variable": "改什么", "expected_effect": "看什么指标", "falsify_by": "怎样算被证伪", "suggested_geolab_strategy": "statistics|cite_sources|quotation|structured_faq|freshness|none", "evidence_ids": ["E1","E2"]}
  ],
  "caveats": ["局限"]
}
"""


def _name(bid: str, name_map: dict[str, str]) -> str:
    return name_map.get(bid, bid)


def build_evidence_pack(
    rows: list[dict],
    name_map: dict[str, str],
    limit: int = 36,
) -> tuple[list[dict], str]:
    """Deterministically mine contrastive evidence for the insight agent."""
    organic = [r for r in rows if is_organic(r)]
    evidence: list[dict] = []

    def add(kind: str, row: dict, note: str, quote: str) -> None:
        eid = f"E{len(evidence)+1}"
        evidence.append(
            {
                "id": eid,
                "kind": kind,
                "query_id": row.get("query_id"),
                "query": row.get("query_text"),
                "qtype": row.get("qtype"),
                "category": row.get("category"),
                "model": row.get("model"),
                "run": row.get("run"),
                "note": note,
                "quote": (quote or "")[:240],
                "brands": row.get("rule_brand_ids") or [],
                "first": row.get("rule_first_id"),
            }
        )

    # 1. Same query, different models, different first brand
    by_qr: dict[tuple, list] = defaultdict(list)
    for r in organic:
        by_qr[(r["query_id"], r.get("run", 0))].append(r)
    contrasts = []
    for (qid, run), items in by_qr.items():
        firsts = {it["model"]: it.get("rule_first_id") for it in items}
        vals = set(firsts.values())
        if len(vals) >= 2 and any(v for v in vals):
            contrasts.append(items)
    contrasts.sort(key=lambda items: items[0]["query_id"])
    for items in contrasts[:8]:
        for it in items:
            first = it.get("rule_first_id")
            add(
                "cross_model_first",
                it,
                f"首位={_name(first, name_map) if first else '无'}",
                (it.get("answer") or "")[:240],
            )
        if len(evidence) >= limit // 2:
            break

    # 2. Unstable across runs
    by_qm: dict[tuple, list] = defaultdict(list)
    for r in organic:
        by_qm[(r["query_id"], r["model"])].append(r)
    unstable = []
    for k, items in by_qm.items():
        if len(items) < 2:
            continue
        sets = [set(it.get("rule_brand_ids") or []) for it in items]
        if sets[0] != sets[-1]:
            unstable.append(items)
    unstable.sort(key=lambda items: items[0]["query_id"])
    for items in unstable[:6]:
        for it in sorted(items, key=lambda x: x.get("run", 0)):
            add(
                "cross_run_unstable",
                it,
                f"run={it.get('run')} 品牌={','.join(_name(b, name_map) for b in (it.get('rule_brand_ids') or []))}",
                (it.get("answer") or "")[:240],
            )
        if len(evidence) >= limit * 3 // 4:
            break

    # 3. Answers with URLs (possible citations / hallucinations)
    url_rows = [r for r in rows if any(s.get("url") for s in (r.get("rule_sources") or []))]
    for r in url_rows[:6]:
        urls = [s.get("url") for s in r.get("rule_sources") or [] if s.get("url")]
        add("has_url", r, "回答含 URL: " + ", ".join(urls)[:200], (r.get("answer") or "")[:240])

    # 4. High-uncertainty or no-brand organic answers
    empty = [r for r in organic if not r.get("rule_brand_ids")]
    for r in empty[:4]:
        add("no_brand", r, "该条回答规则层未抽出品牌", (r.get("answer") or "")[:240])

    evidence = evidence[:limit]
    brief_lines = []
    for e in evidence:
        brief_lines.append(
            f"{e['id']} [{e['kind']}] {e['query_id']} {e['category']}/{e['qtype']} "
            f"model={e['model']} run={e['run']} {e['note']}\n"
            f"  问题：{e['query']}\n"
            f"  片段：{e['quote']}"
        )
    return evidence, "\n\n".join(brief_lines)


def metrics_brief(
    rows: list[dict],
    name_map: dict[str, str],
    category_names: dict[str, str],
) -> str:
    organic = [r for r in rows if is_organic(r)]
    lines = [
        f"总回答 {len(rows)} 条，其中自发提及分析集（排除问题已含品牌）{len(organic)} 条。",
        "整体 SOV（前 10）：",
    ]
    sov = share_of_voice(organic)
    for bid, v in sorted(sov.items(), key=lambda kv: -kv[1])[:10]:
        lines.append(
            f"  {_name(bid, name_map)}: SOV={v:.3f}, 提及率={mention_rate(organic, bid):.3f}"
        )
    # by category
    cats = sorted({r["category"] for r in organic})
    for cat in cats:
        sub = [r for r in organic if r["category"] == cat]
        sov_c = share_of_voice(sub)
        top = sorted(sov_c.items(), key=lambda kv: -kv[1])[:5]
        top_s = ", ".join(f"{_name(b, name_map)} {v:.2f}" for b, v in top)
        lines.append(f"品类 {category_names.get(cat, cat)} (n={len(sub)}) 前5 SOV: {top_s}")
    # by model
    models = sorted({r["model"] for r in organic})
    for m in models:
        sub = [r for r in organic if r["model"] == m]
        sov_m = share_of_voice(sub)
        top = sorted(sov_m.items(), key=lambda kv: -kv[1])[:5]
        top_s = ", ".join(f"{_name(b, name_map)} {v:.2f}" for b, v in top)
        lines.append(f"模型 {m} 前5 SOV: {top_s}")
    st = stability_by_query_model(organic)
    lines.append(f"跨采样稳定性（同题同模型）: mean Jaccard={st['mean_jaccard']}, 首位一致率={st['mean_first_agree']}, n_pairs={st['n_pairs']}")
    cm = cross_model_jaccard(organic, run=0)
    lines.append(f"跨模型 Jaccard（run=0）: {cm['pairwise_mean_jaccard']}")
    return "\n".join(lines)


def verify_citations(obj: dict, evidence_ids: set[str]) -> dict:
    """Drop or flag claims that cite unknown evidence ids."""
    if not obj:
        return {"opportunities": [], "hypotheses": [], "caveats": ["洞察解析失败"], "invalid_citations": []}
    invalid = []

    def filt(items, kind):
        kept = []
        for it in items or []:
            ids = [str(x) for x in (it.get("evidence_ids") or [])]
            bad = [i for i in ids if i not in evidence_ids]
            if bad or len(ids) < 2:
                invalid.append({"kind": kind, "id": it.get("id"), "bad": bad, "ids": ids})
                it = dict(it)
                it["citation_ok"] = False
                it["citation_issue"] = "unknown_id" if bad else "fewer_than_2"
            else:
                it = dict(it)
                it["citation_ok"] = True
            kept.append(it)
        return kept

    return {
        "opportunities": filt(obj.get("opportunities"), "opportunity"),
        "hypotheses": filt(obj.get("hypotheses"), "hypothesis"),
        "caveats": list(obj.get("caveats") or []),
        "invalid_citations": invalid,
    }


async def run_insight_agent(
    client: LLMClient,
    rows: list[dict],
    name_map: dict[str, str],
    category_names: dict[str, str],
    model: str,
) -> dict[str, Any]:
    evidence, ev_text = build_evidence_pack(rows, name_map)
    brief = metrics_brief(rows, name_map, category_names)
    user = (
        "【指标摘要】\n" + brief + "\n\n【证据包】\n" + ev_text
        + "\n\n请根据 Skills「visibility_audit」「opportunity_mining」产出机会和假设。"
    )
    res = await client.chat(
        model,
        [
            {"role": "system", "content": INSIGHT_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=1800,
        seed=42,
        json_mode=True,
        purpose="georadar_insight",
    )
    obj = parse_json_object(res.content)
    verified = verify_citations(obj, {e["id"] for e in evidence})
    verified["evidence"] = evidence
    verified["metrics_brief"] = brief
    verified["raw_content"] = res.content
    verified["llm_error"] = res.error
    verified["cost_cny"] = res.cost_cny
    verified["prompt_tokens"] = res.prompt_tokens
    verified["completion_tokens"] = res.completion_tokens
    verified["cached"] = res.cached
    return verified
