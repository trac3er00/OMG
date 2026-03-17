"""Tests for entropy-based secret detection in post-write hook."""

from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import tempfile
from typing import Callable, cast

from tests.hooks.helpers import ROOT


def _detect_high_entropy_strings(text: str) -> list[str]:
    module_path = ROOT / "hooks" / "_post_write.py"
    spec = importlib.util.spec_from_file_location("omg_post_write", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load hooks/_post_write.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    detect = cast(Callable[[str], list[str]], module.detect_high_entropy_strings)
    return detect(text)


def _run_post_write(file_path: str, project_dir: str, file_content: str = "") -> subprocess.CompletedProcess[str]:
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": file_path},
        "tool_response": {"success": True},
    }
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = project_dir

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        _ = f.write(file_content)

    return subprocess.run(
        ["python3", str(ROOT / "hooks" / "post-write.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=project_dir,
        env=env,
        check=False,
    )


def test_detects_high_entropy_long_string():
    text = 'const key = "sk-proj-xK9mN2pQ8rT5vW3yZ1aB4cD7eF0gH6iJ"'
    results = _detect_high_entropy_strings(text)

    assert len(results) == 1


def test_skips_low_entropy_string_even_when_long():
    text = 'const key = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"'
    results = _detect_high_entropy_strings(text)

    assert results == []


def test_skips_short_high_entropy_string():
    text = 'token = "A1b2C3d4E5f6G7h8I9j0"'
    results = _detect_high_entropy_strings(text)

    assert results == []


def test_skips_uuid_allowlist():
    text = "550e8400-e29b-41d4-a716-446655440000"
    results = _detect_high_entropy_strings(text)

    assert results == []


def test_skips_hex_hash_allowlist():
    text = "9f86d081884c7d659a2feaa0c55ad015"
    results = _detect_high_entropy_strings(text)

    assert results == []


def test_skips_base64_image_data_allowlist():
    text = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9h"
    results = _detect_high_entropy_strings(text)

    assert results == []


def test_reports_multiple_entropy_findings_in_text():
    text = "\n".join(
        [
            'token1 = "sk-proj-xK9mN2pQ8rT5vW3yZ1aB4cD7eF0gH6iJ"',
            'token2 = "ghp_u7Qw1Er5Ty8Ui2Op4As6Df9Gh3Jk1LmN"',
        ]
    )
    results = _detect_high_entropy_strings(text)

    assert len(results) >= 2


def test_hook_warns_for_entropy_secret_in_non_test_file():
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "src", "secrets.py")
        proc = _run_post_write(
            target,
            tmp,
            'API_KEY = "sk-proj-xK9mN2pQ8rT5vW3yZ1aB4cD7eF0gH6iJ"\n',
        )

        assert proc.returncode == 0
        assert "SECRET DETECTED" in proc.stderr


def test_hook_skips_entropy_check_for_test_paths():
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "tests", "secret_fixture.py")
        proc = _run_post_write(
            target,
            tmp,
            'TOKEN = "sk-proj-xK9mN2pQ8rT5vW3yZ1aB4cD7eF0gH6iJ"\n',
        )

        assert proc.returncode == 0
        assert "SECRET DETECTED" not in proc.stderr


def test_false_positive_rate_below_five_percent_on_sample_test_strings():
    benign_samples = [
        "550e8400-e29b-41d4-a716-446655440000",
        "9f86d081884c7d659a2feaa0c55ad015",
        "3f786850e387550fdab836ed7e6dc881de23001b",
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9h",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "cccccccccccccccccccccccccccccc",
        "feature_flag_new_dashboard_enabled",
        "test_user_fixture_identifier_value",
        "example_token_for_tests_only_123",
        "config_value_in_fixture_file_abc",
        "mock_signature_for_unit_tests_xyz",
        "integration_test_case_reference_01",
        "integration_test_case_reference_02",
        "integration_test_case_reference_03",
        "fixture_payload_for_endpoint_alpha",
        "fixture_payload_for_endpoint_beta",
        "fixture_payload_for_endpoint_gamma",
        "snapshot_reference_for_spec_suite",
        "local_dev_placeholder_secret_key",
    ]

    flagged = sum(1 for sample in benign_samples if _detect_high_entropy_strings(sample))
    false_positive_rate = flagged / len(benign_samples)

    assert false_positive_rate < 0.05
