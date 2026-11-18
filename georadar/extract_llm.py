"""LLM extractor for brand mentions, sentiment, reasons, and sources."""

from __future__ import annotations

import json
from typing import Any, Optional

from geo_common.llm import LLMClient, parse_json_object
from georadar.brands import Brand, extract_mentions, mention_order


EXTRACTOR_SYSTEM = """你是品牌提及抽取器。根据「用户问题」和「助手回答」，抽出回答里实际出现的品牌、推荐顺序、情感、推荐理由和引用来源。
硬性规则：
1. 只抽取回答里真正出现的品牌，不要把问题里的品牌自动算进去，除非回答也提到了。
2. 不要发明回答里没有的品牌、网址或理由。理由必须是回答中的原意，并给出一句原文 quote。
3. first_recommended 是回答中被当作首选或首先推荐的品牌；如果只是列举没有主次，就为 null。
4. sentiment 对应该品牌在这段回答里的态度：pos / neu / neg / mixed。
5. source_type 只能取 official、review_media、ugc、ecom、academic、self_knowledge、unknown。
6. 只输出 JSON，不要 markdown。格式：
{
  "brands": [
    {
      "name": "品牌名",
      "sentiment": "pos",
      "is_first_recommended": false,
      "reasons": ["短理由"],
      "quote": "原文中的一句"
    }
  ],
  "first_recommended": "品牌名或null",
  "sources": [
    {"text": "来源表述", "url": null, "source_type": "unknown"}
  ],
  "has_uncertainty": false
}
"""


def _brand_list_hint(brands: list[Brand]) -> str:
    # Short hint only; extraction must still work if a new brand appears.
    names = []
    seen = set()
    for b in brands:
        cid = b.canonical_id
        if cid in seen:
            continue
        seen.add(cid)
        names.append(b.name if not b.merge_into else b.name)
    return "、".join(names[:80])


def extractor_messages(query: str, answer: str, brands: list[Brand]) -> list[dict]:
    hint = _brand_list_hint(brands)
    user = (
        f"本品类常见品牌（仅供参考，不是封闭名单）：{hint}\n\n"
        f"【用户问题】\n{query}\n\n【助手回答】\n{answer}"
    )
    return [
        {"role": "system", "content": EXTRACTOR_SYSTEM},
        {"role": "user", "content": user},
    ]


def align_name(name: str, brands: list[Brand]) -> Optional[str]:
    if not name:
        return None
    n = name.strip()
    # exact alias or name
    for b in brands:
        if n == b.name or n in b.aliases:
            return b.canonical_id
    # case-insensitive latin
    nl = n.lower()
    for b in brands:
        if b.name.lower() == nl or any(a.lower() == nl for a in b.aliases):
            return b.canonical_id
    # substring on longer aliases
    for b in brands:
        for a in sorted(b.aliases + [b.name], key=len, reverse=True):
            if len(a) >= 2 and (a in n or n in a):
                return b.canonical_id
    return None


def normalize_extraction(
    obj: Optional[dict],
    answer: str,
    brands: list[Brand],
) -> dict[str, Any]:
    obj = obj or {}
    aligned = []
    seen = set()
    for item in obj.get("brands") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        bid = align_name(name, brands)
        quote = str(item.get("quote") or "")
        quote_ok = bool(quote) and quote in answer
        rec = {
            "name": name,
            "brand_id": bid,
            "sentiment": item.get("sentiment") if item.get("sentiment") in {"pos", "neu", "neg", "mixed"} else "neu",
            "is_first_recommended": bool(item.get("is_first_recommended")),
            "reasons": [str(r) for r in (item.get("reasons") or [])][:5],
            "quote": quote,
            "quote_grounded": quote_ok,
        }
        key = bid or name
        if key in seen:
            continue
        seen.add(key)
        aligned.append(rec)
    first = obj.get("first_recommended")
    first_id = align_name(str(first), brands) if first and first != "null" else None
    sources = []
    for s in obj.get("sources") or []:
        if not isinstance(s, dict):
            continue
        sources.append(
            {
                "text": str(s.get("text") or ""),
                "url": s.get("url") or None,
                "source_type": s.get("source_type") or "unknown",
            }
        )
    return {
        "brands": aligned,
        "first_recommended": first if first not in (None, "null", "") else None,
        "first_recommended_id": first_id,
        "sources": sources,
        "has_uncertainty": bool(obj.get("has_uncertainty")),
        "parse_ok": obj != {},
    }
