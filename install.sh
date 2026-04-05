#!/bin/bash
set -euo pipefail

echo "⚠️  install.sh is deprecated. Use: npx omg init" >&2
exec npx @trac3r/oh-my-god init "$@"
