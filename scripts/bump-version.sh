#!/bin/bash
# bump-version.sh — Sync all version files and push release tag
# Usage: ./scripts/bump-version.sh 2.0.1
set -euo pipefail

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version>"
    echo "  Example: $0 2.0.1"
    echo "  Example: $0 2.1.0-b"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"

echo "Bumping all version files to $VERSION..."

python3 - "$VERSION" "$ROOT" <<'PY'
import json, sys
from pathlib import Path

version = sys.argv[1]
root = Path(sys.argv[2])

# package.json
p = root / "package.json"
d = json.loads(p.read_text())
d["version"] = version
p.write_text(json.dumps(d, indent=2) + "\n")
print(f"  ✓ package.json → {version}")

# .claude-plugin/plugin.json
p = root / ".claude-plugin/plugin.json"
d = json.loads(p.read_text())
d["version"] = version
p.write_text(json.dumps(d, indent=2) + "\n")
print(f"  ✓ plugin.json → {version}")

# .claude-plugin/marketplace.json (3 version fields)
p = root / ".claude-plugin/marketplace.json"
d = json.loads(p.read_text())
d["version"] = version
if isinstance(d.get("metadata"), dict):
    d["metadata"]["version"] = version
if isinstance(d.get("plugins"), list) and d["plugins"]:
    d["plugins"][0]["version"] = version
p.write_text(json.dumps(d, indent=2) + "\n")
print(f"  ✓ marketplace.json → {version}")
PY

echo ""
echo "All version files updated to $VERSION"
echo ""
echo "Committing and tagging..."
cd "$ROOT"
git add package.json .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "chore: bump version to $VERSION"
git tag "v$VERSION"
echo ""
echo "Done! Push with:"
echo "  git push origin main && git push origin v$VERSION"
