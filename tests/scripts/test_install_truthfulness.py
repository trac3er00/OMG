"""Tests that install documentation matches actual postinstall behavior.

Prevents the recurring bug where docs claim npm install applies configuration
but postinstall only runs --plan.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestInstallTruthfulness:
    """Install docs must not claim more than postinstall actually does."""

    def test_postinstall_is_plan_only(self) -> None:
        """package.json postinstall must be plan-only."""
        pkg = json.loads(
            (REPO_ROOT / "package.json").read_text(encoding="utf-8")
        )
        postinstall = pkg["scripts"]["postinstall"]
        assert "--plan" in postinstall, "postinstall must run --plan"
        assert "--apply" not in postinstall, "postinstall must not run --apply"

    def test_generated_fast_path_does_not_claim_automatic(self) -> None:
        """Generated install-fast-path must not claim automatic registration."""
        from runtime.release_surface_compiler import _install_fast_path_content

        content = _install_fast_path_content()
        assert "automatically" not in content.lower(), (
            "Generated fast-path must not claim automatic registration "
            "when postinstall is plan-only"
        )

    def test_readme_quickstart_mentions_apply(self) -> None:
        """README quickstart must mention --apply when describing what npm install does."""
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        quickstart_idx = readme.find("npm install @trac3er/oh-my-god")
        generated_idx = readme.find("<!-- OMG:GENERATED:quickstart -->")
        if quickstart_idx >= 0 and generated_idx >= 0:
            authored_section = readme[quickstart_idx:generated_idx]
            if "registers" in authored_section.lower() or "wires" in authored_section.lower():
                assert "--apply" in authored_section, (
                    "README quickstart claims npm install does things "
                    "but doesn't mention --apply"
                )

    def test_install_guides_generated_not_misleading(self) -> None:
        """Install guide generated sections must not claim automatic registration."""
        for guide in ("claude-code.md", "codex.md", "gemini.md", "kimi.md"):
            path = REPO_ROOT / "docs" / "install" / guide
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            m = re.search(
                r"<!-- OMG:GENERATED:install-fast-path -->(.*?)"
                r"<!-- /OMG:GENERATED:install-fast-path -->",
                content,
                re.DOTALL,
            )
            if m:
                assert "automatically" not in m.group(1).lower(), (
                    f"{guide}: generated fast-path block claims automatic registration"
                )

    def test_claude_code_guide_does_not_claim_npm_install_is_equivalent(self) -> None:
        """claude-code.md authored prose must not overclaim what npm install does."""
        path = REPO_ROOT / "docs" / "install" / "claude-code.md"
        content = path.read_text(encoding="utf-8")
        assert "`npm install` is equivalent for OMG" not in content, (
            "claude-code.md must not claim npm install alone is equivalent "
            "to the native plugin install flow when --apply is required"
        )
