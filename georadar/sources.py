"""Rule-based citation / URL / source-type extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://[^\s\]）)＞>\"']+", re.I)
# 「据X报道」「根据X」「来源：X」「参考X」
CITE_RE = re.compile(
    r"(?:据|根据|依据|参考|引自|来源[:：是为]|参见|见)\s*"
    r"[《\"“]?([^，。；\n]{2,30})[》\"”]?"
    r"(?:报道|评测|报告|官网|数据|指出|显示|介绍|发布)?"
)

SOURCE_TYPE_RULES: list[tuple[str, list[str]]] = [
    ("official", ["官网", "官方", "品牌宣称", "官方参数", "规格书", "新闻稿", "厂商"]),
    ("review_media", ["评测", "媒体", "杂志", "什么值得买", "中关村在线", "ZOL", "爱范儿", "极客公园",
                      "实验室", "Consumer Reports", "Wirecutter", "汽车之家", "懂车帝", "车质网"]),
    ("ugc", ["小红书", "知乎", "口碑", "用户评价", "用户反馈", "开箱", "种草", "点评", "论坛", "Reddit"]),
    ("ecom", ["京东", "天猫", "淘宝", "旗舰店", "电商", "店铺"]),
    ("academic", ["论文", "期刊", "国家标准", "GB/T", "ISO", "FDA", "研究显示"]),
    ("self_knowledge", ["训练数据", "已有知识", "据我所知", "就我所知", "根据我的知识"]),
]


@dataclass
class SourceHit:
    text: str
    url: Optional[str] = None
    source_type: str = "unknown"
    start: int = 0
    well_formed_url: bool = False


def _classify(text: str) -> str:
    low = text.lower()
    for stype, kws in SOURCE_TYPE_RULES:
        for k in kws:
            if k.lower() in low:
                return stype
    return "unknown"


def _clean_url(u: str) -> str:
    return u.rstrip("。，、；；.,)]}》”'")


def extract_sources(text: str) -> list[SourceHit]:
    if not text:
        return []
    hits: list[SourceHit] = []
    seen = set()
    for m in URL_RE.finditer(text):
        url = _clean_url(m.group(0))
        key = ("url", url)
        if key in seen:
            continue
        seen.add(key)
        ok = False
        try:
            p = urlparse(url)
            ok = p.scheme in ("http", "https") and bool(p.netloc) and "." in p.netloc
        except ValueError:
            ok = False
        hits.append(
            SourceHit(
                text=url,
                url=url,
                source_type=_classify(url + " " + text[max(0, m.start() - 20) : m.end() + 10]),
                start=m.start(),
                well_formed_url=ok,
            )
        )
    for m in CITE_RE.finditer(text):
        phrase = m.group(0).strip()
        key = ("cite", phrase)
        if key in seen:
            continue
        seen.add(key)
        hits.append(
            SourceHit(
                text=phrase,
                url=None,
                source_type=_classify(phrase),
                start=m.start(),
                well_formed_url=False,
            )
        )
    hits.sort(key=lambda h: h.start)
    return hits
