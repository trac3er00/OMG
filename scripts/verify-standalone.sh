#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${1:-$(mktemp -d)}"

echo "[verify-standalone] source: $ROOT_DIR"
echo "[verify-standalone] workdir: $TMP_DIR"

tar --exclude="./vendor/omc" --exclude="./.omc" --exclude="./.pytest_cache" -cf - -C "$ROOT_DIR" . | (cd "$TMP_DIR" && tar -xf -)

cd "$TMP_DIR"
python3 scripts/oal.py compat gate --max-bridge 0 --output .oal/evidence/oal-compat-gap.json

if command -v pyenv >/dev/null 2>&1 && pyenv prefix 3.12.7 >/dev/null 2>&1; then
  PYENV_VERSION=3.12.7 python -m pytest -q
else
  python3 -m pytest -q
fi

echo "[verify-standalone] passed"
