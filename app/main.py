"""Lightweight workbench to inspect GeoRadar and GeoLab results."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from geo_common.paths import EVAL, ANSWERS, INSIGHTS, ROOT

app = FastAPI(title="GEO Workbench")
STATIC = Path(__file__).resolve().parent / "static"


def _load(path: Path):
    if not path.is_file():
        return None
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/georadar/metrics")
def georadar_metrics():
    data = _load(EVAL / "results_georadar.json")
    if data is None:
        return JSONResponse({"error": "run scripts/run_georadar.py first"}, status_code=404)
    return data


@app.get("/api/georadar/insights")
def georadar_insights():
    data = _load(INSIGHTS / "georadar_insights.json")
    return data or {}


@app.get("/api/geolab/metrics")
def geolab_metrics():
    data = _load(EVAL / "results_geolab.json")
    if data is None:
        return JSONResponse({"error": "run scripts/run_geolab.py first"}, status_code=404)
    return data


@app.get("/api/reports/{name}")
def reports(name: str):
    allowed = {
        "results_georadar.md": EVAL / "results_georadar.md",
        "badcases_georadar.md": EVAL / "badcases_georadar.md",
        "results_geolab.md": EVAL / "results_geolab.md",
        "badcases_geolab.md": EVAL / "badcases_geolab.md",
    }
    path = allowed.get(name)
    if not path or not path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return HTMLResponse(
        "<pre style='white-space:pre-wrap;font-family:sans-serif;max-width:980px;margin:24px auto'>"
        + path.read_text(encoding="utf-8").replace("&", "&amp;").replace("<", "&lt;")
        + "</pre>"
    )
