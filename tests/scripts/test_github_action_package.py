"""Tests for the official OMG GitHub Action composite package (action.yml)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ACTION_PATH = ROOT / "action.yml"


@pytest.fixture(scope="module")
def action_data() -> dict:
    assert ACTION_PATH.exists(), f"action.yml not found at {ACTION_PATH}"
    return yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))


# ── 1. action.yml exists ─────────────────────────────────────────────
def test_action_yml_exists():
    assert ACTION_PATH.exists(), "action.yml must exist at repository root"


# ── 2. All 6 required inputs are present ─────────────────────────────
REQUIRED_INPUTS = {
    "repo-full-name",
    "pr-number",
    "head-sha",
    "github-app-id",
    "github-app-installation-id",
    "github-app-private-key",
}


def test_action_has_all_required_inputs(action_data: dict):
    inputs = action_data.get("inputs", {})
    assert isinstance(inputs, dict)
    missing = REQUIRED_INPUTS - set(inputs.keys())
    assert not missing, f"Missing required inputs: {missing}"
    for name in REQUIRED_INPUTS:
        assert inputs[name].get("required") is True, f"Input '{name}' must be required"


# ── 3. Composite action ──────────────────────────────────────────────
def test_action_uses_composite(action_data: dict):
    runs = action_data.get("runs", {})
    assert runs.get("using") == "composite", "runs.using must be 'composite'"


# ── 4. Check-run name matches stable contract ────────────────────────
def test_check_run_name_matches_contract(action_data: dict):
    expected = "OMG PR Reviewer"

    assert action_data.get("name") == expected, (
        f"action.yml name must be '{expected}', got '{action_data.get('name')}'"
    )

    bot_path = ROOT / "runtime" / "github_review_bot.py"
    assert bot_path.exists(), "runtime/github_review_bot.py must exist"
    bot_src = bot_path.read_text(encoding="utf-8")
    assert f'CHECK_RUN_NAME = "{expected}"' in bot_src, (
        f"runtime/github_review_bot.py must define CHECK_RUN_NAME = \"{expected}\""
    )


# ── 5. Post-review step includes required CLI args ───────────────────
def test_post_review_step_has_required_args():
    raw = ACTION_PATH.read_text(encoding="utf-8")
    assert "post-review" in raw, "action.yml must contain post-review command"
    assert "--event-path" in raw, "post-review must include --event-path"
    assert "--input" in raw, "post-review must include --input"
    assert "--output" in raw, "post-review must include --output"
    assert "artifacts/reviewer-bot-pr-event.json" in raw
    assert "artifacts/reviewer-bot-pr-input.json" in raw
    assert "artifacts/reviewer-bot-pr-output.json" in raw


# ── 6. Action name is the stable check-run contract ──────────────────
def test_action_name_is_stable_contract(action_data: dict):
    assert action_data.get("name") == "OMG PR Reviewer", (
        "Action name must be 'OMG PR Reviewer' (stable check-run contract)"
    )
