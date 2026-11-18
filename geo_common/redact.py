"""Strip secrets from error / log strings. Never leave a Bearer token."""

from __future__ import annotations

import re


def redact(text: str, key: str = "") -> str:
    if not text:
        return text
    s = str(text)
    if key:
        s = s.replace(key, "[REDACTED]")
    s = re.sub(r"Bearer\s+\S+", "Bearer [REDACTED]", s, flags=re.I)
    s = re.sub(
        r"(api[_-]?key|authorization|JWT_SECRET|AES_MASTER_KEY|DATABASE_URL|"
        r"DEEPSEEK_API_KEY|SILICONFLOW_API_KEY|REDIS_URL|CELERY_BROKER_URL)\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        s,
        flags=re.I,
    )
    return s
