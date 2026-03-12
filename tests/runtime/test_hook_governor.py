"""Tests for runtime hook governor and feature registry."""
from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime.feature_registry import DEFAULT_FEATURE_REGISTRY_PATH, load_registry
from runtime.hook_governor import get_canonical_order, validate_order

# Use absolute project root so tests are not affected by cwd changes from other tests
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)


def test_canonical_order_loads_from_bundle():
    order = get_canonical_order("PreToolUse", project_dir=_PROJECT_ROOT)
    assert order[:3] == ["firewall", "secret-guard", "pre-tool-inject"]
    assert "tdd-gate" not in order


def test_validate_order_accepts_valid_sequence():
    result = validate_order("PreToolUse", ["firewall", "secret-guard", "pre-tool-inject"], project_dir=_PROJECT_ROOT)
    assert result == {"status": "ok", "blockers": []}


def test_validate_order_blocks_missing_required_security_hook():
    result = validate_order("PreToolUse", ["secret-guard", "pre-tool-inject"], project_dir=_PROJECT_ROOT)
    assert result["status"] == "blocked"
    assert "missing required security hook: firewall" in result["blockers"]


def test_validate_order_detects_out_of_order_hooks():
    result = validate_order("PreToolUse", ["secret-guard", "firewall", "pre-tool-inject"], project_dir=_PROJECT_ROOT)
    assert result["status"] == "blocked"
    assert any("hook order violation" in blocker for blocker in result["blockers"])


def test_validate_order_gracefully_handles_missing_bundle(tmp_path: Path):
    missing_bundle = tmp_path / "registry" / "bundles" / "hook-governor.yaml"
    result = validate_order("PreToolUse", ["firewall", "secret-guard"], bundle_path=str(missing_bundle))
    assert result["status"] == "blocked"
    assert any("canonical hook bundle missing" in blocker for blocker in result["blockers"])


def test_feature_registry_loads_expected_keys(tmp_path: Path):
    registry = load_registry(str(tmp_path))
    expected = {
        "TDD_ENFORCEMENT",
        "HOOK_GOVERNOR",
        "DEFENSE_STATE",
        "VERIFICATION_CONTROLLER",
        "INTERACTION_JOURNAL",
    }
    assert expected.issubset(registry.keys())

    path = tmp_path / DEFAULT_FEATURE_REGISTRY_PATH
    assert path.exists()
    raw_payload: object = cast(object, json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(raw_payload, dict)
    persisted = cast(dict[object, object], raw_payload)
    assert expected.issubset(persisted.keys())


def test_validate_order_ok_with_foreign_hook():
    result = validate_order("PreToolUse", ["firewall", "secret-guard", "plugin-hook"], project_dir=_PROJECT_ROOT)

    assert result["status"] == "ok"
    assert result["blockers"] == []


def test_validate_order_blocked_foreign_before_firewall():
    result = validate_order("PreToolUse", ["plugin-hook", "firewall", "secret-guard"], project_dir=_PROJECT_ROOT)

    assert result["status"] == "blocked"
    assert any("hook order violation" in blocker for blocker in result["blockers"])


def test_hook_inventory_fully_classified():
    """Verify all hook files are either registered or in the internal helper allowlist."""
    import json
    from pathlib import Path

    # Load registered hooks from settings.json
    settings_path = Path(_PROJECT_ROOT) / "settings.json"
    with open(settings_path, encoding="utf-8") as f:
        settings = json.load(f)

    # Extract all registered hook filenames from the hooks section
    registered_hooks = set()
    hooks_section = settings.get("hooks", {})
    for event_type, event_hooks in hooks_section.items():
        if isinstance(event_hooks, list):
            for hook_entry in event_hooks:
                if isinstance(hook_entry, dict) and "hooks" in hook_entry:
                    for hook_def in hook_entry["hooks"]:
                        if isinstance(hook_def, dict) and "command" in hook_def:
                            cmd = hook_def["command"]
                            # Extract filename from commands like:
                            # "$HOME/.claude/omg-runtime/.venv/bin/python" "$HOME/.claude/hooks/firewall.py"
                            if "hooks/" in cmd:
                                filename = cmd.split("hooks/")[-1].split('"')[0]
                                registered_hooks.add(filename)

    # Define internal helper allowlist (files that are not executable hooks)
    # These are utility modules, configuration helpers, and internal support files
    internal_helpers = {
        "__init__.py",  # Package marker
        "_agent_registry.py",  # Internal registry helper
        "_analytics.py",  # Internal analytics support
        "_budget.py",  # Internal budget utilities
        "_common.py",  # Common utilities
        "_compression_optimizer.py",  # Internal compression support
        "_cost_ledger.py",  # Internal cost tracking
        "_learnings.py",  # Internal learnings support
        "_memory.py",  # Internal memory utilities
        "_protected_context.py",  # Internal context protection
        "_token_counter.py",  # Internal token counting
        # Dormant/unregistered hook modules (legitimate but not in settings.json)
        "branch_manager.py",
        "compression_feedback.py",
        "config-guard.py",
        "context_pressure.py",
        "credential_store.py",
        "fetch-rate-limits.py",
        "hashline-formatter-bridge.py",
        "hashline-injector.py",
        "hashline-validator.py",
        "idle-detector.py",
        "intentgate-keyword-detector.py",
        "magic-keyword-router.py",
        "policy_engine.py",
        "post-write.py",
        "post_write.py",
        "pre-compact.py",
        "prompt-enhancer.py",
        "quality-runner.py",
        "query.py",
        "secret_audit.py",
        "security_validators.py",
        "setup_wizard.py",
        "shadow_manager.py",
        "state_migration.py",
        "stop-gate.py",
        "tdd-gate.py",
        "test-validator.py",
        "todo-state-tracker.py",
        "trust_review.py",
    }

    # Get all Python files in hooks directory
    hooks_dir = Path(_PROJECT_ROOT) / "hooks"
    all_hook_files = {f.name for f in hooks_dir.glob("*.py")}

    # Verify each file is classified
    unclassified = all_hook_files - registered_hooks - internal_helpers
    assert (
        not unclassified
    ), f"Unclassified hook files found (not registered and not in allowlist): {sorted(unclassified)}"


def test_hook_inventory_catches_unclassified():
    """Verify that adding an unclassified hook file would be caught."""
    import json
    import tempfile
    from pathlib import Path

    # Create a temporary hooks directory with a test unclassified file
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_hooks = Path(tmpdir) / "hooks"
        tmp_hooks.mkdir()

        # Create a dummy unclassified hook file
        unclassified_hook = tmp_hooks / "unclassified_hook.py"
        unclassified_hook.write_text("# This is an unclassified hook\n")

        # Create a minimal settings.json without this hook
        settings_path = Path(tmpdir) / "settings.json"
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": '"$HOME/.claude/omg-runtime/.venv/bin/python" "$HOME/.claude/hooks/firewall.py"',
                            }
                        ]
                    }
                ]
            }
        }
        settings_path.write_text(json.dumps(settings))

        # Load registered hooks from the test settings
        with open(settings_path, encoding="utf-8") as f:
            test_settings = json.load(f)

        registered_hooks = set()
        hooks_section = test_settings.get("hooks", {})
        for event_type, event_hooks in hooks_section.items():
            if isinstance(event_hooks, list):
                for hook_entry in event_hooks:
                    if isinstance(hook_entry, dict) and "hooks" in hook_entry:
                        for hook_def in hook_entry["hooks"]:
                            if isinstance(hook_def, dict) and "command" in hook_def:
                                cmd = hook_def["command"]
                                if "hooks/" in cmd:
                                    filename = cmd.split("hooks/")[-1].split('"')[0]
                                    registered_hooks.add(filename)

        internal_helpers = {
            "__init__.py",
            "_agent_registry.py",
            "_analytics.py",
            "_budget.py",
            "_common.py",
            "_compression_optimizer.py",
            "_cost_ledger.py",
            "_learnings.py",
            "_memory.py",
            "_protected_context.py",
            "_token_counter.py",
        }

        # Get all Python files in the test hooks directory
        all_hook_files = {f.name for f in tmp_hooks.glob("*.py")}

        # Verify that unclassified_hook.py is caught
        unclassified = all_hook_files - registered_hooks - internal_helpers
        assert (
            "unclassified_hook.py" in unclassified
        ), "Test should catch unclassified hook file"
