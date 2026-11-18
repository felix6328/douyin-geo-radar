"""OpenAI-compatible SiliconFlow client.

- Loads only SILICONFLOW_API_KEY (official https://api.siliconflow.cn/v1).
- Never uses DEEPSEEK_* (may point at a third-party relay).
- Disk cache by request hash so retries do not re-bill.
- Cost jsonl is gitignored and contains no key.
- Thinking/reasoning is disabled to keep cost and answers comparable.
- A process-wide spend cap aborts before starting a new call.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

from geo_common.envload import (
    SILICONFLOW_BASE_URL,
    estimate_cost_cny,
    load_siliconflow_api_key,
)
from geo_common.paths import CACHE_DIR, COST_DIR, ensure_data_dirs
from geo_common.redact import redact

# Hard cap for this repo's experiments. Abort a *new* call if cumulative
# estimated CNY (this process + prior jsonl) would exceed this.
SPEND_CAP_CNY = 28.0


@dataclass
class ChatResult:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hit_tokens: int = 0
    cost_cny: Optional[float] = None
    cost_note: str = ""
    latency_ms: float = 0.0
    cached: bool = False
    finish_reason: str = ""
    raw_content: str = ""
    error: str = ""

    def token_total(self) -> int:
        return int(self.prompt_tokens or 0) + int(self.completion_tokens or 0)


def _cache_hit_tokens(usage: dict) -> int:
    if not usage:
        return 0
    details = usage.get("prompt_tokens_details") or {}
    for k in ("prompt_cache_hit_tokens", "cache_hit_tokens", "cached_tokens"):
        if usage.get(k) is not None:
            try:
                return int(usage[k] or 0)
            except (TypeError, ValueError):
                pass
    try:
        return int(details.get("cached_tokens") or details.get("cache_hit_tokens") or 0)
    except (TypeError, ValueError):
        return 0


def _strip_think(content: str) -> str:
    if not content:
        return ""
    s = content
    # Common wrappers if a model ignores enable_thinking=false.
    for a, b in (
        ("<think>", "</think>"),
        ("<thinking>", "</thinking>"),
        ("<reason>", "</reason>"),
    ):
        while a in s and b in s:
            i, j = s.find(a), s.find(b)
            if i < 0 or j < i:
                break
            s = s[:i] + s[j + len(b):]
    return s.strip()


def request_hash(payload: dict) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cache_path(kind: str, h: str) -> Path:
    ensure_data_dirs()
    d = CACHE_DIR / kind / h[:2]
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{h}.json"


def read_cache(kind: str, h: str) -> Optional[dict]:
    p = _cache_path(kind, h)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_cache(kind: str, h: str, obj: dict) -> None:
    p = _cache_path(kind, h)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


_spend_lock = asyncio.Lock()
_session_spend = 0.0
_prior_loaded = False
_prior_spend = 0.0


def _load_prior_spend() -> float:
    global _prior_loaded, _prior_spend
    if _prior_loaded:
        return _prior_spend
    ensure_data_dirs()
    total = 0.0
    for p in COST_DIR.glob("*.jsonl"):
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                v = row.get("cost_cny")
                if v is not None:
                    total += float(v)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    _prior_spend = total
    _prior_loaded = True
    return _prior_spend


def cumulative_spend_cny() -> float:
    return _load_prior_spend() + _session_spend


def append_cost(row: dict) -> None:
    ensure_data_dirs()
    p = COST_DIR / "llm.jsonl"
    # Never persist a key. Redact just in case a caller slipped.
    safe = {k: v for k, v in row.items() if "key" not in k.lower() and "authorization" not in k.lower()}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(safe, ensure_ascii=False, default=str) + "\n")


class SpendCapExceeded(RuntimeError):
    pass


class LLMClient:
    def __init__(
        self,
        concurrency: int = 6,
        timeout: float = 120.0,
        cache_kind: str = "chat",
        spend_cap: float = SPEND_CAP_CNY,
    ) -> None:
        self.key = load_siliconflow_api_key()
        self.base = SILICONFLOW_BASE_URL
        self.sem = asyncio.Semaphore(concurrency)
        self.timeout = timeout
        self.cache_kind = cache_kind
        self.spend_cap = spend_cap
        self._http: Optional[httpx.AsyncClient] = None

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    async def _http_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self.timeout)
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _payload(
        self,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        seed: Optional[int],
        json_mode: bool,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            # Disable chain-of-thought across families; ignored if unsupported.
            "enable_thinking": False,
            "thinking": {"type": "disabled"},
        }
        if seed is not None:
            payload["seed"] = int(seed)
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 800,
        seed: Optional[int] = None,
        json_mode: bool = False,
        purpose: str = "",
        use_cache: bool = True,
    ) -> ChatResult:
        global _session_spend
        payload = self._payload(model, messages, temperature, max_tokens, seed, json_mode)
        h = request_hash(payload)
        if use_cache:
            hit = read_cache(self.cache_kind, h)
            if hit and hit.get("content") is not None:
                cost, note = estimate_cost_cny(
                    model,
                    int(hit.get("prompt_tokens") or 0),
                    int(hit.get("completion_tokens") or 0),
                    int(hit.get("cache_hit_tokens") or 0),
                )
                return ChatResult(
                    content=_strip_think(hit.get("content") or ""),
                    raw_content=hit.get("content") or "",
                    model=model,
                    prompt_tokens=int(hit.get("prompt_tokens") or 0),
                    completion_tokens=int(hit.get("completion_tokens") or 0),
                    cache_hit_tokens=int(hit.get("cache_hit_tokens") or 0),
                    cost_cny=0.0,  # already billed; do not double-count
                    cost_note="disk cache hit, 本次不重复计费。" + (note or ""),
                    latency_ms=0.0,
                    cached=True,
                    finish_reason=hit.get("finish_reason") or "cache",
                )

        if not self.key:
            return ChatResult(content="", model=model, error="no_api_key")

        prior = _load_prior_spend()
        if prior + _session_spend >= self.spend_cap:
            raise SpendCapExceeded(
                f"累计估算费用已达 {prior + _session_spend:.4f} 元，超过上限 {self.spend_cap}。"
            )

        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base}/chat/completions"
        last_err = ""
        body = None
        t0 = time.perf_counter()
        async with self.sem:
            client = await self._http_client()
            for attempt in range(5):
                try:
                    r = await client.post(url, headers=headers, json=payload)
                    if r.status_code == 429 or r.status_code >= 500:
                        last_err = redact(f"HTTP {r.status_code} {r.text[:200]}", self.key)
                        # TPM limits need a longer pause than transient 5xx.
                        base = 8.0 if r.status_code == 429 else 1.5
                        await asyncio.sleep(base * (2 ** attempt))
                        continue
                    if r.status_code >= 400:
                        last_err = redact(f"HTTP {r.status_code} {r.text[:400]}", self.key)
                        break
                    body = r.json()
                    last_err = ""
                    break
                except (httpx.HTTPError, json.JSONDecodeError) as e:
                    last_err = redact(f"{type(e).__name__}: {e}", self.key)
                    await asyncio.sleep(1.5 * (2 ** attempt))
        latency = (time.perf_counter() - t0) * 1000

        if not body:
            return ChatResult(
                content="",
                model=model,
                latency_ms=latency,
                error=last_err or "empty_response",
            )

        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        # Some models put text in reasoning_content when thinking is on.
        if not content and message.get("reasoning_content"):
            content = ""  # do not treat chain-of-thought as the answer
        content = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        usage = body.get("usage") or {}
        pt = int(usage.get("prompt_tokens") or 0)
        ct = int(usage.get("completion_tokens") or 0)
        cht = _cache_hit_tokens(usage)
        cost, note = estimate_cost_cny(model, pt, ct, cht)
        if cost:
            _session_spend += float(cost)

        record = {
            "content": content,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "cache_hit_tokens": cht,
            "finish_reason": choice.get("finish_reason") or "",
            "model": model,
        }
        if use_cache:
            write_cache(self.cache_kind, h, record)

        append_cost(
            {
                "ts": time.time(),
                "purpose": purpose,
                "model": model,
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "cache_hit_tokens": cht,
                "cost_cny": cost,
                "latency_ms": round(latency, 2),
                "hash": h,
                "cached": False,
            }
        )
        return ChatResult(
            content=_strip_think(content),
            raw_content=content,
            model=model,
            prompt_tokens=pt,
            completion_tokens=ct,
            cache_hit_tokens=cht,
            cost_cny=cost,
            cost_note=note,
            latency_ms=latency,
            cached=False,
            finish_reason=record["finish_reason"],
        )


def _strip_fence(s: str) -> str:
    import re
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _repair_truncated_json(s: str) -> Optional[dict]:
    """Best-effort close of truncated JSON objects (e.g. hit max_tokens)."""
    i = s.find("{")
    if i < 0:
        return None
    s = s[i:]
    stack: list[str] = []
    in_str = False
    escape = False
    for ch in s:
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()
    if in_str:
        s += '"'
    closers = {"{": "}", "[": "]"}
    while stack:
        s += closers[stack.pop()]
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def parse_json_object(content: str) -> Optional[dict]:
    if not content:
        return None
    s = _strip_fence(content)
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        i, j = s.find("{"), s.rfind("}")
        if i >= 0 and j > i:
            try:
                obj = json.loads(s[i : j + 1])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
        return _repair_truncated_json(s)
