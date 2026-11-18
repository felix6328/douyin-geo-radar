
from __future__ import annotations
import asyncio
from geo_common.llm import cumulative_spend_cny

async def gather_progress(coros, label: str, every: int = 25):
    n = len(coros)
    done = 0
    lock = asyncio.Lock()
    print(f"{label}: 0/{n} starting, spend={cumulative_spend_cny():.4f}", flush=True)

    async def wrap(c):
        nonlocal done
        try:
            return await c
        finally:
            async with lock:
                done += 1
                if done % every == 0 or done == n:
                    print(f"{label}: {done}/{n} spend={cumulative_spend_cny():.4f}", flush=True)

    return await asyncio.gather(*[wrap(c) for c in coros], return_exceptions=True)
