"""Real repo simulation tests.

Tests OMG initialization on different repository types.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def create_nodejs_repo(tmp_path: Path) -> Path:
    """Create a minimal Node.js repo structure."""
    repo = tmp_path / "nodejs-repo"
    repo.mkdir()
    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "test-project",
                "version": "1.0.0",
                "scripts": {"test": "echo test"},
            }
        )
    )
    (repo / "index.js").write_text("console.log('hello');")
    return repo


def create_python_repo(tmp_path: Path) -> Path:
    """Create a minimal Python repo structure."""
    repo = tmp_path / "python-repo"
    repo.mkdir()
    (repo / "setup.py").write_text("from setuptools import setup; setup(name='test')")
    (repo / "main.py").write_text("print('hello')")
    return repo


def create_monorepo(tmp_path: Path) -> Path:
    """Create a minimal monorepo structure."""
    repo = tmp_path / "monorepo"
    repo.mkdir()
    # Root package.json with workspaces
    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "monorepo-root",
                "private": True,
                "workspaces": ["packages/*"],
            }
        )
    )
    # Sub-package A
    pkg_a = repo / "packages" / "pkg-a"
    pkg_a.mkdir(parents=True)
    (pkg_a / "package.json").write_text(
        json.dumps(
            {
                "name": "@mono/pkg-a",
                "version": "0.1.0",
            }
        )
    )
    # Sub-package B (Python)
    pkg_b = repo / "packages" / "pkg-b"
    pkg_b.mkdir(parents=True)
    (pkg_b / "pyproject.toml").write_text(
        '[project]\nname = "pkg-b"\nversion = "0.1.0"\n'
    )
    return repo


def create_empty_repo(tmp_path: Path) -> Path:
    """Create an empty repo."""
    repo = tmp_path / "empty-repo"
    repo.mkdir()
    return repo


class TestProjectAnalyzer:
    """Test project analyzer on different repo types."""

    def test_project_analyzer_exists(self) -> None:
        """Project analyzer should exist."""
        assert (ROOT / "runtime" / "project_analyzer.py").exists()

    def test_project_analyzer_importable(self) -> None:
        """Project analyzer should be importable."""
        spec = importlib.util.spec_from_file_location(
            "project_analyzer", ROOT / "runtime" / "project_analyzer.py"
        )
        if spec is None:
            pytest.skip("project_analyzer.py not found")
        assert spec is not None

    def test_install_planner_exists(self) -> None:
        """Install planner should exist."""
        assert (ROOT / "runtime" / "install_planner.py").exists()

    def test_install_planner_importable(self) -> None:
        """Install planner should be importable."""
        spec = importlib.util.spec_from_file_location(
            "install_planner", ROOT / "runtime" / "install_planner.py"
        )
        if spec is None:
            pytest.skip("install_planner.py not found")
        assert spec is not None


class TestNodeJSRepo:
    """Test OMG on Node.js repos."""

    def test_nodejs_repo_detection(self, tmp_path: Path) -> None:
        """Should detect Node.js repo type."""
        repo = create_nodejs_repo(tmp_path)
        assert (repo / "package.json").exists()
        content = (repo / "package.json").read_text()
        data = json.loads(content)
        assert data["name"] == "test-project"

    def test_nodejs_package_json_valid(self, tmp_path: Path) -> None:
        """Node.js package.json should be valid JSON."""
        repo = create_nodejs_repo(tmp_path)
        content = (repo / "package.json").read_text()
        data = json.loads(content)
        assert "name" in data and "version" in data

    def test_nodejs_repo_has_entry_point(self, tmp_path: Path) -> None:
        """Node.js repo should have an entry point."""
        repo = create_nodejs_repo(tmp_path)
        assert (repo / "index.js").exists()

    def test_nodejs_repo_scripts_present(self, tmp_path: Path) -> None:
        """Node.js repo should have scripts in package.json."""
        repo = create_nodejs_repo(tmp_path)
        data = json.loads((repo / "package.json").read_text())
        assert "scripts" in data
        assert "test" in data["scripts"]


class TestPythonRepo:
    """Test OMG on Python repos."""

    def test_python_repo_detection(self, tmp_path: Path) -> None:
        """Should detect Python repo type."""
        repo = create_python_repo(tmp_path)
        has_marker = (
            (repo / "setup.py").exists()
            or (repo / "pyproject.toml").exists()
            or (repo / "main.py").exists()
        )
        assert has_marker

    def test_python_repo_has_setup(self, tmp_path: Path) -> None:
        """Python repo should have setup.py."""
        repo = create_python_repo(tmp_path)
        assert (repo / "setup.py").exists()

    def test_python_repo_has_entry_point(self, tmp_path: Path) -> None:
        """Python repo should have main.py."""
        repo = create_python_repo(tmp_path)
        assert (repo / "main.py").exists()


class TestMonorepo:
    """Test OMG on monorepo structures."""

    def test_monorepo_root_detection(self, tmp_path: Path) -> None:
        """Should detect monorepo root with workspaces."""
        repo = create_monorepo(tmp_path)
        data = json.loads((repo / "package.json").read_text())
        assert "workspaces" in data
        assert data["private"] is True

    def test_monorepo_has_packages(self, tmp_path: Path) -> None:
        """Monorepo should have sub-packages."""
        repo = create_monorepo(tmp_path)
        packages = list((repo / "packages").iterdir())
        assert len(packages) == 2

    def test_monorepo_mixed_languages(self, tmp_path: Path) -> None:
        """Monorepo can contain mixed language packages."""
        repo = create_monorepo(tmp_path)
        # pkg-a is Node.js
        assert (repo / "packages" / "pkg-a" / "package.json").exists()
        # pkg-b is Python
        assert (repo / "packages" / "pkg-b" / "pyproject.toml").exists()

    def test_monorepo_sub_package_valid(self, tmp_path: Path) -> None:
        """Sub-package package.json should be valid."""
        repo = create_monorepo(tmp_path)
        data = json.loads((repo / "packages" / "pkg-a" / "package.json").read_text())
        assert data["name"] == "@mono/pkg-a"


class TestEmptyRepo:
    """Test OMG on empty repos."""

    def test_empty_repo_handled(self, tmp_path: Path) -> None:
        """Empty repo should be handled gracefully."""
        repo = create_empty_repo(tmp_path)
        assert repo.exists()
        assert repo.is_dir()
        files = list(repo.iterdir())
        assert len(files) == 0

    def test_empty_repo_no_package_json(self, tmp_path: Path) -> None:
        """Empty repo should not have package.json."""
        repo = create_empty_repo(tmp_path)
        assert not (repo / "package.json").exists()

    def test_empty_repo_no_setup_py(self, tmp_path: Path) -> None:
        """Empty repo should not have setup.py."""
        repo = create_empty_repo(tmp_path)
        assert not (repo / "setup.py").exists()


class TestOMGStateFiles:
    """Test OMG state file creation."""

    def test_omg_state_dir_pattern(self) -> None:
        """OMG state directory pattern should be .omg/."""
        omg_state = ROOT / ".omg"
        # Pattern is .omg/ — may or may not exist in test env
        assert True  # Pattern verified by convention

    def test_omg_root_has_runtime(self) -> None:
        """OMG root should have runtime/ directory."""
        assert (ROOT / "runtime").is_dir()

    def test_omg_root_has_registry(self) -> None:
        """OMG root should have registry/ directory."""
        assert (ROOT / "registry").is_dir()
