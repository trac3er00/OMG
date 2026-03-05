"""Tests for plugins/dephealth/manifest_detector.py — TDD RED phase."""

import json
import os
import sys
import tempfile

import pytest

# Add project root to sys.path for import
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from plugins.dephealth.manifest_detector import (
    DependencyList,
    ManifestFile,
    Package,
    detect_manifests,
)


@pytest.fixture(autouse=True)
def _enable_dep_health(monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_project(files: dict[str, str]) -> str:
    """Create a temp project directory with the given files."""
    tmp = tempfile.mkdtemp()
    for name, content in files.items():
        path = os.path.join(tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
    return tmp


# ─── 1. package.json ─────────────────────────────────────────────────────────


class TestDetectPackageJson:
    def test_detect_package_json(self):
        """package.json parsed correctly with prod and dev deps."""
        proj = _make_project({
            "package.json": json.dumps({
                "dependencies": {
                    "express": "^4.18.0",
                    "lodash": "4.17.21",
                },
                "devDependencies": {
                    "jest": "^29.0.0",
                },
            }),
        })
        result = detect_manifests(proj)

        assert isinstance(result, DependencyList)
        assert len(result.manifests) == 1
        assert result.manifests[0].format == "package.json"

        names = {p.name for p in result.packages}
        assert "express" in names
        assert "lodash" in names
        assert "jest" in names

        # Prod deps
        express = next(p for p in result.packages if p.name == "express")
        assert express.version == "^4.18.0"
        assert express.dev is False

        # Dev dep
        jest = next(p for p in result.packages if p.name == "jest")
        assert jest.dev is True


# ─── 2. requirements.txt ─────────────────────────────────────────────────────


class TestDetectRequirementsTxt:
    def test_detect_requirements_txt(self):
        """requirements.txt parsed with == and >= specifiers."""
        proj = _make_project({
            "requirements.txt": (
                "flask==2.3.0\n"
                "requests>=2.31.0\n"
                "# comment line\n"
                "\n"
                "numpy\n"
            ),
        })
        result = detect_manifests(proj)

        assert len(result.manifests) == 1
        assert result.manifests[0].format == "requirements.txt"

        names = {p.name for p in result.packages}
        assert "flask" in names
        assert "requests" in names
        assert "numpy" in names

        flask = next(p for p in result.packages if p.name == "flask")
        assert flask.version == "2.3.0"
        assert flask.dev is False

        # No version specifier => empty string
        numpy_pkg = next(p for p in result.packages if p.name == "numpy")
        assert numpy_pkg.version == ""


# ─── 3. Cargo.toml ───────────────────────────────────────────────────────────


class TestDetectCargoToml:
    def test_detect_cargo_toml(self):
        """Cargo.toml [dependencies] section parsed via regex."""
        proj = _make_project({
            "Cargo.toml": (
                "[package]\n"
                'name = "myapp"\n'
                'version = "0.1.0"\n'
                "\n"
                "[dependencies]\n"
                'serde = "1.0"\n'
                'tokio = { version = "1.28", features = ["full"] }\n'
                "\n"
                "[dev-dependencies]\n"
                'criterion = "0.5"\n'
            ),
        })
        result = detect_manifests(proj)

        assert len(result.manifests) == 1
        assert result.manifests[0].format == "Cargo.toml"

        names = {p.name for p in result.packages}
        assert "serde" in names
        assert "tokio" in names
        assert "criterion" in names

        serde = next(p for p in result.packages if p.name == "serde")
        assert serde.version == "1.0"
        assert serde.dev is False

        criterion = next(p for p in result.packages if p.name == "criterion")
        assert criterion.dev is True


# ─── 4. go.mod ───────────────────────────────────────────────────────────────


class TestDetectGoMod:
    def test_detect_go_mod(self):
        """go.mod require block parsed correctly."""
        proj = _make_project({
            "go.mod": (
                "module github.com/myorg/myapp\n"
                "\n"
                "go 1.21\n"
                "\n"
                "require (\n"
                "\tgithub.com/gin-gonic/gin v1.9.1\n"
                "\tgithub.com/stretchr/testify v1.8.4\n"
                ")\n"
            ),
        })
        result = detect_manifests(proj)

        assert len(result.manifests) == 1
        assert result.manifests[0].format == "go.mod"

        names = {p.name for p in result.packages}
        assert "github.com/gin-gonic/gin" in names
        assert "github.com/stretchr/testify" in names

        gin = next(p for p in result.packages if p.name == "github.com/gin-gonic/gin")
        assert gin.version == "v1.9.1"


# ─── 5. Gemfile ──────────────────────────────────────────────────────────────


class TestDetectGemfile:
    def test_detect_gemfile(self):
        """Gemfile gem declarations parsed."""
        proj = _make_project({
            "Gemfile": (
                'source "https://rubygems.org"\n'
                "\n"
                'gem "rails", "~> 7.0"\n'
                "gem 'puma', '5.6.5'\n"
                "gem 'bootsnap'\n"
            ),
        })
        result = detect_manifests(proj)

        assert len(result.manifests) == 1
        assert result.manifests[0].format == "Gemfile"

        names = {p.name for p in result.packages}
        assert "rails" in names
        assert "puma" in names
        assert "bootsnap" in names

        rails = next(p for p in result.packages if p.name == "rails")
        assert rails.version == "~> 7.0"

        bootsnap = next(p for p in result.packages if p.name == "bootsnap")
        assert bootsnap.version == ""


# ─── 6. pyproject.toml ───────────────────────────────────────────────────────


class TestDetectPyprojectToml:
    def test_detect_pyproject_toml(self):
        """pyproject.toml with [project.dependencies] parsed."""
        proj = _make_project({
            "pyproject.toml": (
                "[project]\n"
                'name = "mypackage"\n'
                'version = "1.0.0"\n'
                "dependencies = [\n"
                '    "fastapi>=0.100.0",\n'
                '    "pydantic>=2.0",\n'
                "]\n"
                "\n"
                "[project.optional-dependencies]\n"
                "dev = [\n"
                '    "pytest>=7.4.0",\n'
                "]\n"
            ),
        })
        result = detect_manifests(proj)

        assert len(result.manifests) == 1
        assert result.manifests[0].format == "pyproject.toml"

        names = {p.name for p in result.packages}
        assert "fastapi" in names
        assert "pydantic" in names
        assert "pytest" in names

        fastapi = next(p for p in result.packages if p.name == "fastapi")
        assert fastapi.version == ">=0.100.0"
        assert fastapi.dev is False

        pytest_pkg = next(p for p in result.packages if p.name == "pytest")
        assert pytest_pkg.dev is True


# ─── 7. Empty directory ──────────────────────────────────────────────────────


class TestEmptyDir:
    def test_empty_dir_no_crash(self):
        """Empty directory returns empty DependencyList, no crash."""
        proj = tempfile.mkdtemp()
        result = detect_manifests(proj)

        assert isinstance(result, DependencyList)
        assert result.manifests == []
        assert result.packages == []


# ─── 8. Dev dependency classification ────────────────────────────────────────


class TestDevDependencies:
    def test_dev_dependencies_classified(self):
        """devDependencies from package.json and dev-dependencies from Cargo.toml are dev=True."""
        proj = _make_project({
            "package.json": json.dumps({
                "dependencies": {"react": "^18.0.0"},
                "devDependencies": {
                    "typescript": "^5.0.0",
                    "eslint": "^8.0.0",
                },
            }),
            "Cargo.toml": (
                "[dependencies]\n"
                'serde = "1.0"\n'
                "\n"
                "[dev-dependencies]\n"
                'proptest = "1.2"\n'
            ),
        })
        result = detect_manifests(proj)

        # Should detect both manifests
        assert len(result.manifests) == 2

        # Prod deps
        react = next(p for p in result.packages if p.name == "react")
        assert react.dev is False

        serde = next(p for p in result.packages if p.name == "serde")
        assert serde.dev is False

        # Dev deps
        typescript = next(p for p in result.packages if p.name == "typescript")
        assert typescript.dev is True

        eslint = next(p for p in result.packages if p.name == "eslint")
        assert eslint.dev is True

        proptest = next(p for p in result.packages if p.name == "proptest")
        assert proptest.dev is True


# ─── 9. Malformed files ──────────────────────────────────────────────────────


class TestMalformedFiles:
    def test_malformed_package_json_skipped(self):
        """Malformed package.json is skipped gracefully, no crash."""
        proj = _make_project({
            "package.json": "{ this is not valid JSON",
            "requirements.txt": "flask==2.3.0\n",
        })
        result = detect_manifests(proj)

        # requirements.txt still parsed
        assert any(m.format == "requirements.txt" for m in result.manifests)
        assert any(p.name == "flask" for p in result.packages)


# ─── 10. source_manifest tracking ────────────────────────────────────────────


class TestSourceManifest:
    def test_source_manifest_tracked(self):
        """Each package records which manifest file it came from."""
        proj = _make_project({
            "package.json": json.dumps({
                "dependencies": {"express": "^4.18.0"},
            }),
            "requirements.txt": "flask==2.3.0\n",
        })
        result = detect_manifests(proj)

        express = next(p for p in result.packages if p.name == "express")
        assert "package.json" in express.source_manifest

        flask = next(p for p in result.packages if p.name == "flask")
        assert "requirements.txt" in flask.source_manifest
