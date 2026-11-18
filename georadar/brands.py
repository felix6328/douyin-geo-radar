"""Brand dictionary loading and rule-based mention extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import yaml

from geo_common.paths import CONFIGS


@dataclass
class Brand:
    id: str
    name: str
    aliases: list[str]
    category: str
    merge_into: Optional[str] = None
    exclusion_substrings: list[str] = field(default_factory=list)
    require_any_nearby: list[str] = field(default_factory=list)
    require_any: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def canonical_id(self) -> str:
        return self.merge_into or self.id

    @property
    def display_name(self) -> str:
        return self.name


@dataclass
class Mention:
    brand_id: str
    brand_name: str
    alias: str
    start: int
    end: int
    category: str


def load_dictionary(path: Optional[Path] = None) -> dict[str, list[Brand]]:
    path = path or (CONFIGS / "brands" / "dictionary.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: dict[str, list[Brand]] = {}
    for cat, block in (raw.get("categories") or {}).items():
        brands = []
        for b in block.get("brands") or []:
            aliases = [a for a in (b.get("aliases") or []) if a]
            # longest first at match time; keep original here
            brands.append(
                Brand(
                    id=b["id"],
                    name=b["name"],
                    aliases=aliases,
                    category=cat,
                    merge_into=b.get("merge_into"),
                    exclusion_substrings=list(b.get("exclusion_substrings") or []),
                    require_any_nearby=list(b.get("require_any_nearby") or []),
                    require_any=list(b.get("require_any") or []),
                    note=b.get("note") or "",
                )
            )
        out[cat] = brands
    return out


def _canonical_names(brands: list[Brand]) -> dict[str, str]:
    """canonical_id -> display name, preferring the non-merge entry."""
    names: dict[str, str] = {}
    for b in brands:
        cid = b.canonical_id
        if b.merge_into:
            names.setdefault(cid, b.name)
        else:
            names[cid] = b.name
    return names


def brand_name_map(dictionary: dict[str, list[Brand]]) -> dict[str, str]:
    names: dict[str, str] = {}
    for brands in dictionary.values():
        names.update(_canonical_names(brands))
    return names


def _nearby_window(text: str, start: int, end: int, radius: int = 20) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)]


def _excluded(text: str, start: int, end: int, exclusions: list[str]) -> bool:
    for ex in exclusions:
        # If the exclusion contains the matched span as prefix or the match
        # sits inside the exclusion starting at or before `start`.
        # Check a small window ending at start+len(ex).
        lo = max(0, start - max(0, len(ex) - (end - start)))
        hi = min(len(text), start + len(ex) + 2)
        if ex and ex in text[lo:hi]:
            # only exclude if this match overlaps that occurrence
            k = text.find(ex, lo, hi)
            while k != -1 and k < hi:
                if k <= start < k + len(ex) or k < end <= k + len(ex) or (start <= k and end >= k + len(ex)):
                    return True
                k = text.find(ex, k + 1, hi)
    return False


def extract_mentions(
    text: str,
    brands: Iterable[Brand],
    *,
    category: Optional[str] = None,
) -> list[Mention]:
    """Longest-alias-first, overlap-resolved mention finder.

    Ambiguous short aliases must pass require_any_nearby (in a ±20 char
    window) or require_any (anywhere in the whole text).
    """
    if not text:
        return []
    candidates: list[tuple[int, int, Brand, str]] = []  # start, end, brand, alias
    for b in brands:
        if category and b.category != category:
            continue
        for alias in b.aliases:
            if not alias:
                continue
            start = 0
            while True:
                i = text.find(alias, start)
                if i < 0:
                    break
                j = i + len(alias)
                start = i + 1
                if _excluded(text, i, j, b.exclusion_substrings):
                    continue
                if b.require_any:
                    if not any(tok and tok in text for tok in b.require_any):
                        continue
                if b.require_any_nearby:
                    win = _nearby_window(text, i, j, radius=24)
                    # also accept if the token appears in the same sentence
                    if not any(tok and tok in win for tok in b.require_any_nearby):
                        # sentence-level fallback
                        sent = _sentence_around(text, i)
                        if not any(tok and tok in sent for tok in b.require_any_nearby):
                            continue
                candidates.append((i, j, b, alias))

    # Resolve overlaps: prefer longer match, then earlier start.
    candidates.sort(key=lambda x: (-(x[1] - x[0]), x[0]))
    taken = [False] * len(text)
    mentions: list[Mention] = []
    names = _canonical_names(list(brands))
    for i, j, b, alias in candidates:
        if any(taken[k] for k in range(i, min(j, len(taken)))):
            continue
        for k in range(i, j):
            taken[k] = True
        cid = b.canonical_id
        mentions.append(
            Mention(
                brand_id=cid,
                brand_name=names.get(cid, b.name),
                alias=alias,
                start=i,
                end=j,
                category=b.category,
            )
        )
    mentions.sort(key=lambda m: (m.start, -m.end))
    return mentions


def _sentence_around(text: str, pos: int) -> str:
    seps = "。！？\n；;!?"
    a, b = pos, pos
    while a > 0 and text[a - 1] not in seps:
        a -= 1
    while b < len(text) and text[b] not in seps:
        b += 1
    return text[a:b]


def first_brand(mentions: list[Mention]) -> Optional[Mention]:
    return mentions[0] if mentions else None


def mention_order(mentions: list[Mention]) -> list[str]:
    seen = []
    for m in mentions:
        if m.brand_id not in seen:
            seen.append(m.brand_id)
    return seen
