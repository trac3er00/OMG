"""OMG standalone legacy-compat dispatcher.

Primary namespace is `compat/*` while legacy `omg/*` aliases remain supported.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Callable, TypedDict

from hooks.policy_engine import evaluate_bash_command
from lab.pipeline import run_pipeline
from runtime.adoption import CANONICAL_VERSION
from runtime.canonical_surface import get_canonical_hosts, get_compat_hosts
from runtime.dispatcher import dispatch_runtime
from runtime.plugin_diagnostics import run_plugin_diagnostics
from runtime.security_check import run_security_check
from runtime.team_router import TeamDispatchRequest, dispatch_team

CONTRACT_SNAPSHOT_SCHEMA = "OmgCompatContractSnapshot"
LEGACY_CONTRACT_SNAPSHOT_SCHEMA = "OmgCompatContractSnapshot"
CONTRACT_SNAPSHOT_VERSION = CANONICAL_VERSION
LEGACY_SNAPSHOT_VERSION = "0.9.0"
GAP_REPORT_SCHEMA = "OmgCompatGapReport"
LEGACY_GAP_REPORT_SCHEMA = "OmgCompatGapReport"
RESULT_SCHEMA = "OmgCompatResult"
LEGACY_RESULT_SCHEMA = "OmgCompatResult"
DEFAULT_CONTRACT_SNAPSHOT_PATH = "runtime/omg_compat_contract_snapshot.json"
LEGACY_CONTRACT_SNAPSHOT_PATH = "runtime/omg_contract_snapshot.json"
DEFAULT_GAP_REPORT_PATH = ".omg/evidence/omg-compat-gap.json"
LEGACY_GAP_REPORT_PATH = ".omg/evidence/compat-gap.json"
DEFAULT_AUDIT_LEDGER_PATH = ".omg/state/ledger/omg-compat-audit.jsonl"
LEGACY_AUDIT_LEDGER_PATH = ".omg/state/ledger/compat-audit.jsonl"
DEFAULT_EVENT_DISPATCH = "compat_dispatch"
DEFAULT_EVENT_REQUEST = "compat_dispatch_request"
LEGACY_EVENT_ALIASES: dict[str, str] = {
    DEFAULT_EVENT_DISPATCH: "omg_dispatch",
    DEFAULT_EVENT_REQUEST: "omg_dispatch_request",
}

MAX_PROBLEM_CHARS = 4000
MAX_CONTEXT_CHARS = 12000
MAX_EXPECTED_OUTCOME_CHARS = 3000
MAX_FILES_PER_REQUEST = 50
MAX_FILE_PATH_CHARS = 260
WINDOWS_ABS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_dir(project_dir: str | None) -> str:
    return project_dir or os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def _is_safe_relative_path(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/")
    if not normalized or normalized.startswith(("/", "~")) or normalized.startswith("//"):
        return False
    if WINDOWS_ABS_PATH_RE.match(file_path):
        return False
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    return ".." not in parts


LEGACY_SKILL_ROUTES: dict[str, str] = {
    "analyze": "maintainer",
    "autopilot": "runtime_ship",
    "beads": "maintainer",
    "build-fix": "runtime_ship",
    "cancel": "cancel",
    "ccg": "ccg",
    "claude-flow": "ccg",
    "claude-mem": "memory",
    "code-review": "review",
    "compound-engineering": "ccg",
    "compounding-engineering": "ccg",
    "configure-notifications": "health",
    "configure-openclaw": "health",
    "deepinit": "init",
    "external-context": "teams",
    "hooks-mastery": "health",
    "hud": "health",
    "learn-about-omg": "learn",
    "learner": "learn",
    "mcp-setup": "health",
    "memsearch": "memory",
    "note": "memory",
    "omg-doctor": "health",
    "omg-help": "help",
    "omg-setup": "init",
    "omg-teams": "teams",
    "pipeline": "pipeline",
    "plan": "plan",
    "planning-with-files": "plan",
    "project-session-manager": "memory",
    "ralph": "runtime_ship",
    "ralph-wiggum": "runtime_ship",
    "ralph-init": "init",
    "ralplan": "plan",
    "release": "runtime_ship",
    "review": "review",
    "sci-omg": "maintainer",
    "security-review": "security_check",
    "skill": "learn",
    "omg-superpowers": "plan",
    "tdd": "plan",
    "team": "teams",
    "trace": "maintainer",
    "ultrapilot": "runtime_ship",
    "ultraqa": "review",
    "ultrawork": "runtime_ship",
    "writer-memory": "memory",
}
# Backward-compatible export
OMG_COMPAT_SKILL_ROUTES = LEGACY_SKILL_ROUTES

ROUTE_MATURITY: dict[str, str] = {
    "teams": "native",
    "ccg": "native",
    "runtime_ship": "native",
    "pipeline": "native",
    "memory": "native",
    "init": "native",
    "health": "native",
    "help": "native",
    "review": "native",
    "plan": "native",
    "secure": "native",
    "security_check": "native",
    "learn": "native",
    "maintainer": "native",
    "cancel": "native",
}

SKILL_MATURITY_OVERRIDES: dict[str, str] = {
    # Next-phase native promotion batch
    "autopilot": "native",
    "ralph": "native",
    "ultrapilot": "native",
    "ultrawork": "native",
    "review": "native",
    "code-review": "native",
    "ultraqa": "native",
    "release": "native",
    "tdd": "native",
    "plan": "native",
    "ralplan": "native",
    # Final bridge -> native promotion batch
    "analyze": "native",
    "build-fix": "native",
    "learn-about-omg": "native",
    "learner": "native",
    "note": "native",
    "project-session-manager": "native",
    "sci-omg": "native",
    "skill": "native",
    "trace": "native",
    "writer-memory": "native",
    # Ecosystem imports promoted as first-class native routes
    "omg-superpowers": "native",
    "ralph-wiggum": "native",
    "claude-flow": "native",
    "claude-mem": "native",
    "memsearch": "native",
    "beads": "native",
    "planning-with-files": "native",
    "hooks-mastery": "native",
    "compound-engineering": "native",
    "compounding-engineering": "native",
}

ROUTE_INPUTS: dict[str, dict[str, Any]] = {
    "teams": {"required": ["problem"], "optional": ["context", "files", "expected_outcome"]},
    "ccg": {"required": ["problem"], "optional": ["context", "files", "expected_outcome"]},
    "runtime_ship": {"required": ["problem"], "optional": ["expected_outcome"]},
    "pipeline": {"required": ["problem"], "optional": ["context"]},
    "memory": {"required": ["problem"], "optional": ["context"]},
    "init": {"required": [], "optional": ["problem"]},
    "health": {"required": [], "optional": ["problem"]},
    "help": {"required": [], "optional": []},
    "review": {"required": ["problem"], "optional": ["context", "files"]},
    "plan": {"required": ["problem"], "optional": ["expected_outcome"]},
    "secure": {"required": ["problem"], "optional": []},
    "security_check": {"required": [], "optional": ["problem"]},
    "learn": {"required": ["problem"], "optional": ["context"]},
    "maintainer": {"required": ["problem"], "optional": ["context"]},
    "cancel": {"required": [], "optional": []},
}

ROUTE_OUTPUTS: dict[str, dict[str, Any]] = {
    "teams": {"schema": "TeamDispatchResult"},
    "ccg": {"schema": "TeamDispatchResult"},
    "runtime_ship": {"schema": "RuntimeDispatchResult"},
    "pipeline": {"schema": "LabPipelineResult"},
    "memory": {"schema": "StateMutationResult"},
    "init": {"schema": "BootstrapResult"},
    "health": {"schema": "HealthSnapshot"},
    "help": {"schema": "CompatibilityHelp"},
    "review": {"schema": "TeamDispatchResult"},
    "plan": {"schema": "PlanningArtifacts"},
    "secure": {"schema": "PolicyDecision"},
    "security_check": {"schema": "SecurityCheckResult"},
    "learn": {"schema": "LearningArtifact"},
    "maintainer": {"schema": "MaintainerCompatArtifact"},
    "cancel": {"schema": "CancelResult"},
}

ROUTE_SIDE_EFFECTS: dict[str, list[str]] = {
    "teams": [],
    "ccg": [],
    "runtime_ship": [],
    "pipeline": [],
    "memory": [".omg/state/working-memory.md", ".omg/state/session.json (psm only)"],
    "init": [".omg/state/*", ".omg/idea.yml", ".omg/policy.yaml", ".omg/runtime.yaml"],
    "health": [],
    "help": [],
    "review": [],
    "plan": [".omg/state/_plan.md", ".omg/state/_checklist.md", ".omg/idea.yml"],
    "secure": [],
    "security_check": [],
    "learn": [".omg/state/working-memory.md"],
    "maintainer": [".omg/evidence/compat-*.json"],
    "cancel": [".omg/shadow/active-run (removed when exists)"],
}

SKILL_OUTPUT_SCHEMA_OVERRIDES: dict[str, str] = {
    "review": "ReviewSynthesis",
    "code-review": "ReviewSynthesis",
    "ultraqa": "ReviewSynthesis",
    "analyze": "AnalysisCompatArtifact",
    "trace": "AnalysisCompatArtifact",
    "sci-omg": "AnalysisCompatArtifact",
    "project-session-manager": "SessionState",
}

SKILL_SIDE_EFFECT_OVERRIDES: dict[str, list[str]] = {
    "autopilot": [".omg/state/persistent-mode.json"],
    "ralph": [".omg/state/persistent-mode.json"],
    "ralph-wiggum": [".omg/state/persistent-mode.json"],
    "ultrapilot": [".omg/state/persistent-mode.json"],
    "ultrawork": [".omg/state/persistent-mode.json"],
    "release": [".omg/evidence/release-draft.md"],
    "build-fix": [".omg/state/build-fix.md"],
    "analyze": [".omg/evidence/analysis-analyze.json"],
    "trace": [".omg/evidence/analysis-trace.json"],
    "sci-omg": [".omg/evidence/analysis-sci-omg.json"],
    "project-session-manager": [".omg/state/session.json"],
    "learn-about-omg": [".omg/knowledge/learning/learn-about-omg.md"],
    "learner": [".omg/knowledge/learning/learner.md"],
    "skill": [".omg/knowledge/learning/skill.md"],
    "note": [".omg/knowledge/notes.md"],
    "writer-memory": [".omg/knowledge/writer-memory.md"],
    "omg-superpowers": [".omg/state/_plan.md", ".omg/state/_checklist.md"],
    "planning-with-files": [".omg/state/_plan.md", ".omg/state/_checklist.md"],
    "claude-mem": [".omg/state/working-memory.md"],
    "memsearch": [".omg/state/working-memory.md"],
    "beads": [".omg/evidence/compat-beads.json"],
    "hooks-mastery": [],
    "claude-flow": [],
    "compound-engineering": [],
    "compounding-engineering": [],
}

SKILL_ROUTE_NOTES: dict[str, str] = {
    "omg-teams": "Legacy tmux worker dispatch replaced by internal Team router.",
    "project-session-manager": "Session metadata maintained in .omg/state/session.json.",
    "omg-setup": "Bootstraps OMG standalone state and baseline config files.",
    "omg-doctor": "Health checks run against OMG standalone layout.",
    "pipeline": "Routes to OMG lab policy+pipeline executor.",
    "release": "Routes to runtime ship and emits release draft artifact.",
    "tdd": "Generates plan/checklist scaffolding for red-green-refactor workflow.",
    "security-review": "Deprecated alias to the canonical OMG security-check engine.",
    "build-fix": "Creates targeted fix checklist and routes execution to runtime.",
    "analyze": "Writes structured analysis evidence artifact.",
    "trace": "Writes trace evidence artifact for debugging chain.",
    "learner": "Writes learning note into .omg/knowledge/learning.",
    "writer-memory": "Writes long-form memory artifact for writing workflows.",
    "omg-superpowers": "Imports TDD-first planning discipline into OMG plan route.",
    "ralph-wiggum": "Persistent iteration loop via runtime persistent-mode state.",
    "claude-flow": "Maps to CCG route for multi-agent orchestration semantics.",
    "claude-mem": "Maps to memory route for durable working-context updates.",
    "memsearch": "Maps to memory route for retrieval-oriented context search workflow.",
    "beads": "Maps to maintainer route for context engineering artifacts.",
    "planning-with-files": "Strengthens file-native planning artifacts in .omg/state.",
    "hooks-mastery": "Maps to health route for hook quality and readiness checks.",
    "compound-engineering": "Maps to CCG route for compounding, iterative orchestration.",
    "compounding-engineering": "Alias to compound-engineering orchestration route.",
}


def _contract_for(skill: str, route: str) -> dict[str, Any]:
    outputs = dict(ROUTE_OUTPUTS.get(route, {"schema": "Unknown"}))
    if skill in SKILL_OUTPUT_SCHEMA_OVERRIDES:
        outputs["schema"] = SKILL_OUTPUT_SCHEMA_OVERRIDES[skill]
    side_effects = SKILL_SIDE_EFFECT_OVERRIDES.get(skill, ROUTE_SIDE_EFFECTS.get(route, []))
    return {
        "skill": skill,
        "route": route,
        "maturity": SKILL_MATURITY_OVERRIDES.get(skill, ROUTE_MATURITY.get(route, "bridge")),
        "inputs": ROUTE_INPUTS.get(route, {"required": [], "optional": []}),
        "outputs": outputs,
        "side_effects": side_effects,
        "notes": SKILL_ROUTE_NOTES.get(skill, ""),
    }


LEGACY_SKILL_CONTRACTS: dict[str, dict[str, Any]] = {
    skill: _contract_for(skill, route) for skill, route in LEGACY_SKILL_ROUTES.items()
}
# Backward-compatible export
OMG_COMPAT_SKILL_CONTRACTS = LEGACY_SKILL_CONTRACTS


def list_compat_skills() -> list[str]:
    return sorted(LEGACY_SKILL_ROUTES.keys())


def list_compat_skill_contracts() -> list[dict[str, Any]]:
    return [LEGACY_SKILL_CONTRACTS[name] for name in list_compat_skills()]


def get_compat_skill_contract(skill: str) -> dict[str, Any] | None:
    return LEGACY_SKILL_CONTRACTS.get(skill)


def build_contract_snapshot_payload(*, include_generated_at: bool = True) -> dict[str, Any]:
    canonical_hosts = get_canonical_hosts()
    compat_hosts = get_compat_hosts()
    payload: dict[str, Any] = {
        "schema": CONTRACT_SNAPSHOT_SCHEMA,
        "contract_version": CONTRACT_SNAPSHOT_VERSION,
        "count": len(LEGACY_SKILL_CONTRACTS),
        "contracts": list_compat_skill_contracts(),
        "host_surfaces": {
            "canonical_parity_hosts": canonical_hosts,
            "release_blocking_hosts": canonical_hosts,
            "compatibility_only_hosts": compat_hosts,
            "release_non_blocking_hosts": compat_hosts,
        },
    }
    if include_generated_at:
        payload["generated_at"] = _now()
    return payload


def migrate_contract_snapshot_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    migrated = dict(payload)
    migrations: list[str] = []

    if "schema" not in migrated:
        migrated["schema"] = LEGACY_CONTRACT_SNAPSHOT_SCHEMA
        migrations.append("assign-missing-schema:legacy-omg")

    if migrated.get("schema") == LEGACY_CONTRACT_SNAPSHOT_SCHEMA:
        migrated["schema"] = CONTRACT_SNAPSHOT_SCHEMA
        migrations.append("migrate-schema-legacy-to-omg")

    if "contract_version" not in migrated:
        migrated["contract_version"] = LEGACY_SNAPSHOT_VERSION
        migrations.append("assign-missing-contract-version:0.9.0")

    if migrated.get("contract_version") == LEGACY_SNAPSHOT_VERSION:
        # v0.9.0 lacked explicit schema/version constraints.
        migrated["schema"] = CONTRACT_SNAPSHOT_SCHEMA
        migrated["contract_version"] = CONTRACT_SNAPSHOT_VERSION
        migrations.append(f"migrate-0.9.0-to-{CONTRACT_SNAPSHOT_VERSION}")

    return migrated, migrations


def build_compat_gap_report(project_dir: str | None = None) -> dict[str, Any]:
    root = _project_dir(project_dir)
    _ensure_state_layout(root)
    contracts = list_compat_skill_contracts()
    maturity_counts = Counter(c["maturity"] for c in contracts)
    route_counts = Counter(c["route"] for c in contracts)
    bridge_skills = [c["skill"] for c in contracts if c["maturity"] != "native"]
    report = {
        "schema": GAP_REPORT_SCHEMA,
        "generated_at": _now(),
        "total_skills": len(contracts),
        "maturity_counts": dict(sorted(maturity_counts.items())),
        "route_counts": dict(sorted(route_counts.items())),
        "native_skills": sorted(c["skill"] for c in contracts if c["maturity"] == "native"),
        "bridge_skills": sorted(bridge_skills),
    }
    out = os.path.join(root, DEFAULT_GAP_REPORT_PATH)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=True)
    legacy_out = os.path.join(root, LEGACY_GAP_REPORT_PATH)
    if legacy_out != out:
        with open(legacy_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=True)
    report["report_path"] = out
    report["legacy_report_path"] = legacy_out
    return report


def _result(
    *,
    skill: str,
    route: str,
    status: str = "ok",
    routed_to: str = "",
    findings: list[str] | None = None,
    actions: list[str] | None = None,
    artifacts: list[str] | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "status": status,
        "skill": skill,
        "route": route,
        "routed_to": routed_to,
        "contract": get_compat_skill_contract(skill) or {},
        "findings": findings or [],
        "actions": actions or [],
        "artifacts": artifacts or [],
        "result": result or {},
        "generated_at": _now(),
    }


def _ensure_state_layout(project_dir: str) -> None:
    for rel in ["state", "knowledge", "evidence", "trust", "shadow"]:
        os.makedirs(os.path.join(project_dir, ".omg", rel), exist_ok=True)


def _append_audit_event(project_dir: str, event: dict[str, Any]) -> None:
    _ensure_state_layout(project_dir)
    ledger_dir = os.path.join(project_dir, ".omg", "state", "ledger")
    os.makedirs(ledger_dir, exist_ok=True)
    payload = dict(event)
    payload.setdefault("ts", _now())
    payloads = [payload]
    event_name = str(payload.get("event", ""))
    if event_name in LEGACY_EVENT_ALIASES:
        legacy_payload = dict(payload)
        legacy_payload["event"] = LEGACY_EVENT_ALIASES[event_name]
        legacy_payload["alias_of"] = event_name
        payloads.append(legacy_payload)
    for rel in (DEFAULT_AUDIT_LEDGER_PATH, LEGACY_AUDIT_LEDGER_PATH):
        ledger_path = os.path.join(project_dir, rel)
        os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
        with open(ledger_path, "a", encoding="utf-8") as f:
            for one in payloads:
                f.write(json.dumps(one, ensure_ascii=True) + "\n")


def validate_compat_request(
    *,
    skill: str,
    problem: str,
    context: str,
    files: list[str] | None,
    expected_outcome: str,
) -> tuple[bool, str]:
    if skill not in LEGACY_SKILL_ROUTES:
        return False, f"Unknown skill: {skill}"

    if len(problem) > MAX_PROBLEM_CHARS:
        return False, f"problem too long (max {MAX_PROBLEM_CHARS})"
    if len(context) > MAX_CONTEXT_CHARS:
        return False, f"context too long (max {MAX_CONTEXT_CHARS})"
    if len(expected_outcome) > MAX_EXPECTED_OUTCOME_CHARS:
        return False, f"expected_outcome too long (max {MAX_EXPECTED_OUTCOME_CHARS})"

    route = LEGACY_SKILL_ROUTES[skill]
    required = set(ROUTE_INPUTS.get(route, {}).get("required", []))
    if "problem" in required and not problem.strip():
        return False, "problem is required for this skill"

    file_list = files or []
    if len(file_list) > MAX_FILES_PER_REQUEST:
        return False, f"too many files (max {MAX_FILES_PER_REQUEST})"
    for file_path in file_list:
        if not isinstance(file_path, str) or not file_path:
            return False, "invalid file path: must be non-empty string"
        if "\x00" in file_path:
            return False, "invalid file path: contains null byte"
        if len(file_path) > MAX_FILE_PATH_CHARS:
            return False, f"invalid file path: exceeds {MAX_FILE_PATH_CHARS} chars"
        if file_path != file_path.strip():
            return False, "invalid file path: leading/trailing whitespace is not allowed"
        if not _is_safe_relative_path(file_path):
            return False, "invalid file path: must be a safe relative path"

    return True, "ok"


def _write_if_missing(path: str, content: str) -> None:
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _append_memory(project_dir: str, message: str) -> str:
    _ensure_state_layout(project_dir)
    wm_path = os.path.join(project_dir, ".omg", "state", "working-memory.md")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    line = f"- [{ts}] {message}\n"
    with open(wm_path, "a", encoding="utf-8") as f:
        f.write(line)
    return wm_path


def _update_session_state(project_dir: str, message: str) -> str:
    _ensure_state_layout(project_dir)
    session_path = os.path.join(project_dir, ".omg", "state", "session.json")
    payload: dict[str, Any] = {"last_updated": _now(), "entries": []}
    if os.path.exists(session_path):
        try:
            with open(session_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                payload = data
        except Exception:
            pass
    payload.setdefault("entries", [])
    if not isinstance(payload["entries"], list):
        payload["entries"] = []
    payload["entries"].append({"ts": _now(), "message": message})
    payload["entries"] = payload["entries"][-100:]
    payload["last_updated"] = _now()
    with open(session_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)
    return session_path


def _append_knowledge_note(project_dir: str, rel_path: str, line: str) -> str:
    _ensure_state_layout(project_dir)
    full = os.path.join(project_dir, ".omg", rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")
    return full


def _write_learning_artifact(project_dir: str, skill: str, message: str, context: str) -> str:
    path = os.path.join(project_dir, ".omg", "knowledge", "learning", f"{skill}.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"## {_now()}\n")
        f.write(f"- skill: {skill}\n")
        f.write(f"- message: {message}\n")
        if context:
            f.write(f"- context: {context}\n")
        f.write("\n")
    return path


def _write_analysis_artifact(project_dir: str, skill: str, message: str, context: str, files: list[str]) -> str:
    _ensure_state_layout(project_dir)
    out = os.path.join(project_dir, ".omg", "evidence", f"analysis-{skill}.json")
    payload = {
        "schema": "AnalysisCompatArtifact",
        "skill": skill,
        "generated_at": _now(),
        "problem": message,
        "context": context,
        "files": files,
        "findings": [
            "Structured analysis generated by OMG compat dispatcher.",
            "Use review/teams routes for deeper remediation proposals.",
        ],
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)
    return out


def _write_maintainer_artifact(project_dir: str, skill: str, problem: str) -> str:
    _ensure_state_layout(project_dir)
    out_path = os.path.join(project_dir, ".omg", "evidence", f"compat-{skill}.json")
    payload = {
        "schema": "MaintainerCompatArtifact",
        "skill": skill,
        "generated_at": _now(),
        "summary": problem or f"compat route for {skill}",
        "signals": {
            "triage": "unverified",
            "release_notes": "unverified",
            "review": "unverified",
        },
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)
    return out_path


def _init_bootstrap(project_dir: str, reason: str) -> list[str]:
    _ensure_state_layout(project_dir)
    profile_path = os.path.join(project_dir, ".omg", "state", "profile.yaml")
    idea_path = os.path.join(project_dir, ".omg", "idea.yml")
    policy_path = os.path.join(project_dir, ".omg", "policy.yaml")
    runtime_path = os.path.join(project_dir, ".omg", "runtime.yaml")
    plan_path = os.path.join(project_dir, ".omg", "state", "_plan.md")
    checklist_path = os.path.join(project_dir, ".omg", "state", "_checklist.md")
    qg_path = os.path.join(project_dir, ".omg", "state", "quality-gate.json")

    _write_if_missing(
        profile_path,
        "name: omg-project\n"
        "description: initialized by OMG standalone compat bootstrap\n"
        "language: unknown\n"
        "framework: unknown\n"
        "stack: []\n"
        "conventions: {}\n"
        "ai_behavior: {}\n"
        "preferences:\n"
        "  architecture_requests: []\n"
        "  constraints: {}\n"
        "  routing:\n"
        "    prefer_clarification: false\n"
        "user_vector:\n"
        "  tags: []\n"
        "  summary: \"\"\n"
        "  confidence: 0.0\n"
        "profile_provenance:\n"
        "  recent_updates: []\n",
    )
    _write_if_missing(
        idea_path,
        "goal: \"\"\n"
        "constraints: []\n"
        "acceptance: []\n"
        "risk:\n"
        "  security: []\n"
        "  performance: []\n"
        "  compatibility: []\n"
        "evidence_required:\n"
        "  tests: []\n"
        "  security_scans: []\n"
        "  reproducibility: []\n"
        "  artifacts: []\n",
    )
    _write_if_missing(
        policy_path,
        "mode: warn_and_run\ncritical_block: true\n",
    )
    _write_if_missing(
        runtime_path,
        "default: claude\navailable:\n  - claude\n  - gpt\n  - local\n",
    )
    _write_if_missing(
        plan_path,
        "# Compat Plan\n"
        f"goal: {reason or 'bootstrap'}\n"
        "CHANGE_BUDGET=small\n",
    )
    _write_if_missing(
        checklist_path,
        "- [ ] define goal\n- [ ] run verification\n- [ ] ship with evidence\n",
    )
    if not os.path.exists(qg_path):
        with open(qg_path, "w", encoding="utf-8") as f:
            json.dump({"lint": "pytest -q", "test": "pytest -q"}, f, indent=2, ensure_ascii=True)
    return [
        os.path.relpath(profile_path, project_dir),
        os.path.relpath(idea_path, project_dir),
        os.path.relpath(policy_path, project_dir),
        os.path.relpath(runtime_path, project_dir),
        os.path.relpath(plan_path, project_dir),
        os.path.relpath(checklist_path, project_dir),
        os.path.relpath(qg_path, project_dir),
    ]


def _health_snapshot(project_dir: str) -> dict[str, Any]:
    p = Path(project_dir)
    omg_root = p / ".omg"
    checks = [
        {"name": "python>=3.8", "ok": sys.version_info >= (3, 8)},
        {"name": ".omg exists", "ok": omg_root.exists()},
        {"name": ".omg/state exists", "ok": (omg_root / "state").exists()},
        {"name": ".omg/idea.yml exists", "ok": (omg_root / "idea.yml").exists()},
        {"name": ".omg/policy.yaml exists", "ok": (omg_root / "policy.yaml").exists()},
    ]
    all_ok = all(c["ok"] for c in checks)
    return {
        "project_dir": str(p),
        "status": "pass" if all_ok else "warn",
        "checks": checks,
        "omg_exists": omg_root.exists(),
        "state_exists": (omg_root / "state").exists(),
        "knowledge_exists": (omg_root / "knowledge").exists(),
        "evidence_exists": (omg_root / "evidence").exists(),
    }


def _doctor_check(name: str, *, ok: bool, message: str, required: bool = True) -> dict[str, Any]:
    if ok:
        status = "ok"
    elif required:
        status = "blocker"
    else:
        status = "warning"
    return {"name": name, "status": status, "message": message, "required": required}


def _check_plugin_compat(root_dir: Path) -> dict[str, Any]:
    try:
        result = run_plugin_diagnostics(str(root_dir))
    except Exception as exc:
        return _doctor_check(
            "plugin_compatibility",
            ok=False,
            message=f"plugin diagnostics error: {exc}",
            required=False,
        )

    status = str(result.get("status", "error"))
    summary = result.get("summary", {})
    summary = summary if isinstance(summary, dict) else {}
    total_records = int(summary.get("total_records", 0))
    total_conflicts = int(summary.get("total_conflicts", 0))
    blockers = int(summary.get("blockers", 0))
    return _doctor_check(
        "plugin_compatibility",
        ok=status in {"ok", "warn"},
        message=(
            f"plugin compatibility: {total_records} records, "
            f"{total_conflicts} conflicts, {blockers} blockers"
        ),
        required=False,
    )


def run_doctor(*, root_dir: Path | None = None) -> dict[str, Any]:
    """Canonical install/runtime verification engine.

    Called by both ``omg doctor`` CLI and the ``omg-doctor`` compat route.
    """
    from runtime.contract_compiler import _check_version_identity_drift

    repo_root = root_dir or Path(__file__).resolve().parent.parent
    checks: list[dict[str, Any]] = []

    # 1. Python version >= 3.10
    py_ok = sys.version_info >= (3, 10)
    checks.append(_doctor_check(
        "python_version",
        ok=py_ok,
        message=f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        + ("" if py_ok else " (requires >=3.10)"),
    ))

    # 2. fastmcp availability
    fastmcp_ok = False
    fastmcp_msg = ""
    try:
        import importlib
        importlib.import_module("fastmcp")
        fastmcp_ok = True
        fastmcp_msg = "fastmcp importable"
    except ImportError:
        fastmcp_msg = "fastmcp not installed — required for MCP server"
    checks.append(_doctor_check("fastmcp", ok=fastmcp_ok, message=fastmcp_msg))

    # 3. omg-control reachable (stdio config present in .mcp.json)
    mcp_json_path = repo_root / ".mcp.json"
    omg_control_ok = False
    omg_control_msg = ".mcp.json not found"
    if mcp_json_path.exists():
        try:
            with open(mcp_json_path, "r", encoding="utf-8") as f:
                mcp_data = json.load(f)
            servers = mcp_data.get("mcpServers", {})
            if "omg-control" in servers:
                ctrl = servers["omg-control"]
                if ctrl.get("command"):
                    omg_control_ok = True
                    omg_control_msg = f"omg-control configured (stdio: {ctrl['command']})"
                else:
                    omg_control_ok = True
                    omg_control_msg = "omg-control configured (non-stdio)"
            else:
                omg_control_msg = "omg-control not found in .mcp.json mcpServers"
        except (json.JSONDecodeError, KeyError) as exc:
            omg_control_msg = f".mcp.json parse error: {exc}"
    checks.append(_doctor_check("omg_control_reachable", ok=omg_control_ok, message=omg_control_msg))

    # 4. Policy files present
    policy_path = repo_root / ".omg" / "policy.yaml"
    commands_dir = repo_root / "commands"
    policy_ok = policy_path.exists() or commands_dir.exists()
    if policy_path.exists() and commands_dir.exists():
        policy_msg = "policy.yaml and commands/ present"
    elif policy_path.exists():
        policy_msg = "policy.yaml present (commands/ missing)"
    elif commands_dir.exists():
        policy_msg = "commands/ present (policy.yaml missing)"
    else:
        policy_msg = "neither policy.yaml nor commands/ found"
    checks.append(_doctor_check("policy_files", ok=policy_ok, message=policy_msg))

    # 5. Metadata drift (release identity)
    drift_result = _check_version_identity_drift(repo_root)
    drift_ok = drift_result.get("status") == "ok"
    drift_blockers = drift_result.get("blockers", [])
    drift_msg = "all version surfaces aligned" if drift_ok else f"{len(drift_blockers)} drift(s): {'; '.join(drift_blockers[:3])}"
    checks.append(_doctor_check("metadata_drift", ok=drift_ok, message=drift_msg))

    # 6. Compiled bundles exist (optional)
    bundles_dir = repo_root / "dist"
    bundles_ok = bundles_dir.exists() and any(bundles_dir.iterdir()) if bundles_dir.exists() else False
    bundles_msg = "dist/ contains compiled bundles" if bundles_ok else "dist/ missing or empty"
    checks.append(_doctor_check("compiled_bundles", ok=bundles_ok, message=bundles_msg, required=False))

    # 7. Host compatibility (optional)
    claude_dir = os.environ.get("CLAUDE_DIR", os.path.expanduser("~/.claude"))
    host_ok = os.path.isdir(claude_dir)
    host_msg = f"host config dir exists ({claude_dir})" if host_ok else f"host config dir not found ({claude_dir})"
    checks.append(_doctor_check("host_compatibility", ok=host_ok, message=host_msg, required=False))

    # 8. HTTP memory — optional, never required
    memory_msg = "HTTP memory not configured (optional)"
    if mcp_json_path.exists():
        try:
            with open(mcp_json_path, "r", encoding="utf-8") as f:
                mcp_data = json.load(f)
            mem_cfg = mcp_data.get("mcpServers", {}).get("omg-memory", {})
            if mem_cfg.get("type") == "http" and mem_cfg.get("url"):
                memory_msg = f"omg-memory configured at {mem_cfg['url']} (optional, not probed)"
        except (json.JSONDecodeError, KeyError):
            pass
    checks.append(_doctor_check("memory_reachable", ok=True, message=memory_msg, required=False))

    # 9. Managed runtime venv (optional)
    managed_venv_path = Path(claude_dir) / "omg-runtime" / ".venv"
    venv_ok = managed_venv_path.exists()
    venv_msg = f"managed venv at {managed_venv_path}" if venv_ok else f"managed venv not found at {managed_venv_path} (install via OMG-setup.sh)"
    checks.append(_doctor_check("managed_runtime", ok=venv_ok, message=venv_msg, required=False))

    plugin_check = _check_plugin_compat(repo_root)
    checks.append(plugin_check)

    has_blocker = any(c["status"] == "blocker" for c in checks)
    return {
        "schema": "DoctorResult",
        "status": "fail" if has_blocker else "pass",
        "checks": checks,
        "plugin_compatibility": plugin_check,
        "version": CANONICAL_VERSION,
    }


class DoctorFixSpec(TypedDict):
    fixable: bool
    fix_handler: Callable[[Path, dict[str, Any]], dict[str, Any]] | None
    fixable_in_context: bool
    suggestion: str


def _fix_omg_control_reachable(root_dir: Path, _check: dict[str, Any]) -> dict[str, Any]:
    from runtime.config_transaction import ConfigTransaction

    mcp_json_path = root_dir / ".mcp.json"
    mcp_data: dict[str, Any] = {}
    if mcp_json_path.exists():
        try:
            with open(mcp_json_path, "r", encoding="utf-8") as f:
                mcp_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    servers = mcp_data.setdefault("mcpServers", {})
    servers["omg-control"] = {
        "command": "python3",
        "args": ["-m", "runtime.omg_mcp_server"],
    }
    content = json.dumps(mcp_data, indent=2, ensure_ascii=True) + "\n"
    return {"planned_path": str(mcp_json_path), "content": content, "mode": 0o644}


def _fix_policy_files(root_dir: Path, _check: dict[str, Any]) -> dict[str, Any]:
    policy_path = root_dir / ".omg" / "policy.yaml"
    if policy_path.exists():
        return {}
    content = "mode: warn_and_run\ncritical_block: true\n"
    return {"planned_path": str(policy_path), "content": content, "mode": 0o644}


def _fix_metadata_drift(root_dir: Path, check: dict[str, Any]) -> dict[str, Any]:
    from runtime.adoption import CANONICAL_VERSION
    from runtime.contract_compiler import _check_version_identity_drift

    drift_result = _check_version_identity_drift(root_dir)
    drift_details = drift_result.get("drift_details", {})
    if not drift_details:
        return {}

    first_label = next(iter(drift_details))
    old_version = drift_details[first_label]
    parts = first_label.split(":", 1)
    rel_path = parts[0] if parts else first_label
    target = root_dir / rel_path
    if not target.exists():
        return {}
    original = target.read_text(encoding="utf-8")
    patched = original.replace(old_version, CANONICAL_VERSION) if old_version != "<not found>" else original
    if patched == original:
        return {}
    return {"planned_path": str(target), "content": patched, "mode": 0o644}


DOCTOR_FIX_SPECS: dict[str, DoctorFixSpec] = {
    "python_version": {
        "fixable": False,
        "fix_handler": None,
        "fixable_in_context": False,
        "suggestion": "Install Python >= 3.10 from python.org or via your package manager",
    },
    "fastmcp": {
        "fixable": False,
        "fix_handler": None,
        "fixable_in_context": False,
        "suggestion": "Run: pip install fastmcp",
    },
    "omg_control_reachable": {
        "fixable": True,
        "fix_handler": _fix_omg_control_reachable,
        "fixable_in_context": True,
        "suggestion": "",
    },
    "policy_files": {
        "fixable": True,
        "fix_handler": _fix_policy_files,
        "fixable_in_context": True,
        "suggestion": "",
    },
    "metadata_drift": {
        "fixable": True,
        "fix_handler": _fix_metadata_drift,
        "fixable_in_context": True,
        "suggestion": "",
    },
}

_DEFAULT_FIX_SPEC: DoctorFixSpec = {
    "fixable": False,
    "fix_handler": None,
    "fixable_in_context": False,
    "suggestion": "Manual intervention required",
}


def run_doctor_fix(*, root_dir: Path | None = None, dry_run: bool = True) -> dict[str, Any]:
    from runtime.config_transaction import ConfigTransaction, ConfigTransactionError

    doctor_result = run_doctor(root_dir=root_dir)
    repo_root = root_dir or Path(__file__).resolve().parent.parent

    enriched_checks: list[dict[str, Any]] = []
    fix_receipts: list[dict[str, Any]] = []

    for check in doctor_result["checks"]:
        spec = DOCTOR_FIX_SPECS.get(check["name"], _DEFAULT_FIX_SPEC)
        enriched = dict(check)
        enriched["fixable"] = spec["fixable"]
        if not spec["fixable"]:
            enriched["suggestion"] = spec["suggestion"]
        enriched_checks.append(enriched)

        if check["status"] == "ok" or not spec["fixable"] or spec["fix_handler"] is None:
            continue

        handler = spec["fix_handler"]
        plan_data = handler(repo_root, check)
        if not plan_data or "planned_path" not in plan_data:
            continue

        lock_dir = tempfile.mkdtemp(prefix="doctor-fix-")
        tx = ConfigTransaction(
            lock_path=Path(lock_dir) / "doctor-fix.lock",
            backup_root=Path(lock_dir) / "backups",
        )
        tx.plan(
            plan_data["planned_path"],
            plan_data["content"],
            mode=plan_data.get("mode", 0o644),
        )

        try:
            receipt = tx.dry_run() if dry_run else tx.execute()
        except ConfigTransactionError as exc:
            receipt = exc.receipt or {
                "planned_writes": [],
                "executed_writes": [],
                "backup_path": "",
                "verification": {},
                "executed": False,
                "rollback": None,
            }

        fix_receipts.append({
            "check": check["name"],
            "action": plan_data.get("action", f"fix_{check['name']}"),
            "backup_path": receipt.get("backup_path", ""),
            "verification": receipt.get("verification", {}),
            "executed": receipt.get("executed", False),
            "rollback": receipt.get("rollback"),
        })

    has_blocker = any(c["status"] == "blocker" for c in enriched_checks)
    unfixed_blockers = has_blocker and dry_run

    return {
        "schema": "DoctorFixResult",
        "mode": "dry_run" if dry_run else "fix",
        "status": "fail" if unfixed_blockers else doctor_result["status"],
        "checks": enriched_checks,
        "fix_receipts": fix_receipts,
        "version": CANONICAL_VERSION,
    }


def _write_release_artifact(project_dir: str, message: str) -> str:
    _ensure_state_layout(project_dir)
    out = os.path.join(project_dir, ".omg", "evidence", "release-draft.md")
    if not os.path.exists(out):
        with open(out, "w", encoding="utf-8") as f:
            f.write("# Release Draft\n\n")
    with open(out, "a", encoding="utf-8") as f:
        f.write(f"- {_now()}: {message}\n")
    return out


def _write_build_fix_artifact(project_dir: str, message: str) -> str:
    _ensure_state_layout(project_dir)
    out = os.path.join(project_dir, ".omg", "state", "build-fix.md")
    with open(out, "a", encoding="utf-8") as f:
        f.write(f"## {_now()}\n")
        f.write(f"- target: {message}\n")
        f.write("- checklist:\n")
        f.write("  - reproduce failure\n")
        f.write("  - implement minimal fix\n")
        f.write("  - run focused tests\n")
        f.write("  - run full regression\n\n")
    return out


def _write_persistent_state(
    project_dir: str,
    *,
    mode: str,
    goal: str,
    context: str,
    expected_outcome: str,
    runtime_result: dict[str, Any],
) -> str:
    _ensure_state_layout(project_dir)
    path = os.path.join(project_dir, ".omg", "state", "persistent-mode.json")
    payload: dict[str, Any] = {
        "schema": "PersistentModeState",
        "mode": mode,
        "status": "active",
        "goal": goal,
        "context": context,
        "expected_outcome": expected_outcome,
        "started_at": _now(),
        "last_updated": _now(),
        "last_runtime_status": runtime_result.get("status", "unknown"),
        "history": [],
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                current = json.load(f)
            if isinstance(current, dict):
                payload.update(current)
        except Exception:
            pass
    payload.setdefault("history", [])
    if not isinstance(payload["history"], list):
        payload["history"] = []
    payload["mode"] = mode
    payload["status"] = "active"
    payload["goal"] = goal
    payload["context"] = context
    payload["expected_outcome"] = expected_outcome
    payload["last_updated"] = _now()
    payload["last_runtime_status"] = runtime_result.get("status", "unknown")
    payload["history"].append(
        {
            "ts": _now(),
            "event": "dispatch",
            "goal": goal,
            "runtime_status": runtime_result.get("status", "unknown"),
        }
    )
    payload["history"] = payload["history"][-200:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)
    return path


def _run_dual_review(
    problem: str,
    context: str,
    files: list[str],
    expected_outcome: str,
) -> dict[str, Any]:
    codex_req = TeamDispatchRequest(
        target="codex",
        problem=f"review: {problem}",
        context=context,
        files=files,
        expected_outcome=expected_outcome,
    )
    ccg_req = TeamDispatchRequest(
        target="ccg",
        problem=f"cross-check: {problem}",
        context=context,
        files=files,
        expected_outcome=expected_outcome,
    )
    codex = dispatch_team(codex_req).to_dict()
    ccg = dispatch_team(ccg_req).to_dict()
    merged_actions: list[str] = []
    seen = set()
    for source in (codex.get("actions", []), ccg.get("actions", [])):
        for action in source:
            if action not in seen:
                seen.add(action)
                merged_actions.append(action)
    synthesis = {
        "schema": "ReviewSynthesis",
        "status": "ok",
        "tracks": {"codex": codex, "ccg": ccg},
        "summary": [
            "Dual-track review executed (codex + ccg).",
            f"Merged action count: {len(merged_actions)}",
        ],
        "actions": merged_actions,
    }
    return synthesis


def _ensure_plan_artifacts(project_dir: str, goal: str) -> list[str]:
    _ensure_state_layout(project_dir)
    plan_path = os.path.join(project_dir, ".omg", "state", "_plan.md")
    checklist_path = os.path.join(project_dir, ".omg", "state", "_checklist.md")
    idea_path = os.path.join(project_dir, ".omg", "idea.yml")
    _write_if_missing(
        plan_path,
        "# Deep Plan\n"
        f"goal: {goal or 'compat planning'}\n"
        "CHANGE_BUDGET=small\n"
        "phases:\n"
        "- foundation\n- implementation\n- verification\n",
    )
    _write_if_missing(
        checklist_path,
        "- [ ] write failing test\n- [ ] implement minimal fix\n- [ ] run tests\n",
    )
    _write_if_missing(
        idea_path,
        "goal: \"compat-plan\"\n"
        "constraints: []\n"
        "acceptance: []\n"
        "risk:\n"
        "  security: []\n"
        "  performance: []\n"
        "  compatibility: []\n"
        "evidence_required:\n"
        "  tests: []\n"
        "  security_scans: []\n"
        "  reproducibility: []\n"
        "  artifacts: []\n",
    )
    return [
        os.path.relpath(plan_path, project_dir),
        os.path.relpath(checklist_path, project_dir),
        os.path.relpath(idea_path, project_dir),
    ]


def _ensure_tdd_artifacts(project_dir: str, goal: str) -> list[str]:
    _ensure_state_layout(project_dir)
    plan_path = os.path.join(project_dir, ".omg", "state", "_plan.md")
    checklist_path = os.path.join(project_dir, ".omg", "state", "_checklist.md")
    idea_path = os.path.join(project_dir, ".omg", "idea.yml")
    with open(plan_path, "w", encoding="utf-8") as f:
        f.write(
            "# TDD Plan\n"
            f"goal: {goal or 'tdd workflow'}\n"
            "CHANGE_BUDGET=small\n"
            "workflow:\n"
            "- red: write failing test\n"
            "- green: minimal implementation\n"
            "- refactor: clean while tests stay green\n"
        )
    with open(checklist_path, "w", encoding="utf-8") as f:
        f.write(
            "- [ ] red: create failing test for target behavior\n"
            "- [ ] red: run targeted test and confirm failure reason\n"
            "- [ ] green: write minimal code to pass test\n"
            "- [ ] green: re-run targeted test and confirm pass\n"
            "- [ ] refactor: clean implementation without behavior change\n"
            "- [ ] verify: run full test suite\n"
        )
    _write_if_missing(
        idea_path,
        "goal: \"tdd\"\n"
        "constraints: []\n"
        "acceptance: []\n"
        "risk:\n"
        "  security: []\n"
        "  performance: []\n"
        "  compatibility: []\n"
        "evidence_required:\n"
        "  tests: []\n"
        "  security_scans: []\n"
        "  reproducibility: []\n"
        "  artifacts: []\n",
    )
    return [
        os.path.relpath(plan_path, project_dir),
        os.path.relpath(checklist_path, project_dir),
        os.path.relpath(idea_path, project_dir),
    ]


def dispatch_compat_skill(
    *,
    skill: str,
    problem: str = "",
    context: str = "",
    files: list[str] | None = None,
    expected_outcome: str = "",
    project_dir: str | None = None,
) -> dict[str, Any]:
    normalized = skill.strip()
    root = _project_dir(project_dir)

    def _emit(payload: dict[str, Any]) -> dict[str, Any]:
        _append_audit_event(
            root,
            {
                "event": DEFAULT_EVENT_DISPATCH,
                "skill": normalized,
                "route": payload.get("route", ""),
                "status": payload.get("status", "unknown"),
                "routed_to": payload.get("routed_to", ""),
                "problem_chars": len(problem),
                "context_chars": len(context),
                "file_count": len(files or []),
            },
        )
        return payload

    def _res(**kwargs: Any) -> dict[str, Any]:
        return _emit(_result(**kwargs))

    if not normalized:
        return _res(
            skill=skill,
            route="unknown",
            status="error",
            findings=["Missing skill name."],
            actions=["Provide --skill value."],
        )

    route = LEGACY_SKILL_ROUTES.get(normalized)
    if route is None:
        return _res(
            skill=normalized,
            route="unknown",
            status="error",
            findings=[f"Unsupported skill: {normalized}"],
            actions=["Use `omg compat list` to see supported skill names."],
        )

    is_valid, reason = validate_compat_request(
        skill=normalized,
        problem=problem,
        context=context,
        files=files,
        expected_outcome=expected_outcome,
    )
    if not is_valid:
        return _res(
            skill=normalized,
            route=route,
            status="error",
            findings=[f"Invalid request: {reason}"],
            actions=["Adjust inputs and retry."],
        )

    _append_audit_event(
        root,
        {
            "event": DEFAULT_EVENT_REQUEST,
            "skill": normalized,
            "route": route,
            "problem_chars": len(problem),
            "context_chars": len(context),
            "file_count": len(files or []),
        },
    )

    msg = problem or f"compat dispatch via {normalized}"
    file_list = files or []

    if route == "teams":
        req = TeamDispatchRequest(
            target="auto",
            problem=msg,
            context=context,
            files=file_list,
            expected_outcome=expected_outcome,
        )
        team = dispatch_team(req).to_dict()
        return _res(
            skill=normalized,
            route=route,
            routed_to=str(team.get("evidence", {}).get("target", "")),
            findings=["Team route dispatched."],
            actions=["Review findings and apply selected actions."],
            result=team,
        )

    if route == "ccg":
        req = TeamDispatchRequest(
            target="ccg",
            problem=msg,
            context=context,
            files=file_list,
            expected_outcome=expected_outcome,
        )
        ccg = dispatch_team(req).to_dict()
        return _res(
            skill=normalized,
            route=route,
            routed_to="ccg",
            findings=["CCG route dispatched."],
            actions=["Review merged action plan."],
            result=ccg,
        )

    if route == "runtime_ship":
        runtime = dispatch_runtime(
            "claude",
            {"goal": msg, "constraints": [], "acceptance": [expected_outcome] if expected_outcome else []},
        )
        status = "ok" if runtime.get("status") == "ok" else "error"
        artifacts: list[str] = []
        if normalized in {"autopilot", "ralph", "ultrapilot", "ultrawork"}:
            persistent = _write_persistent_state(
                root,
                mode=normalized,
                goal=msg,
                context=context,
                expected_outcome=expected_outcome,
                runtime_result=runtime,
            )
            artifacts.append(os.path.relpath(persistent, root))
        if normalized == "release" and status == "ok":
            rel = _write_release_artifact(root, msg)
            artifacts.append(os.path.relpath(rel, root))
        if normalized == "build-fix" and status == "ok":
            build_fix = _write_build_fix_artifact(root, msg)
            artifacts.append(os.path.relpath(build_fix, root))
        return _res(
            skill=normalized,
            route=route,
            status=status,
            routed_to="claude",
            findings=["Runtime dispatch completed." if status == "ok" else "Runtime dispatch failed."],
            actions=[
                "Inspect runtime response and continue.",
                "If persistent mode is active, keep iterating until checklist completion.",
            ],
            result=runtime,
            artifacts=artifacts,
        )

    if route == "pipeline":
        pipeline = run_pipeline(
            {
                "dataset": {"source": "clean-source", "license": "mit"},
                "base_model": {"source": "open-model", "allow_distill": True},
                "target_metric": 0.7,
                "simulated_metric": 0.8,
                "evaluation_notes": f"compat:{normalized}",
            }
        )
        status = "ok" if pipeline.get("status") in {"ready", "published"} else "error"
        return _res(
            skill=normalized,
            route=route,
            status=status,
            findings=["Pipeline route executed."],
            actions=["Use `omg lab eval` when evaluation is ready."],
            result=pipeline,
        )

    if route == "memory":
        if normalized == "project-session-manager":
            session = _update_session_state(root, msg)
            return _res(
                skill=normalized,
                route=route,
                findings=["Session state updated."],
                actions=["Use session state to continue long-running work."],
                artifacts=[os.path.relpath(session, root)],
            )
        if normalized == "writer-memory":
            writer = _append_knowledge_note(
                root,
                "knowledge/writer-memory.md",
                f"- [{_now()}] {msg}",
            )
            return _res(
                skill=normalized,
                route=route,
                findings=["Writer memory updated."],
                actions=["Reuse writer-memory notes for long-form drafting."],
                artifacts=[os.path.relpath(writer, root)],
            )
        if normalized == "note":
            note = _append_knowledge_note(
                root,
                "knowledge/notes.md",
                f"- [{_now()}] {msg}",
            )
            return _res(
                skill=normalized,
                route=route,
                findings=["Note appended to knowledge log."],
                actions=["Review notes during planning and handoff."],
                artifacts=[os.path.relpath(note, root)],
            )
        wm_path = _append_memory(root, msg)
        return _res(
            skill=normalized,
            route=route,
            findings=["Working memory updated."],
            actions=["Continue work with refreshed context."],
            artifacts=[os.path.relpath(wm_path, root)],
        )

    if route == "init":
        artifacts = _init_bootstrap(root, msg)
        return _res(
            skill=normalized,
            route=route,
            findings=["OMG layout initialized."],
            actions=["Run `omg compat run --skill omg-doctor` to verify health."],
            artifacts=artifacts,
        )

    if route == "health":
        if normalized == "omg-doctor":
            doctor_result = run_doctor(root_dir=Path(root))
            snapshot = {
                "project_dir": root,
                "status": doctor_result["status"],
                "checks": doctor_result["checks"],
            }
            return _res(
                skill=normalized,
                route=route,
                findings=["Doctor verification completed."],
                actions=["Fix any blocker checks before shipping."],
                result=snapshot,
            )
        snapshot = _health_snapshot(root)
        return _res(
            skill=normalized,
            route=route,
            findings=["Health snapshot generated."],
            actions=["Create missing .omg folders if any field is false."],
            result=snapshot,
        )

    if route == "help":
        return _res(
            skill=normalized,
            route=route,
            findings=["Compatibility help generated."],
            actions=["Run `omg compat list`, `omg compat contract --all`, then `omg compat run --skill <name>`."],
            result={
                "supported_skills": list_compat_skills(),
                "gap_report_hint": DEFAULT_GAP_REPORT_PATH,
            },
        )

    if route == "review":
        if normalized in {"review", "code-review", "ultraqa"}:
            review = _run_dual_review(msg, context, file_list, expected_outcome)
            routed_to = "codex+ccg"
            findings = ["Dual-track review route dispatched."]
        else:
            req = TeamDispatchRequest(
                target="codex",
                problem=f"review: {msg}",
                context=context,
                files=file_list,
                expected_outcome=expected_outcome,
            )
            review = dispatch_team(req).to_dict()
            routed_to = "codex"
            findings = ["Review route dispatched."]
        return _res(
            skill=normalized,
            route=route,
            routed_to=routed_to,
            findings=findings,
            actions=["Address high-risk findings first."],
            result=review,
        )

    if route == "plan":
        if normalized == "tdd":
            artifacts = _ensure_tdd_artifacts(root, msg)
            findings = ["TDD artifacts are ready (red-green-refactor)."]
            actions = ["Execute checklist in strict red -> green -> refactor order."]
        else:
            artifacts = _ensure_plan_artifacts(root, msg)
            findings = ["Plan artifacts are ready."]
            actions = ["Refine _plan/_checklist then execute with evidence."]
        return _res(
            skill=normalized,
            route=route,
            findings=findings,
            actions=actions,
            artifacts=artifacts,
        )

    if route == "secure":
        decision = evaluate_bash_command(problem or "echo safe")
        return _res(
            skill=normalized,
            route=route,
            findings=["Security policy evaluation completed."],
            actions=["If action is deny, revise command and retry."],
            result=decision.to_dict(),
        )

    if route == "security_check":
        check = run_security_check(
            project_dir=root,
            scope=msg or ".",
            include_live_enrichment=False,
        )
        return _res(
            skill=normalized,
            route=route,
            findings=["Canonical OMG security check completed."],
            actions=["Review high-severity findings before ship/release."],
            result=check,
        )

    if route == "learn":
        if normalized in {"learn-about-omg", "learner", "skill"}:
            learn_path = _write_learning_artifact(root, normalized, msg, context)
            return _res(
                skill=normalized,
                route=route,
                findings=["Learning artifact recorded."],
                actions=["Promote stable patterns from learning artifacts into reusable commands/skills."],
                artifacts=[os.path.relpath(learn_path, root)],
            )
        note_path = _append_memory(root, f"learn: {msg}")
        return _res(
            skill=normalized,
            route=route,
            findings=["Learning note recorded."],
            actions=["Review .omg/state/working-memory.md for accumulated insights."],
            artifacts=[os.path.relpath(note_path, root)],
        )

    if route == "maintainer":
        if normalized in {"analyze", "trace", "sci-omg"}:
            artifact = _write_analysis_artifact(root, normalized, msg, context, file_list)
            return _res(
                skill=normalized,
                route=route,
                findings=["Analysis artifact generated."],
                actions=["Use findings to create targeted fix/review tasks."],
                artifacts=[os.path.relpath(artifact, root)],
            )
        artifact = _write_maintainer_artifact(root, normalized, msg)
        return _res(
            skill=normalized,
            route=route,
            findings=["Maintainer artifact generated."],
            actions=["Attach artifact to maintainer workflow or release notes."],
            artifacts=[os.path.relpath(artifact, root)],
        )

    if route == "cancel":
        active_path = os.path.join(root, ".omg", "shadow", "active-run")
        if os.path.exists(active_path):
            os.remove(active_path)
        persistent_path = os.path.join(root, ".omg", "state", "persistent-mode.json")
        if os.path.exists(persistent_path):
            try:
                with open(persistent_path, "r", encoding="utf-8") as f:
                    persistent = json.load(f)
                if isinstance(persistent, dict):
                    persistent["status"] = "cancelled"
                    persistent["last_updated"] = _now()
                    with open(persistent_path, "w", encoding="utf-8") as f:
                        json.dump(persistent, f, indent=2, ensure_ascii=True)
            except Exception:
                pass
        return _res(
            skill=normalized,
            route=route,
            findings=["Active run state cleared."],
            actions=["Start a new run when ready."],
        )

    return _res(
        skill=normalized,
        route=route,
        status="error",
        findings=["Route exists but has no handler."],
        actions=["Implement missing handler."],
    )


def list_omg_skills() -> list[str]:
    return list_compat_skills()


def list_omg_skill_contracts() -> list[dict[str, Any]]:
    return list_compat_skill_contracts()


def get_omg_skill_contract(skill: str) -> dict[str, Any] | None:
    return get_compat_skill_contract(skill)


def build_omg_gap_report(project_dir: str | None = None) -> dict[str, Any]:
    return build_compat_gap_report(project_dir)


def validate_omg_request(
    *,
    skill: str,
    problem: str,
    context: str,
    files: list[str] | None,
    expected_outcome: str,
) -> tuple[bool, str]:
    return validate_compat_request(
        skill=skill,
        problem=problem,
        context=context,
        files=files,
        expected_outcome=expected_outcome,
    )


def dispatch_omg_skill(
    *,
    skill: str,
    problem: str = "",
    context: str = "",
    files: list[str] | None = None,
    expected_outcome: str = "",
    project_dir: str | None = None,
) -> dict[str, Any]:
    return dispatch_compat_skill(
        skill=skill,
        problem=problem,
        context=context,
        files=files,
        expected_outcome=expected_outcome,
        project_dir=project_dir,
    )
