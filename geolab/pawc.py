"""Impression metrics from Aggarwal et al., KDD 2024 (GEO paper).

Word Count (Eq. 2):
    Imp_wc(c_i, r) = sum_{s in S_{c_i}} |s|  /  sum_{s in S_r} |s|

Position-Adjusted Word Count (Eq. 3):
    Imp_pwc(c_i, r) = sum_{s in S_{c_i}} |s| * exp(-pos(s) / |S|)  /  sum_{s in S_r} |s|

pos(s) is the 1-based sentence index. When a sentence cites multiple sources,
its word count is shared equally (paper §2.2.1).

Chinese |s| is the number of jieba tokens after dropping punctuation.
Citation of a document: explicit markers like [beiyu_nova_air], [1] mapped
to a doc, or 【北屿官网】-style aliases. Brand-name-only mentions are recorded
separately and do NOT count as citations for PAWC (stricter than 'any mention').
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

import jieba

from geolab.corpus import Document, TARGET_ID

SENT_SPLIT = re.compile(r"(?<=[。！？!?\n])")
CITE_RE = re.compile(r"\[([^\[\]]+)\]|【([^【】]+)】")
PUNCT = set(" \t\r\n，。！？、；：,.!?;:（）()【】[]《》\"'“”·—…-")


def _is_cite_only(s: str) -> bool:
    rest = CITE_RE.sub("", s)
    rest = re.sub(r"[\s。．.、，,;；:：]+", "", rest)
    return len(rest) == 0 and bool(CITE_RE.search(s))


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in SENT_SPLIT.split(text or "") if p and p.strip()]
    if not parts:
        return [text.strip()] if text and text.strip() else []
    merged: list[str] = []
    for p in parts:
        if merged and _is_cite_only(p):
            merged[-1] = merged[-1] + p
        else:
            merged.append(p)
    return merged


def word_len(sentence: str) -> int:
    toks = [t for t in jieba.cut(sentence) if t.strip() and not all(ch in PUNCT for ch in t)]
    return max(0, len(toks))


def parse_citations(sentence: str, id_aliases: dict[str, str]) -> list[str]:
    """Return canonical doc ids cited in this sentence."""
    found = []
    for m in CITE_RE.finditer(sentence):
        raw = (m.group(1) or m.group(2) or "").strip()
        key = raw.lower().strip()
        if key in id_aliases:
            cid = id_aliases[key]
            if cid not in found:
                found.append(cid)
            continue
        # numeric [1] handled by caller via numbered context
        if raw in id_aliases:
            cid = id_aliases[raw]
            if cid not in found:
                found.append(cid)
    return found


def build_aliases(docs: list[Document], numbered: Optional[list[str]] = None) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for d in docs:
        aliases[d.doc_id.lower()] = d.doc_id
        aliases[d.doc_id] = d.doc_id
        if d.brand:
            aliases[d.brand] = d.doc_id
            aliases[d.brand.lower()] = d.doc_id
            aliases[f"{d.brand}官网"] = d.doc_id
            aliases[f"{d.brand}产品页"] = d.doc_id
        # title
        aliases[d.title] = d.doc_id
    if numbered:
        for i, did in enumerate(numbered, start=1):
            aliases[str(i)] = did
            aliases[f"d{i}"] = did
            aliases[f"文档{i}"] = did
    return aliases


@dataclass
class Impression:
    doc_id: str
    imp_wc: float
    imp_pwc: float
    n_cited_sentences: int
    first_cite_pos: Optional[int]
    mentioned_brand: bool


def impressions(
    answer: str,
    docs: list[Document],
    numbered: Optional[list[str]] = None,
    target_brand: str = "北屿",
    target_id: str = TARGET_ID,
) -> dict[str, Impression]:
    sents = split_sentences(answer)
    aliases = build_aliases(docs, numbered)
    n = len(sents)
    denom = sum(word_len(s) for s in sents) or 1
    # accumulate raw weights
    wc: dict[str, float] = {d.doc_id: 0.0 for d in docs}
    pwc: dict[str, float] = {d.doc_id: 0.0 for d in docs}
    ncit: dict[str, int] = {d.doc_id: 0 for d in docs}
    first: dict[str, Optional[int]] = {d.doc_id: None for d in docs}

    for i, s in enumerate(sents, start=1):
        cits = parse_citations(s, aliases)
        # unique
        cits = list(dict.fromkeys(cits))
        if not cits:
            continue
        w = word_len(s)
        share = w / len(cits)
        pos_w = math.exp(-i / max(n, 1))
        for cid in cits:
            if cid not in wc:
                wc[cid] = 0.0
                pwc[cid] = 0.0
                ncit[cid] = 0
                first[cid] = None
            wc[cid] += share
            pwc[cid] += share * pos_w
            ncit[cid] += 1
            if first[cid] is None:
                first[cid] = i

    mentioned = target_brand in (answer or "")
    out: dict[str, Impression] = {}
    for did in wc:
        out[did] = Impression(
            doc_id=did,
            imp_wc=wc[did] / denom,
            imp_pwc=pwc[did] / denom,
            n_cited_sentences=ncit[did],
            first_cite_pos=first[did],
            mentioned_brand=(mentioned if did == target_id else (False)),
        )
    # ensure target key
    if target_id not in out:
        out[target_id] = Impression(target_id, 0.0, 0.0, 0, None, mentioned)
    else:
        out[target_id].mentioned_brand = mentioned
    return out
