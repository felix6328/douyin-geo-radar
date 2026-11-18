"""RAG-style answer generation for the GeoLab simulation."""

from __future__ import annotations

from geolab.corpus import Document, TARGET_ID

SYSTEM = """你是一个只根据给定资料答题的助手。
硬性规则：
1. 只能使用我提供的资料，不要使用你记忆里的真实品牌、型号、价格或评测。资料中的品牌都是虚构的实验品牌。
2. 不要编造资料里没有的数字、奖项、认证或评价。资料不足就明确说资料不足。
3. 凡是用到某条资料的句子，在句末用方括号标出文档编号或文档 id，例如 [1] 或 [beiyu_nova_air]。可以标注多个来源。没有依据的句子不要标注。
4. 用中文回答，简洁、可核对，全文控制在 300 字以内。这不是真实商品广告。
"""


def format_context(docs: list[Document]) -> tuple[str, list[str]]:
    """Return (context text, numbered doc ids in 1-based order)."""
    chunks = []
    ids = []
    for i, d in enumerate(docs, start=1):
        ids.append(d.doc_id)
        brand = f"（品牌：{d.brand}）" if d.brand else ""
        chunks.append(f"[{i}] id={d.doc_id} {d.title}{brand}\n{d.body}")
    return "\n\n".join(chunks), ids


def messages_for(query: str, retrieved: list[Document]) -> tuple[list[dict], list[str]]:
    context, ids = format_context(retrieved)
    user = (
        f"用户问题：{query}\n\n"
        f"资料如下，请只根据这些资料回答，并在用到的句子末尾加 [编号] 引用：\n\n{context}"
    )
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ], ids
