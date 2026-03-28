#!/usr/bin/env python3
"""OMG CLI entrypoint.

Implements practical command-line flows for:
- omg ship
- omg fix --issue
- omg secure
- omg security check
- omg maintainer
- omg trust review
- omg runtime dispatch
- omg lab train / omg lab eval
- omg forge run
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any, cast

# --- Path resolution (never relies on CWD) ---
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = Path(SCRIPTS_DIR).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if sys.version_info < (3, 10):
    sys.exit(
        "\n\u274c OMG requires Python 3.10 or newer.\n"
        "   Found: Python {}.{}\n"
        "   Install Python 3.10+ and ensure 'python3' resolves to it.\n".format(
            sys.version_info.major, sys.version_info.minor
        )
    )

from hooks._common import bootstrap_runtime_paths

bootstrap_runtime_paths(__file__)

from hooks.policy_engine import evaluate_bash_command
from hooks.shadow_manager import create_evidence_pack
from hooks.trust_review import review_config_change, write_trust_manifest
from lab.pipeline import publish_artifact, run_pipeline, run_pipeline_with_evidence
from runtime.forge_agents import dispatch_specialists, resolve_specialists
from runtime.forge_contracts import load_forge_mvp, validate_forge_job
from runtime.forge_run_id import normalize_run_id
from runtime.issue_surface import IssueSurface
from runtime.dispatcher import dispatch_runtime
from runtime.api_twin import ingest_contract, record_fixture, serve_fixture, verify_fixture
from runtime.data_lineage import build_lineage_manifest
from runtime.eval_gate import evaluate_trace
from runtime.incident_replay import build_incident_pack
from runtime.domain_packs import get_domain_pack_contract
from runtime.doc_generator import generate_docs, check_docs, GENERATED_ARTIFACTS
from runtime.release_artifact_audit import (
    format_release_audit_text,
    resolve_github_token,
    run_release_artifact_audit,
)
from runtime.preflight import run_preflight
from runtime.remote_supervisor import issue_local_supervisor_session, verify_local_supervisor_token
from runtime.security_check import run_security_check
from runtime.contract_compiler import (
    build_release_readiness,
    compile_contract_outputs,
    compile_method_artifacts,
    validate_contract_registry,
)
from runtime.tracebank import record_trace
from runtime.compat import (
    DEFAULT_CONTRACT_SNAPSHOT_PATH,
    DEFAULT_GAP_REPORT_PATH,
    build_contract_snapshot_payload,
    build_compat_gap_report,
    dispatch_compat_skill,
    get_compat_skill_contract,
    list_compat_skill_contracts,
    list_compat_skills,
    run_doctor,
    run_doctor_fix,
    run_env_doctor,
)
from runtime.validate import run_validate, format_text as validate_format_text
from runtime.plugin_diagnostics import approve_plugin, run_plugin_diagnostics
from runtime.adoption import CANONICAL_VERSION, VALID_PRESETS, VALID_PRESETS_ALL, PRESET_HOOK_COUNT, PRESET_HOOK_MAPPING
from runtime.install_planner import compute_install_plan, execute_plan, InstallAction
from runtime.canonical_surface import get_canonical_hosts
from runtime.ecosystem import ecosystem_status, list_ecosystem_repos, sync_ecosystem_repos
from runtime.team_router import TeamDispatchRequest, dispatch_team, execute_ccg_mode, execute_crazy_mode
from runtime.release_run_coordinator import resolve_current_run_id
from runtime.subscription_tiers import detect_tier
from runtime.policy_pack_loader import list_policy_packs, load_policy_pack


CANONICAL_HOST_CHOICES = tuple(get_canonical_hosts())


def _parse_simple_idea_yaml(path: str) -> dict[str, Any]:
    """Minimal parser for `.omg/idea.yml` template shape."""
    idea: dict[str, Any] = {
        "goal": "",
        "constraints": [],
        "acceptance": [],
        "risk": {"security": [], "performance": [], "compatibility": []},
        "evidence_required": {"tests": [], "security_scans": [], "reproducibility": [], "artifacts": []},
    }
    section: str | None = None
    subsection: str | None = None

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("goal:"):
                idea["goal"] = stripped.split(":", 1)[1].strip().strip("\"'")
                section = None
                subsection = None
                continue

            if stripped in {"constraints:", "acceptance:", "risk:", "evidence_required:"}:
                section = stripped[:-1]
                subsection = None
                continue

            if section in {"risk", "evidence_required"} and stripped.endswith(":") and not stripped.startswith("- "):
                subsection = stripped[:-1]
                continue

            if stripped.startswith("- "):
                value = stripped[2:].strip().strip("\"'")
                if section in {"constraints", "acceptance"}:
                    idea[section].append(value)
                elif section in {"risk", "evidence_required"} and subsection:
                    idea[section].setdefault(subsection, []).append(value)

    return idea


def _load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return data


def _ensure_project_dir() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def _now_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def cmd_ship(args: argparse.Namespace) -> int:
    project_dir = _ensure_project_dir()
    release_audit = run_release_artifact_audit(
        ROOT_DIR,
        repo="trac3r00/OMG",
        version=CANONICAL_VERSION,
        github_token=resolve_github_token(),
    )
    if release_audit.get("overall_status") != "ok":
        print(json.dumps({
            "status": "error",
            "error_code": "RELEASE_AUDIT_BLOCKED",
            "message": "Release artifact audit drift blocks omg ship.",
            "release_audit": release_audit,
        }, indent=2))
        return 2
    idea_path = args.idea
    idea = _parse_simple_idea_yaml(idea_path) if idea_path.endswith((".yml", ".yaml")) else _load_json(idea_path)

    runtime = args.runtime
    dispatched = dispatch_runtime(runtime, idea)
    if dispatched.get("status") != "ok":
        print(json.dumps(dispatched, indent=2))
        return 2

    run_id = args.run_id or _now_run_id()
    verification = dispatched.get("verification", {})
    checks = verification.get("checks", []) if isinstance(verification, dict) else []
    preflight = run_preflight(project_dir, goal=str(idea.get("goal", "")))
    security_result = run_security_check(project_dir=project_dir, scope=".")
    trace = record_trace(
        project_dir,
        trace_type="ship",
        route=preflight["route"],
        status="ok",
        plan=dispatched.get("plan", {}),
        verify=verification if isinstance(verification, dict) else {},
        metadata={"runtime": runtime, "run_id": run_id},
    )
    eval_result = evaluate_trace(
        project_dir,
        trace_id=trace["trace_id"],
        suites=["planning", "security"],
        metrics={
            "planning": 1.0 if dispatched.get("status") == "ok" else 0.0,
            "security": max(float(security_result["trust_scores"].get("overall", 0.0)), 0.0),
        },
    )
    lineage = build_lineage_manifest(
        project_dir,
        artifact_type="evidence-pack",
        sources=[{"kind": "repo", "path": ".", "license": "MIT"}],
        privacy="internal",
        license="MIT",
        derivation={"trace_id": trace["trace_id"], "route": preflight["route"], "eval_path": eval_result["path"]},
        trace_id=trace["trace_id"],
    )
    evidence_path = create_evidence_pack(
        project_dir,
        run_id,
        tests=checks if isinstance(checks, list) else [],
        security_scans=security_result.get("security_scans", []),
        diff_summary={"runtime": runtime, "goal": idea.get("goal", "")},
        reproducibility={"command": f"omg ship --runtime {runtime} --idea {idea_path}"},
        unresolved_risks=security_result.get("unresolved_risks", []),
        provenance=security_result["provenance"],
        trust_scores=security_result["trust_scores"],
        api_twin={"recommended_route": preflight["route"] if preflight["route"] == "api-twin" else ""},
        route_metadata=preflight,
        trace_ids=[trace["trace_id"]],
        lineage=lineage,
    )

    out = {
        "status": "ok",
        "command": "ship",
        "runtime": runtime,
        "run_id": run_id,
        "goal": idea.get("goal", ""),
        "evidence_path": os.path.relpath(evidence_path, project_dir),
        "trace_id": trace["trace_id"],
        "eval_path": eval_result["path"],
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_fix(args: argparse.Namespace) -> int:
    project_dir = _ensure_project_dir()
    issue_surface = IssueSurface(project_dir=project_dir)
    scan_run_id = f"fix-{_sanitize_token(args.issue)}-{_now_run_id()}"
    issue_report = issue_surface.scan(
        scan_run_id,
        surfaces=["live_session", "plugin_interop", "governed_tools", "forge_runs"],
    )
    goal = f"Fix issue {args.issue}"
    dispatched = dispatch_runtime(args.runtime, {"goal": goal, "acceptance": [f"issue-{args.issue}-resolved"]})
    dispatched["issue_surface"] = {
        "run_id": issue_report.run_id,
        "report_path": str(issue_report.summary.get("report_path", "")),
        "summary": issue_report.summary,
    }
    print(json.dumps(dispatched, indent=2))
    return 0 if dispatched.get("status") == "ok" else 2


def cmd_issue(args: argparse.Namespace) -> int:
    run_id = args.run_id or _now_run_id()
    surfaces = [item.strip() for item in str(args.surfaces).split(",") if item.strip()]
    issue_surface = IssueSurface(project_dir=_ensure_project_dir())
    report = issue_surface.scan(run_id, surfaces=surfaces or None)

    result: dict[str, Any] = {
        "schema": "IssueCommandResult",
        "status": "ok",
        "run_id": run_id,
        "report_path": str(report.summary.get("report_path", "")),
        "report": report.to_dict(),
    }
    if args.simulate_surface and args.simulate_scenario:
        result["simulation"] = issue_surface.simulate_failure(args.simulate_surface, args.simulate_scenario)
    print(json.dumps(result, indent=2))
    return 0


def cmd_secure(args: argparse.Namespace) -> int:
    decision = evaluate_bash_command(args.command)
    print(json.dumps(decision.to_dict(), indent=2))
    return 0 if decision.action != "deny" else 3


def cmd_undo(args: argparse.Namespace) -> int:
    from runtime.interaction_journal import InteractionJournal

    project_dir = _ensure_project_dir()
    run_id = resolve_current_run_id(project_dir=project_dir)
    result = InteractionJournal(project_dir).undo(args.step_id, run_id=run_id)
    print(json.dumps(result, indent=2))
    return 2 if result.get("status") == "rollback_failed" else 0


def cmd_security_check(args: argparse.Namespace) -> int:
    waivers = json.loads(args.waivers_json) if args.waivers_json else None
    result = run_security_check(
        project_dir=_ensure_project_dir(),
        scope=args.scope,
        include_live_enrichment=bool(args.live_enrichment),
        waivers=waivers,
    )
    print(json.dumps(result, indent=2))
    return 0


def _sanitize_token(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(value).strip())
    return cleaned or "unknown"


def cmd_waive_tests(args: argparse.Namespace) -> int:
    project_dir = _ensure_project_dir()
    issued_at = datetime.now(timezone.utc).isoformat()
    lock_id = str(args.lock_id).strip()
    reason = str(args.reason).strip()
    run_id = resolve_current_run_id(project_dir=project_dir)

    evidence_dir = Path(project_dir) / ".omg" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    artifact_name = f"waiver-tests-{_sanitize_token(lock_id)}-{_now_run_id()}.json"
    artifact_path = evidence_dir / artifact_name
    artifact_rel_path = str(artifact_path.relative_to(project_dir)).replace("\\", "/")

    payload = {
        "schema": "WaiverEvidence",
        "schema_version": 1,
        "lock_id": lock_id,
        "run_id": run_id,
        "reason": reason,
        "issued_at": issued_at,
        "artifact_path": artifact_rel_path,
    }
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(payload, indent=2))
    return 0


def cmd_api_twin_ingest(args: argparse.Namespace) -> int:
    result = ingest_contract(_ensure_project_dir(), name=args.name, source_path=args.source)
    print(json.dumps(result, indent=2))
    return 0


def cmd_api_twin_record(args: argparse.Namespace) -> int:
    result = record_fixture(
        _ensure_project_dir(),
        name=args.name,
        endpoint=args.endpoint,
        cassette_version=args.cassette_version,
        request=json.loads(args.request_json),
        response=json.loads(args.response_json),
        validated=bool(args.validated),
        redactions=json.loads(args.redactions_json) if args.redactions_json else None,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_api_twin_serve(args: argparse.Namespace) -> int:
    result = serve_fixture(
        _ensure_project_dir(),
        name=args.name,
        endpoint=args.endpoint,
        cassette_version=args.cassette_version,
        latency_ms=int(args.latency_ms),
        failure_mode=args.failure_mode,
        schema_drift=bool(args.schema_drift),
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_api_twin_verify(args: argparse.Namespace) -> int:
    result = verify_fixture(
        _ensure_project_dir(),
        name=args.name,
        endpoint=args.endpoint,
        cassette_version=args.cassette_version,
        live_response=json.loads(args.live_response_json),
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    result = run_preflight(_ensure_project_dir(), goal=args.goal)
    print(json.dumps(result, indent=2))
    return 0


def _emit_not_implemented_stub(command: str, *, details: dict[str, Any] | None = None) -> int:
    payload: dict[str, Any] = {
        "schema": "OperatorContractStub",
        "status": "not_implemented",
        "error_code": "NOT_YET_IMPLEMENTED",
        "command": command,
        "message": f"{command} is registered but not yet implemented",
    }
    if details:
        payload.update(details)
    print(json.dumps(payload, indent=2))
    return 2


def cmd_resolve_policy(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "json")
    provider = getattr(args, "provider", "claude")

    tier_result = detect_tier(provider, project_dir=_ensure_project_dir())

    pack_ids = list_policy_packs()
    packs: list[dict[str, Any]] = []
    for pack_id in pack_ids:
        try:
            pack = load_policy_pack(pack_id)
            packs.append(dict(pack))
        except Exception:
            packs.append({"id": pack_id, "error": "failed_to_load"})

    effective_policy: dict[str, Any] = {
        "tool_restrictions": [],
        "network_posture": "open",
        "approval_threshold": 1,
        "protected_paths": [],
        "evidence_requirements": [],
        "data_sharing": "allowed",
    }

    overrides: list[dict[str, Any]] = []
    for pack in packs:
        if "error" in pack:
            continue
        for list_field in ("tool_restrictions", "protected_paths", "evidence_requirements"):
            pack_values = pack.get(list_field, [])
            if not isinstance(pack_values, list):
                continue
            existing = effective_policy.get(list_field, [])
            for v in pack_values:
                if v not in existing:
                    existing.append(v)
                    overrides.append({"field": list_field, "value": v, "source": pack.get("id", "unknown")})
            effective_policy[list_field] = existing

        for scalar_field in ("network_posture", "data_sharing"):
            pack_value = pack.get(scalar_field)
            if pack_value and pack_value != effective_policy.get(scalar_field):
                overrides.append({
                    "field": scalar_field,
                    "old_value": effective_policy[scalar_field],
                    "new_value": pack_value,
                    "source": pack.get("id", "unknown"),
                })
                effective_policy[scalar_field] = pack_value

        pack_threshold = pack.get("approval_threshold", 1)
        if isinstance(pack_threshold, int) and pack_threshold > effective_policy["approval_threshold"]:
            overrides.append({
                "field": "approval_threshold",
                "old_value": effective_policy["approval_threshold"],
                "new_value": pack_threshold,
                "source": pack.get("id", "unknown"),
            })
            effective_policy["approval_threshold"] = pack_threshold

    provenance: list[dict[str, Any]] = [
        {
            "source": "tier_detection",
            "provider": provider,
            "tier": tier_result["tier"],
            "confidence": tier_result["confidence"],
            "provenance": tier_result["provenance"],
        },
    ]
    for pack in packs:
        provenance.append({
            "source": "policy_pack",
            "pack_id": pack.get("id", ""),
            "description": pack.get("description", ""),
        })

    output: dict[str, Any] = {
        "schema": "EffectivePolicy",
        "tier": dict(tier_result),
        "channel": "public",
        "preset": "balanced",
        "packs": [{"id": p.get("id", ""), "description": p.get("description", "")} for p in packs],
        "effective_policy": effective_policy,
        "overrides": overrides,
        "provenance": provenance,
    }

    if fmt == "json":
        print(json.dumps(output, indent=2))
    else:
        print("=== Effective Policy ===")
        print(f"Tier: {tier_result['tier']} (confidence: {tier_result['confidence']:.2f})")
        print("Channel: public")
        print("Preset: balanced")
        if packs:
            print(f"\nActive packs ({len(packs)}):")
            for p in packs:
                print(f"  - {p.get('id', '')}: {p.get('description', '')}")
        if overrides:
            print(f"\nOverrides ({len(overrides)}):")
            for o in overrides:
                print(f"  {o['field']}: {o.get('value', o.get('new_value', ''))} (from {o['source']})")
    return 0


def cmd_policy_pack_list(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "json")
    pack_ids = list_policy_packs()
    packs: list[dict[str, Any]] = []
    for pack_id in pack_ids:
        try:
            pack = load_policy_pack(pack_id)
            packs.append(dict(pack))
        except Exception:
            packs.append({"id": pack_id, "error": "failed_to_load"})

    output: dict[str, Any] = {
        "schema": "PolicyPackList",
        "packs": packs,
        "count": len(packs),
    }
    if fmt == "json":
        print(json.dumps(output, indent=2))
    else:
        print(f"Policy Packs ({len(packs)}):")
        for p in packs:
            print(f"  - {p.get('id', 'unknown')}: {p.get('description', 'N/A')}")
    return 0


def cmd_policy_pack_diff(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "json")
    pack_id = getattr(args, "pack_id", "")
    if not pack_id:
        err = {"schema": "PolicyPackDiff", "status": "error", "reason": "pack_id is required"}
        print(json.dumps(err, indent=2) if fmt == "json" else f"Error: {err['reason']}")
        return 1
    try:
        pack = load_policy_pack(pack_id)
    except Exception:
        err = {"schema": "PolicyPackDiff", "status": "error", "reason": f"pack '{pack_id}' not found"}
        print(json.dumps(err, indent=2) if fmt == "json" else f"Error: {err['reason']}")
        return 1
    pack_dict = dict(pack)
    overrides = pack_dict.get("overrides", pack_dict.get("tool_restrictions", []))
    output: dict[str, Any] = {
        "schema": "PolicyPackDiff",
        "status": "ok",
        "pack_id": pack_id,
        "description": pack_dict.get("description", ""),
        "overrides": overrides,
        "fields_affected": len(overrides) if isinstance(overrides, list) else 0,
    }
    if fmt == "json":
        print(json.dumps(output, indent=2))
    else:
        print(f"Policy Pack Diff: {pack_id}")
        print(f"  Description: {output['description']}")
        print(f"  Overrides ({output['fields_affected']}):")
        if isinstance(overrides, list):
            for o in overrides:
                print(f"    - {o}")
    return 0


def cmd_policy_pack_scaffold(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "json")
    pack_id = getattr(args, "pack_id", "new-pack")
    scaffold: dict[str, Any] = {
        "schema": "PolicyPackScaffold",
        "status": "ok",
        "pack_id": pack_id,
        "template": {
            "id": pack_id,
            "description": f"Custom policy pack: {pack_id}",
            "overrides": {},
            "tool_restrictions": [],
            "required_evidence": [],
        },
        "output_path": f"registry/policy-packs/{pack_id}.yaml",
    }
    if fmt == "json":
        print(json.dumps(scaffold, indent=2))
    else:
        import yaml as yaml_mod
        print(f"Scaffold for policy pack '{pack_id}':")
        print(f"  Output: {scaffold['output_path']}")
        print("  Template:")
        print(yaml_mod.dump(scaffold["template"], default_flow_style=False, indent=2))
    return 0


def cmd_policy_pack_keygen(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "json")
    output_path = getattr(args, "output", None)
    add_to_trust_root = getattr(args, "add_to_trust_root", False)

    from registry.verify_artifact import _load_ed25519_backend, _key_id_from_public_key

    try:
        serialization, Ed25519PrivateKey, _ = _load_ed25519_backend()
    except ModuleNotFoundError as exc:
        print(json.dumps({"schema": "PolicyPackKeygen", "status": "error", "error": str(exc)}))
        return 1

    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    key_id = _key_id_from_public_key(public_key_raw)
    private_b64 = base64.b64encode(private_raw).decode("ascii")
    public_b64 = base64.b64encode(public_key_raw).decode("ascii")

    keypair: dict[str, Any] = {
        "key_id": key_id,
        "algorithm": "ed25519-minisign",
        "private_key": private_b64,
        "public_key": public_b64,
    }

    written_path: str | None = None
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(keypair, indent=2) + "\n", encoding="utf-8")
        written_path = str(out)

    if add_to_trust_root:
        trust_root_path = ROOT_DIR / "registry" / "trusted_signers.json"
        try:
            trust_root: dict[str, Any] = json.loads(trust_root_path.read_text(encoding="utf-8"))
        except Exception:
            trust_root = {"version": 1, "signers": []}

        signer_entry: dict[str, Any] = {
            "key_id": key_id,
            "algorithm": "ed25519-minisign",
            "public_key": public_b64,
            "status": "active",
            "usage": ["dev", "test", "offline-attestation"],
            "owner": "omg-local",
            "notes": "Generated by policy-pack keygen",
        }
        signers_list: list[Any] = trust_root.get("signers", [])
        existing_ids = {s.get("key_id") for s in signers_list if isinstance(s, dict)}
        if key_id not in existing_ids:
            signers_list.append(signer_entry)
            trust_root["signers"] = signers_list
            trust_root_path.write_text(json.dumps(trust_root, indent=2) + "\n", encoding="utf-8")

    output: dict[str, Any] = {
        "schema": "PolicyPackKeygen",
        "status": "ok",
        "key_id": key_id,
        "algorithm": "ed25519-minisign",
        "public_key": public_b64,
    }
    if written_path:
        output["output_path"] = written_path

    if fmt == "json":
        print(json.dumps(output, indent=2))
    else:
        print("Generated Ed25519 keypair:")
        print(f"  Key ID: {key_id}")
        print("  Algorithm: ed25519-minisign")
        print(f"  Public key: {public_b64}")
        if written_path:
            print(f"  Written to: {written_path}")
        if add_to_trust_root:
            print("  Added to trust root: registry/trusted_signers.json")
    return 0


def cmd_policy_pack_sign(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "json")
    pack_id = getattr(args, "pack_id", "")
    key_id = getattr(args, "key_id", None)
    key_path = getattr(args, "key_path", None)

    from registry.approval_artifact import create_approval_artifact
    from registry.verify_artifact import (
        _canonical_json, _DEFAULT_DEV_SIGNER_KEY_ID, _load_trusted_signers,
        _load_ed25519_backend, _key_id_from_public_key,
    )

    if not key_id:
        signers = _load_trusted_signers()
        key_id = next(iter(signers), _DEFAULT_DEV_SIGNER_KEY_ID) if signers else _DEFAULT_DEV_SIGNER_KEY_ID

    private_key = os.environ.get("OMG_SIGNING_KEY", "")
    if not private_key and key_path:
        try:
            key_data = Path(key_path).read_text(encoding="utf-8").strip()
            try:
                key_json = json.loads(key_data)
                if isinstance(key_json, dict) and "private_key" in key_json:
                    private_key = key_json["private_key"]
                    if not key_id or key_id == _DEFAULT_DEV_SIGNER_KEY_ID:
                        key_id = key_json.get("key_id", key_id)
                else:
                    private_key = key_data
            except json.JSONDecodeError:
                private_key = key_data
        except Exception as exc:
            print(json.dumps({"schema": "PolicyPackSign", "status": "error", "error": str(exc)}))
            return 1
    if not private_key:
        print(json.dumps({"schema": "PolicyPackSign", "status": "error",
                          "error": "no signing key: set OMG_SIGNING_KEY or --key-path"}))
        return 1

    try:
        pack = load_policy_pack(pack_id)
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"schema": "PolicyPackSign", "status": "error", "error": str(exc)}))
        return 1

    canonical = _canonical_json(dict(pack))
    digest = hashlib.sha256(canonical).hexdigest()

    try:
        approval = create_approval_artifact(
            artifact_digest=digest,
            action="policy-pack-sign",
            scope=f"policy-pack/{pack_id}",
            reason=f"Signing policy pack {pack_id}",
            signer_key_id=key_id,
            signer_private_key=private_key,
        )
    except Exception as exc:
        print(json.dumps({"schema": "PolicyPackSign", "status": "error", "error": str(exc)}))
        return 1

    packs_dir = ROOT_DIR / "registry" / "policy-packs"
    sig_path = packs_dir / f"{pack_id}.signature.json"
    lock_path = packs_dir / f"{pack_id}.lock.json"

    signature_artifact = asdict(approval)
    sig_path.write_text(json.dumps(signature_artifact, indent=2) + "\n", encoding="utf-8")

    # Derive signer public key from private key for lockfile attestation
    signer_public_key_b64 = ""
    try:
        serialization, Ed25519PrivateKey, _ = _load_ed25519_backend()
        private_raw = base64.b64decode(private_key, validate=True)
        priv_key_obj = Ed25519PrivateKey.from_private_bytes(private_raw)
        public_key_raw = priv_key_obj.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        signer_public_key_b64 = base64.b64encode(public_key_raw).decode("ascii")
    except Exception:
        pass  # Best-effort; lockfile still valid without public key

    lockfile = {
        "lockfile_version": 1,
        "pack_id": pack_id,
        "pack_path": f"registry/policy-packs/{pack_id}.yaml",
        "canonical_digest": digest,
        "signer_key_id": key_id,
        "signer_public_key": signer_public_key_b64,
        "algorithm": "ed25519-minisign",
        "signature_path": f"registry/policy-packs/{pack_id}.signature.json",
        "created_at": approval.issued_at,
    }
    lock_path.write_text(json.dumps(lockfile, indent=2) + "\n", encoding="utf-8")

    output: dict[str, Any] = {
        "schema": "PolicyPackSign",
        "status": "signed",
        "pack_id": pack_id,
        "canonical_digest": digest,
        "signer_key_id": key_id,
        "signature_path": str(sig_path.relative_to(ROOT_DIR)),
        "lock_path": str(lock_path.relative_to(ROOT_DIR)),
    }
    if fmt == "json":
        print(json.dumps(output, indent=2))
    else:
        print(f"Signed: {pack_id}")
        print(f"  Digest: {digest}")
        print(f"  Signer: {key_id}")
        print(f"  Signature: {sig_path.relative_to(ROOT_DIR)}")
        print(f"  Lock: {lock_path.relative_to(ROOT_DIR)}")
    return 0


def _verify_single_pack(pack_id: str) -> dict[str, Any]:
    from registry.approval_artifact import verify_approval_artifact
    from registry.verify_artifact import _canonical_json

    packs_dir = ROOT_DIR / "registry" / "policy-packs"
    lock_path = packs_dir / f"{pack_id}.lock.json"

    if not lock_path.exists():
        return {"status": "error", "pack_id": pack_id,
                "error": f"lockfile not found: {lock_path.relative_to(ROOT_DIR)}"}

    try:
        lockfile = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "error", "pack_id": pack_id, "error": str(exc)}

    sig_path = ROOT_DIR / lockfile.get("signature_path", "")
    if not sig_path.exists():
        return {"status": "error", "pack_id": pack_id,
                "error": f"signature not found: {lockfile.get('signature_path', '')}"}

    try:
        sig_artifact = json.loads(sig_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "error", "pack_id": pack_id, "error": str(exc)}

    try:
        pack = load_policy_pack(pack_id)
    except (FileNotFoundError, ValueError) as exc:
        return {"status": "error", "pack_id": pack_id, "error": str(exc)}

    canonical = _canonical_json(dict(pack))
    digest = hashlib.sha256(canonical).hexdigest()

    if digest != lockfile.get("canonical_digest", ""):
        return {"status": "tampered", "pack_id": pack_id,
                "error": "pack content changed since signing",
                "expected_digest": lockfile.get("canonical_digest", ""),
                "actual_digest": digest}

    result = verify_approval_artifact(sig_artifact, expected_artifact_digest=digest)
    if not result.get("valid"):
        return {"status": "failed", "pack_id": pack_id,
                "error": result.get("reason", "verification failed")}

    return {
        "status": "verified",
        "pack_id": pack_id,
        "canonical_digest": digest,
        "signer_key_id": lockfile.get("signer_key_id", ""),
    }


def cmd_policy_pack_verify(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "json")
    verify_all = getattr(args, "all", False)
    pack_id = getattr(args, "pack_id", "") or ""

    if verify_all:
        packs_dir = ROOT_DIR / "registry" / "policy-packs"
        lock_files = sorted(packs_dir.glob("*.lock.json"))
        if not lock_files:
            print(json.dumps({"schema": "PolicyPackVerifyAll", "status": "error",
                              "error": "no lockfiles found", "results": []}))
            return 1

        results: list[dict[str, Any]] = []
        all_ok = True
        for lf in lock_files:
            pid = lf.name.removesuffix(".lock.json")
            r = _verify_single_pack(pid)
            results.append(r)
            if r["status"] != "verified":
                all_ok = False

        output: dict[str, Any] = {
            "schema": "PolicyPackVerifyAll",
            "status": "verified" if all_ok else "failed",
            "total": len(results),
            "passed": sum(1 for r in results if r["status"] == "verified"),
            "failed": sum(1 for r in results if r["status"] != "verified"),
            "results": results,
        }
        if fmt == "json":
            print(json.dumps(output, indent=2))
        else:
            print(f"Verify all: {output['passed']}/{output['total']} passed")
            for r in results:
                status_icon = "OK" if r["status"] == "verified" else "FAIL"
                print(f"  [{status_icon}] {r['pack_id']}")
        return 0 if all_ok else 1

    if not pack_id:
        print(json.dumps({"schema": "PolicyPackVerify", "status": "error",
                          "error": "pack_id required (or use --all)"}))
        return 1

    r = _verify_single_pack(pack_id)
    r["schema"] = "PolicyPackVerify"
    if fmt == "json":
        print(json.dumps(r, indent=2))
    else:
        if r["status"] == "verified":
            print(f"Verified: {pack_id}")
            print(f"  Digest: {r.get('canonical_digest', '')}")
            print(f"  Signer: {r.get('signer_key_id', '')}")
        else:
            print(f"Failed: {pack_id}: {r.get('error', '')}")
    return 0 if r["status"] == "verified" else 1


def cmd_proof_summary(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "json")
    project_dir = _ensure_project_dir()

    from runtime.evidence_query import list_evidence_packs
    from runtime.evidence_narrator import narrate

    packs = list_evidence_packs(project_dir)

    if not packs:
        result: dict[str, Any] = {
            "schema": "ProofSummary",
            "status": "no_evidence",
            "claims": [],
            "evidence_list": [],
            "missing_artifacts": [],
            "rollback_status": "n/a",
            "next_actions": ["Run a task to generate evidence"],
        }
    else:
        latest = packs[0]
        narrative = narrate(cast(Any, latest))

        claims: list[Any] = []
        pack_claims = latest.get("claims")
        if isinstance(pack_claims, list):
            claims = pack_claims

        evidence_list: list[dict[str, Any]] = []
        artifacts = latest.get("artifacts")
        if isinstance(artifacts, list):
            for art in artifacts:
                if isinstance(art, dict):
                    evidence_list.append({
                        "kind": art.get("kind", ""),
                        "path": art.get("path", ""),
                        "summary": art.get("summary", ""),
                    })

        missing: list[str] = []
        requirements = latest.get("evidence_requirements")
        if isinstance(requirements, list):
            artifact_kinds = {str(a.get("kind", "")) for a in artifacts if isinstance(a, dict)} if isinstance(artifacts, list) else set()
            for req in requirements:
                if str(req) not in artifact_kinds:
                    missing.append(str(req))

        rollback_status = "n/a"
        unresolved = latest.get("unresolved_risks")
        if isinstance(unresolved, list) and unresolved:
            rollback_status = "risks_present"

        result = {
            "schema": "ProofSummary",
            "status": str(latest.get("status", "found")),
            "run_id": str(latest.get("run_id", "")),
            "claims": claims,
            "evidence_list": evidence_list,
            "missing_artifacts": missing,
            "rollback_status": rollback_status,
            "narrative": dict(narrative),
            "next_actions": narrative.get("next_actions", []),
        }

    if fmt == "json":
        print(json.dumps(result, indent=2))
    elif fmt == "text":
        from runtime.explainer_formatter import format_terminal as _fmt_term_proof

        narrative_dict = result.get("narrative", {
            "verdict_summary": result.get("status", "unknown"),
            "blockers_section": result.get("missing_artifacts", []),
            "provenance_note": None,
            "evidence_paths_section": [],
            "next_actions": result.get("next_actions", []),
        })
        print(_fmt_term_proof(narrative_dict))
    else:
        lines = ["# Proof Summary", ""]
        lines.append(f"**Status:** {result['status']}")
        if result.get("run_id"):
            lines.append(f"**Run ID:** {result['run_id']}")
        lines.append("")
        if result.get("claims"):
            lines.append("## Claims")
            for claim in result["claims"]:
                lines.append(f"- {claim}")
            lines.append("")
        if result.get("evidence_list"):
            lines.append("## Evidence")
            for ev in result["evidence_list"]:
                lines.append(f"- **{ev.get('kind', 'unknown')}**: {ev.get('summary', ev.get('path', ''))}")
            lines.append("")
        if result.get("missing_artifacts"):
            lines.append("## Missing Artifacts")
            for m in result["missing_artifacts"]:
                lines.append(f"- {m}")
            lines.append("")
        lines.append(f"**Rollback Status:** {result.get('rollback_status', 'n/a')}")
        lines.append("")
        if result.get("next_actions"):
            lines.append("## Next Actions")
            for action in result["next_actions"]:
                lines.append(f"- {action}")
        print("\n".join(lines))

    return 0


def cmd_explain_run(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "json")
    project_dir = _ensure_project_dir()
    run_id = str(args.run_id).strip()

    from runtime.evidence_query import get_evidence_pack, query_evidence

    pack = get_evidence_pack(project_dir, run_id)

    if pack is None:
        records = query_evidence(project_dir, run_id=run_id)
        if not records:
            result: dict[str, Any] = {
                "schema": "RunExplanation",
                "run_id": run_id,
                "status": "not_found",
            }
            print(json.dumps(result, indent=2))
            return 0
        evidence: list[dict[str, Any]] = list(records)
    else:
        evidence = [dict(pack)]

    result = {
        "schema": "RunExplanation",
        "run_id": run_id,
        "status": "found",
        "evidence_count": len(evidence),
        "evidence": evidence,
    }

    if fmt == "json":
        print(json.dumps(result, indent=2))
    elif fmt == "text" or fmt == "markdown":
        from runtime.evidence_narrator import narrate as _narrate_run
        from runtime.explainer_formatter import format_markdown as _fmt_md
        from runtime.explainer_formatter import format_terminal as _fmt_term

        narrative = _narrate_run(cast(Any, {"status": result["status"], "evidence_paths": {}, "blockers": [], "next_steps": []}))
        if fmt == "text":
            print(_fmt_term(dict(narrative)))
        else:
            print(_fmt_md(dict(narrative)))

    return 0


def cmd_blocked_last(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "text")
    project_dir = _ensure_project_dir()
    state_file = Path(project_dir) / ".omg" / "state" / "last-block-explanation.json"

    if not state_file.exists():
        print("No block explanation found — try running a tool to trigger governance.")
        return 0

    try:
        block = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("No block explanation found — state file unreadable.")
        return 0

    narrative: dict[str, Any] = {
        "verdict_summary": block.get("explanation", ""),
        "blockers_section": [block.get("reason_code", "unknown")],
        "next_actions": ["Review the blocked tool call and address the governance concern"],
        "evidence_paths_section": [],
        "provenance_note": f"Tool: {block.get('tool', '?')} | {block.get('timestamp', '')}",
    }

    if fmt == "markdown":
        from runtime.explainer_formatter import format_markdown as _fmt_md
        print(_fmt_md(narrative))
    else:
        from runtime.explainer_formatter import format_terminal as _fmt_term
        print(_fmt_term(narrative))

    return 0


def cmd_proof_open(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "markdown")
    project_dir = _ensure_project_dir()
    run_id_arg = getattr(args, "run_id", None)

    from runtime.evidence_query import list_evidence_packs
    from runtime.evidence_narrator import narrate as _narrate
    from runtime.explainer_formatter import format_markdown as _fmt_md
    from runtime.explainer_formatter import format_terminal as _fmt_term

    packs = list_evidence_packs(project_dir)

    if not packs:
        print("No evidence packs found. Run a governed task to generate evidence,")
        print("then re-run: omg proof open")
        return 0

    pack = packs[0]
    run_id = str(run_id_arg) if run_id_arg else str(pack.get("run_id", "unknown"))

    narrative = _narrate(cast(Any, pack))
    md = _fmt_md(dict(narrative))

    out = Path(project_dir) / ".omg" / "evidence" / f"proof-open-{run_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")

    print(f"proof-open: {run_id}")
    if fmt == "text":
        print(_fmt_term(dict(narrative)))
    else:
        print(md)

    return 0


def cmd_budget_simulate(args: argparse.Namespace) -> int:
    import uuid as _uuid

    project_dir = _ensure_project_dir()
    fmt = getattr(args, "format", "json")
    tier_input = str(getattr(args, "tier", "") or "").strip().lower()
    channel = str(getattr(args, "channel", "") or "public").strip()
    preset = str(getattr(args, "preset", "") or "balanced").strip()
    task_desc = str(getattr(args, "task", "") or "").strip()

    tier_detection = detect_tier(str(args.provider), project_dir=project_dir)
    tier = tier_input or str(tier_detection.get("tier", "free"))

    tier_token_limits: dict[str, int] = {
        "free": 10_000,
        "pro": 100_000,
        "team": 500_000,
        "enterprise_tier": 2_000_000,
    }
    token_limit = int(args.token_limit) if int(args.token_limit) > 0 else int(tier_token_limits.get(tier, 10_000))
    tokens_used = max(0, int(args.tokens_used))

    if bool(args.enforce):
        from runtime.budget_envelopes import get_budget_envelope_manager

        mgr = get_budget_envelope_manager(project_dir)
        temp_id = f"simulate-{_uuid.uuid4().hex[:8]}"

        mgr.create_envelope(temp_id, token_limit=token_limit)
        mgr.record_usage(temp_id, tokens=tokens_used)
        envelope_check = mgr.check_envelope(temp_id)

        try:
            mgr._envelope_path(temp_id).unlink(missing_ok=True)
        except OSError:
            pass

        result: dict[str, Any] = {
            "schema": "BudgetSimulateResult",
            "status": "blocked" if envelope_check.governance_action == "block" else "ok",
            "reason": envelope_check.reason,
            "tier": tier,
            "provider": str(args.provider),
            "channel": channel,
            "preset": preset,
            "enforce": True,
            "usage": {"tokens_used": tokens_used},
            "limits": {"token_limit": token_limit},
            "tier_limits": tier_token_limits,
            "check": {
                "status": envelope_check.status,
                "breached_dimensions": list(envelope_check.breached_dimensions),
                "governance_action": envelope_check.governance_action,
                "reason": envelope_check.reason,
            },
        }
        if task_desc:
            result["task"] = task_desc

        print(json.dumps(result, indent=2))
        return 2 if envelope_check.governance_action == "block" else 0

    breached = tokens_used > token_limit
    check: dict[str, Any] = {
        "status": "breach" if breached else "ok",
        "breached_dimensions": ["tokens"] if breached else [],
        "governance_action": "block" if breached else "warn",
        "reason": (
            f"simulated tokens exceeded tier limit ({tokens_used}>{token_limit})"
            if breached
            else "simulated usage within tier limits"
        ),
    }

    result = {
        "schema": "BudgetSimulateResult",
        "status": "preview",
        "tier": tier,
        "provider": str(args.provider),
        "channel": channel,
        "preset": preset,
        "enforce": False,
        "tier_detection": tier_detection,
        "usage": {"tokens_used": tokens_used},
        "limits": {"token_limit": token_limit},
        "tier_limits": tier_token_limits,
        "check": check,
    }
    if task_desc:
        result["task"] = task_desc

    print(json.dumps(result, indent=2))
    return 0


def cmd_domain_pack(args: argparse.Namespace) -> int:
    result = get_domain_pack_contract(args.name)
    print(json.dumps(result, indent=2))
    return 0


def _emit_vision_placeholder(command: str) -> int:
    print(
        json.dumps(
            {
                "status": "error",
                "error_code": "INVALID_VISION_INPUT",
                "message": f"{command} is registered, but runtime execution is not implemented yet",
            },
            indent=2,
        )
    )
    return 2


def cmd_vision_ocr(args: argparse.Namespace) -> int:
    return _emit_vision_placeholder("vision ocr")


def cmd_vision_compare(args: argparse.Namespace) -> int:
    return _emit_vision_placeholder("vision compare")


def cmd_vision_analyze(args: argparse.Namespace) -> int:
    return _emit_vision_placeholder("vision analyze")


def cmd_vision_batch(args: argparse.Namespace) -> int:
    return _emit_vision_placeholder("vision batch")


def cmd_vision_eval(args: argparse.Namespace) -> int:
    return _emit_vision_placeholder("vision eval")


def cmd_trace_record(args: argparse.Namespace) -> int:
    result = record_trace(
        _ensure_project_dir(),
        trace_type=args.trace_type,
        route=args.route,
        status=args.status,
        plan=json.loads(args.plan_json) if args.plan_json else {},
        verify=json.loads(args.verify_json) if args.verify_json else {},
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_eval_gate(args: argparse.Namespace) -> int:
    result = evaluate_trace(
        _ensure_project_dir(),
        trace_id=args.trace_id,
        suites=args.suites.split(","),
        metrics=json.loads(args.metrics_json),
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 2


def cmd_delta_classify(args: argparse.Namespace) -> int:
    from runtime.delta_classifier import classify_project_changes

    touched_files = [item for item in args.files.split(",") if item]
    result = classify_project_changes(_ensure_project_dir(), touched_files=touched_files or None, goal=args.goal)
    print(json.dumps(result, indent=2))
    return 0


def cmd_incident_replay(args: argparse.Namespace) -> int:
    result = build_incident_pack(
        _ensure_project_dir(),
        title=args.title,
        failing_tests=[item for item in args.failing_tests.split(",") if item],
        logs=[item for item in args.logs.split("|") if item],
        diff_summary=json.loads(args.diff_summary_json),
        trace_id=args.trace_id or None,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_lineage(args: argparse.Namespace) -> int:
    result = build_lineage_manifest(
        _ensure_project_dir(),
        artifact_type=args.artifact_type,
        sources=json.loads(args.sources_json),
        privacy=args.privacy,
        license=args.license_name,
        derivation=json.loads(args.derivation_json),
        trace_id=args.trace_id or None,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 2


def cmd_supervisor_issue(args: argparse.Namespace) -> int:
    result = issue_local_supervisor_session(
        _ensure_project_dir(),
        worker_id=args.worker_id,
        shared_secret=args.shared_secret,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_supervisor_verify(args: argparse.Namespace) -> int:
    result = verify_local_supervisor_token(args.token, shared_secret=args.shared_secret)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 2


def cmd_maintainer(args: argparse.Namespace) -> int:
    project_dir = _ensure_project_dir()
    out_dir = Path(project_dir) / ".omg" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "oss-impact.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "activity": {"commits": "unverified", "reviews": "unverified", "releases": "unverified"},
        "dependents": {"direct": "unverified", "transitive": "unverified"},
        "adoption_signals": {"downloads": "unverified", "stars": "unverified"},
        "summary_500_words": "",
        "integrity": {"metric_manipulation": "forbidden"},
    }
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "path": str(out_file)}, indent=2))
    return 0


def cmd_trust_review(args: argparse.Namespace) -> int:
    old_cfg = _load_json(args.old)
    new_cfg = _load_json(args.new)
    review = review_config_change(args.file, old_cfg, new_cfg)
    manifest = write_trust_manifest(_ensure_project_dir(), review)
    print(json.dumps({"review": review, "manifest": manifest}, indent=2))
    return 0


def cmd_runtime_dispatch(args: argparse.Namespace) -> int:
    if args.idea_json:
        idea = json.loads(args.idea_json)
    elif args.idea:
        idea = _load_json(args.idea)
    else:
        idea = {"goal": "unspecified"}
    result = dispatch_runtime(args.runtime, idea)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "ok" else 2


def cmd_lab_train(args: argparse.Namespace) -> int:
    job = json.loads(args.job_json) if args.job_json else _load_json(args.job)
    result = run_pipeline(job)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") in {"ready", "failed_evaluation"} else 2


def cmd_lab_eval(args: argparse.Namespace) -> int:
    result = json.loads(args.result_json) if args.result_json else _load_json(args.result)
    out = publish_artifact(result)
    print(json.dumps(out, indent=2))
    return 0 if out.get("status") == "published" else 2


def cmd_forge_run(args: argparse.Namespace) -> int:
    preset = args.preset
    if preset != "labs":
        print(
            json.dumps(
                {"status": "error", "message": f"forge requires labs preset, got: {preset}"},
                indent=2,
            )
        )
        return 2

    project_dir = _ensure_project_dir()
    run_id = normalize_run_id(args.run_id if args.run_id else None)
    job = json.loads(args.job_json) if args.job_json else _load_json(args.job)

    valid, validation_reason = validate_forge_job(job)
    if not valid:
        print(json.dumps({"status": "error", "message": validation_reason}, indent=2))
        return 2

    specialist_dispatch: dict[str, Any] | None = None
    if "specialists" in job or "domain" in job:
        specialist_dispatch = dispatch_specialists(job, project_dir, run_id=run_id)
        if specialist_dispatch.get("status") == "blocked":
            print(json.dumps(specialist_dispatch, indent=2))
            return 2

    result = run_pipeline_with_evidence(project_dir, job, run_id)
    if specialist_dispatch is not None:
        result = dict(result)
        result["specialist_dispatch"] = specialist_dispatch
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") in {"ready", "failed_evaluation"} else 2


def cmd_forge_vision_agent(args: argparse.Namespace) -> int:
    preset = args.preset
    if preset != "labs":
        print(
            json.dumps(
                {"status": "error", "message": f"forge requires labs preset, got: {preset}"},
                indent=2,
            )
        )
        return 2

    project_dir = _ensure_project_dir()
    run_id = normalize_run_id(args.run_id if args.run_id else None)

    job: dict[str, Any] = {
        "dataset": {
            "name": "vision-agent",
            "license": "apache-2.0",
            "source": "internal-curated",
        },
        "base_model": {
            "name": "distill-base-v1",
            "source": "approved-registry",
            "allow_distill": True,
        },
        "target_metric": float(args.target_metric),
        "simulated_metric": float(args.simulated_metric),
        "specialists": resolve_specialists("vision-agent"),
        "domain": "vision",
    }

    if args.job_json:
        override = json.loads(args.job_json)
        if not isinstance(override, dict):
            print(json.dumps({"status": "error", "message": "--job-json must be an object"}, indent=2))
            return 2
        job.update(override)

    specialist_dispatch = dispatch_specialists(job, project_dir, run_id=run_id)
    if specialist_dispatch.get("status") == "blocked":
        print(json.dumps(specialist_dispatch, indent=2))
        return 2

    result = run_pipeline_with_evidence(project_dir, job, run_id)
    out = dict(result)
    out["specialist_dispatch"] = specialist_dispatch
    out["agent_path"] = "vision-agent"
    print(json.dumps(out, indent=2))
    return 0 if out.get("status") in {"ready", "failed_evaluation"} else 2


def _cmd_forge_domain(args: argparse.Namespace, domain: str) -> int:
    preset = args.preset
    if preset != "labs":
        print(
            json.dumps(
                {"status": "error", "message": f"forge requires labs preset, got: {preset}"},
                indent=2,
            )
        )
        return 2

    project_dir = _ensure_project_dir()
    run_id = normalize_run_id(args.run_id if args.run_id else None)

    mvp = load_forge_mvp()
    starter_templates = cast(dict[str, Any], mvp["starter_templates"])
    job: dict[str, Any] = dict(starter_templates[domain])

    if args.job_json:
        override = json.loads(args.job_json)
        if not isinstance(override, dict):
            print(json.dumps({"status": "error", "message": "--job-json must be an object"}, indent=2))
            return 2
        job.update(override)

    specialist_dispatch = dispatch_specialists(job, project_dir, run_id=run_id)
    if specialist_dispatch.get("status") == "blocked":
        print(json.dumps(specialist_dispatch, indent=2))
        return 2

    result = run_pipeline_with_evidence(project_dir, job, run_id)
    out = dict(result)
    out["specialist_dispatch"] = specialist_dispatch
    out["agent_path"] = domain
    print(json.dumps(out, indent=2))
    return 0 if out.get("status") in {"ready", "failed_evaluation"} else 2


def cmd_forge_robotics(args: argparse.Namespace) -> int:
    return _cmd_forge_domain(args, "robotics")


def cmd_forge_algorithms(args: argparse.Namespace) -> int:
    return _cmd_forge_domain(args, "algorithms")


def cmd_forge_health(args: argparse.Namespace) -> int:
    return _cmd_forge_domain(args, "health")


def cmd_forge_cybersecurity(args: argparse.Namespace) -> int:
    return _cmd_forge_domain(args, "cybersecurity")


def cmd_teams(args: argparse.Namespace) -> int:
    files = [f.strip() for f in args.files.split(",") if f.strip()] if args.files else []
    req = TeamDispatchRequest(
        target=args.target,
        problem=args.problem,
        context=args.context,
        files=files,
        expected_outcome=args.expected_outcome,
    )
    result = dispatch_team(req).to_dict()
    print(json.dumps(result, indent=2))
    return 0


def cmd_team(args: argparse.Namespace) -> int:
    return cmd_teams(args)


def cmd_ccg(args: argparse.Namespace) -> int:
    files = [f.strip() for f in args.files.split(",") if f.strip()] if args.files else []
    result = execute_ccg_mode(
        problem=args.problem,
        project_dir=_ensure_project_dir(),
        context=args.context,
        files=files,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_crazy(args: argparse.Namespace) -> int:
    files = [f.strip() for f in args.files.split(",") if f.strip()] if args.files else []
    result = execute_crazy_mode(
        problem=args.problem,
        project_dir=_ensure_project_dir(),
        context=args.context,
        files=files,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_compat_list(args: argparse.Namespace) -> int:
    skills = list_compat_skills()
    print(json.dumps({"status": "ok", "count": len(skills), "skills": skills}, indent=2))
    return 0


def cmd_compat_contract(args: argparse.Namespace) -> int:
    if args.all:
        contracts = list_compat_skill_contracts()
        print(json.dumps({"status": "ok", "count": len(contracts), "contracts": contracts}, indent=2))
        return 0
    if not args.skill:
        print(json.dumps({"status": "error", "message": "Provide --skill or --all"}, indent=2))
        return 2
    contract = get_compat_skill_contract(args.skill)
    if not contract:
        print(json.dumps({"status": "error", "message": f"Unknown skill: {args.skill}"}, indent=2))
        return 2
    print(json.dumps({"status": "ok", "contract": contract}, indent=2))
    return 0


def cmd_compat_gap_report(args: argparse.Namespace) -> int:
    report = build_compat_gap_report(_ensure_project_dir())
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    print(json.dumps({"status": "ok", "report": report}, indent=2))
    return 0


def cmd_compat_snapshot(args: argparse.Namespace) -> int:
    payload = build_contract_snapshot_payload(include_generated_at=True)
    out_path = args.output or DEFAULT_CONTRACT_SNAPSHOT_PATH
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(json.dumps({"status": "ok", "output": out_path, "count": payload["count"]}, indent=2))
    return 0


def cmd_compat_gate(args: argparse.Namespace) -> int:
    report = build_compat_gap_report(_ensure_project_dir())
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    bridge_count = int(report.get("maturity_counts", {}).get("bridge", 0))
    if bridge_count > args.max_bridge:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": f"OMG compat gate failed: bridge={bridge_count} > max_bridge={args.max_bridge}",
                    "report": report,
                },
                indent=2,
            )
        )
        return 3
    print(
        json.dumps(
            {
                "status": "ok",
                "message": f"OMG compat gate passed: bridge={bridge_count} <= max_bridge={args.max_bridge}",
                "report": report,
            },
            indent=2,
        )
    )
    return 0


def cmd_compat_run(args: argparse.Namespace) -> int:
    files = [f.strip() for f in args.files.split(",") if f.strip()] if args.files else []
    result = dispatch_compat_skill(
        skill=args.skill,
        problem=args.problem,
        context=args.context,
        files=files,
        expected_outcome=args.expected_outcome,
        project_dir=_ensure_project_dir(),
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "ok" else 2


def cmd_ecosystem_list(args: argparse.Namespace) -> int:
    repos = list_ecosystem_repos()
    print(json.dumps({"status": "ok", "count": len(repos), "repos": repos}, indent=2))
    return 0


def cmd_ecosystem_status(args: argparse.Namespace) -> int:
    result = ecosystem_status(project_dir=_ensure_project_dir())
    print(json.dumps(result, indent=2))
    return 0


def cmd_ecosystem_sync(args: argparse.Namespace) -> int:
    names = [name.strip() for name in args.names.split(",") if name.strip()] if args.names else []
    result = sync_ecosystem_repos(
        project_dir=_ensure_project_dir(),
        names=names,
        update=bool(args.update),
        depth=int(args.depth),
    )
    print(json.dumps(result, indent=2))
    errors = [entry for entry in result.get("entries", []) if entry.get("status") == "error"]
    return 0 if not errors else 2


def _load_release_identity_validator() -> Any:
    validator_path = ROOT_DIR / "scripts" / "validate-release-identity.py"
    spec = importlib.util.spec_from_file_location("validate_release_identity", validator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load validate-release-identity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cmd_contract_validate(args: argparse.Namespace) -> int:
    result = validate_contract_registry(ROOT_DIR)

    release_identity_scope = getattr(args, "release_identity_scope", "all")
    forbid_version = getattr(args, "forbid_version", "") or None

    try:
        validator = _load_release_identity_validator()
        canonical = validator.extract_canonical_version(ROOT_DIR / "runtime" / "adoption.py")
        if canonical is None:
            release_identity = {
                "canonical_version": None,
                "scope": release_identity_scope,
                "forbid_version": forbid_version,
                "overall_status": "fail",
                "error": "CANONICAL_VERSION not found",
            }
        else:
            authored_result = (
                validator.validate_authored(ROOT_DIR, canonical)
                if release_identity_scope in {"authored", "all"}
                else {"status": "skipped", "blockers": []}
            )
            derived_result = (
                validator.validate_derived(ROOT_DIR, canonical)
                if release_identity_scope in {"derived", "all"}
                else {"status": "skipped", "blockers": []}
            )
            residue_result = (
                validator.scan_scoped_residue(ROOT_DIR, forbid_version)
                if forbid_version
                else None
            )
            release_identity = validator.build_report(
                canonical=canonical,
                scope=release_identity_scope,
                forbid_version=forbid_version,
                authored=authored_result,
                derived=derived_result,
                scoped_residue=residue_result,
            )
    except Exception as exc:
        release_identity = {
            "canonical_version": None,
            "scope": release_identity_scope,
            "forbid_version": forbid_version,
            "overall_status": "fail",
            "error": f"release identity validator failed: {exc}",
        }

    result["release_identity"] = release_identity
    status_ok = result.get("status") == "ok" and release_identity.get("overall_status") == "ok"
    if not status_ok:
        result["status"] = "error"

    print(json.dumps(result, indent=2))
    return 0 if status_ok else 2


def cmd_contract_compile(args: argparse.Namespace) -> int:
    hosts = args.hosts or []
    if getattr(args, "method", False):
        result = compile_method_artifacts(
            root_dir=ROOT_DIR,
            output_root=args.output_root,
            hosts=hosts,
            channel=args.channel,
        )
    else:
        result = compile_contract_outputs(
            root_dir=ROOT_DIR,
            output_root=args.output_root,
            hosts=hosts,
            channel=args.channel,
        )
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "ok" else 2


def cmd_release_readiness(args: argparse.Namespace) -> int:
    if not os.environ.get("OMG_RELEASE_READY_PROVIDERS", "").strip():
        os.environ["OMG_RELEASE_READY_PROVIDERS"] = ",".join(get_canonical_hosts())
    if not os.environ.get("OMG_REQUIRE_HOST_PARITY_REPORT", "").strip():
        os.environ["OMG_REQUIRE_HOST_PARITY_REPORT"] = "1"
    result = build_release_readiness(
        root_dir=ROOT_DIR,
        output_root=args.output_root,
        channel=args.channel,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "ok" else 2


def _add_compat_subcommands(parent: argparse.ArgumentParser, *, dest: str) -> None:
    compat_sub = parent.add_subparsers(dest=dest, required=True)
    compat_list = compat_sub.add_parser("list", help="List supported legacy skill names")
    compat_list.set_defaults(func=cmd_compat_list)
    compat_contract = compat_sub.add_parser("contract", help="Show skill contract schema")
    compat_contract.add_argument("--skill", default="")
    compat_contract.add_argument("--all", action="store_true")
    compat_contract.set_defaults(func=cmd_compat_contract)
    compat_gap = compat_sub.add_parser("gap-report", help="Write compatibility maturity report")
    compat_gap.add_argument("--output", default=DEFAULT_GAP_REPORT_PATH)
    compat_gap.set_defaults(func=cmd_compat_gap_report)
    compat_snapshot = compat_sub.add_parser("snapshot", help="Write current skill contracts snapshot")
    compat_snapshot.add_argument("--output", default=DEFAULT_CONTRACT_SNAPSHOT_PATH)
    compat_snapshot.set_defaults(func=cmd_compat_snapshot)
    compat_gate = compat_sub.add_parser("gate", help="Fail if bridge skill count exceeds threshold")
    compat_gate.add_argument("--max-bridge", type=int, default=0)
    compat_gate.add_argument("--output", default=DEFAULT_GAP_REPORT_PATH)
    compat_gate.set_defaults(func=cmd_compat_gate)
    compat_run = compat_sub.add_parser("run", help="Run a legacy skill through OMG router")
    compat_run.add_argument("--skill", required=True)
    compat_run.add_argument("--problem", default="")
    compat_run.add_argument("--context", default="")
    compat_run.add_argument("--files", default="")
    compat_run.add_argument("--expected-outcome", default="")
    compat_run.set_defaults(func=cmd_compat_run)


def _add_ecosystem_subcommands(parent: argparse.ArgumentParser, *, dest: str) -> None:
    ecosystem_sub = parent.add_subparsers(dest=dest, required=True)
    ecosystem_list = ecosystem_sub.add_parser("list", help="List OMG ecosystem integration targets")
    ecosystem_list.set_defaults(func=cmd_ecosystem_list)

    ecosystem_status_cmd = ecosystem_sub.add_parser("status", help="Show current ecosystem install status")
    ecosystem_status_cmd.set_defaults(func=cmd_ecosystem_status)

    ecosystem_sync = ecosystem_sub.add_parser("sync", help="Clone or refresh ecosystem repositories")
    ecosystem_sync.add_argument("--names", default="", help="Comma-separated repo names or aliases")
    ecosystem_sync.add_argument("--update", action="store_true", help="Fetch latest refs for existing clones")
    ecosystem_sync.add_argument("--depth", type=int, default=1, help="Git depth for shallow clone/fetch")
    ecosystem_sync.set_defaults(func=cmd_ecosystem_sync)


def cmd_provider_parity_eval(args: argparse.Namespace) -> int:
    from runtime.provider_parity_eval import run_provider_parity_eval
    result = run_provider_parity_eval(
        task_path=args.task,
        mode=args.mode,
        output_root=args.output_root or None,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "ok" else 2


def cmd_context_compile(args: argparse.Namespace) -> int:
    from runtime.context_compiler import compile_context_packets
    hosts = args.hosts or []
    result = compile_context_packets(
        root_dir=ROOT_DIR,
        output_root=args.output_root,
        hosts=hosts,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "ok" else 2


def _add_context_subcommands(parent: argparse.ArgumentParser, *, dest: str) -> None:
    context_sub = parent.add_subparsers(dest=dest, required=True)
    context_compile = context_sub.add_parser("compile", help="Compile bounded context packets for canonical hosts")
    context_compile.add_argument(
        "--host",
        dest="hosts",
        action="append",
        choices=list(CANONICAL_HOST_CHOICES),
        required=True,
        help="Host to compile context for (repeat for multiple hosts)",
    )
    context_compile.add_argument("--output-root", default="", help="Write outputs to this root instead of the repo root")
    context_compile.set_defaults(func=cmd_context_compile)


def _add_contract_subcommands(parent: argparse.ArgumentParser, *, dest: str) -> None:
    contract_sub = parent.add_subparsers(dest=dest, required=True)

    contract_validate = contract_sub.add_parser("validate", help="Validate contract doc, schema, and bundle registry")
    contract_validate.add_argument(
        "--release-identity-scope",
        default="all",
        choices=["authored", "derived", "all"],
        help="Scope for embedded release identity validation",
    )
    contract_validate.add_argument(
        "--forbid-version",
        default="",
        help="Optional stale version to reject in scoped residue targets",
    )
    contract_validate.set_defaults(func=cmd_contract_validate)

    contract_compile = contract_sub.add_parser(
        "compile", help="Compile host artifacts from the canonical contract"
    )
    contract_compile.add_argument(
        "--host",
        dest="hosts",
        action="append",
        choices=list(CANONICAL_HOST_CHOICES),
        required=True,
        help="Host to compile (repeat for multiple hosts)",
    )
    contract_compile.add_argument("--channel", default="public", choices=["public", "enterprise"])
    contract_compile.add_argument("--output-root", default="", help="Write outputs to this root instead of the repo root")
    contract_compile.add_argument("--method", action="store_true", default=False, help="Emit signed seven-phase methodology artifacts instead of host artifacts")
    contract_compile.set_defaults(func=cmd_contract_compile)


def cmd_profile_review(args: argparse.Namespace) -> int:
    """Read-only review of governed profile state."""
    from runtime.profile_io import load_profile, ensure_governed_preferences, profile_version_from_map, assess_profile_risk

    project_dir = _ensure_project_dir()
    profile_path = os.path.join(project_dir, ".omg", "state", "profile.yaml")
    profile = load_profile(profile_path)

    # Ensure governed_preferences structure exists (in-memory only, no write)
    ensure_governed_preferences(profile)
    governed = profile.get("governed_preferences", {})
    governed = governed if isinstance(governed, dict) else {}

    style_entries = governed.get("style", [])
    style_entries = style_entries if isinstance(style_entries, list) else []
    safety_entries = governed.get("safety", [])
    safety_entries = safety_entries if isinstance(safety_entries, list) else []

    pending = []
    for entry in style_entries + safety_entries:
        if isinstance(entry, dict) and entry.get("confirmation_state") == "pending_confirmation":
            pending.append({
                "field": entry.get("field", ""),
                "value": entry.get("value", ""),
                "section": entry.get("section", ""),
            })

    decay_candidates = []
    for entry in style_entries:
        if not isinstance(entry, dict):
            continue
        dm = entry.get("decay_metadata")
        if isinstance(dm, dict):
            score = 0.0
            try:
                score = float(dm.get("decay_score", 0.0))
            except (TypeError, ValueError):
                pass
            if score > 0:
                decay_candidates.append({
                    "field": entry.get("field", ""),
                    "value": entry.get("value", ""),
                    "decay_score": score,
                    "last_seen_at": dm.get("last_seen_at", ""),
                    "decay_reason": dm.get("decay_reason", ""),
                })

    provenance_obj = profile.get("profile_provenance")
    provenance = provenance_obj if isinstance(provenance_obj, dict) else {}
    recent_updates = provenance.get("recent_updates", [])
    recent_updates = recent_updates if isinstance(recent_updates, list) else []
    provenance_summary = [
        {
            "run_id": str(u.get("run_id", "")),
            "source": str(u.get("source", "")),
            "field": str(u.get("field", "")),
            "updated_at": str(u.get("updated_at", "")),
        }
        for u in recent_updates
        if isinstance(u, dict)
    ]

    version = profile_version_from_map(profile) if profile else ""

    risk = assess_profile_risk(profile)

    result: dict[str, Any] = {
        "schema": "ProfileReview",
        "style": style_entries,
        "safety": safety_entries,
        "pending_confirmations": pending,
        "decay_candidates": decay_candidates,
        "provenance_summary": provenance_summary,
        "profile_version": version,
        "risk_assessment": risk,
    }

    fmt = getattr(args, "format", "json")
    if fmt == "json":
        print(json.dumps(result, indent=2))
    else:
        print("=== Profile Review ===")
        print(f"Profile version: {version[:16]}..." if version else "Profile version: (none)")
        print(f"\n--- Style preferences ({len(style_entries)}) ---")
        for e in style_entries:
            if isinstance(e, dict):
                print(f"  {e.get('field', '?')}: {e.get('value', '?')}  [{e.get('confirmation_state', '?')}]")
        print(f"\n--- Safety preferences ({len(safety_entries)}) ---")
        for e in safety_entries:
            if isinstance(e, dict):
                print(f"  {e.get('field', '?')}: {e.get('value', '?')}  [{e.get('confirmation_state', '?')}]")
        if pending:
            print(f"\n--- Pending confirmations ({len(pending)}) ---")
            for p in pending:
                print(f"  {p['section']}/{p['field']}: {p['value']}")
        else:
            print("\n--- Pending confirmations: none ---")
        if decay_candidates:
            print(f"\n--- Decay candidates ({len(decay_candidates)}) ---")
            for d in decay_candidates:
                print(f"  {d['field']}: score={d['decay_score']:.3f}  reason={d['decay_reason']}")
        else:
            print("\n--- Decay candidates: none ---")
        if provenance_summary:
            print(f"\n--- Provenance ({len(provenance_summary)} recent updates) ---")
            for p in provenance_summary:
                print(f"  [{p['updated_at']}] {p['source']} -> {p['field']}")
        else:
            print("\n--- Provenance: no recent updates ---")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "text")
    fix_mode = getattr(args, "fix", False)
    dry_run = getattr(args, "dry_run", False)
    repair_pack_filter = getattr(args, "repair_pack", None)

    if fix_mode:
        result = run_doctor_fix(root_dir=ROOT_DIR, dry_run=dry_run)
        for receipt in result.get("fix_receipts", []):
            receipt["repair_pack"] = _infer_repair_pack(receipt.get("check", ""))
        for check in result.get("checks", []):
            check["repair_pack"] = _infer_repair_pack(check.get("name", ""))

        if repair_pack_filter:
            result["checks"] = [c for c in result["checks"] if c.get("repair_pack") == repair_pack_filter]
            result["fix_receipts"] = [r for r in result.get("fix_receipts", []) if r.get("repair_pack") == repair_pack_filter]

        if fmt == "json":
            print(json.dumps(result, indent=2))
        else:
            mode_label = "DRY RUN" if dry_run else "FIX"
            pack_label = f" [pack: {repair_pack_filter}]" if repair_pack_filter else ""
            print(f"Doctor ({mode_label}){pack_label}")
            for check in result["checks"]:
                marker = "PASS" if check["status"] == "ok" else ("BLOCKER" if check["status"] == "blocker" else "WARN")
                fix_tag = " [fixable]" if check.get("fixable") else ""
                req_tag = "" if check["required"] else " (optional)"
                pack_tag = f" [{check.get('repair_pack', 'general')}]"
                print(f"  {marker:>7} {check['name']}: {check['message']}{req_tag}{fix_tag}{pack_tag}")
            for receipt in result.get("fix_receipts", []):
                executed_tag = "applied" if receipt["executed"] else "planned"
                print(f"  FIX [{executed_tag}] {receipt['check']}: {receipt['action']} [{receipt.get('repair_pack', 'general')}]")
            blockers = sum(1 for c in result["checks"] if c["status"] == "blocker")
            fixes = len(result.get("fix_receipts", []))
            print(f"\nBLOCKER [{blockers}] | FIXES [{fixes}]")
        return 0 if result["status"] == "pass" else 1

    result = run_doctor(root_dir=ROOT_DIR)
    for check in result.get("checks", []):
        check["repair_pack"] = _infer_repair_pack(check.get("name", ""))

    if repair_pack_filter:
        result["checks"] = [c for c in result["checks"] if c.get("repair_pack") == repair_pack_filter]

    if fmt == "json":
        print(json.dumps(result, indent=2))
    else:
        pack_label = f" [pack: {repair_pack_filter}]" if repair_pack_filter else ""
        print(f"Doctor{pack_label}")
        for check in result["checks"]:
            marker = "PASS" if check["status"] == "ok" else ("BLOCKER" if check["status"] == "blocker" else "WARN")
            req_tag = "" if check["required"] else " (optional)"
            pack_tag = f" [{check.get('repair_pack', 'general')}]"
            print(f"  {marker:>7} {check['name']}: {check['message']}{req_tag}{pack_tag}")
        blockers = sum(1 for c in result["checks"] if c["status"] == "blocker")
        warnings = sum(1 for c in result["checks"] if c["status"] == "warning")
        passed = sum(1 for c in result["checks"] if c["status"] == "ok")
        print(f"\nPASS [{passed}] | WARN [{warnings}] | BLOCKER [{blockers}]")
    return 0 if result["status"] == "pass" else 1


def cmd_env_doctor(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "text")
    result = run_env_doctor(root_dir=ROOT_DIR)
    for check in result.get("checks", []):
        check["repair_pack"] = _infer_repair_pack(check.get("name", ""))

    if fmt == "json":
        print(json.dumps(result, indent=2))
    else:
        print("Env Doctor")
        for check in result["checks"]:
            marker = "PASS" if check["status"] == "ok" else ("BLOCKER" if check["status"] == "blocker" else "WARN")
            req_tag = "" if check["required"] else " (optional)"
            pack_tag = f" [{check.get('repair_pack', 'general')}]"
            print(f"  {marker:>7} {check['name']}: {check['message']}{req_tag}{pack_tag}")
        blockers = sum(1 for c in result["checks"] if c["status"] == "blocker")
        warnings = sum(1 for c in result["checks"] if c["status"] == "warning")
        passed = sum(1 for c in result["checks"] if c["status"] == "ok")
        print(f"\nPASS [{passed}] | WARN [{warnings}] | BLOCKER [{blockers}]")
    return 0 if result["status"] == "pass" else 1


def _detect_clis() -> dict[str, Any]:
    """Detect which host CLIs are available on PATH."""
    import shutil

    hosts = {"codex": "codex", "gemini": "gemini", "kimi": "kimi"}
    result: dict[str, Any] = {}
    for host, binary in hosts.items():
        result[host] = {"detected": shutil.which(binary) is not None}
    return result


def _install_action_to_dict(action: InstallAction) -> dict[str, Any]:
    return {
        "host": action.host,
        "target_path": action.target_path,
        "description": action.description,
        "kind": action.kind,
    }


def _format_install_plan_text(plan_data: dict[str, Any]) -> str:
    lines: list[str] = ["Install Plan"]
    blockers = plan_data.get("integrity_errors", [])
    if blockers:
        lines.append(f"  BLOCKERS ({len(blockers)}):")
        for b in blockers:
            lines.append(f"    - {b}")
    actions = plan_data.get("actions", [])
    lines.append(f"  Actions ({len(actions)}):")
    for a in actions:
        lines.append(f"    [{a['host']}] {a['description']} -> {a['target_path']}")
    lines.append(f"  Pre-checks: {', '.join(plan_data.get('pre_checks', []))}")
    lines.append(f"  Post-checks: {', '.join(plan_data.get('post_checks', []))}")
    return "\n".join(lines)


def _format_install_dryrun_text(result_data: dict[str, Any]) -> str:
    lines: list[str] = ["Install Dry-Run Result"]
    lines.append(f"  Executed: {result_data.get('executed', False)}")
    errors = result_data.get("errors", [])
    if errors:
        lines.append(f"  Errors ({len(errors)}):")
        for e in errors:
            lines.append(f"    - {e}")
    completed = result_data.get("actions_completed", [])
    skipped = result_data.get("actions_skipped", [])
    lines.append(f"  Actions completed: {len(completed)}")
    lines.append(f"  Actions skipped: {len(skipped)}")
    for s in skipped:
        lines.append(f"    skipped: {s}")
    return "\n".join(lines)


def _format_install_apply_text(result_data: dict[str, Any]) -> str:
    lines: list[str] = ["Install Apply Result"]
    lines.append(f"  Executed: {result_data.get('executed', False)}")
    errors = result_data.get("errors", [])
    if errors:
        lines.append(f"  Errors ({len(errors)}):")
        for e in errors:
            lines.append(f"    - {e}")
    for receipt in result_data.get("receipts", []):
        executed_tag = "applied" if receipt["executed"] else "planned"
        lines.append(f"  [{executed_tag}] {receipt['check']}: {receipt['action']}")
        lines.append(f"    backup: {receipt['backup_path']}")
    return "\n".join(lines)


REPAIR_PACK_MAP: dict[str, str] = {
    "python_version": "runtime",
    "fastmcp": "runtime",
    "omg_control_reachable": "runtime",
    "managed_runtime": "runtime",
    "memory_reachable": "runtime",
    "policy_files": "governance",
    "metadata_drift": "governance",
    "compiled_bundles": "release",
    "host_compatibility": "host",
    "plugin_compatibility": "host",
}

HOST_KEYWORDS: list[tuple[str, str]] = [
    ("claude", "claude"),
    ("codex", "codex"),
    ("gemini", "gemini"),
    ("kimi", "kimi"),
    ("opencode", "opencode"),
]


def _infer_repair_pack(check_name: str) -> str:
    if check_name in REPAIR_PACK_MAP:
        return REPAIR_PACK_MAP[check_name]
    name_lower = check_name.lower()
    for keyword, pack in HOST_KEYWORDS:
        if keyword in name_lower:
            return pack
    if "python" in name_lower or "runtime" in name_lower or "mcp" in name_lower:
        return "runtime"
    if "policy" in name_lower or "metadata" in name_lower:
        return "governance"
    return "general"


def _run_install_preflight(fmt: str) -> dict[str, Any]:
    if os.environ.get("OMG_TEST_PREFLIGHT_BLOCK") == "1":
        return {
            "schema": "DoctorResult",
            "status": "fail",
            "checks": [
                {
                    "name": "test_blocker",
                    "status": "blocker",
                    "message": "simulated blocking check",
                    "required": True,
                    "remediation": "Fix the simulated blocker",
                },
            ],
            "version": "test",
        }
    return run_env_doctor(root_dir=ROOT_DIR)


def _format_preflight_text(preflight: dict[str, Any]) -> str:
    lines: list[str] = ["Running env preflight..."]
    for check in preflight.get("checks", []):
        tag = check["status"].upper()
        line = f"  [{tag}] {check['name']}: {check['message']}"
        if check["status"] == "blocker" and check.get("required"):
            line += f"\n         Remediation: {check.get('remediation', 'N/A')}"
        lines.append(line)
    if preflight["status"] == "pass":
        lines.append("  Preflight: PASS")
    else:
        lines.append("  Preflight: FAIL")
    return "\n".join(lines)


def cmd_install(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "text")
    preset = getattr(args, "preset", "balanced")
    mode = getattr(args, "mode", "omg-only")
    do_plan = getattr(args, "plan", False)
    do_dry_run = getattr(args, "dry_run", False)
    do_apply = getattr(args, "apply", False)
    skip_preflight = getattr(args, "skip_preflight", False)

    is_ci = getattr(args, "ci", False) or os.environ.get("OMG_CI") == "1"
    is_non_interactive = getattr(args, "non_interactive", False)
    if not do_plan and not do_dry_run and not do_apply:
        if is_ci or is_non_interactive:
            do_apply = True
        else:
            if fmt == "json":
                print(json.dumps({"error": "specify --plan, --dry-run, or --apply"}, indent=2))
            else:
                print("Error: specify --plan, --dry-run, or --apply")
                print("Run `omg install --plan` to preview, or `omg install --apply` to execute.")
            return 1

    preflight_data: dict[str, Any] | None = None
    if (do_plan or do_apply) and not skip_preflight:
        preflight_data = _run_install_preflight(fmt)
        if fmt != "json":
            print(_format_preflight_text(preflight_data))
        required_blockers = [
            c for c in preflight_data.get("checks", [])
            if c.get("status") == "blocker" and c.get("required") is True
        ]
        if required_blockers:
            blocked_output: dict[str, Any] = {"preflight": preflight_data}
            if do_plan:
                blocked_output["schema"] = "InstallPlan"
                blocked_output["status"] = "blocked"
                blocked_output["actions"] = []
                blocked_output["pre_checks"] = []
                blocked_output["post_checks"] = []
                blocked_output["integrity_errors"] = []
            else:
                blocked_output["schema"] = "InstallApplyResult"
                blocked_output["executed"] = False
                blocked_output["actions"] = []
                blocked_output["receipts"] = []
                blocked_output["errors"] = [
                    f"env preflight blocker: {c['name']}: {c['message']}" for c in required_blockers
                ]
            if fmt == "json":
                print(json.dumps(blocked_output, indent=2))
            else:
                for c in required_blockers:
                    print(f"  BLOCKED: {c['name']}: {c['message']}")
                    if c.get("remediation"):
                        print(f"           Remediation: {c['remediation']}")
            return 1

    preflight_inject: dict[str, Any] = {}
    if skip_preflight:
        preflight_inject = {"preflight": {"skipped": True}}
    elif preflight_data is not None:
        preflight_inject = {"preflight": preflight_data}

    detected_clis = _detect_clis()
    plan = compute_install_plan(
        project_dir=str(ROOT_DIR),
        detected_clis=detected_clis,
        preset=preset,
        mode=mode,
        selected_ids=None,
    )

    from runtime.install_planner import _verify_install_integrity
    integrity_errors = _verify_install_integrity(Path(plan.source_root))

    if do_plan:
        plan_data: dict[str, Any] = {
            "schema": "InstallPlan",
            "actions": [_install_action_to_dict(a) for a in plan.actions],
            "pre_checks": plan.pre_checks,
            "post_checks": plan.post_checks,
            "source_root": plan.source_root,
            "integrity_errors": integrity_errors,
            **preflight_inject,
        }
        if integrity_errors:
            plan_data["status"] = "blocked"
            if fmt == "json":
                print(json.dumps(plan_data, indent=2))
            else:
                print(_format_install_plan_text(plan_data))
            return 1
        plan_data["status"] = "ok"
        if fmt == "json":
            print(json.dumps(plan_data, indent=2))
        else:
            print(_format_install_plan_text(plan_data))
        return 0

    if do_apply:
        if integrity_errors:
            err_data: dict[str, Any] = {
                "schema": "InstallApplyResult",
                "executed": False,
                "actions": [_install_action_to_dict(a) for a in plan.actions],
                "receipts": [],
                "errors": integrity_errors,
                **preflight_inject,
            }
            if fmt == "json":
                print(json.dumps(err_data, indent=2))
            else:
                print(_format_install_apply_text(err_data))
            return 1

        result = execute_plan(plan, dry_run=False)
        config_receipt = result.get("receipt") or {}
        backup_path = ""
        if isinstance(config_receipt, dict):
            backup_path = str(config_receipt.get("backup_path", ""))

        receipts: list[dict[str, Any]] = []
        for action in plan.actions:
            receipts.append({
                "check": f"install_{action.host}",
                "action": action.description,
                "backup_path": backup_path,
                "executed": result["executed"],
                "rollback_ref": backup_path,
            })

        apply_data: dict[str, Any] = {
            "schema": "InstallApplyResult",
            "executed": result["executed"],
            "actions": [_install_action_to_dict(a) for a in plan.actions],
            "receipts": receipts,
            "actions_completed": result["actions_completed"],
            "actions_skipped": result["actions_skipped"],
            "errors": result["errors"],
            **preflight_inject,
        }
        has_errors = bool(result["errors"])
        if fmt == "json":
            print(json.dumps(apply_data, indent=2, default=str))
        else:
            print(_format_install_apply_text(apply_data))
        return 1 if has_errors else 0

    result = execute_plan(plan, dry_run=True)
    result_data: dict[str, Any] = {
        "schema": "InstallResult",
        "executed": result["executed"],
        "actions_completed": result["actions_completed"],
        "actions_skipped": result["actions_skipped"],
        "receipt": result["receipt"],
        "errors": result["errors"],
        "integrity_errors": integrity_errors,
        "actions": [_install_action_to_dict(a) for a in plan.actions],
        **preflight_inject,
    }
    has_errors = bool(result["errors"]) or bool(integrity_errors)
    if fmt == "json":
        print(json.dumps(result_data, indent=2, default=str))
    else:
        print(_format_install_dryrun_text(result_data))
    return 1 if has_errors else 0


def cmd_validate(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "text")
    result = run_validate(root_dir=ROOT_DIR)
    if fmt == "json":
        print(json.dumps(result, indent=2))
    else:
        print(validate_format_text(result))
    return 0 if result["status"] == "pass" else 1


def _format_plugin_diagnostics_text(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    lines = [
        "Plugin Diagnostics",
        f"Status: {result.get('status', 'unknown').upper()}",
        (
            "Records: "
            f"{summary.get('total_records', 0)} | Conflicts: {summary.get('total_conflicts', 0)} "
            f"(blockers={summary.get('blockers', 0)}, warnings={summary.get('warnings', 0)}, infos={summary.get('infos', 0)})"
        ),
    ]

    next_actions = result.get("next_actions", [])
    if isinstance(next_actions, list) and next_actions:
        lines.append("Next Actions:")
        for action in next_actions:
            lines.append(f"- {action}")

    elapsed_ms = result.get("elapsed_ms", 0.0)
    lines.append(f"Elapsed: {elapsed_ms:.2f}ms")
    return "\n".join(lines)


def cmd_diagnose_plugins(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "text")
    result = run_plugin_diagnostics(root=str(ROOT_DIR), live=bool(getattr(args, "live", False)))
    if fmt == "json":
        print(json.dumps(result, indent=2))
    else:
        print(_format_plugin_diagnostics_text(result))
    return 0


def cmd_diagnose_plugins_approve(args: argparse.Namespace) -> int:
    fmt = getattr(args, "format", "json")
    result = approve_plugin(args.source, args.host, args.reason, root=str(ROOT_DIR))
    if fmt == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"Approval status: {result.get('status', 'unknown')}")
        print(str(result.get("message", "")))
    return 0 if result.get("status") == "ok" else 2

def _add_release_subcommands(parent: argparse.ArgumentParser, *, dest: str) -> None:
    release_sub = parent.add_subparsers(dest=dest, required=True)

    release_audit = release_sub.add_parser("audit", help="Audit release artifacts and remote release surfaces")
    release_audit.add_argument("--artifact", action="store_true", help="Run the release artifact audit")
    release_audit.add_argument("--apply", action="store_true", help="Apply GitHub release remediation")
    release_audit.add_argument("--confirm", default="", help="Confirmation token that must match the target version for --apply")
    release_audit.add_argument("--repo", default="trac3r00/OMG", help="GitHub owner/name repo slug")
    release_audit.add_argument("--version", default="", help="Override target version")
    release_audit.add_argument("--format", default="text", choices=["text", "json"])
    release_audit.add_argument("--output-json", default="", help="Write JSON report to this path")
    release_audit.set_defaults(func=cmd_release_audit)

    release_readiness = release_sub.add_parser("readiness", help="Check production release readiness for compiled artifacts")
    release_readiness.add_argument("--channel", default="dual", choices=["public", "enterprise", "dual"])
    release_readiness.add_argument("--output-root", default="", help="Check compiled outputs from this root instead of the repo root")
    release_readiness.set_defaults(func=cmd_release_readiness)


def cmd_release_audit(args: argparse.Namespace) -> int:
    if not getattr(args, "artifact", False):
        print("release audit currently requires --artifact", file=sys.stderr)
        return 2

    report = run_release_artifact_audit(
        ROOT_DIR,
        repo=str(args.repo),
        version=str(args.version),
        apply=bool(getattr(args, "apply", False)),
        confirm=str(getattr(args, "confirm", "")),
        github_token=resolve_github_token(),
    )
    if getattr(args, "output_json", ""):
        output_path = Path(str(args.output_json))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if getattr(args, "format", "text") == "json":
        print(json.dumps(report, indent=2))
    else:
        print(format_release_audit_text(report))
    if report.get("status") == "error":
        return 2
    return 0 if report.get("overall_status") == "ok" else 1


def cmd_docs_generate(args: argparse.Namespace) -> int:
    check_root = Path(args.output_root) if args.output_root else ROOT_DIR

    if args.check:
        result = check_docs(check_root)
        if result["status"] != "ok":
            print("Doc check FAILED. Drift detected:")
            for d in result["drift"]:
                print(f"  - {d}")
            print("\nRun 'python3 scripts/omg.py docs generate' to fix.")
            return 1
        print("Doc check PASSED. No drift detected.")
        return 0

    output_root = Path(args.output_root) if args.output_root else ROOT_DIR / ".sisyphus" / "tmp" / "generated-docs"
    result = generate_docs(output_root)
    if result["status"] == "ok":
        if not args.output_root:
            for name in GENERATED_ARTIFACTS:
                src = output_root / name
                dst = ROOT_DIR / name
                dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Copied all {len(GENERATED_ARTIFACTS)} artifacts to repo root")

        print(f"Successfully generated docs at: {result['output_root']}")
        for artifact in result["artifacts"]:
            print(f"  - {artifact}")
        return 0
    print(f"Failed to generate docs: {result.get('error', 'Unknown error')}")
    return 1


# ---------------------------------------------------------------------------
# Skill CLI commands (NF6c: Human approval + promotion UX for Skill Foundry)
# ---------------------------------------------------------------------------

_SKILL_PROMOTION_THRESHOLD = 3  # Minimum passing runs required for promotion


def cmd_skill_list(args: argparse.Namespace) -> int:
    """List all skills (active and proposed)."""
    project_dir = _ensure_project_dir()
    project_path = Path(project_dir)

    # Read registry
    registry_path = project_path / ".omg" / "state" / "skill_registry" / "compact.json"
    active_skills: list[str] = []
    if registry_path.exists():
        try:
            registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
            active_skills = registry_data.get("active", [])
        except (json.JSONDecodeError, OSError):
            pass

    # Read proposals
    proposals_dir = project_path / ".omg" / "state" / "skill-proposals"
    proposals: list[dict[str, Any]] = []
    if proposals_dir.exists():
        for proposal_file in proposals_dir.glob("proposal-*.json"):
            if "-eval.json" in proposal_file.name or "-promoted.json" in proposal_file.name:
                continue
            try:
                proposal_data = json.loads(proposal_file.read_text(encoding="utf-8"))
                if proposal_data.get("schema") == "SkillProposal":
                    proposals.append(proposal_data)
            except (json.JSONDecodeError, OSError):
                continue

    if not active_skills and not proposals:
        print("No skills found.")
        return 0

    # Print table
    print(f"{'Name':<30} | {'Status':<12} | {'Source':<12}")
    print("-" * 60)

    for skill in active_skills:
        print(f"{skill:<30} | {'active':<12} | {'registry':<12}")

    for proposal in proposals:
        name = proposal.get("name", "unknown")
        status = proposal.get("status", "proposed")
        source = proposal.get("source", "unknown")
        print(f"{name:<30} | {status:<12} | {source:<12}")

    return 0


def cmd_skill_review(args: argparse.Namespace) -> int:
    """Review a skill proposal with evaluation details."""
    project_dir = _ensure_project_dir()
    project_path = Path(project_dir)
    proposal_id = args.proposal_id

    proposals_dir = project_path / ".omg" / "state" / "skill-proposals"
    proposal_path = proposals_dir / f"{proposal_id}.json"
    eval_path = proposals_dir / f"{proposal_id}-eval.json"

    if not proposal_path.exists():
        print(f"Proposal not found: {proposal_id}")
        return 1

    try:
        proposal_data = json.loads(proposal_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error reading proposal: {exc}")
        return 1

    # Read evaluation if exists
    eval_data: dict[str, Any] = {}
    if eval_path.exists():
        try:
            eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # Display proposal details
    print(f"Proposal ID: {proposal_id}")
    print(f"Name: {proposal_data.get('name', 'unknown')}")
    print(f"Status: {proposal_data.get('status', 'proposed')}")
    print(f"Description: {proposal_data.get('description', 'N/A')}")
    print(f"Created: {proposal_data.get('created_at', 'N/A')}")
    print("")

    # Display evaluation results
    if eval_data:
        proof_gate = eval_data.get("proof_gate_result", {})
        verdict = proof_gate.get("verdict", "unknown")
        blockers = proof_gate.get("blockers", [])
        evidence_summary = proof_gate.get("evidence_summary", {})
        claim_count = evidence_summary.get("claim_count", 0)

        print(f"Evaluation Status: {eval_data.get('status', 'unknown')}")
        print(f"Proof Gate Verdict: {verdict}")
        print(f"Blockers: {len(blockers)}")
        print(f"Passing Runs: {claim_count}")

        # Check promotion eligibility
        if claim_count < _SKILL_PROMOTION_THRESHOLD:
            print(f"")
            print(f"Needs more evidence: {_SKILL_PROMOTION_THRESHOLD - claim_count} more passing runs required")
    else:
        print("No evaluation data available.")

    return 0


def cmd_skill_promote(args: argparse.Namespace) -> int:
    """Promote a skill proposal to active status."""
    project_dir = _ensure_project_dir()
    project_path = Path(project_dir)
    proposal_id = args.proposal_id

    proposals_dir = project_path / ".omg" / "state" / "skill-proposals"
    proposal_path = proposals_dir / f"{proposal_id}.json"
    eval_path = proposals_dir / f"{proposal_id}-eval.json"
    promoted_path = proposals_dir / f"{proposal_id}-promoted.json"

    if not proposal_path.exists():
        print(f"Proposal not found: {proposal_id}")
        return 1

    try:
        proposal_data = json.loads(proposal_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error reading proposal: {exc}")
        return 1

    # Read evaluation
    eval_data: dict[str, Any] = {}
    if eval_path.exists():
        try:
            eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # Check evaluation status
    proof_gate = eval_data.get("proof_gate_result", {})
    verdict = proof_gate.get("verdict", "unknown")
    evidence_summary = proof_gate.get("evidence_summary", {})
    claim_count = evidence_summary.get("claim_count", 0)

    # Check for failing verdict
    if verdict == "fail":
        print(f"Cannot promote: proof gate verdict is 'fail'")
        print(f"Blockers: {proof_gate.get('blockers', [])}")
        return 1

    # Check for sufficient evidence
    if claim_count < _SKILL_PROMOTION_THRESHOLD:
        print(f"Insufficient evidence: need {_SKILL_PROMOTION_THRESHOLD} passing runs, have {claim_count}")
        return 1

    # Create promotion artifact
    from datetime import datetime, timezone

    promotion_data = {
        "schema": "SkillPromotion",
        "proposal_id": proposal_id,
        "name": proposal_data.get("name", "unknown"),
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "evidence_summary": evidence_summary,
        "proof_gate_verdict": verdict,
    }

    promoted_path.write_text(json.dumps(promotion_data, indent=2), encoding="utf-8")

    print(f"Promoted skill: {proposal_data.get('name', proposal_id)}")
    print(f"Promotion artifact: {promoted_path}")

    return 0


def _add_skill_subcommands(parent: argparse.ArgumentParser, *, dest: str) -> None:
    """Add skill subcommands to the parser."""
    sub = parent.add_subparsers(dest=dest, required=True)

    list_cmd = sub.add_parser("list", help="List all skills (active and proposed)")
    list_cmd.set_defaults(func=cmd_skill_list)

    review_cmd = sub.add_parser("review", help="Review a skill proposal")
    review_cmd.add_argument("proposal_id", help="Proposal ID to review")
    review_cmd.set_defaults(func=cmd_skill_review)

    promote_cmd = sub.add_parser("promote", help="Promote a skill proposal to active status")
    promote_cmd.add_argument("proposal_id", help="Proposal ID to promote")
    promote_cmd.set_defaults(func=cmd_skill_promote)


# --- Memory CLI handlers ---


def _get_memory_store() -> Any:
    """Get a MemoryStore instance using OMG_MEMORY_STORE env var or default."""
    from runtime.memory_store import MemoryStore

    store_path = os.environ.get("OMG_MEMORY_STORE")
    return MemoryStore(store_path=store_path) if store_path else MemoryStore()


def cmd_memory_export(args: argparse.Namespace) -> int:
    """Export memory items to JSON or Markdown format."""
    store = _get_memory_store()
    items = store.list_all(include_quarantined=True)

    output_format = getattr(args, "format", "json")
    output_path = getattr(args, "output", None)

    if output_format == "markdown":
        lines = ["# OMG Shared Memory Export", ""]
        for item in items:
            lines.append(f"## {item.get('key', 'unknown')}")
            lines.append(f"- ID: {item.get('id', '')}")
            lines.append(f"- Content: {item.get('content', '')}")
            lines.append(f"- Source: {item.get('source_cli', '')}")
            lines.append(f"- Created: {item.get('created_at', '')}")
            lines.append("")
        content = "\n".join(lines)
    else:
        content = json.dumps(items, indent=2)

    if output_path:
        Path(output_path).write_text(content, encoding="utf-8")
    else:
        print(content)
    return 0


def cmd_memory_import(args: argparse.Namespace) -> int:
    """Import memory items from a JSON file."""
    import_path = getattr(args, "file", None)
    review = getattr(args, "review", False)

    if not import_path or not Path(import_path).exists():
        print(json.dumps({"status": "error", "message": f"File not found: {import_path}"}))
        return 1

    try:
        items = json.loads(Path(import_path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "message": f"Invalid JSON: {exc}"}))
        return 1

    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        print(json.dumps({"status": "error", "message": "Expected a JSON array of memory item objects"}))
        return 1

    store = _get_memory_store()
    count = store.import_items(items, quarantined=not review)
    print(json.dumps({"status": "ok", "imported": count, "quarantined": not review}))
    return 0


def cmd_memory_list(args: argparse.Namespace) -> int:
    """List memory items with optional filtering."""
    store = _get_memory_store()
    layer = getattr(args, "layer", None)

    # Note: MemoryStore uses 'namespace' internally, but tests use 'layer' terminology
    items = store.list_all(namespace=layer, include_quarantined=True)

    # Print table header
    print("ID | Key | Layer | Confidence | Created At")
    print("-" * 60)
    for item in items:
        item_id = str(item.get("id", ""))[:8]
        key = str(item.get("key", ""))[:20]
        layer_val = str(item.get("namespace", item.get("layer", "default")))
        confidence = str(item.get("confidence", "1.0"))
        created = str(item.get("created_at", ""))[:19]
        print(f"{item_id} | {key} | {layer_val} | {confidence} | {created}")
    return 0


def cmd_memory_sync(args: argparse.Namespace) -> int:
    """Sync memory items from external sources like Claude.ai web paste."""
    from_web = getattr(args, "from_web", None)

    if not from_web or not Path(from_web).exists():
        print(json.dumps({"status": "error", "message": f"File not found: {from_web}"}))
        return 1

    try:
        paste_content = Path(from_web).read_text(encoding="utf-8")
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        return 1

    # Parse bullet-point style paste (- Item content)
    lines = [line.strip() for line in paste_content.strip().split("\n")]
    items = []
    for line in lines:
        if line.startswith("- "):
            content = line[2:].strip()
            if content:
                items.append({
                    "id": str(__import__("uuid").uuid4()),
                    "key": f"web-paste-{len(items)+1}",
                    "content": content,
                    "source_cli": "web-paste",
                    "tags": ["imported", "web"],
                })

    store = _get_memory_store()
    count = store.import_items(items, quarantined=True)
    print(json.dumps({"status": "ok", "imported": count, "source": "web-paste"}))
    return 0


def _add_memory_subcommands(parent: argparse.ArgumentParser, *, dest: str) -> None:
    """Add memory subcommands to the parser."""
    sub = parent.add_subparsers(dest=dest, required=True)

    export_cmd = sub.add_parser("export", help="Export memory items")
    export_cmd.add_argument("--format", default="json", choices=["json", "markdown"])
    export_cmd.add_argument("--output", default=None, help="Output file path")
    export_cmd.set_defaults(func=cmd_memory_export)

    import_cmd = sub.add_parser("import", help="Import memory items from JSON file")
    import_cmd.add_argument("file", help="JSON file to import")
    import_cmd.add_argument("--review", action="store_true", help="Mark items as reviewed (not quarantined)")
    import_cmd.set_defaults(func=cmd_memory_import)

    list_cmd = sub.add_parser("list", help="List memory items")
    list_cmd.add_argument("--layer", default=None, help="Filter by layer/namespace")
    list_cmd.set_defaults(func=cmd_memory_list)

    sync_cmd = sub.add_parser("sync", help="Sync memory from external sources")
    sync_cmd.add_argument("--from-web", dest="from_web", help="Path to web paste file")
    sync_cmd.set_defaults(func=cmd_memory_sync)


def _add_docs_subcommands(parent: argparse.ArgumentParser, *, dest: str) -> None:
    sub = parent.add_subparsers(dest=dest)

    generate = sub.add_parser("generate", help="Generate machine-readable and human-readable docs")
    generate.add_argument("--output-root", default="", help="Output directory for generated docs")
    generate.add_argument("--check", action="store_true", help="Exit non-zero if generated docs differ from disk")
    generate.set_defaults(func=cmd_docs_generate)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omg", description=f"OMG {CANONICAL_VERSION} CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    ship = sub.add_parser("ship", help="Idea -> Evidence -> PR flow")
    ship.add_argument("--idea", default=".omg/idea.yml")
    ship.add_argument("--runtime", default="claude", choices=["claude", "gpt", "local"])
    ship.add_argument("--run-id", default="")
    ship.set_defaults(func=cmd_ship)

    fix = sub.add_parser("fix", help="Issue-driven fix flow")
    fix.add_argument("--issue", required=True)
    fix.add_argument("--runtime", default="claude", choices=["claude", "gpt", "local"])
    fix.set_defaults(func=cmd_fix)

    issue = sub.add_parser("issue", help="Active issue diagnostics and red-team simulation")
    issue.add_argument("--run-id", default="")
    issue.add_argument(
        "--surfaces",
        default="",
        help=(
            "Comma-separated surfaces to scan: "
            "live_session,forge_runs,hooks,skills,mcps,plugin_interop,governed_tools,domain_pipelines"
        ),
    )
    issue.add_argument("--simulate-surface", default="")
    issue.add_argument("--simulate-scenario", default="")
    issue.set_defaults(func=cmd_issue)

    undo = sub.add_parser("undo", help="Undo last interaction step")
    undo.add_argument("--step-id", default="", help="Journal step ID to undo (latest if omitted)")
    undo.set_defaults(func=cmd_undo)

    secure = sub.add_parser("secure", help="Evaluate command risk")
    secure.add_argument("--command", required=True)
    secure.set_defaults(func=cmd_secure)

    security = sub.add_parser("security", help="Canonical OMG security workflows")
    security_sub = security.add_subparsers(dest="security_command", required=True)
    security_check = security_sub.add_parser("check", help="Run canonical OMG security check")
    security_check.add_argument("--scope", default=".")
    security_check.add_argument("--live-enrichment", action="store_true")
    security_check.add_argument("--waivers-json", default="")
    security_check.set_defaults(func=cmd_security_check)

    waive_tests = sub.add_parser("waive-tests", help="Emit structured waiver evidence for test-intent lock exceptions")
    waive_tests.add_argument("--lock-id", required=True)
    waive_tests.add_argument("--reason", required=True)
    waive_tests.set_defaults(func=cmd_waive_tests)

    api_twin = sub.add_parser("api-twin", help="Contract replay and fixture-based API simulation")
    api_twin_sub = api_twin.add_subparsers(dest="api_twin_command", required=True)
    api_twin_ingest = api_twin_sub.add_parser("ingest", help="Ingest OpenAPI/Postman/example contract input")
    api_twin_ingest.add_argument("--name", required=True)
    api_twin_ingest.add_argument("--source", required=True)
    api_twin_ingest.set_defaults(func=cmd_api_twin_ingest)
    api_twin_record = api_twin_sub.add_parser("record", help="Record approved fixture response")
    api_twin_record.add_argument("--name", required=True)
    api_twin_record.add_argument("--endpoint", default="default")
    api_twin_record.add_argument("--cassette-version", default="v1")
    api_twin_record.add_argument("--request-json", required=True)
    api_twin_record.add_argument("--response-json", required=True)
    api_twin_record.add_argument("--validated", action="store_true")
    api_twin_record.add_argument("--redactions-json", default="")
    api_twin_record.set_defaults(func=cmd_api_twin_record)
    api_twin_serve = api_twin_sub.add_parser("serve", help="Replay a fixture with optional drift/failure injection")
    api_twin_serve.add_argument("--name", required=True)
    api_twin_serve.add_argument("--endpoint", default="default")
    api_twin_serve.add_argument("--cassette-version", default="v1")
    api_twin_serve.add_argument("--latency-ms", type=int, default=0)
    api_twin_serve.add_argument("--failure-mode", default="")
    api_twin_serve.add_argument("--schema-drift", action="store_true")
    api_twin_serve.set_defaults(func=cmd_api_twin_serve)
    api_twin_verify = api_twin_sub.add_parser("verify", help="Validate a fixture against a live response")
    api_twin_verify.add_argument("--name", required=True)
    api_twin_verify.add_argument("--endpoint", default="default")
    api_twin_verify.add_argument("--cassette-version", default="v1")
    api_twin_verify.add_argument("--live-response-json", required=True)
    api_twin_verify.set_defaults(func=cmd_api_twin_verify)

    preflight = sub.add_parser("preflight", help="Structured OMG preflight routing")
    preflight.add_argument("--goal", required=True)
    preflight.set_defaults(func=cmd_preflight)

    resolve_policy = sub.add_parser("resolve-policy", help="Resolve effective policy from tier, presets, and packs")
    resolve_policy.add_argument("--format", default="json", choices=["json", "text"], dest="format")
    resolve_policy.add_argument("--provider", default="claude")
    resolve_policy.set_defaults(func=cmd_resolve_policy)

    policy_pack = sub.add_parser("policy-pack", help="Policy pack management")
    policy_pack_sub = policy_pack.add_subparsers(dest="policy_pack_command", required=True)
    policy_pack_list_cmd = policy_pack_sub.add_parser("list", help="List available policy packs")
    policy_pack_list_cmd.add_argument("--format", default="json", choices=["json", "text"], dest="format")
    policy_pack_list_cmd.set_defaults(func=cmd_policy_pack_list)
    policy_pack_diff_cmd = policy_pack_sub.add_parser("diff", help="Show overrides for a policy pack")
    policy_pack_diff_cmd.add_argument("pack_id", help="Policy pack id to diff")
    policy_pack_diff_cmd.add_argument("--format", default="json", choices=["json", "text"], dest="format")
    policy_pack_diff_cmd.set_defaults(func=cmd_policy_pack_diff)
    policy_pack_scaffold_cmd = policy_pack_sub.add_parser("scaffold", help="Generate a new policy pack template")
    policy_pack_scaffold_cmd.add_argument("pack_id", nargs="?", default="new-pack", help="Pack id for the scaffold")
    policy_pack_scaffold_cmd.add_argument("--format", default="json", choices=["json", "text"], dest="format")
    policy_pack_scaffold_cmd.set_defaults(func=cmd_policy_pack_scaffold)
    policy_pack_keygen_cmd = policy_pack_sub.add_parser("keygen", help="Generate an Ed25519 signing keypair")
    policy_pack_keygen_cmd.add_argument("--output", default=None, help="Path to write keypair JSON file")
    policy_pack_keygen_cmd.add_argument("--add-to-trust-root", action="store_true", default=False, dest="add_to_trust_root",
                                        help="Append generated public key to trusted_signers.json")
    policy_pack_keygen_cmd.add_argument("--format", default="json", choices=["json", "text"], dest="format")
    policy_pack_keygen_cmd.set_defaults(func=cmd_policy_pack_keygen)
    policy_pack_sign_cmd = policy_pack_sub.add_parser("sign", help="Sign a policy pack for attestation")
    policy_pack_sign_cmd.add_argument("pack_id", help="Policy pack id to sign")
    policy_pack_sign_cmd.add_argument("--key-id", default=None, dest="key_id", help="Signer key id")
    policy_pack_sign_cmd.add_argument("--key-path", default=None, dest="key_path", help="Path to private key file (raw base64 or JSON keypair)")
    policy_pack_sign_cmd.add_argument("--format", default="json", choices=["json", "text"], dest="format")
    policy_pack_sign_cmd.set_defaults(func=cmd_policy_pack_sign)
    policy_pack_verify_cmd = policy_pack_sub.add_parser("verify", help="Verify a signed policy pack")
    policy_pack_verify_cmd.add_argument("pack_id", nargs="?", default="", help="Policy pack id to verify")
    policy_pack_verify_cmd.add_argument("--all", action="store_true", default=False, help="Verify all signed packs")
    policy_pack_verify_cmd.add_argument("--format", default="json", choices=["json", "text"], dest="format")
    policy_pack_verify_cmd.set_defaults(func=cmd_policy_pack_verify)

    proof = sub.add_parser("proof", help="Proof helpers")
    proof_sub = proof.add_subparsers(dest="proof_command", required=True)
    proof_summary = proof_sub.add_parser("summary", help="Summarize proof status")
    proof_summary.add_argument("--format", default="json", choices=["json", "markdown", "text"], dest="format")
    proof_summary.set_defaults(func=cmd_proof_summary)
    proof_open = proof_sub.add_parser("open", help="Open latest evidence pack as narrated proof")
    proof_open.add_argument("--run-id", default=None, dest="run_id")
    proof_open.add_argument("--format", default="markdown", choices=["markdown", "text"], dest="format")
    proof_open.set_defaults(func=cmd_proof_open)

    blocked = sub.add_parser("blocked", help="Inspect governance block explanations")
    blocked.add_argument("--last", action="store_true", required=True, help="Show the last block explanation")
    blocked.add_argument("--format", default="text", choices=["text", "markdown"], dest="format")
    blocked.set_defaults(func=cmd_blocked_last)

    explain = sub.add_parser("explain", help="Explain run artifacts")
    explain_sub = explain.add_subparsers(dest="explain_command", required=True)
    explain_run = explain_sub.add_parser("run", help="Explain run by id")
    explain_run.add_argument("--run-id", required=True)
    explain_run.add_argument("--format", default="json", choices=["json", "markdown", "text"], dest="format")
    explain_run.set_defaults(func=cmd_explain_run)

    budget = sub.add_parser("budget", help="Budget envelope operations")
    budget_sub = budget.add_subparsers(dest="budget_command", required=True)
    budget_simulate = budget_sub.add_parser("simulate", help="Simulate budget envelope outcomes")
    budget_simulate.add_argument("--provider", default="claude")
    budget_simulate.add_argument("--tier", default="")
    budget_simulate.add_argument("--channel", default="public")
    budget_simulate.add_argument("--preset", default="balanced")
    budget_simulate.add_argument("--task", default="", dest="task")
    budget_simulate.add_argument("--tokens-used", type=int, default=0)
    budget_simulate.add_argument("--token-limit", type=int, default=0)
    budget_simulate.add_argument("--enforce", action="store_true")
    budget_simulate.add_argument("--format", default="json", choices=["json", "text"], dest="format")
    budget_simulate.set_defaults(func=cmd_budget_simulate)

    domain_pack = sub.add_parser("domain-pack", help="Inspect optional domain pack contracts")
    domain_pack.add_argument("--name", required=True, choices=["robotics", "vision", "algorithms", "health"])
    domain_pack.set_defaults(func=cmd_domain_pack)

    vision = sub.add_parser("vision", help="OCR, visual diff, and semantic image analysis")
    vision_sub = vision.add_subparsers(dest="vision_command", required=True)
    vision_ocr = vision_sub.add_parser("ocr", help="Extract text from one or more images")
    vision_ocr.set_defaults(func=cmd_vision_ocr)
    vision_compare = vision_sub.add_parser("compare", help="Compare one or more images deterministically")
    vision_compare.set_defaults(func=cmd_vision_compare)
    vision_analyze = vision_sub.add_parser("analyze", help="Run semantic image analysis")
    vision_analyze.set_defaults(func=cmd_vision_analyze)
    vision_batch = vision_sub.add_parser("batch", help="Run a vision batch job")
    vision_batch.set_defaults(func=cmd_vision_batch)
    vision_eval = vision_sub.add_parser("eval", help="Evaluate vision job outputs")
    vision_eval.set_defaults(func=cmd_vision_eval)

    tracebank = sub.add_parser("tracebank", help="Record structured route traces")
    tracebank.add_argument("--trace-type", required=True)
    tracebank.add_argument("--route", required=True)
    tracebank.add_argument("--status", default="ok")
    tracebank.add_argument("--plan-json", default="")
    tracebank.add_argument("--verify-json", default="")
    tracebank.set_defaults(func=cmd_trace_record)

    eval_gate = sub.add_parser("eval-gate", help="Evaluate a trace for release gating")
    eval_gate.add_argument("--trace-id", required=True)
    eval_gate.add_argument("--suites", required=True, help="Comma-separated suite names")
    eval_gate.add_argument("--metrics-json", required=True)
    eval_gate.set_defaults(func=cmd_eval_gate)

    delta = sub.add_parser("delta-classifier", help="Classify repo changes for routing and policy")
    delta.add_argument("--goal", default="")
    delta.add_argument("--files", default="")
    delta.set_defaults(func=cmd_delta_classify)

    incident = sub.add_parser("incident-replay", help="Build an incident replay pack")
    incident.add_argument("--title", required=True)
    incident.add_argument("--failing-tests", default="")
    incident.add_argument("--logs", default="")
    incident.add_argument("--diff-summary-json", required=True)
    incident.add_argument("--trace-id", default="")
    incident.set_defaults(func=cmd_incident_replay)

    lineage = sub.add_parser("data-lineage", help="Build lineage metadata for generated artifacts")
    lineage.add_argument("--artifact-type", required=True)
    lineage.add_argument("--sources-json", required=True)
    lineage.add_argument("--privacy", required=True)
    lineage.add_argument("--license-name", required=True)
    lineage.add_argument("--derivation-json", required=True)
    lineage.add_argument("--trace-id", default="")
    lineage.set_defaults(func=cmd_lineage)

    supervisor = sub.add_parser("remote-supervisor", help="Local-only authenticated supervisor session helpers")
    supervisor_sub = supervisor.add_subparsers(dest="remote_supervisor_command", required=True)
    supervisor_issue = supervisor_sub.add_parser("issue", help="Issue a local supervisor session")
    supervisor_issue.add_argument("--worker-id", required=True)
    supervisor_issue.add_argument("--shared-secret", required=True)
    supervisor_issue.set_defaults(func=cmd_supervisor_issue)
    supervisor_verify = supervisor_sub.add_parser("verify", help="Verify a supervisor session token")
    supervisor_verify.add_argument("--token", required=True)
    supervisor_verify.add_argument("--shared-secret", required=True)
    supervisor_verify.set_defaults(func=cmd_supervisor_verify)

    maintainer = sub.add_parser("maintainer", help="OSS maintainer evidence helper")
    maintainer.add_argument("--mode", default="impact", choices=["triage", "release", "review", "impact"])
    maintainer.set_defaults(func=cmd_maintainer)

    trust = sub.add_parser("trust", help="Trust review operations")
    trust_sub = trust.add_subparsers(dest="trust_command", required=True)
    trust_review = trust_sub.add_parser("review", help="Review config change")
    trust_review.add_argument("--file", default="settings.json")
    trust_review.add_argument("--old", required=True, help="Path to old config json")
    trust_review.add_argument("--new", required=True, help="Path to new config json")
    trust_review.set_defaults(func=cmd_trust_review)

    runtime = sub.add_parser("runtime", help="Runtime operations")
    runtime_sub = runtime.add_subparsers(dest="runtime_command", required=True)
    runtime_dispatch = runtime_sub.add_parser("dispatch", help="Dispatch runtime job")
    runtime_dispatch.add_argument("--runtime", required=True, choices=["claude", "gpt", "local"])
    runtime_dispatch.add_argument("--idea", default="", help="Path to idea json")
    runtime_dispatch.add_argument("--idea-json", default="", help="Inline idea json")
    runtime_dispatch.set_defaults(func=cmd_runtime_dispatch)

    lab = sub.add_parser("lab", help="Lab pipeline operations")
    lab_sub = lab.add_subparsers(dest="lab_command", required=True)
    lab_train = lab_sub.add_parser("train", help="Run lab pipeline job")
    lab_train.add_argument("--job", default="", help="Path to job json")
    lab_train.add_argument("--job-json", default="", help="Inline job json")
    lab_train.set_defaults(func=cmd_lab_train)
    lab_eval = lab_sub.add_parser("eval", help="Publish lab result when eligible")
    lab_eval.add_argument("--result", default="", help="Path to result json")
    lab_eval.add_argument("--result-json", default="", help="Inline result json")
    lab_eval.set_defaults(func=cmd_lab_eval)

    forge = sub.add_parser("forge", help="Labs-only domain-model prototyping and evaluation")
    forge_sub = forge.add_subparsers(dest="forge_command", required=True)
    forge_run = forge_sub.add_parser("run", help="Run a forge job through the lab pipeline")
    forge_run.add_argument("--job", default="", help="Path to job json")
    forge_run.add_argument("--job-json", default="", help="Inline job json")
    forge_run.add_argument("--preset", default="labs", choices=list(VALID_PRESETS), help="Adoption preset (must be labs)")
    forge_run.add_argument("--run-id", default="", help="Optional run id used for evidence output")
    forge_run.set_defaults(func=cmd_forge_run)

    forge_vision_agent = forge_sub.add_parser(
        "vision-agent",
        help="Run bounded vision-agent forge flow with specialist dispatch",
    )
    forge_vision_agent.add_argument("--job-json", default="", help="Optional job overrides as inline JSON")
    forge_vision_agent.add_argument("--preset", default="labs", choices=list(VALID_PRESETS), help="Adoption preset (must be labs)")
    forge_vision_agent.add_argument("--target-metric", type=float, default=0.8)
    forge_vision_agent.add_argument("--simulated-metric", type=float, default=0.9)
    forge_vision_agent.add_argument("--run-id", default="", help="Optional run id used for evidence output")
    forge_vision_agent.set_defaults(func=cmd_forge_vision_agent)

    for _domain, _func in [
        ("robotics", cmd_forge_robotics),
        ("algorithms", cmd_forge_algorithms),
        ("health", cmd_forge_health),
        ("cybersecurity", cmd_forge_cybersecurity),
    ]:
        _p = forge_sub.add_parser(_domain, help=f"Run bounded {_domain} forge flow with specialist dispatch")
        _p.add_argument("--job-json", default="", help="Optional job overrides as inline JSON")
        _p.add_argument("--preset", default="labs", choices=list(VALID_PRESETS), help="Adoption preset (must be labs)")
        _p.add_argument("--run-id", default="", help="Optional run id used for evidence output")
        _p.set_defaults(func=_func)

    skill = sub.add_parser("skill", help="Skill foundry management")
    _add_skill_subcommands(skill, dest="skill_command")

    teams = sub.add_parser("teams", help="Internal OMG team routing")
    teams.add_argument("--target", default="auto", choices=["auto", "codex", "gemini", "ccg"])
    teams.add_argument("--problem", required=True)
    teams.add_argument("--context", default="")
    teams.add_argument("--files", default="")
    teams.add_argument("--expected-outcome", default="")
    teams.set_defaults(func=cmd_teams)

    team = sub.add_parser("team", help="Internal OMG staged team routing (canonical)")
    team.add_argument("--target", default="auto", choices=["auto", "codex", "gemini", "ccg"])
    team.add_argument("--problem", required=True)
    team.add_argument("--context", default="")
    team.add_argument("--files", default="")
    team.add_argument("--expected-outcome", default="")
    team.set_defaults(func=cmd_team)

    ccg = sub.add_parser("ccg", help="OMG CCG (tri-track) routing")
    ccg.add_argument("--problem", required=True)
    ccg.add_argument("--context", default="")
    ccg.add_argument("--files", default="")
    ccg.add_argument("--expected-outcome", default="")
    ccg.set_defaults(func=cmd_ccg)

    crazy = sub.add_parser("crazy", help="OMG CRAZY mode - parallel multi-agent orchestration")
    crazy.add_argument("--problem", required=True, help="Task description")
    crazy.add_argument("--context", default="", help="Additional context")
    crazy.add_argument("--files", default="", help="Comma-separated focus files")
    crazy.set_defaults(func=cmd_crazy)

    compat = sub.add_parser("compat", help="OMG legacy compatibility bridge")
    _add_compat_subcommands(compat, dest="compat_command")

    omc = sub.add_parser("omc", help="Alias of `compat` for legacy scripts")
    _add_compat_subcommands(omc, dest="omc_command")

    ecosystem = sub.add_parser("ecosystem", help="Upstream ecosystem sync and status")
    _add_ecosystem_subcommands(ecosystem, dest="ecosystem_command")

    contract = sub.add_parser("contract", help="Canonical OMG contract validation and compilation")
    _add_contract_subcommands(contract, dest="contract_command")

    context_parser = sub.add_parser("context", help="Context packet compiler")
    _add_context_subcommands(context_parser, dest="context_command")

    parity_eval = sub.add_parser("provider-parity-eval", help="Evaluate provider parity across canonical hosts")
    parity_eval.add_argument("--task", required=True, help="Path to bounded task JSON file")
    parity_eval.add_argument("--mode", default="recorded", choices=["recorded", "live"], help="Evaluation mode")
    parity_eval.add_argument("--output-root", default="", help="Write outputs here instead of repo root")
    parity_eval.set_defaults(func=cmd_provider_parity_eval)

    release = sub.add_parser("release", help="OMG release audit and readiness checks")
    _add_release_subcommands(release, dest="release_command")

    doctor = sub.add_parser("doctor", help="Canonical install and runtime verification")
    doctor.add_argument("--format", default="text", choices=["text", "json"], dest="format")
    doctor.add_argument("--fix", action="store_true", default=False, help="Attempt to fix failing checks")
    doctor.add_argument("--dry-run", action="store_true", default=False, dest="dry_run", help="Plan fixes without applying (requires --fix)")
    doctor.add_argument("--repair-pack", default=None, dest="repair_pack", help="Filter checks by repair pack (runtime, governance, host, release, claude, codex, gemini, kimi)")
    doctor.set_defaults(func=cmd_doctor)

    validate = sub.add_parser("validate", help="Canonical validation — doctor + contract + profile + install")
    validate.add_argument("--format", default="text", choices=["text", "json"], dest="format")
    validate.set_defaults(func=cmd_validate)

    diagnose_plugins = sub.add_parser("diagnose-plugins", help="Diagnose plugin interoperability and conflicts")
    diagnose_plugins.add_argument("--format", default="text", choices=["text", "json"], dest="format")
    diagnose_plugins.add_argument("--live", action="store_true", help="Enable live probing mode")
    diagnose_plugins.set_defaults(func=cmd_diagnose_plugins)
    diagnose_plugins_sub = diagnose_plugins.add_subparsers(dest="diagnose_plugins_command")

    diagnose_plugins_approve = diagnose_plugins_sub.add_parser("approve", help="Approve a plugin source for host use")
    diagnose_plugins_approve.add_argument("--source", required=True)
    diagnose_plugins_approve.add_argument("--host", required=True)
    diagnose_plugins_approve.add_argument("--reason", required=True)
    diagnose_plugins_approve.add_argument("--format", default="json", choices=["text", "json"], dest="format")
    diagnose_plugins_approve.set_defaults(func=cmd_diagnose_plugins_approve)

    profile_review = sub.add_parser("profile-review", help="Review governed profile state")
    profile_review.add_argument("--format", default="json", choices=["json", "text"], dest="format")
    profile_review.set_defaults(func=cmd_profile_review)

    docs = sub.add_parser("docs", help="OMG documentation generator")
    _add_docs_subcommands(docs, dest="docs_command")

    memory = sub.add_parser("memory", help="Shared memory management")
    _add_memory_subcommands(memory, dest="memory_command")

    install = sub.add_parser("install", help="Compute, dry-run, or apply an install plan")
    install.add_argument("--plan", action="store_true", help="Emit structured action plan without mutations")
    install.add_argument("--dry-run", action="store_true", help="Compute actions and emit receipts without mutations")
    install.add_argument("--apply", action="store_true", help="Execute the install plan with real disk writes")
    install.add_argument("--ci", action="store_true", help="CI mode flag")
    install.add_argument("--non-interactive", action="store_true", dest="non_interactive", help="Non-interactive mode")
    install.add_argument("--skip-preflight", action="store_true", dest="skip_preflight", help="Skip env preflight checks")
    install.add_argument("--format", default="text", choices=["text", "json"], dest="format")
    install.add_argument("--preset", default="balanced", choices=list(VALID_PRESETS_ALL))
    install.add_argument("--mode", default="omg-only", choices=["omg-only", "coexist"])
    install.set_defaults(func=cmd_install)

    env_cmd = sub.add_parser("env", help="Environment preflight and doctor alias")
    env_sub = env_cmd.add_subparsers(dest="env_command", required=True)
    env_doctor_cmd = env_sub.add_parser("doctor", help="Run env preflight doctor checks (alias for doctor --repair-pack host)")
    env_doctor_cmd.add_argument("--format", default="text", choices=["text", "json"], dest="format")
    env_doctor_cmd.add_argument("--fix", action="store_true", default=False, help="Attempt to fix failing checks")
    env_doctor_cmd.add_argument("--dry-run", action="store_true", default=False, dest="dry_run")
    env_doctor_cmd.set_defaults(func=cmd_env_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
