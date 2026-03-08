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
    assert order[:4] == ["firewall", "secret-guard", "tdd-gate", "pre-tool-inject"]


def test_validate_order_accepts_valid_sequence():
    result = validate_order("PreToolUse", ["firewall", "secret-guard", "tdd-gate", "pre-tool-inject"], project_dir=_PROJECT_ROOT)
    assert result == {"status": "ok", "blockers": []}


def test_validate_order_blocks_missing_required_security_hook():
    result = validate_order("PreToolUse", ["secret-guard", "tdd-gate", "pre-tool-inject"], project_dir=_PROJECT_ROOT)
    assert result["status"] == "blocked"
    assert "missing required security hook: firewall" in result["blockers"]


def test_validate_order_detects_out_of_order_hooks():
    result = validate_order("PreToolUse", ["secret-guard", "firewall", "tdd-gate", "pre-tool-inject"], project_dir=_PROJECT_ROOT)
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
