#!/usr/bin/env bash
set -euo pipefail

FORBID_VERSION="${FORBID_VERSION:-}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${1:-$(mktemp -d)}"

echo "[verify-standalone] source: $ROOT_DIR"
echo "[verify-standalone] workdir: $TMP_DIR"

tar --exclude="./.omc" --exclude="./.omg" --exclude="./.pytest_cache" -cf - -C "$ROOT_DIR" . | (cd "$TMP_DIR" && tar -xf -)

cd "$TMP_DIR"
mkdir -p .omg/evidence
export OMG_RELEASE_READY_PROVIDERS="claude,codex,gemini,kimi"
python3 scripts/omg.py doctor --format json > .omg/evidence/doctor.json
python3 scripts/prepare-release-proof-fixtures.py --output-root .
python3 scripts/omg.py contract validate
python3 scripts/omg.py contract compile --host claude --host codex --host gemini --host kimi --channel public --output-root .
python3 scripts/omg.py contract compile --host claude --host codex --host gemini --host kimi --channel enterprise --output-root .
python3 scripts/omg.py release readiness --channel dual --output-root .
python3 scripts/omg.py compat gate --max-bridge 0 --output .omg/evidence/omg-compat-gap.json
python3 scripts/check-omg-public-ready.py

echo "=== Validating release identity ==="
python3 scripts/validate-release-identity.py --scope all --forbid-version "${FORBID_VERSION}"

if command -v pyenv >/dev/null 2>&1 && pyenv prefix 3.12.7 >/dev/null 2>&1; then
  PYENV_VERSION=3.12.7 python -m pytest -q -o addopts=''
else
  python3 -m pytest -q -o addopts=''
fi

echo "[verify-standalone] passed"
