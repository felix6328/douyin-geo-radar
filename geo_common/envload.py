"""Load ONLY SILICONFLOW_API_KEY from a local env file.

``.env.local`` must contain that single variable in this repo (we copy just
that line). The source file on the shared machine may also contain unrelated
secrets; this module parses a single named line and never loads, prints,
logs, or returns those other values. Callers must not log the returned key.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"

# Published list prices, retrieved 2026-11-14 (Asia/Shanghai) from
# https://www.siliconflow.cn/pricing — CNY per 1,000,000 tokens.
# This is not a billing statement. Prices change; every cost figure is an
# estimate labeled with source and retrieval date.
SILICONFLOW_PRICES = {
    "deepseek-ai/DeepSeek-V3.2": {
        "input_cny_per_m": 4.00,
        "output_cny_per_m": 6.00,
        "cache_hit_cny_per_m": 0.40,
        "source": "https://www.siliconflow.cn/pricing",
        "retrieved": "2026-11-14",
        "note": "官网价格页：输入 ¥4/M、输出 ¥6/M、缓存命中 ¥0.40/M。",
    },
    "zai-org/GLM-5.3-Flash": {
        "input_cny_per_m": 0.80,
        "output_cny_per_m": 2.80,
        "cache_hit_cny_per_m": 0.23,
        "source": "https://www.siliconflow.cn/pricing",
        "retrieved": "2026-11-14",
        "note": "官网价格页：输入 ¥0.80/M、输出 ¥2.80/M、缓存命中 ¥0.23/M。",
    },
    "Qwen/Qwen3.6-35B-A3B": {
        "input_cny_per_m": 1.80,
        "output_cny_per_m": 10.80,
        "cache_hit_cny_per_m": None,
        "source": "https://www.siliconflow.cn/pricing",
        "retrieved": "2026-11-14",
        "note": "官网价格页：输入 ¥1.80/M、输出 ¥10.80/M。页面未列出缓存命中价，估算时缓存命中按输入价计。",
    },
    "Qwen/Qwen3.8-27B": {
        "input_cny_per_m": 3.00,
        "output_cny_per_m": 12.00,
        "cache_hit_cny_per_m": None,
        "source": "https://www.siliconflow.cn/pricing",
        "retrieved": "2026-11-14",
        "note": "官网价格页：输入 ¥3.00/M、输出 ¥12.00/M。",
    },
    "zai-org/GLM-4.5-Air": {
        "input_cny_per_m": 1.00,
        "output_cny_per_m": 6.00,
        "cache_hit_cny_per_m": None,
        "source": "https://www.siliconflow.cn/pricing",
        "retrieved": "2026-11-14",
        "note": "官网价格页：输入 ¥1.00/M、输出 ¥6.00/M。",
    },
    "THUDM/GLM-4-32B-0414": {
        "input_cny_per_m": 1.89,
        "output_cny_per_m": 1.89,
        "cache_hit_cny_per_m": None,
        "source": "https://www.siliconflow.cn/pricing",
        "retrieved": "2026-11-14",
        "note": "官网价格页：输入/输出均为 ¥1.89/M。",
    },
}


def candidate_env_paths(root: Optional[Path] = None) -> list[Path]:
    if root is None:
        from geo_common.paths import ROOT
        root = ROOT
    return [root / ".env.local", Path.cwd() / ".env.local"]


def load_siliconflow_api_key(path: Optional[Path] = None) -> str:
    """Return the SiliconFlow API key, or '' if not found.

    Only the line whose name is SILICONFLOW_API_KEY is read. Values of any
    other variable in the same file are discarded and never returned.
    """
    paths = [Path(path)] if path is not None else candidate_env_paths()
    seen: set[Path] = set()
    for p in paths:
        try:
            p = p.resolve()
        except OSError:
            continue
        if p in seen or not p.is_file():
            continue
        seen.add(p)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k.startswith("export "):
                k = k[len("export "):].strip()
            if k != "SILICONFLOW_API_KEY":
                continue
            return v.strip().strip("'").strip('"')
    return ""


def estimate_cost_cny(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cache_hit_tokens: int = 0,
) -> tuple[Optional[float], str]:
    price = SILICONFLOW_PRICES.get(model)
    if not price:
        return None, (
            f"未收录 {model} 的官网标价，只报告 token 用量，不估算人民币。"
        )
    cache_hit_tokens = max(0, int(cache_hit_tokens or 0))
    prompt_tokens = max(0, int(prompt_tokens or 0))
    completion_tokens = max(0, int(completion_tokens or 0))
    billed_input = max(0, prompt_tokens - cache_hit_tokens)
    cache_rate = price["cache_hit_cny_per_m"]
    if cache_rate is None:
        # unknown cache price: bill cache hits at the input rate (conservative)
        cache_rate = price["input_cny_per_m"]
    cny = (
        billed_input / 1_000_000 * price["input_cny_per_m"]
        + cache_hit_tokens / 1_000_000 * cache_rate
        + completion_tokens / 1_000_000 * price["output_cny_per_m"]
    )
    cache_txt = (
        f"缓存命中¥{price['cache_hit_cny_per_m']}/M"
        if price["cache_hit_cny_per_m"] is not None
        else "缓存命中价未列出、估算按输入价计"
    )
    note = (
        f"{model} 标价 输入¥{price['input_cny_per_m']}/M、"
        f"输出¥{price['output_cny_per_m']}/M、{cache_txt}；"
        f"来源 {price['source']}，查阅日期 {price['retrieved']}（Asia/Shanghai）。"
        "此为按返回 token 与标价估算，不是账单原件。"
    )
    return cny, note
