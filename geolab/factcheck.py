"""Fact-check generated or authored content against the product spec.

Reject fabricated awards, competitor-bashing, invented numbers, and URLs
outside the allowed first-party source list. Keyword stuffing may be ugly
and still pass if it only uses allowed facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from geolab.corpus import load_specs

# Awards / ranking claims that must never appear on the target page.
FORBIDDEN_PATTERNS = [
    r"红点奖",
    r"iF\s*设计",
    r"CES",
    r"销量第一",
    r"全球第一",
    r"行业第一",
    r"世界第一",
    r"完胜",
    r"吊打",
    r"索尼授权",
    r"Bose\s*授权",
    r"治疗听力",
    r"治愈听",
    r"医疗器械",
    r"什么值得买满分",
    r"权威媒体评分",
    r"第三方认证证书",  # we allow saying it is NOT a third-party cert
]

# Numbers with units extracted from text.
NUM_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>dB|分贝|mm|毫米|小时|h|分钟|min|克|g|元|块|毫秒|ms|年|台|个月)?"
    r"|(?P<ip>IPX\s?(?P<ipn>\d))"
    r"|(?P<bt>蓝牙\s?(?P<btn>\d+(?:\.\d+)?))",
    re.I,
)


@dataclass
class FactCheckResult:
    ok: bool
    violations: list[str] = field(default_factory=list)

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise AssertionError("factcheck failed: " + "; ".join(self.violations))


def _allowed_number_values(specs: dict) -> set[float]:
    allowed = set()
    for item in specs["target"].get("allowed_numbers") or []:
        allowed.add(float(item["value"]))
    # also all explicit numeric fields
    t = specs["target"]
    for k, v in t.items():
        if isinstance(v, (int, float)):
            allowed.add(float(v))
    return allowed


def factcheck_target_text(text: str, specs: Optional[dict] = None) -> FactCheckResult:
    specs = specs or load_specs()
    violations: list[str] = []
    t = specs["target"]

    # Forbidden claims. Special-case: 「不是第三方认证证书」 is allowed.
    for pat in FORBIDDEN_PATTERNS:
        for m in re.finditer(pat, text, flags=re.I):
            ctx = text[max(0, m.start() - 12) : m.end() + 12]
            if "不是第三方认证" in ctx or "不是第三方" in ctx:
                continue
            if pat == r"CES" and re.search(r"不是.*CES|CES.*不是", ctx):
                continue
            violations.append(f"forbidden_claim:{m.group(0)}")

    # Competitor brand names should not be disparaged with fake numbers on
    # the target page. Mentioning real competitor facts isn't in the allowed
    # source list, so any competitor brand is a violation on the target page.
    for c in specs.get("competitors") or []:
        if c["brand"] in text:
            violations.append(f"competitor_brand_on_target:{c['brand']}")

    allowed = _allowed_number_values(specs)
    # Walk numbers; flag those not in allowed set, with some exceptions
    # (list enumerations like "2–4" shouldn't appear; dates we allow 15, etc.)
    # Ignore isolated 1 (一年 vs 两年 already allowed 2; "一台" etc.)
    for m in re.finditer(r"\d+(?:\.\d+)?", text):
        val = float(m.group(0))
        # years like 2026 already allowed; skip very common structural nums
        if val in allowed:
            continue
        # table punctuation / question numbers: 1-9 appearing as list index
        window = text[max(0, m.start() - 2) : m.end() + 2]
        if re.match(r"(?m)^[\-\*\d]+\s", text[max(0, m.start() - 4) : m.end() + 1]):
            if val <= 20:
                continue
        # skip if it's part of a date already allowed (day 15 etc. in allowed)
        violations.append(f"undeclared_number:{m.group(0)}@{m.start()}")

    # URLs must not appear unless they are clearly fictional-denied; we
    # simply disallow any http(s) on authored target pages.
    if re.search(r"https?://", text):
        violations.append("url_not_in_allowed_sources")

    return FactCheckResult(ok=len(violations) == 0, violations=violations)


def factcheck_all_variants() -> dict[str, FactCheckResult]:
    from geolab.corpus import STRATEGIES

    specs = load_specs()
    out = {}
    for name, doc in STRATEGIES.items():
        out[name] = factcheck_target_text(doc.body, specs)
    return out
