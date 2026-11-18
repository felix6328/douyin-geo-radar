#!/usr/bin/env python3
"""Rebuild GeoLab eval reports from saved answer rows. Does not call the API."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from geolab.report import render_from_saved  # noqa: E402


def main() -> None:
    payload = render_from_saved()
    policy = payload["policy"]
    print(
        f"rendered n={payload['n_main']} frozen={payload['n_frozen']} "
        f"failed={payload['n_failed']} policy={policy['by_qtype']} "
        f"global_best={policy['global_best']}"
    )
    test = payload["paired_test_vs_baseline"]["cite_rate"]
    print(
        f"test paired cite Δ={test['mean']:.4f} "
        f"[{test['ci_low']:.4f}, {test['ci_high']:.4f}] "
        f"excludes_zero={test['excludes_zero']}"
    )


if __name__ == "__main__":
    main()
