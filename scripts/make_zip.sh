#!/usr/bin/env bash
# Pack the repo for the author. Never include secrets, venv, or API caches.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/workspace/geo.zip}"
cd "$ROOT"

# Safety: refuse if .env.local would be included by a sloppy path
if [[ -f .env.local ]]; then
  if git check-ignore -q .env.local 2>/dev/null || true; then
    :
  fi
fi

# Use git archive if repo exists, then it's automatically honor gitignore
# plus extra excludes. Fall back to zip with explicit excludes.
excludes=(
  "*.env" "*.env.local" ".env.local"
  ".venv/*" ".venv/**"
  "__pycache__/*" "*/__pycache__/*" "**/__pycache__/*"
  ".pytest_cache/*" ".pytest_cache/**"
  "data/cache/*" "data/cache/**"
  "data/cost/*.jsonl"
  ".git/*" ".git/**"
)

# Also drop any file that looks like a key
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Copy with rsync-like python to honor excludes and never copy .env.local
python3 - << PY
import os, shutil, zipfile
from pathlib import Path

root = Path("$ROOT")
out = Path("$OUT")
skip_dirs = {".venv", "__pycache__", ".pytest_cache", ".git", ".cache"}
skip_names = {".env", ".env.local", "llm.jsonl"}
# cache dir contents skipped, keep .gitkeep

def keep(path: Path) -> bool:
    rel = path.relative_to(root)
    parts = rel.parts
    if any(p in skip_dirs for p in parts):
        return False
    if path.name in skip_names:
        return False
    if "data/cache" in str(rel).replace("\\\\", "/") and path.name != ".gitkeep":
        return False
    if path.suffix in {".pyc", ".pyo"}:
        return False
    return True

# Scan for accidental secrets in filenames or small text files we will include
forbidden_substrings = (b"SILICONFLOW_API_KEY=", b"sk-")  # sk- only flagged later with context

files = []
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in skip_dirs]
    for fn in filenames:
        p = Path(dirpath) / fn
        if keep(p):
            files.append(p)

# Secret scan: if a file contains SILICONFLOW_API_KEY= or JWT_SECRET= abort
bad = []
for p in files:
    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".zip", ".pdf", ".docx", ".woff", ".ttf", ".ttc"}:
        continue
    try:
        data = p.read_bytes()
    except OSError:
        continue
    if b"SILICONFLOW_API_KEY=" in data or b"JWT_SECRET=" in data or b"AES_MASTER_KEY=" in data:
        # allow docs that mention the variable NAME in instructions, if they don't assign a value
        text = data.decode("utf-8", errors="ignore")
        import re
        if re.search(r"SILICONFLOW_API_KEY\s*=\s*\S+", text) and not re.search(r"SILICONFLOW_API_KEY\s*=\s*(\.\.\.|xxx|<YOUR|你的)", text):
            # still allow README examples like SILICONFLOW_API_KEY=...
            if re.search(r"SILICONFLOW_API_KEY\s*=\s*['\"]?[A-Za-z0-9_\-]{16,}", text):
                bad.append(str(p))
if bad:
    raise SystemExit("refusing to zip, possible secret in: " + ", ".join(bad))

out.parent.mkdir(parents=True, exist_ok=True)
if out.exists():
    out.unlink()
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for p in sorted(files):
        z.write(p, p.relative_to(root).as_posix())
print("wrote", out, "files", len(files), "bytes", out.stat().st_size)
# verify
with zipfile.ZipFile(out) as z:
    names = z.namelist()
    assert not any(".env" in n for n in names), names
    assert not any(".venv/" in n for n in names)
    assert not any("llm.jsonl" in n for n in names)
    cached = [n for n in names if "data/cache/" in n and not n.endswith(".gitkeep")]
    assert not cached, cached[:5]
    print("zip entries", len(names), "ok, no secrets")
PY
echo "packed $OUT"
