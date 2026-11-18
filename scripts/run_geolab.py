#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from geolab.pipeline import run_geolab  # noqa: E402


def main() -> None:
    result = asyncio.run(run_geolab())
    print(f"done n={result['n']} policy={result['policy']['by_qtype']}")


if __name__ == "__main__":
    main()
