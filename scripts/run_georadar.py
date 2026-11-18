#!/usr/bin/env python3
"""Run GeoRadar generation, extraction, metrics and insights."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from georadar.pipeline import run_georadar  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-llm-extract", action="store_true")
    p.add_argument("--skip-insight", action="store_true")
    args = p.parse_args()
    result = asyncio.run(run_georadar(skip_llm_extract=args.skip_llm_extract, skip_insight=args.skip_insight))
    m = result["metrics"]
    print(
        f"done n={m['n_rows']} organic={m['n_organic']} failed={m['n_failed']} "
        f"mention_any={m['mention_any']} spend≈{m['spend_cny_process']:.4f}"
    )


if __name__ == "__main__":
    main()
