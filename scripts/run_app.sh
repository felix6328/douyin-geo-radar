#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8766
