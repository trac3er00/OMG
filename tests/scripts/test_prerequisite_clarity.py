"""Tests that platform and language prerequisites are clearly documented.

Prevents the recurring issue where Python 3.10+ is required but not mentioned
in the README, and OS/platform constraints are buried or missing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestPrerequisiteClarity:
    """README and generated docs must surface all prerequisites."""

    def test_readme_mentions_python_version(self) -> None:
        """README must state the Python version requirement."""
        content = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        assert "3.10" in content, "README must mention Python >=3.10 requirement"

    def test_readme_mentions_node_version(self) -> None:
        """README must state the Node.js version requirement."""
        content = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        assert "18" in content and ("Node" in content or "node" in content), (
            "README must mention the Node >=18 requirement"
        )

    def test_readme_mentions_os_platform(self) -> None:
        """README must state supported platforms."""
        content = (REPO_ROOT / "README.md").read_text(encoding="utf-8").lower()
        assert "macos" in content or "linux" in content, (
            "README must mention supported OS platforms (macOS or Linux)"
        )

    def test_pyproject_python_requirement_matches_docs(self) -> None:
        """pyproject.toml Python requirement must match what docs say."""
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
        pyproject = tomllib.loads(
            (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        requires_python = pyproject["project"]["requires-python"]
        assert "3.10" in requires_python, (
            f"pyproject.toml requires-python is '{requires_python}', expected >=3.10"
        )

    def test_package_json_node_requirement_matches_docs(self) -> None:
        """package.json Node requirement must match what docs say."""
        pkg = json.loads(
            (REPO_ROOT / "package.json").read_text(encoding="utf-8")
        )
        engines = pkg.get("engines", {})
        assert "18" in engines.get("node", ""), (
            "package.json must declare Node >=18 engine requirement"
        )

    def test_generated_fast_path_mentions_python(self) -> None:
        """Generated install fast-path must mention Python as a prerequisite."""
        from runtime.release_surface_compiler import _install_fast_path_content

        content = _install_fast_path_content()
        assert "Python" in content or "python" in content, (
            "Generated fast-path prerequisite must mention Python"
        )

    def test_generated_fast_path_mentions_platform(self) -> None:
        """Generated install fast-path must mention platform constraint."""
        from runtime.release_surface_compiler import _install_fast_path_content

        content = _install_fast_path_content()
        assert "macOS" in content or "Linux" in content or "macos" in content.lower(), (
            "Generated fast-path prerequisite must mention supported platforms"
        )
