#!/usr/bin/env bash
set -euo pipefail

# Sync vendor/omc from upstream oh-my-claudecode.
# Default strategy:
# 1) Try git subtree add/pull (when current repo is a git repository)
# 2) Fallback to direct git clone copy (for non-git workspace packaging)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/Yeachan-Heo/oh-my-claudecode}"
UPSTREAM_BRANCH="${UPSTREAM_BRANCH:-main}"
VENDOR_DIR="$ROOT_DIR/vendor/omc"
TMP_DIR="${TMPDIR:-/tmp}/oal-omc-sync-$$"

echo "[sync-omc] root: $ROOT_DIR"
echo "[sync-omc] upstream: $UPSTREAM_URL ($UPSTREAM_BRANCH)"

if git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[sync-omc] git repo detected — attempting subtree workflow"
  if ! git -C "$ROOT_DIR" remote get-url omc-upstream >/dev/null 2>&1; then
    git -C "$ROOT_DIR" remote add omc-upstream "$UPSTREAM_URL"
  fi
  git -C "$ROOT_DIR" fetch omc-upstream "$UPSTREAM_BRANCH"

  if [ -d "$VENDOR_DIR" ]; then
    git -C "$ROOT_DIR" subtree pull --prefix=vendor/omc omc-upstream "$UPSTREAM_BRANCH" --squash
  else
    git -C "$ROOT_DIR" subtree add --prefix=vendor/omc omc-upstream "$UPSTREAM_BRANCH" --squash
  fi
else
  echo "[sync-omc] non-git workspace detected — using clone+copy fallback"
  rm -rf "$TMP_DIR"
  git clone --depth 1 --branch "$UPSTREAM_BRANCH" "$UPSTREAM_URL" "$TMP_DIR"
  rm -rf "$VENDOR_DIR"
  mkdir -p "$(dirname "$VENDOR_DIR")"
  cp -R "$TMP_DIR" "$VENDOR_DIR"
  rm -rf "$VENDOR_DIR/.git"
  rm -rf "$TMP_DIR"
fi

if [ -f "$VENDOR_DIR/LICENSE" ]; then
  cp "$VENDOR_DIR/LICENSE" "$ROOT_DIR/vendor/omc.LICENSE"
fi

UPSTREAM_HASH="$(git -C "$VENDOR_DIR" rev-parse HEAD 2>/dev/null || true)"
echo "[sync-omc] done. vendor/omc hash: ${UPSTREAM_HASH:-unknown (copied without git metadata)}"

