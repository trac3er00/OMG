#!/usr/bin/env bash
# pre-release-check.sh — Run before creating any GitHub release or pushing a version tag.
# Checks that the tag name is not locked by a previously-deleted immutable GitHub release.
set -euo pipefail

VERSION="${1:-}"
REPO="${2:-trac3er00/OMG}"

if [ -z "$VERSION" ]; then
  echo "Usage: $0 <version> [repo]"
  echo "Example: $0 2.1.8 trac3er00/OMG"
  exit 1
fi

TAG="v${VERSION}"
echo "Checking tag ${TAG} on ${REPO}..."

# Check if tag already exists on remote
if git ls-remote --tags origin "refs/tags/${TAG}" | grep -q "refs/tags/${TAG}"; then
  echo "ERROR: Tag ${TAG} already exists on remote. Delete it first or use a new version."
  exit 1
fi

# Check if GitHub has an immutable release ghost for this tag
RESPONSE=$(gh api "repos/${REPO}/releases/tags/${TAG}" 2>&1 || true)
if echo "$RESPONSE" | grep -q '"immutable": true'; then
  echo "ERROR: Tag ${TAG} was used by an immutable release that was deleted."
  echo "GitHub permanently locks this tag name. You MUST use a different version."
  echo "Contact GitHub Support at https://support.github.com to clear it, or bump the version."
  exit 1
fi

# Check if any release references this tag
if echo "$RESPONSE" | grep -q '"tag_name"'; then
  echo "WARNING: A release already exists for ${TAG}. Verify this is intentional before proceeding."
fi

echo "OK: Tag ${TAG} is available for release."
