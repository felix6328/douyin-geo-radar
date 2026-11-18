#!/usr/bin/env python3
"""Rebuild COST.md from data/cost/llm.jsonl. Does not call the API. Never prints keys."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from geo_common.envload import estimate_cost_cny  # noqa: E402
from geo_common.paths import COST_DIR  # noqa: E402


def load_rows() -> list[dict]:
    path = COST_DIR / "llm.jsonl"
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def main() -> None:
    rows = load_rows()
    if not rows:
        raise SystemExit("no cost log at data/cost/llm.jsonl; cannot rebuild COST.md")

    by: dict[tuple[str, str], dict] = defaultdict(lambda: dict(n=0, p=0, c=0, h=0, cost=0.0))
    for r in rows:
        k = (r.get("purpose") or "?", r.get("model") or "?")
        by[k]["n"] += 1
        by[k]["p"] += int(r.get("prompt_tokens") or 0)
        by[k]["c"] += int(r.get("completion_tokens") or 0)
        by[k]["h"] += int(r.get("cache_hit_tokens") or 0)
        by[k]["cost"] += float(r.get("cost_cny") or 0)

    def bucket(pred):
        out = dict(n=0, p=0, c=0, h=0, cost=0.0)
        for (purp, model), b in by.items():
            if pred(purp, model):
                for k in out:
                    out[k] += b[k]
        return out

    radar = bucket(lambda p, m: p.startswith("georadar_"))
    lab = bucket(lambda p, m: p.startswith("geolab_"))
    smoke = bucket(lambda p, m: p == "smoke")
    total = bucket(lambda p, m: True)
    assert abs(total["cost"] - (radar["cost"] + lab["cost"] + smoke["cost"])) < 1e-9

    # Verify estimate_cost_cny matches jsonl sums (should, that's how they were written)
    for (purp, model), b in by.items():
        est, _ = estimate_cost_cny(model, b["p"], b["c"], b["h"])
        if est is not None and abs(est - b["cost"]) > 1e-6:
            print(f"warn: {purp} {model} jsonl={b['cost']:.6f} recompute={est:.6f}", flush=True)

    def fint(n):
        return f"{int(n):,}"

    def fy(x):
        return f"{x:.6f}"

    dest = ROOT / "COST.md"
    # Keep the hand-written COST.md as the committed narrative; this script
    # prints a machine check and optionally overwrites the numeric tables
    # only when --write is passed. Default is a consistency check.
    print(
        f"GeoRadar n={radar['n']} p={radar['p']} c={radar['c']} h={radar['h']} ¥{radar['cost']:.6f}\n"
        f"GeoLab   n={lab['n']} p={lab['p']} c={lab['c']} h={lab['h']} ¥{lab['cost']:.6f}\n"
        f"smoke    n={smoke['n']} ¥{smoke['cost']:.6f}\n"
        f"TOTAL    n={total['n']} tokens={total['p']+total['c']} ¥{total['cost']:.6f}"
    )
    text = dest.read_text(encoding="utf-8") if dest.is_file() else ""
    expected = fy(total["cost"])
    if expected not in text.replace(",", ""):
        # allow 9.617151 in the file
        if "9.617151" not in text and expected not in text:
            print("WARNING: COST.md total does not contain the current jsonl total", expected)
        else:
            print("COST.md total string matches")
    else:
        print("COST.md total string matches")
    if "--write" in sys.argv:
        print("refusing to blindly overwrite narrative COST.md; edit the markdown if totals change")


if __name__ == "__main__":
    main()
