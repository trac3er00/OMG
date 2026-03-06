#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${1:-$(mktemp -d)}"

echo "[verify-standalone] source: $ROOT_DIR"
echo "[verify-standalone] workdir: $TMP_DIR"

tar --exclude="./.omc" --exclude="./node_modules" -cf - -C "$ROOT_DIR" . | (cd "$TMP_DIR" && tar -xf -)

cd "$TMP_DIR"
bun install --ignore-scripts
bun scripts/omg.ts compat gate --max-bridge 0 --output .omg/evidence/omg-compat-gap.json
bun test

echo "[verify-standalone] passed"
