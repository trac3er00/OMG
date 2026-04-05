from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.hooks.helpers import get_decision, make_file_payload, run_hook_json


def _decision(output: object) -> str | None:
    if not isinstance(output, dict):
        return None
    return get_decision(output)


def _reason(output: dict[str, object] | None) -> str:
    if output is None:
        return ""
    hook = output.get("hookSpecificOutput")
    if not isinstance(hook, dict):
        return ""
    return str(hook.get("permissionDecisionReason", ""))


def _set_untrusted_mode(project_dir: Path, *, active: bool = True) -> None:
    path = project_dir / ".omg" / "state" / "untrusted-content.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"active": active, "provenance": []}), encoding="utf-8")


def test_secret_guard_ignores_non_file_tool() -> None:
    out = run_hook_json(
        "hooks/secret-guard.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}}
    )
    assert out is None


def test_secret_guard_ignores_missing_file_path() -> None:
    out = run_hook_json(
        "hooks/secret-guard.py", {"tool_name": "Read", "tool_input": {}}
    )
    assert out is None


def test_secret_guard_detects_env_file_read() -> None:
    out = run_hook_json(
        "hooks/secret-guard.py", make_file_payload("Read", "/project/.env")
    )
    assert _decision(out) == "deny"
    assert "direct .env read blocked" in _reason(out).lower()


def test_secret_guard_blocks_env_write() -> None:
    out = run_hook_json(
        "hooks/secret-guard.py",
        make_file_payload("Write", "/project/.env"),
        env_overrides={"OMG_TDD_GATE_STRICT": "0"},
    )
    assert _decision(out) == "deny"
    assert "secret file write blocked" in _reason(out).lower()


def test_secret_guard_blocks_sensitive_dotfile_access() -> None:
    out = run_hook_json(
        "hooks/secret-guard.py", make_file_payload("Read", "/project/.npmrc")
    )
    assert _decision(out) == "deny"
    assert "secret file blocked" in _reason(out).lower()


def test_secret_guard_blocks_sensitive_path_pattern() -> None:
    out = run_hook_json(
        "hooks/secret-guard.py", make_file_payload("Read", "/home/user/.ssh/id_ed25519")
    )
    assert _decision(out) == "deny"
    assert "sensitive path blocked" in _reason(out).lower()


def test_secret_guard_allows_normal_read() -> None:
    out = run_hook_json(
        "hooks/secret-guard.py", make_file_payload("Read", "/project/src/app.py")
    )
    assert _decision(out) is None


def test_secret_guard_allows_normal_write_when_gate_permissive(tmp_path: Path) -> None:
    out = run_hook_json(
        "hooks/secret-guard.py",
        make_file_payload("Write", str(tmp_path / "notes.txt")),
        env_overrides={"CLAUDE_PROJECT_DIR": str(tmp_path), "OMG_TDD_GATE_STRICT": "0"},
    )
    assert _decision(out) is None


def test_secret_guard_blocks_write_without_lock_when_gate_strict(
    tmp_path: Path,
) -> None:
    payload = make_file_payload("Write", str(tmp_path / "src" / "unsafe.txt"))
    out = run_hook_json(
        "hooks/secret-guard.py",
        payload,
        env_overrides={
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "OMG_TDD_GATE_STRICT": "1",
            "OMG_RUN_ID": "run-sg-block",
        },
    )

    assert _decision(out) == "deny"
    assert "mutation_context_required" in _reason(out)
    block_artifact = tmp_path / ".omg" / "state" / "last-block-explanation.json"
    assert block_artifact.exists()
    data = json.loads(block_artifact.read_text(encoding="utf-8"))
    assert data.get("tool") == "Write"


def test_secret_guard_uses_metadata_lock_id_for_gate_context(tmp_path: Path) -> None:
    payload = make_file_payload("Write", str(tmp_path / "allowed.txt"))
    assert isinstance(payload, dict)
    tool_input = payload.get("tool_input")
    assert isinstance(tool_input, dict)
    tool_input_any: Any = tool_input
    tool_input_any["metadata"] = {"lock_id": "lock-from-metadata"}
    out = run_hook_json(
        "hooks/secret-guard.py",
        payload,
        env_overrides={
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "OMG_TDD_GATE_STRICT": "0",
            "OMG_RUN_ID": "run-meta-lock",
        },
    )
    assert _decision(out) is None


def test_secret_guard_respects_direct_lock_id_over_metadata(tmp_path: Path) -> None:
    payload = make_file_payload("Write", str(tmp_path / "preferred-lock.txt"))
    assert isinstance(payload, dict)
    tool_input = payload.get("tool_input")
    assert isinstance(tool_input, dict)
    tool_input_any: Any = tool_input
    tool_input_any["lock_id"] = "explicit-lock"
    tool_input_any["metadata"] = {"lock_id": "metadata-lock"}
    out = run_hook_json(
        "hooks/secret-guard.py",
        payload,
        env_overrides={
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "OMG_TDD_GATE_STRICT": "0",
            "OMG_RUN_ID": "run-lock-priority",
        },
    )
    assert _decision(out) is None


def test_secret_guard_asks_on_untrusted_mode_for_write(tmp_path: Path) -> None:
    _set_untrusted_mode(tmp_path, active=True)
    out = run_hook_json(
        "hooks/secret-guard.py",
        make_file_payload("Write", str(tmp_path / "docs" / "safe.md")),
        env_overrides={"CLAUDE_PROJECT_DIR": str(tmp_path), "OMG_TDD_GATE_STRICT": "0"},
    )
    assert _decision(out) == "ask"
    assert "untrusted external content mode" in _reason(out).lower()


def test_secret_guard_bypass_mode_suppresses_ask(tmp_path: Path) -> None:
    _set_untrusted_mode(tmp_path, active=True)
    payload = make_file_payload("Write", str(tmp_path / "docs" / "safe.md"))
    assert isinstance(payload, dict)
    payload["permission_mode"] = "dontask"
    out = run_hook_json(
        "hooks/secret-guard.py",
        payload,
        env_overrides={"CLAUDE_PROJECT_DIR": str(tmp_path), "OMG_TDD_GATE_STRICT": "0"},
    )
    assert out is None


def test_secret_guard_bypass_mode_does_not_suppress_deny() -> None:
    payload = make_file_payload("Read", "/project/.env")
    assert isinstance(payload, dict)
    payload["permission_mode"] = "bypassPermissions"
    out = run_hook_json("hooks/secret-guard.py", payload)
    assert _decision(out) == "deny"


def test_secret_guard_writes_secret_access_audit_log_on_deny(tmp_path: Path) -> None:
    out = run_hook_json(
        "hooks/secret-guard.py",
        make_file_payload("Read", str(tmp_path / ".env.production")),
        env_overrides={"CLAUDE_PROJECT_DIR": str(tmp_path)},
    )
    assert _decision(out) == "deny"
    log_path = tmp_path / ".omg" / "state" / "ledger" / "secret-access.jsonl"
    assert log_path.exists()
    lines = [
        line
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines
    entry = json.loads(lines[-1])
    assert entry["decision"] == "deny"
    assert entry["tool"] == "Read"


def test_secret_guard_writes_secret_access_audit_log_on_allow(tmp_path: Path) -> None:
    out = run_hook_json(
        "hooks/secret-guard.py",
        make_file_payload("Read", str(tmp_path / "README.md")),
        env_overrides={"CLAUDE_PROJECT_DIR": str(tmp_path)},
    )
    assert _decision(out) is None
    log_path = tmp_path / ".omg" / "state" / "ledger" / "secret-access.jsonl"
    assert log_path.exists()
    lines = [
        line
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines
    entry = json.loads(lines[-1])
    assert entry["decision"] == "allow"
    assert entry["tool"] == "Read"


def test_secret_guard_logs_allowlisted_true_on_allowlist_bypass(tmp_path: Path) -> None:
    policy_dir = tmp_path / ".omg"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "policy.yaml").write_text(
        """
allowlist:
  - path: "*.allow.txt"
    tools: ["Read"]
    reason: "test allowlist"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    out = run_hook_json(
        "hooks/secret-guard.py",
        make_file_payload("Read", str(tmp_path / "notes.allow.txt")),
        env_overrides={"CLAUDE_PROJECT_DIR": str(tmp_path)},
    )
    assert _decision(out) is None

    log_path = tmp_path / ".omg" / "state" / "ledger" / "secret-access.jsonl"
    assert log_path.exists()
    lines = [
        line
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines
    entry = json.loads(lines[-1])
    assert entry["allowlisted"] is True
