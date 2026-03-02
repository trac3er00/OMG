"""Frontmatter format checks for command documents."""
from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = ROOT / "commands"
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def test_command_frontmatter_argument_hint_is_quoted_string() -> None:
    for path in sorted(COMMANDS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        assert match is not None, f"{path.name} is missing valid frontmatter delimiters"

        frontmatter = match.group(1)
        for raw_line in frontmatter.splitlines():
            line = raw_line.strip()
            if not line.startswith("argument-hint:"):
                continue
            _, value = line.split(":", 1)
            hint = value.strip()
            assert hint, f"{path.name} has empty argument-hint"
            assert (
                hint.startswith('"') and hint.endswith('"')
            ), f"{path.name} argument-hint must be a quoted string: {hint}"
