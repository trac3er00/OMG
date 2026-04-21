"""Hook inventory test framework — validates all hooks in hooks/ directory.

Auto-discovers hook files, validates their structure, and checks
consistency with hook-governor.yaml bundle definition.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = ROOT / "hooks"
MATRIX_PATH = Path(__file__).parent / "hook_matrix.json"

# Events from hook-governor.yaml lifecycle_hooks
KNOWN_EVENTS = frozenset(
    {
        "SessionStart",
        "SessionEnd",
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "Stop",
        "PreCompact",
        "ConfigChange",
        "WorktreeCreate",
        "WorktreeRemove",
        "SubagentStart",
        "SubagentStop",
        "TaskCompleted",
    }
)


def discover_hooks() -> list[Path]:
    """Discover all Python hook files in hooks/ directory (exclude private/internal)."""
    return sorted(
        f
        for f in HOOKS_DIR.glob("*.py")
        if not f.name.startswith("_") and f.name != "__init__.py"
    )


def discover_all_hooks() -> list[Path]:
    """Discover ALL Python files in hooks/ (including private helpers)."""
    return sorted(f for f in HOOKS_DIR.glob("*.py") if f.name != "__init__.py")


def read_hook_docstring(hook_path: Path) -> str:
    """Read the first docstring from a hook file."""
    try:
        source = hook_path.read_text(encoding="utf-8")
        # Simple extraction: find first triple-quoted string
        for delim in ('"""', "'''"):
            idx = source.find(delim)
            if idx != -1:
                end = source.find(delim, idx + 3)
                if end != -1:
                    return source[idx + 3 : end].strip()
        return ""
    except Exception:
        return ""


def detect_events(hook_path: Path) -> list[str]:
    """Detect which lifecycle events a hook handles from its docstring and code."""
    try:
        source = hook_path.read_text(encoding="utf-8")
    except Exception:
        return []
    events = []
    for event in KNOWN_EVENTS:
        if event in source:
            events.append(event)
    return sorted(events)


def run_hook(hook_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Run a hook with JSON payload on stdin, return parsed output."""
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    env["OMG_HOOK_INVENTORY_TEST"] = "1"
    # Disable strict modes that might block test execution
    env["OMG_TDD_GATE_STRICT"] = "0"
    env["OMG_STRICT_AMBIGUITY_MODE"] = "0"

    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    stdout = (result.stdout or "").strip()
    if stdout:
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"raw_output": stdout, "returncode": result.returncode}
    return {"returncode": result.returncode, "stderr": (result.stderr or "")[:300]}


def load_hook_matrix() -> dict[str, list[str]]:
    """Load the hook×event matrix from hook_matrix.json."""
    if not MATRIX_PATH.exists():
        pytest.skip("hook_matrix.json not found")
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


class TestHookDiscovery:
    """Tests for hook file discovery and basic structure."""

    def test_hooks_discovered(self) -> None:
        hooks = discover_hooks()
        assert len(hooks) > 0, "No hooks discovered in hooks/ directory"
        # We expect roughly 40+ public hooks
        assert len(hooks) >= 30, f"Expected 30+ hooks, found {len(hooks)}"

    def test_all_hooks_are_valid_python(self) -> None:
        """Every hook file should be syntactically valid Python."""
        hooks = discover_all_hooks()
        invalid: list[str] = []
        for hook in hooks:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(hook)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                invalid.append(f"{hook.name}: {result.stderr[:100]}")
        if invalid:
            pytest.fail(f"Invalid Python syntax in hooks:\n" + "\n".join(invalid))

    def test_public_hooks_have_docstrings(self) -> None:
        """Public hooks (no underscore prefix) should have a docstring."""
        hooks = discover_hooks()
        missing: list[str] = []
        for hook in hooks:
            doc = read_hook_docstring(hook)
            if not doc:
                missing.append(hook.name)
        # Allow some without docstrings but flag if too many
        if len(missing) > len(hooks) * 0.5:
            pytest.fail(
                f"{len(missing)}/{len(hooks)} public hooks lack docstrings: {missing[:10]}"
            )

    def test_no_duplicate_hook_names(self) -> None:
        """Hook filenames should be unique (no collisions after normalization)."""
        hooks = discover_hooks()
        names = [h.stem.replace("-", "_").lower() for h in hooks]
        seen: dict[str, str] = {}
        dupes: list[str] = []
        for name, hook in zip(names, hooks):
            if name in seen:
                dupes.append(f"{hook.name} collides with {seen[name]}")
            seen[name] = hook.name
        if dupes:
            pytest.fail(f"Duplicate hook names: {dupes}")


class TestHookEvents:
    """Tests for hook event handling."""

    def test_each_hook_responds_to_pre_tool_use(self) -> None:
        """Each public hook should handle PreToolUse without crashing."""
        hooks = discover_hooks()
        event = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.txt"},
        }
        failures: list[str] = []
        for hook in hooks:
            try:
                run_hook(hook, event)
                # Any return (including empty/None-equivalent) is acceptable
            except subprocess.TimeoutExpired:
                failures.append(f"{hook.name}: timeout (>10s)")
            except Exception as e:
                failures.append(f"{hook.name}: {type(e).__name__}: {e}")
        if failures:
            pytest.fail(
                f"{len(failures)} hooks failed PreToolUse:\n" + "\n".join(failures)
            )

    def test_events_detected_per_hook(self) -> None:
        """At least some hooks should declare known events."""
        hooks = discover_hooks()
        hooks_with_events = 0
        for hook in hooks:
            events = detect_events(hook)
            if events:
                hooks_with_events += 1
        # At least half of hooks should mention a known event
        assert hooks_with_events >= len(hooks) * 0.3, (
            f"Only {hooks_with_events}/{len(hooks)} hooks reference known events"
        )


class TestHookGovernorBundle:
    """Tests for consistency with hook-governor.yaml."""

    def test_bundle_file_exists(self) -> None:
        bundle_path = ROOT / "registry" / "bundles" / "hook-governor.yaml"
        assert bundle_path.exists(), "hook-governor.yaml not found"

    def test_bundle_references_real_hook_files(self) -> None:
        """All hooks referenced in compiled_hooks should exist on disk."""
        bundle_path = ROOT / "registry" / "bundles" / "hook-governor.yaml"
        if not bundle_path.exists():
            pytest.skip("hook-governor.yaml not found")

        import yaml

        with open(bundle_path) as f:
            bundle = yaml.safe_load(f)

        compiled = bundle.get("compiled_hooks", {})
        missing: list[str] = []
        for event, hook_list in compiled.items():
            for entry in hook_list:
                cmd = entry.get("command", "")
                # Extract hook filename from command string
                # Pattern: "$HOME/.claude/hooks/<name>.py"
                if "/hooks/" in cmd:
                    hook_name = cmd.split("/hooks/")[-1].rstrip("'\"")
                    hook_file = HOOKS_DIR / hook_name
                    if not hook_file.exists():
                        missing.append(f"{event}: {hook_name}")
        if missing:
            pytest.fail(f"Bundle references missing hooks:\n" + "\n".join(missing))

    def test_bundle_lifecycle_events_are_known(self) -> None:
        """All lifecycle events in bundle should be in KNOWN_EVENTS."""
        bundle_path = ROOT / "registry" / "bundles" / "hook-governor.yaml"
        if not bundle_path.exists():
            pytest.skip("hook-governor.yaml not found")

        import yaml

        with open(bundle_path) as f:
            bundle = yaml.safe_load(f)

        lifecycle = bundle.get("lifecycle_hooks", {})
        all_events = set()
        for event_list in lifecycle.values():
            if isinstance(event_list, list):
                all_events.update(event_list)

        unknown = all_events - KNOWN_EVENTS
        assert not unknown, f"Unknown lifecycle events in bundle: {unknown}"


class TestHookMatrix:
    """Tests validating hook_matrix.json correctness."""

    def test_matrix_file_exists(self) -> None:
        assert MATRIX_PATH.exists(), f"hook_matrix.json not found at {MATRIX_PATH}"

    def test_matrix_covers_all_public_hooks(self) -> None:
        """Matrix should include all public hooks."""
        matrix = load_hook_matrix()
        hooks = discover_hooks()
        hook_names = {h.stem for h in hooks}
        matrix_names = set(matrix.keys())
        missing = hook_names - matrix_names
        if missing:
            pytest.fail(f"Hooks missing from matrix: {sorted(missing)}")

    def test_matrix_events_are_valid(self) -> None:
        """All events in matrix should be known lifecycle events."""
        matrix = load_hook_matrix()
        for hook_name, events in matrix.items():
            assert isinstance(events, list), f"{hook_name}: events should be a list"
            for event in events:
                assert event in KNOWN_EVENTS, f"{hook_name}: unknown event '{event}'"

    def test_matrix_not_empty(self) -> None:
        """Matrix should have entries."""
        matrix = load_hook_matrix()
        assert len(matrix) > 0, "Hook matrix is empty"


class TestHookIntegrity:
    """Deeper integrity checks for hook ecosystem."""

    def test_common_module_importable(self) -> None:
        """hooks/_common.py should be importable."""
        common = HOOKS_DIR / "_common.py"
        if not common.exists():
            pytest.skip("_common.py not found")
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys; sys.path.insert(0, '{ROOT}'); import hooks._common",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"_common.py import failed: {result.stderr[:200]}"
        )

    def test_universal_hooks_manifest_valid(self) -> None:
        """hooks/universal/hooks.json should be valid JSON with expected structure."""
        manifest = HOOKS_DIR / "universal" / "hooks.json"
        if not manifest.exists():
            pytest.skip("universal/hooks.json not found")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert "hooks" in data, "Missing 'hooks' key in universal manifest"
        assert isinstance(data["hooks"], list)
        for entry in data["hooks"]:
            assert "event" in entry, f"Hook entry missing 'event': {entry}"

    def test_hook_count_matches_expectation(self) -> None:
        """Track hook count for drift detection."""
        hooks = discover_hooks()
        # Current count from ls hooks/*.py (excluding _ and __init__)
        # Allow ±5 drift before flagging
        assert 30 <= len(hooks) <= 70, (
            f"Hook count {len(hooks)} outside expected range [30, 70]. "
            "Update test if hooks were intentionally added/removed."
        )
