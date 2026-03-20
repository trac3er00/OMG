#!/usr/bin/env python3
"""Stop Hook Dispatcher — Priority-based multiplexer for stop checks."""
from __future__ import annotations

import json
import importlib.util
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import warnings

HOOKS_DIR = str(Path(__file__).resolve().parent)
PROJECT_ROOT = str(Path(HOOKS_DIR).parent)
PORTABLE_RUNTIME_ROOT = str(Path(PROJECT_ROOT) / "omg-runtime")
for path in (HOOKS_DIR, PROJECT_ROOT, PORTABLE_RUNTIME_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from hooks._common import (  # noqa: E402
    _get_session_id,
    atomic_json_write,
    block_decision,
    bootstrap_runtime_paths,
    check_performance_budget,
    get_feature_flag,
    get_project_dir,
    has_recent_tool_activity,
    json_input,
    log_hook_error,
    read_checklist_session,
    hook_reentry_guard,
    record_stop_block,
    reset_stop_block_tracker,
    _resolve_project_dir,
    setup_crash_handler,
    should_skip_stop_hooks,
    STOP_CHECK_MAX_MS,
    STOP_DISPATCHER_TOTAL_MAX_MS,
    write_checklist_session,
)
from hooks.state_migration import resolve_state_file  # noqa: E402

bootstrap_runtime_paths(__file__)

from runtime.release_run_coordinator import resolve_current_run_id  # noqa: E402
from runtime import test_intent_lock  # noqa: E402


setup_crash_handler("stop_dispatcher")


NON_SOURCE_PATTERNS = [
    ".test.",
    "__test",
    "_test.",
    "/tests/",
    "tests/",
    "/test/",
    "test/",
    "spec",
    "__tests__",
    ".spec.",
    "script/",
    "scripts/",
    "/config/",
    ".config.",
    "package.json",
    "tsconfig",
    "eslint",
    "prettier",
    ".env",
    "mock",
    "fixture",
    "snapshot",
    "__mocks__",
    "jest.",
    "vitest.",
    "setup.",
    ".omg/",
    ".omc/",
    "omg-",
    "CLAUDE.md",
    "AGENTS.md",
    "readme",
    "changelog",
    "license",
    ".gitignore",
    ".dockerignore",
    "dockerfile",
    "docker-compose",
    "makefile",
    ".github/",
    ".vscode/",
    ".idea/",
    "memory/",
    ".claude/projects/",
]

INTERNAL_CONTROL_PATH_PATTERNS = [
    ".omg/",
    ".omc/",
    "hooks/",
    "CLAUDE.md",
    "AGENTS.md",
]


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _read_policy_flags(project_root: str) -> tuple[str, bool]:
    mode = "warn_and_run"
    require_evidence_pack = False
    policy_path = os.path.join(project_root, ".omg", "policy.yaml")
    if not os.path.exists(policy_path):
        return mode, require_evidence_pack

    try:
        with open(policy_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("mode:"):
                    mode = line.split(":", 1)[1].strip().strip("'\"") or mode
                elif line.startswith("require_evidence_pack:"):
                    value = line.split(":", 1)[1].strip().strip("'\"")
                    require_evidence_pack = _to_bool(value, require_evidence_pack)
    except Exception as e:  # security: policy enforcement
        print(f"[OMG] stop_dispatcher: {type(e).__name__}: {e}", file=sys.stderr)
    return mode, require_evidence_pack


def _is_non_source_path(file_path: str) -> bool:
    fl = str(file_path).lower()
    return any(p in fl for p in NON_SOURCE_PATTERNS)


def _is_internal_control_path(file_path: str) -> bool:
    fl = str(file_path).lower()
    return any(p.lower() in fl for p in INTERNAL_CONTROL_PATH_PATTERNS)


_RALPH_DEFAULT_TIMEOUT_MINUTES = 10


def _watchdog_check(start_time):
    """Return True if the dispatcher has exceeded its wall-clock budget."""
    return (time.time() - start_time) >= (STOP_DISPATCHER_TOTAL_MAX_MS / 1000)


try:
    from hooks.shadow_manager import has_recent_evidence  # type: ignore
except Exception:  # intentional: optional feature — shadow_manager may not exist
    has_recent_evidence = None

# Import hyphenated modules via importlib
_test_validator_check = None
_quality_runner_check = None
try:
    _tv_spec = importlib.util.spec_from_file_location(
        "test_validator", os.path.join(os.path.dirname(__file__), "test-validator.py"))
    if _tv_spec and _tv_spec.loader:
        _tv_mod = importlib.util.module_from_spec(_tv_spec)
        _tv_spec.loader.exec_module(_tv_mod)
        _test_validator_check = getattr(_tv_mod, "check_test_quality", None)
except Exception:  # intentional: crash isolation for optional module
    pass
try:
    _qr_spec = importlib.util.spec_from_file_location(
        "quality_runner", os.path.join(os.path.dirname(__file__), "quality-runner.py"))
    if _qr_spec and _qr_spec.loader:
        _qr_mod = importlib.util.module_from_spec(_qr_spec)
        _qr_spec.loader.exec_module(_qr_mod)
        _quality_runner_check = getattr(_qr_mod, "check_quality_runner", None)
except Exception:  # intentional: crash isolation for optional module
    pass

def _build_context(project_dir: str, stop_payload: dict | None = None) -> dict[str, object]:
    ledger_path = resolve_state_file(
        project_dir,
        "state/ledger/tool-ledger.jsonl",
        "ledger/tool-ledger.jsonl",
    )
    ledger_entries = []
    if os.path.exists(ledger_path):
        try:
            with open(ledger_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        ledger_entries.append(entry)
                    except json.JSONDecodeError:
                        pass  # intentional: skip malformed ledger lines
        except Exception as e:  # security: dispatch context building
            print(f"[OMG] stop_dispatcher: {type(e).__name__}: {e}", file=sys.stderr)

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    recent_entries = []
    for entry in ledger_entries:
        ts = entry.get("ts", "")
        if ts >= cutoff:
            recent_entries.append(entry)

    recent_commands = [
        e.get("command", "").lower()[:300]
        for e in recent_entries
        if e.get("command")
    ]
    recent_tools = {e.get("tool", "") for e in recent_entries}
    recent_exit_codes = [
        (e.get("command", ""), e.get("exit_code"))
        for e in recent_entries
        if e.get("exit_code") is not None
    ]
    write_entries = [
        e
        for e in recent_entries
        if e.get("tool") in ("Write", "Edit", "MultiEdit")
    ]
    material_write_entries = [
        e for e in write_entries if not _is_internal_control_path(str(e.get("file", "")))
    ]
    source_write_entries = [
        e for e in material_write_entries if not _is_non_source_path(str(e.get("file", "")))
    ]

    # --- Current-turn provenance from stop-hook payload ---
    # The stop payload (data from json_input()) may contain tool_use_results
    # representing the CURRENT TURN's tool calls. We extract Write/Edit/MultiEdit
    # entries from the payload to determine current-turn source writes independently
    # of the 2-hour ledger window.
    current_turn_source_write_entries: list[dict] = []
    current_turn_run_id: str | None = None

    try:
        current_turn_run_id = resolve_current_run_id(project_dir)
    except Exception as e:  # security: run_id resolution is best-effort
        print(f"[OMG] stop_dispatcher: resolve_current_run_id: {type(e).__name__}: {e}", file=sys.stderr)

    current_turn_commands: list[str] = []

    if stop_payload and isinstance(stop_payload, dict):
        # Claude Code stop hooks use "tool_use_results" key
        raw_tool_results = stop_payload.get("tool_use_results") or stop_payload.get("tool_results") or []
        if isinstance(raw_tool_results, list):
            for result in raw_tool_results:
                if not isinstance(result, dict):
                    continue
                tool_name = result.get("tool_name") or result.get("tool") or ""
                file_path = str(result.get("file") or result.get("path") or "")
                if tool_name in ("Write", "Edit", "MultiEdit") and file_path:
                    if (not _is_internal_control_path(file_path)
                            and not _is_non_source_path(file_path)):
                        current_turn_source_write_entries.append(result)
                if tool_name == "Bash":
                    cmd = (result.get("tool_input") or {}).get("command", "")
                    if cmd:
                        current_turn_commands.append(cmd.lower()[:300])

    return {
        "ledger_path": ledger_path,
        "ledger_entries": ledger_entries,
        "recent_entries": recent_entries,
        "recent_commands": recent_commands,
        "recent_tools": recent_tools,
        "recent_exit_codes": recent_exit_codes,
        "write_entries": write_entries,
        "material_write_entries": material_write_entries,
        "source_write_entries": source_write_entries,
        "has_writes": bool(write_entries),
        "has_material_writes": bool(material_write_entries),
        "has_source_writes": bool(source_write_entries),
        # Current-turn provenance (additive — does not replace ledger fields)
        "current_turn_source_write_entries": current_turn_source_write_entries,
        "current_turn_has_source_writes": bool(current_turn_source_write_entries),
        "current_turn_run_id": current_turn_run_id,
        "current_turn_commands": current_turn_commands,
    }


def check_verification(data, project_dir):
    if not get_feature_flag("verification", True):
        return []

    context = data["_stop_ctx"]
    blocks = []
    advisories = data.setdefault("_stop_advisories", [])

    recent_commands = context["recent_commands"]
    current_turn_commands = context.get("current_turn_commands", [])
    all_commands = recent_commands + current_turn_commands
    has_source_writes = context["has_source_writes"] or context.get("current_turn_has_source_writes", False)

    # Cooldown: if recently blocked and current turn has test commands, skip check
    cooldown_path = os.path.join(project_dir, ".omg/state/ledger/.verification-blocked.json")
    if current_turn_commands and os.path.exists(cooldown_path):
        try:
            with open(cooldown_path, "r", encoding="utf-8") as f:
                cooldown = json.load(f)
            elapsed = time.time() - cooldown.get("ts", 0)
            if elapsed < 60:
                has_test_in_turn = any(
                    any(kw in cmd for kw in ["test", "jest", "vitest", "pytest", "cargo test", "go test"])
                    for cmd in current_turn_commands
                )
                if has_test_in_turn:
                    return blocks
        except Exception:
            pass

    has_test = any(
        any(kw in cmd for kw in ["test", "jest", "vitest", "pytest", "cargo test", "go test"])
        for cmd in all_commands
    )
    has_lint = any(
        any(kw in cmd for kw in ["lint", "eslint", "ruff check", "golint", "clippy"])
        for cmd in all_commands
    )
    has_build = any(
        any(kw in cmd for kw in ["build", "compile", "tsc", "cargo build", "go build", "make"])
        for cmd in all_commands
    )
    has_any_verification = has_test or has_lint or has_build

    data["_has_test"] = has_test

    qg_path = resolve_state_file(project_dir, "state/quality-gate.json", "quality-gate.json")
    expected_checks = []
    if os.path.exists(qg_path):
        try:
            with open(qg_path, "r", encoding="utf-8", errors="ignore") as f:
                qg = json.load(f)
            for step in ["format", "lint", "typecheck", "test"]:
                cmd = qg.get(step)
                if isinstance(cmd, str) and cmd.strip():
                    expected_checks.append(step)
        except Exception as e:  # security: quality gate loading
            print(f"[OMG] stop_dispatcher: {type(e).__name__}: {e}", file=sys.stderr)

    if has_source_writes and not has_any_verification:
        if expected_checks:
            blocks.append(
                "Code was modified but NO verification commands were run.\n"
                f"Quality gate expects: {', '.join(expected_checks)}.\n"
                "Run your verification commands before completing.\n"
                "If you can't run them, explicitly state what is **Unverified** and why."
            )
        else:
            blocks.append(
                "Code was modified but NO verification commands were run.\n"
                "No quality-gate.json configured, but at minimum run lint/test/build.\n"
                "Run /OMG:init to configure quality gates, or explicitly state\n"
                "what is **Unverified** and why."
            )
        # Write cooldown marker so next invocation with test commands can skip
        try:
            atomic_json_write(cooldown_path, {"ts": time.time(), "reason": "verification_missing"})
        except Exception:
            pass

    policy_mode, policy_require_evidence = _read_policy_flags(project_dir)
    env_evidence_required = os.environ.get("OMG_EVIDENCE_REQUIRED")
    evidence_required = _to_bool(env_evidence_required, policy_require_evidence)
    strict_evidence_gate = policy_mode.strip().lower() not in {
        "warn_and_run",
        "warn",
        "advisory",
        "report_only",
    }

    if has_source_writes and evidence_required:
        has_ev = False
        if has_recent_evidence is not None:
            try:
                has_ev = bool(has_recent_evidence(project_dir, hours=24))
            except Exception as e:  # security: evidence verification
                print(f"[OMG] stop_dispatcher: {type(e).__name__}: {e}", file=sys.stderr)
                has_ev = False
        else:
            ev_dir = os.path.join(project_dir, ".omg", "evidence")
            has_ev = os.path.isdir(ev_dir) and any(n.endswith(".json") for n in os.listdir(ev_dir))

        if not has_ev:
            message = (
                "OMG v1 evidence gate: source code was modified but no EvidencePack was found.\n"
                "Create .omg/evidence/<run-id>.json before completing.\n"
                "Required fields: tests, security_scans, diff_summary, reproducibility, unresolved_risks."
            )
            if strict_evidence_gate:
                blocks.append(message)
            else:
                advisories.append(
                    f"[OMG advisory] {message} (policy mode: {policy_mode or 'warn_and_run'})"
                )

    return blocks


def check_diff_budget(data, project_dir):
    if not get_feature_flag("diff_budget", True):
        return []

    blocks = []
    changed_files = []
    try:
        max_files, max_loc = 3, 120
        plan_path = resolve_state_file(project_dir, "state/_plan.md", "_plan.md")
        if os.path.exists(plan_path):
            with open(plan_path, "r", encoding="utf-8", errors="ignore") as f:
                plan = f.read()
            if "CHANGE_BUDGET=large" in plan:
                max_files, max_loc = 999, 999999
            elif "CHANGE_BUDGET=medium" in plan:
                max_files, max_loc = 8, 400

        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=project_dir,
        )
        changed_files = [line for line in result.stdout.strip().split("\n") if line]
        files_changed = len(changed_files)

        result2 = subprocess.run(
            ["git", "diff", "--numstat"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=project_dir,
        )
        total_loc = 0
        for line in result2.stdout.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2:
                try:
                    added = int(parts[0]) if parts[0] != "-" else 0
                    removed = int(parts[1]) if parts[1] != "-" else 0
                    total_loc += added + removed
                except ValueError:
                    pass  # intentional: skip unparseable numstat lines

        if files_changed > max_files or total_loc > max_loc:
            blocks.append(
                f"Diff exceeds budget: {files_changed} files / {total_loc} LOC "
                f"(limit: {max_files} / {max_loc}).\n"
                "Reduce scope OR set CHANGE_BUDGET=medium/large in .omg/state/_plan.md."
            )
    except Exception as e:  # security: diff budget enforcement
        print(f"[OMG] stop_dispatcher: {type(e).__name__}: {e}", file=sys.stderr)

    data["_changed_files"] = changed_files
    return blocks


def check_recent_failures(data, project_dir):
    if not get_feature_flag("recent_failures", True):
        return []

    del project_dir

    recent_entries = data["_stop_ctx"]["recent_entries"]
    blocks = []
    recent_bash = [
        (e.get("command", "")[:80], e.get("exit_code"))
        for e in recent_entries
        if e.get("tool") == "Bash" and e.get("exit_code") is not None
    ]
    if len(recent_bash) >= 3:
        last_three = recent_bash[-3:]
        all_failed = all(exit_code != 0 for _, exit_code in last_three)
        if all_failed:
            cmds = [f"  {cmd} (exit {exit_code})" for cmd, exit_code in last_three]
            blocks.append(
                "Last 3 commands ALL FAILED:\n"
                + "\n".join(cmds)
                + "\n"
                + "Do not claim completion with unresolved failures.\n"
                + "Fix the failures, or document them as **Unverified**."
            )
    return blocks


_TEST_DIR_NAMES = frozenset({"tests", "test", "__tests__"})
_SKIP_DIR_SEGMENTS = frozenset({"build", "dist", "node_modules", ".git"})


def _is_test_file_path(rel_path):
    parts = rel_path.replace("\\", "/").split("/")
    if any(seg in _SKIP_DIR_SEGMENTS for seg in parts[:-1]):
        return False
    basename = parts[-1].lower() if parts else ""
    if any(p in basename for p in (".test.", ".spec.", "_test.", ".tests.")):
        return True
    if "__tests__" in rel_path:
        return True
    if basename.startswith("test_"):
        parent_dirs = {p.lower() for p in parts[:-1]}
        return not parent_dirs or bool(parent_dirs & _TEST_DIR_NAMES)
    return False


def check_test_execution(data, project_dir):
    if not get_feature_flag("test_execution", True):
        return []

    del project_dir

    context = data["_stop_ctx"]
    has_material_writes = context["has_material_writes"]
    has_test = bool(data.get("_has_test", False))
    changed_files = data.get("_changed_files", [])
    blocks = []

    if has_material_writes:
        test_files_modified = False
        try:
            for file_path in changed_files:
                if _is_test_file_path(file_path):
                    test_files_modified = True
                    break
        except Exception as e:  # security: test execution check
            print(f"[OMG] stop_dispatcher: {type(e).__name__}: {e}", file=sys.stderr)

        if test_files_modified and not has_test:
            blocks.append(
                "Test files were modified but test suite was never executed.\n"
                "Run your test command to verify the tests actually pass."
            )

    return blocks


def check_test_validator_coverage(data, project_dir):
    if not get_feature_flag("test_validator_coverage", True):
        return []

    del project_dir

    has_source_writes = data["_stop_ctx"]["has_source_writes"]
    changed_files = data.get("_changed_files", [])
    if not has_source_writes or not changed_files:
        return []

    source_changed = False
    test_or_qa_changed = False
    for file_path in changed_files:
        fl = file_path.lower()
        is_test_like = any(
            token in fl
            for token in (
                "test",
                "spec",
                "__tests__",
                ".test.",
                ".spec.",
                "qa",
                "quality",
                "e2e",
            )
        )
        if is_test_like:
            test_or_qa_changed = True
        elif not _is_non_source_path(fl):
            source_changed = True

    if source_changed and not test_or_qa_changed:
        return [
            "TEST-VALIDATOR: Source changes detected without test/QA updates.\n"
            "Add or update user-journey tests (including edge/error cases) for every new behavior."
        ]
    return []


def check_false_fix(data, project_dir):
    if not get_feature_flag("false_fix", True):
        return []

    del project_dir

    has_material_writes = data["_stop_ctx"]["has_material_writes"]
    changed_files = data.get("_changed_files", [])
    blocks = []

    if has_material_writes:
        non_source_only = True
        try:
            for file_path in changed_files:
                fl = file_path.lower()
                is_non_source = any(p in fl for p in NON_SOURCE_PATTERNS)
                if not is_non_source:
                    non_source_only = False
                    break
        except Exception as e:  # security: false fix detection
            print(f"[OMG] stop_dispatcher: {type(e).__name__}: {e}", file=sys.stderr)
            non_source_only = False

        if non_source_only and has_material_writes and len(changed_files) > 0:
            blocks.append(
                "⚠ FALSE FIX DETECTED: Only test/script/config files were modified.\n"
                "No actual source code was changed. If the task was to fix a bug or\n"
                "implement a feature, you likely changed test expectations to match\n"
                "broken behavior instead of fixing the real code.\n\n"
                "Go back and modify the actual SOURCE files, not just tests/configs."
            )

    return blocks


def check_write_failures(data, project_dir):
    if not get_feature_flag("write_failures", True):
        return []

    del project_dir

    recent_entries = data["_stop_ctx"]["recent_entries"]
    has_material_writes = data["_stop_ctx"]["has_material_writes"]
    blocks = []

    if has_material_writes:
        failed_writes = []
        for entry in recent_entries[-30:]:
            if entry.get("tool") in ("Write", "Edit", "MultiEdit"):
                success = entry.get("success")
                file_path = entry.get("file", "unknown")
                if _is_internal_control_path(str(file_path)):
                    continue
                if success is False:
                    failed_writes.append(file_path)
        if failed_writes:
            unique_fails = list(dict.fromkeys(failed_writes))[:5]
            blocks.append(
                "⚠ WRITE/EDIT FAILURE DETECTED:\n"
                f"These file operations may have failed: {', '.join(unique_fails)}\n\n"
                "Before claiming success, you MUST:\n"
                "1. Read the file to verify your changes are actually there\n"
                "2. If the file wasn't updated, retry with a different method:\n"
                "   - If Write failed (file exists): use Edit or Bash heredoc\n"
                "   - If Edit failed (hook error): verify file, then retry\n"
                "   - If hook error from external plugin: the write may have succeeded —\n"
                "     READ the file to check before retrying\n"
                "3. Report honestly: 'Write failed' not 'Updated successfully'"
            )

    return blocks


def check_bare_done(data, project_dir):
    """CHECK: Bare completion detection — blocks lazy 'Done.' responses."""
    if not get_feature_flag("bare_done", True):
        return []

    del project_dir

    transcript_path = data.get("transcript_path", "")
    if not transcript_path or not os.path.isfile(transcript_path):
        return []

    # Find the last assistant message in the transcript
    last_assistant_text = ""
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if entry.get("type") != "assistant":
                    continue
                msg = entry.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, str):
                    last_assistant_text = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            last_assistant_text = block.get("text", "")
                        elif isinstance(block, str):
                            last_assistant_text = block
    except Exception:
        return []

    if not last_assistant_text:
        return []

    # Only flag short responses
    if len(last_assistant_text) >= 200:
        return []

    # Check for structured content markers — these indicate a real report
    structured_markers = ["##", "- ", "```", "**Checks**", "**Files**"]
    for marker in structured_markers:
        if marker in last_assistant_text:
            return []

    # Check for bare completion patterns
    bare_patterns = [
        r"^\s*done\.?\s*$",
        r"^\s*complete\.?\s*$",
        r"^\s*completed\.?\s*$",
        r"^\s*finished\.?\s*$",
        r"^\s*all\s+done\.?\s*$",
    ]
    text_lower = last_assistant_text.strip()
    for pat in bare_patterns:
        if re.match(pat, text_lower, re.IGNORECASE):
            return [
                "Bare completion detected. Provide a structured report with: "
                "files modified, checks run, and confidence level."
            ]

    return []


def _proof_chain_strict_enabled() -> bool:
    return os.environ.get("OMG_PROOF_CHAIN_STRICT", "1").strip() != "0"


def _load_test_delta_from_evidence(project_dir: str, run_id: str | None) -> dict[str, object]:
    evidence_dir = os.path.join(project_dir, ".omg", "evidence")
    if not os.path.isdir(evidence_dir):
        return {}

    candidates = sorted(
        [
            os.path.join(evidence_dir, name)
            for name in os.listdir(evidence_dir)
            if name.endswith(".json")
        ],
        key=os.path.getmtime,
        reverse=True,
    )
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("schema") != "EvidencePack":
            continue
        payload_run_id = str(payload.get("run_id", "")).strip()
        if run_id and payload_run_id and payload_run_id != run_id:
            continue
        test_delta = payload.get("test_delta")
        if isinstance(test_delta, dict):
            return test_delta
    return {}


def _has_waiver_artifact(delta_summary: dict[str, object]) -> bool:
    waiver = delta_summary.get("waiver_artifact")
    if isinstance(waiver, dict):
        for field in ("artifact_path", "path", "id", "reason"):
            if str(waiver.get(field, "")).strip():
                return True
    return False


def _has_weakened_or_drift(delta_summary: dict[str, object]) -> bool:
    flags = delta_summary.get("flags")
    if not isinstance(flags, list):
        return False
    risk_flags = {
        "weakened_assertions",
        "tests_mismatch",
        "selector_drift",
        "removed_touched_area_coverage",
        "integration_to_mock_downgrade",
        "snapshot_only_refresh",
    }
    normalized = {str(item).strip().lower() for item in flags if str(item).strip()}
    return bool(normalized & risk_flags)


def check_tdd_proof_chain(data, project_dir):
    if not get_feature_flag("tdd_proof_chain", True):
        return []

    context = data["_stop_ctx"]
    has_current_turn_writes = context.get("current_turn_has_source_writes")
    has_writes = has_current_turn_writes if has_current_turn_writes is not None else context.get("has_source_writes", False)
    if not has_writes:
        return []

    run_id = resolve_current_run_id(project_dir=project_dir)
    lock_verdict = test_intent_lock.verify_lock(project_dir, run_id=run_id)
    delta_summary = data.get("_test_delta") if isinstance(data.get("_test_delta"), dict) else {}
    if not delta_summary:
        delta_summary = _load_test_delta_from_evidence(project_dir, run_id)

    lock_missing = str(lock_verdict.get("status", "")).strip() != "ok"
    weakened_without_waiver = _has_weakened_or_drift(delta_summary) and not _has_waiver_artifact(delta_summary)
    if not lock_missing and not weakened_without_waiver:
        return []

    strict_mode = _proof_chain_strict_enabled()
    if strict_mode:
        _tdd_reason_code = "tdd_proof_chain_incomplete"
        try:
            from runtime.evidence_narrator import format_block_explanation
            _tdd_explanation = format_block_explanation(_tdd_reason_code, {"tool": "stop_dispatcher"})
            _tdd_enhanced_reason = f"{_tdd_reason_code}: {_tdd_explanation}"
        except Exception:
            _tdd_enhanced_reason = _tdd_reason_code
        try:
            import os as _tdd_os
            from datetime import datetime as _tdd_dt, timezone as _tdd_tz
            _tdd_artifact_dir = _tdd_os.path.join(project_dir, ".omg", "state")
            _tdd_os.makedirs(_tdd_artifact_dir, exist_ok=True)
            with open(_tdd_os.path.join(_tdd_artifact_dir, "last-block-explanation.json"), "w", encoding="utf-8") as _tdd_f:
                json.dump({
                    "reason_code": _tdd_reason_code,
                    "explanation": _tdd_enhanced_reason,
                    "tool": "stop_dispatcher",
                    "timestamp": _tdd_dt.now(_tdd_tz.utc).isoformat(),
                }, _tdd_f, indent=2)
        except Exception:
            pass
        return [json.dumps({"status": "blocked", "reason": _tdd_enhanced_reason}, sort_keys=True)]

    warnings.warn(
        "tdd_proof_chain_incomplete_permissive",
        RuntimeWarning,
        stacklevel=2,
    )
    advisories = data.setdefault("_stop_advisories", [])
    advisories.append(
        "[OMG advisory] tdd proof chain incomplete: active lock evidence or waiver artifact is missing. "
        "Production default is fail-closed; OMG_PROOF_CHAIN_STRICT=0 downgrades to advisory."
    )
    return []

def check_simplifier(data, project_dir):
    """CHECK 7: Code simplifier — advisory only, never blocks."""
    if not get_feature_flag("simplifier", True):
        return []

    context = data["_stop_ctx"]
    source_write_entries = context.get("source_write_entries", [])
    if not source_write_entries:
        return []

    generic_name_re = re.compile(
        r'\b(data|result|item|temp|val|obj|info|stuff|thing)\b'
    )
    noise_comment_re = re.compile(
        r'^\s*(#|//) (get|set|return|check|create|update|delete) '
    )
    def_line_re = re.compile(r'^\s*(def |let |const |var )')

    advisories = []
    seen = set()

    for entry in source_write_entries:
        file_path = str(entry.get("file", ""))
        if not file_path or file_path in seen:
            continue
        seen.add(file_path)

        full_path = (
            file_path
            if os.path.isabs(file_path)
            else os.path.join(project_dir, file_path)
        )

        try:
            size = os.path.getsize(full_path)
            if size > 10240:  # Skip files >10KB
                continue
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except (OSError, IOError):
            continue  # intentional: skip unreadable files

        if not lines:
            continue

        total = len(lines)
        comment_count = sum(
            1 for line in lines
            if line.strip() and re.match(r'^\s*(#|//|/\*|\*)', line)
        )

        if total > 0 and comment_count / total > 0.40:
            pct = comment_count * 100 // total
            advisories.append(
                f"@simplifier: {file_path} — {pct}% comment lines ({comment_count}/{total})"
            )

        for line in lines:
            if def_line_re.match(line) and generic_name_re.search(line):
                advisories.append(
                    f"@simplifier: {file_path} — generic name: {line.strip()[:80]}"
                )
                break

        for line in lines:
            if noise_comment_re.match(line):
                advisories.append(
                    f"@simplifier: {file_path} — noise comment: {line.strip()[:60]}"
                )
                break

    if advisories:
        for adv in advisories:
            print(adv, file=sys.stderr)

    return []  # Never blocks


def format_ralph_block_reason(state, project_dir):
    """Build the rich reason string that Claude sees as its next prompt."""
    original = state.get('original_prompt', '')
    iteration = state.get('iteration', 0)
    max_iter = state.get('max_iterations', 50)
    checklist_path = state.get('checklist_path', '')

    progress = ''
    if checklist_path:
        full = os.path.join(project_dir, checklist_path)
        if os.path.exists(full):
            try:
                with open(full) as f:
                    lines = f.readlines()
                    done = sum(1 for l in lines if re.search(r'\[x\]', l, re.IGNORECASE))
                    total = sum(1 for l in lines if re.search(r'^\s*-\s*\[[ x!]\]', l))
                    progress = f' | Progress: {done}/{total}'
            except OSError:
                pass  # intentional: progress display is optional

    return (
        f"Ralph loop iteration {iteration}/{max_iter}{progress}. "
        f"Continue working on: {original}\n"
        f"If truly done, run: /OMG:ralph-stop"
    )

def persist_ralph_question(project_dir, question_text):
    """Persist a pending clarification question in the Ralph loop state.

    Called when any hook or the context engine detects ambiguity during a
    Ralph iteration.  The next stop-hook check will emit the question via
    block_decision and end the turn — no tool action may proceed.
    """
    ralph_path = os.path.join(project_dir, ".omg", "state", "ralph-loop.json")
    if not os.path.exists(ralph_path):
        return
    try:
        with open(ralph_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        return
    state["question_pending"] = True
    state["question_text"] = str(question_text).strip()[:500]
    state["question_emitted_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json_write(ralph_path, state)


def check_ralph_loop(project_dir, data):
    """Check Ralph loop state and return (block_reasons, advisories, is_question).

    When *is_question* is True the block is a clarification question and the
    caller MUST use block_reason="clarification_required" so that the turn
    ends without any further tool action.
    """
    del data

    if not get_feature_flag("ralph_loop"):
        return [], [], False
    ralph_path = os.path.join(project_dir, ".omg", "state", "ralph-loop.json")
    if not os.path.exists(ralph_path):
        return [], [], False
    try:
        with open(ralph_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        return [], [], False
    if not state.get("active"):
        return [], [], False

    # --- Pending clarification question: block and end turn immediately ---
    if state.get("question_pending"):
        question_text = str(state.get("question_text", "")).strip()
        if not question_text:
            question_text = "Clarification required before continuing Ralph loop"
        # Do NOT increment iteration — the loop is paused on the question
        return [question_text], [], True

    # Check if Ralph loop has expired
    _raw_timeout = os.environ.get("OMG_RALPH_TIMEOUT_MINUTES", "")
    try:
        timeout_minutes = int(_raw_timeout) if _raw_timeout.strip() else _RALPH_DEFAULT_TIMEOUT_MINUTES
    except (ValueError, TypeError):
        timeout_minutes = _RALPH_DEFAULT_TIMEOUT_MINUTES
    started_at_str = state.get("started_at")
    if started_at_str:
        try:
            started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            elapsed = now - started_at
            if elapsed.total_seconds() > timeout_minutes * 60:
                state["active"] = False
                atomic_json_write(ralph_path, state)
                return [], [f"Ralph loop expired after {timeout_minutes} minutes. Stopping."], False
        except (ValueError, TypeError):
            pass
    
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 50)
    if iteration >= max_iter:
        state["active"] = False
        atomic_json_write(ralph_path, state)
        return [], ["Ralph loop reached max iterations. Stopping."], False
    state["iteration"] = iteration + 1
    atomic_json_write(ralph_path, state)
    reason = format_ralph_block_reason(state, project_dir)
    return [reason], [], False


def check_planning_gate(project_dir, data=None):
    if not get_feature_flag("planning_enforcement"):
        return [], []
    current_turn_has_writes = (data or {}).get("_stop_ctx", {}).get("current_turn_has_source_writes", True)
    if not current_turn_has_writes:
        return [], []
    checklist = resolve_state_file(project_dir, "state/_checklist.md", "_checklist.md")
    if not os.path.exists(checklist):
        return [], []
    try:
        with open(checklist, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return [], []
    total = sum(1 for l in lines if re.search(r"^\s*-\s*\[[ x!]\]", l))
    done = sum(1 for l in lines if re.search(r"^\s*-\s*\[x\]", l, re.IGNORECASE))
    blocked = sum(1 for l in lines if re.search(r"^\s*-\s*\[!\]", l))
    pending = total - done - blocked
    if pending > 0:
        sidecar_path = os.path.join(project_dir, ".omg", "state", "_checklist.session")
        if not os.path.exists(sidecar_path):
            write_checklist_session(project_dir)

        session_data = read_checklist_session(project_dir)
        current_session = _get_session_id()
        stale_reason = None
        if session_data:
            checklist_session = str(session_data.get("session_id", "")).strip()
            if (
                checklist_session
                and current_session != "unknown"
                and checklist_session != current_session
            ):
                stale_reason = "different session"
            created_at = str(session_data.get("created_at", "")).strip()
            if not stale_reason and created_at:
                try:
                    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if created_dt.tzinfo is None:
                        created_dt = created_dt.replace(tzinfo=timezone.utc)
                    age = datetime.now(timezone.utc) - created_dt.astimezone(timezone.utc)
                    if age.total_seconds() > 2 * 3600:
                        stale_reason = f"{age.total_seconds() / 3600:.1f}h old"
                except (ValueError, TypeError):
                    pass
        else:
            try:
                age_hours = (time.time() - os.path.getmtime(checklist)) / 3600
                if age_hours > 2:
                    stale_reason = f"{age_hours:.1f}h old (mtime fallback)"
            except OSError:
                pass

        if stale_reason:
            return [], [
                f"[OMG advisory] Planning gate: stale checklist ({stale_reason}). "
                f"{done}/{total} complete, {pending} pending. "
                f"Clear with: rm .omg/state/_checklist.md"
            ]

        # Check context pressure — demote to advisory if high
        _pressure_path = os.path.join(project_dir, ".omg", "state", ".context-pressure.json")
        _is_high_pressure = False
        try:
            if os.path.exists(_pressure_path):
                with open(_pressure_path, "r") as _f:
                    _pressure = json.load(_f)
                _is_high_pressure = _pressure.get("is_high", False)
        except Exception:
            pass
        
        if _is_high_pressure:
            # Demote to advisory — don't block when context is exhausted
            return [], [f"[OMG advisory] Planning gate: {done}/{total} complete, {pending} pending. (demoted: context pressure high)"]
        
        return [
            f"Planning gate: {done}/{total} complete, {pending} pending. Complete checklist before finishing."
        ], []
    if pending == 0 and done >= 3:
        activity = has_recent_tool_activity(project_dir, since_minutes=60)
        if not activity.get("has_writes") and not activity.get("has_tests"):
            return [], [
                f"[OMG advisory] All {done} checklist items marked [x] but "
                f"no code changes or test runs found in tool-ledger. "
                f"If work was done externally, this can be ignored."
            ]
    return [], []


def check_scope_drift(project_dir):
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project_dir,
        )
        changed_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        if not changed_files:
            return []
        plan_path = resolve_state_file(project_dir, "state/_plan.md", "_plan.md")
        if not os.path.exists(plan_path):
            return []
        with open(plan_path, "r", encoding="utf-8") as f:
            plan_content = f.read()
        mentioned = sum(1 for f in changed_files if os.path.basename(f) in plan_content)
        outside = len(changed_files) - mentioned
        if changed_files and (outside / len(changed_files)) > 0.3:
            return [f"Scope drift: {outside}/{len(changed_files)} changed files not in plan."]
    except Exception as e:  # security: scope drift detection
        print(f"[OMG] stop_dispatcher: {type(e).__name__}: {e}", file=sys.stderr)
    return []



def check_todo_continuation(data: dict[str, object]) -> dict[str, str] | None:
    """Check if agent should continue due to incomplete todos.
    Returns a dict with continuation response if idle, None otherwise.
    Budget: STOP_CHECK_MAX_MS (15s)
    Feature flag: OMG_TODO_ENFORCEMENT_ENABLED
    """
    if not get_feature_flag("TODO_ENFORCEMENT", default=False):
        return None

    project_dir = get_project_dir()
    signal_path = os.path.join(project_dir, ".omg", "state", "idle_signal.json")

    if not os.path.exists(signal_path):
        return None

    try:
        with open(signal_path, "r", encoding="utf-8") as f:
            idle_signal = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(idle_signal, dict):
        return None

    if not idle_signal.get("idle_detected", False):
        return None

    incomplete_count = idle_signal.get("incomplete_count", 0)
    incomplete_items = idle_signal.get("incomplete_items", [])

    return {
        "decision": "block",
        "reason": f"Incomplete todos detected ({incomplete_count} items). Please complete: {', '.join(incomplete_items[:3])}"
    }


def main():
    _watchdog_start = time.time()

    with hook_reentry_guard("stop_dispatcher") as acquired:
        if not acquired:
            sys.exit(0)
        _main_body(_watchdog_start)


def _main_body(_watchdog_start):
    data = json_input()

    # Unified guard: stop-hook loop, context-limit, and re-entry detection
    if should_skip_stop_hooks(data):
        sys.exit(0)

    # Watchdog: bail out if we already burned too much wall-clock time
    if _watchdog_check(_watchdog_start):
        print("[OMG] stop_dispatcher: wall-clock watchdog expired", file=sys.stderr)
        sys.exit(0)

    project_dir = _resolve_project_dir()
    data["_stop_ctx"] = _build_context(project_dir, stop_payload=data)
    data["_stop_advisories"] = []

    # P1: Ralph loop check (implemented in Task 18)
    block_reasons, advisories, is_question = check_ralph_loop(project_dir, data)
    if advisories:
        data["_stop_advisories"].extend(advisories)
    if block_reasons:
        # Clarification questions use a distinct block_reason so the turn
        # ends cleanly — no tool action may follow a question emission.
        br = "clarification_required" if is_question else "ralph_loop"
        block_decision(block_reasons[0], block_reason=br, project_dir=project_dir)
        return

    if _watchdog_check(_watchdog_start):
        print("[OMG] stop_dispatcher: wall-clock watchdog expired", file=sys.stderr)
        sys.exit(0)

    # P2: Planning enforcement (implemented in Task 22)
    block_reasons, advisories = check_planning_gate(project_dir, data=data)
    if block_reasons:
        block_decision(block_reasons[0], block_reason="planning_gate", project_dir=project_dir)
        return
    advisories.extend(check_scope_drift(project_dir))
    if advisories:
        data["_stop_advisories"].extend(advisories)

    if _watchdog_check(_watchdog_start):
        print("[OMG] stop_dispatcher: wall-clock watchdog expired", file=sys.stderr)
        sys.exit(0)

    # P3: Todo continuation enforcement (Task 1.6)
    _p3_start = time.monotonic()
    todo_result = check_todo_continuation(data)
    _p3_elapsed = (time.monotonic() - _p3_start) * 1000
    check_performance_budget("check_todo_continuation", _p3_elapsed, STOP_CHECK_MAX_MS)
    if todo_result and todo_result.get("decision") == "block":
        block_decision(todo_result["reason"], block_reason="todo_continuation", project_dir=project_dir)
        return

    if _watchdog_check(_watchdog_start):
        print("[OMG] stop_dispatcher: wall-clock watchdog expired", file=sys.stderr)
        sys.exit(0)

    blocks = []
    for check_fn in [
        check_verification,
        check_diff_budget,
        check_recent_failures,
        check_test_execution,
        check_tdd_proof_chain,
        check_test_validator_coverage,
        check_false_fix,
        check_write_failures,
        check_bare_done,
        _test_validator_check,
        _quality_runner_check,
    ]:
        if _watchdog_check(_watchdog_start):
            print("[OMG] stop_dispatcher: wall-clock watchdog expired during quality checks", file=sys.stderr)
            sys.exit(0)
        if check_fn is None:
            continue
        try:
            result = check_fn(data, project_dir)
            if result:
                blocks.extend(result)
        except Exception as exc:
            name = getattr(check_fn, "__name__", str(check_fn))
            log_hook_error("stop_dispatcher", exc, {"check": name})

    advisories = data.get("_stop_advisories", [])
    if advisories:
        print("\n".join(advisories), file=sys.stderr)

    if blocks:
        block_decision("\n\n---\n\n".join(blocks), block_reason="quality_check", project_dir=project_dir)
        return

    check_simplifier(data, project_dir)
    reset_stop_block_tracker(project_dir)
    sys.exit(0)


if __name__ == "__main__":
    main()
