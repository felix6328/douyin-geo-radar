from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs"
DATA = ROOT / "data"
EVAL = ROOT / "eval"
COST_DIR = DATA / "cost"
CACHE_DIR = DATA / "cache"
ANSWERS = DATA / "answers"
GOLD = DATA / "gold"
INSIGHTS = DATA / "insights"
REPORTS = DATA / "reports"
CORPUS = DATA / "corpus"


def ensure_data_dirs() -> None:
    for p in (COST_DIR, CACHE_DIR, ANSWERS, GOLD, INSIGHTS, REPORTS, CORPUS):
        p.mkdir(parents=True, exist_ok=True)
        (p / ".gitkeep").touch(exist_ok=True)
