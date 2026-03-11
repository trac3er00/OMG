"""
Framework Detector — detect test frameworks from project configuration files.

Scans a project directory for known config files (package.json, pyproject.toml,
setup.cfg, Cargo.toml, go.mod, Gemfile) and returns a FrameworkInfo dataclass
describing the detected framework(s).

Feature flag: TEST_GENERATION (default False) — detection works regardless.
Stdlib only: json, pathlib, re, dataclasses.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FrameworkInfo:
    """Describes a detected test framework and its conventions."""

    framework: str = "unknown"
    config_file: str = ""
    test_dir: str = ""
    assertion_style: str = ""
    mock_library: str = ""
    multi_framework: list[str] = field(default_factory=list)


# --- JS/TS framework metadata ---

_JS_FRAMEWORKS = {
    "vitest": {
        "framework": "vitest",
        "assertion_style": "expect",
        "mock_library": "vi.mock",
        "test_dir": "__tests__",
    },
    "jest": {
        "framework": "jest",
        "assertion_style": "expect",
        "mock_library": "jest.mock",
        "test_dir": "__tests__",
    },
    "mocha": {
        "framework": "mocha",
        "assertion_style": "assert",
        "mock_library": "sinon",
        "test_dir": "test",
    },
    "@playwright/test": {
        "framework": "playwright",
        "assertion_style": "expect",
        "mock_library": "",
        "test_dir": "tests",
    },
}

# Detection priority: vitest > jest > mocha (vitest first because projects
# migrating from jest often keep jest in devDeps alongside vitest)
_JS_PRIORITY = ["vitest", "jest", "mocha", "@playwright/test"]


def _detect_from_package_json(project_dir: str) -> FrameworkInfo | None:
    """Detect JS/TS framework from package.json devDependencies and scripts."""
    pkg_path = Path(project_dir) / "package.json"
    if not pkg_path.is_file():
        return None

    try:
        with open(pkg_path, "r", encoding="utf-8") as f:
            pkg = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    dev_deps = pkg.get("devDependencies", {})
    deps = pkg.get("dependencies", {})
    scripts = pkg.get("scripts", {})
    all_deps = {**deps, **dev_deps}

    # Also check scripts for framework names
    scripts_text = " ".join(str(v) for v in scripts.values())

    detected = []
    for fw_key in _JS_PRIORITY:
        if fw_key in all_deps:
            detected.append(fw_key)
        elif fw_key.lstrip("@").split("/")[-1] in scripts_text:
            detected.append(fw_key)

    if not detected:
        return None

    primary_key = detected[0]
    meta = _JS_FRAMEWORKS[primary_key]

    multi = []
    if len(detected) > 1:
        multi = [_JS_FRAMEWORKS[k]["framework"] for k in detected]

    return FrameworkInfo(
        framework=meta["framework"],
        config_file="package.json",
        test_dir=meta["test_dir"],
        assertion_style=meta["assertion_style"],
        mock_library=meta["mock_library"],
        multi_framework=multi,
    )


def _detect_from_pyproject_toml(project_dir: str) -> FrameworkInfo | None:
    """Detect pytest from pyproject.toml [tool.pytest.*] section."""
    path = Path(project_dir) / "pyproject.toml"
    if not path.is_file():
        return None

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    if re.search(r"\[tool\.pytest", content):
        # Try to extract testpaths
        test_dir = "tests"
        m = re.search(r'testpaths\s*=\s*\["?([^"\]\s]+)', content)
        if m:
            test_dir = m.group(1)

        return FrameworkInfo(
            framework="pytest",
            config_file="pyproject.toml",
            test_dir=test_dir,
            assertion_style="assert",
            mock_library="unittest.mock",
            multi_framework=[],
        )

    # Check for pytest in dependencies
    if re.search(r"pytest", content):
        return FrameworkInfo(
            framework="pytest",
            config_file="pyproject.toml",
            test_dir="tests",
            assertion_style="assert",
            mock_library="unittest.mock",
            multi_framework=[],
        )

    return None


def _detect_from_setup_cfg(project_dir: str) -> FrameworkInfo | None:
    """Detect pytest from setup.cfg [tool:pytest] section."""
    path = Path(project_dir) / "setup.cfg"
    if not path.is_file():
        return None

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    if re.search(r"\[tool:pytest\]", content):
        test_dir = "tests"
        m = re.search(r"testpaths\s*=\s*(\S+)", content)
        if m:
            test_dir = m.group(1)

        return FrameworkInfo(
            framework="pytest",
            config_file="setup.cfg",
            test_dir=test_dir,
            assertion_style="assert",
            mock_library="unittest.mock",
            multi_framework=[],
        )

    return None


def _detect_from_go_mod(project_dir: str) -> FrameworkInfo | None:
    """Detect Go test from go.mod presence."""
    path = Path(project_dir) / "go.mod"
    if not path.is_file():
        return None

    return FrameworkInfo(
        framework="go test",
        config_file="go.mod",
        test_dir=".",
        assertion_style="testing.T",
        mock_library="testify/mock",
        multi_framework=[],
    )


def _detect_from_cargo_toml(project_dir: str) -> FrameworkInfo | None:
    """Detect Rust/cargo test from Cargo.toml presence."""
    path = Path(project_dir) / "Cargo.toml"
    if not path.is_file():
        return None

    return FrameworkInfo(
        framework="cargo test",
        config_file="Cargo.toml",
        test_dir="tests",
        assertion_style="assert!",
        mock_library="mockall",
        multi_framework=[],
    )


def _detect_from_gemfile(project_dir: str) -> FrameworkInfo | None:
    """Detect RSpec from Gemfile containing 'rspec'."""
    path = Path(project_dir) / "Gemfile"
    if not path.is_file():
        return None

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    if re.search(r"['\"]rspec['\"]", content):
        return FrameworkInfo(
            framework="rspec",
            config_file="Gemfile",
            test_dir="spec",
            assertion_style="expect",
            mock_library="rspec-mocks",
            multi_framework=[],
        )

    return None


# Ordered detector chain — first match wins (except multi-framework from JS)
_DETECTORS = [
    _detect_from_package_json,
    _detect_from_pyproject_toml,
    _detect_from_setup_cfg,
    _detect_from_go_mod,
    _detect_from_cargo_toml,
    _detect_from_gemfile,
]


def detect_test_framework(project_dir: str) -> FrameworkInfo:
    """Detect test framework(s) in a project directory.

    Scans known config files in priority order. Returns FrameworkInfo with
    framework='unknown' if nothing detected (never crashes).

    Feature flag TEST_GENERATION gates downstream generation — detection
    itself always works.

    Args:
        project_dir: Absolute or relative path to the project root.

    Returns:
        FrameworkInfo dataclass with detected framework metadata.
    """
    try:
        for detector in _DETECTORS:
            result = detector(project_dir)
            if result is not None:
                return result
    except Exception:
        # Crash isolation: return unknown on any unexpected error
        pass

    return FrameworkInfo()
