#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from registry.verify_artifact import sign_artifact_statement


_DEV_PRIVATE_KEY = "Hx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8="
_DEV_KEY_ID = "1f5fe64ec2f8c901"
_DETERMINISM_VERSION = "forge-determinism-v1"
_DETERMINISM_SCOPE = "same-hardware"
_TEMPERATURE_LOCK = {
    "critical_model_paths": 0.0,
    "critical_tool_paths": 0.0,
}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _context_checksum(*, run_id: str, profile_version: str, intent_gate_version: str) -> str:
    material = f"{run_id}|{profile_version}|{intent_gate_version}"
    return hashlib.sha256(material.encode("utf-8", errors="ignore")).hexdigest()


def _build_deterministic_contract(run_id: str) -> dict[str, object]:
    digest = hashlib.sha256(run_id.encode("utf-8")).digest()
    return {
        "seed": int.from_bytes(digest[:8], byteorder="big", signed=False),
        "temperature_lock": dict(_TEMPERATURE_LOCK),
        "determinism_version": _DETERMINISM_VERSION,
        "determinism_scope": _DETERMINISM_SCOPE,
    }


def prepare_release_proof_fixtures(output_root: Path) -> None:
    trace_id = "trace-1"
    eval_id = "eval-1"
    run_id = "run-1"
    lock_id = "lock-1"
    profile_version = "profile-v1"
    intent_gate_version = "1.0.0"
    context_checksum = _context_checksum(
        run_id=run_id,
        profile_version=profile_version,
        intent_gate_version=intent_gate_version,
    )
    deterministic_contract = _build_deterministic_contract(run_id)
    artifact_digest = hashlib.sha256(f"{run_id}:release-artifact".encode("utf-8")).hexdigest()
    artifact_path = f"dist/public/{run_id}-release-bundle.tgz"
    artifact = {
        "id": f"release-{run_id}",
        "signer": "omg-local",
        "checksum": f"sha256:{artifact_digest}",
        "attestation": sign_artifact_statement(
            artifact_path=artifact_path,
            subject_digest=artifact_digest,
            signer_key=_DEV_PRIVATE_KEY,
            signer_key_id=_DEV_KEY_ID,
        ),
        "permissions": ["read"],
        "static_scan": [],
        "risk_level": "low",
    }

    junit_path = output_root / ".omg" / "evidence" / "junit.xml"
    coverage_path = output_root / ".omg" / "evidence" / "coverage.xml"
    sarif_path = output_root / ".omg" / "evidence" / "results.sarif"
    browser_trace_path = output_root / ".omg" / "evidence" / "browser_trace.json"
    lineage_path = output_root / ".omg" / "lineage" / "lineage-1.json"
    eval_path = output_root / ".omg" / "evals" / "latest.json"
    security_path = output_root / ".omg" / "evidence" / "security-check.json"
    evidence_path = output_root / ".omg" / "evidence" / "run-1.json"
    forge_path = output_root / ".omg" / "evidence" / "forge-specialists-run-1.json"
    release_run_path = output_root / ".omg" / "state" / "release_run_coordinator" / "run-1.json"
    lock_path = output_root / ".omg" / "state" / "test-intent-lock" / "lock-1.json"
    rollback_path = output_root / ".omg" / "state" / "rollback_manifest" / "run-1-step-1.json"
    session_health_path = output_root / ".omg" / "state" / "session_health" / "run-1.json"
    council_verdicts_path = output_root / ".omg" / "state" / "council_verdicts" / "run-1.json"
    intent_gate_path = output_root / ".omg" / "state" / "intent_gate" / "run-1.json"
    profile_path = output_root / ".omg" / "state" / "profile.yaml"
    tracebank_path = output_root / ".omg" / "tracebank" / "events.jsonl"
    exec_kernel_path = output_root / ".omg" / "state" / "exec-kernel" / "run-1.json"
    watchdog_path = output_root / ".omg" / "evidence" / "subagents" / "run-1-replay.json"
    merge_writer_path = output_root / ".omg" / "evidence" / "merge-writer-run-1.json"
    ledger_path = output_root / ".omg" / "state" / "ledger" / "tool-ledger.jsonl"
    budget_path = output_root / ".omg" / "state" / "budget-envelopes" / "run-1.json"
    issue_report_path = output_root / ".omg" / "evidence" / "issues" / "run-1.json"
    host_parity_path = output_root / ".omg" / "evidence" / "host-parity-run-1.json"
    music_omr_path = output_root / ".omg" / "evidence" / "music-omr-run-1.json"

    # Ensure directories exist
    for p in [exec_kernel_path, watchdog_path, merge_writer_path, ledger_path, budget_path, issue_report_path, host_parity_path, music_omr_path]:
        p.parent.mkdir(parents=True, exist_ok=True)

    _write_text(
        junit_path,
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="release-proof" tests="1" failures="0" errors="0">
    <testcase classname="release" name="standalone_ready" time="0.01" />
  </testsuite>
</testsuites>
""",
    )
    _write_text(
        coverage_path,
        """<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="1.0" branch-rate="1.0" version="1.0" />
""",
    )
    _write_json(
        sarif_path,
        {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [{"tool": {"driver": {"name": "release-proof"}}, "results": []}],
        },
    )
    _write_json(
        browser_trace_path,
        {
            "trace": {"name": "browser-smoke"},
            "events": [{"type": "navigation", "url": "https://example.test"}],
        },
    )
    _write_json(
        lineage_path,
        {
            "schema": "LineageRecord",
            "trace_id": trace_id,
            "path": ".omg/lineage/lineage-1.json",
        },
    )
    _write_json(
        eval_path,
        {
            "schema": "EvalGateResult",
            "eval_id": eval_id,
            "trace_id": trace_id,
            "lineage": {"trace_id": trace_id, "path": ".omg/lineage/lineage-1.json"},
            "timestamp": "2026-03-07T00:00:00Z",
            "executor": {"user": "release-bot", "pid": 1},
            "environment": {"hostname": "localhost", "platform": "linux"},
            "status": "ok",
            "summary": {"regressed": False},
        },
    )
    _write_json(
        security_path,
        {
            "schema": "SecurityCheckResult",
            "status": "ok",
            "evidence": {"sarif_path": ".omg/evidence/results.sarif"},
            "context_checksum": context_checksum,
            "profile_version": profile_version,
            "intent_gate_version": intent_gate_version,
        },
    )
    _write_json(
        evidence_path,
            {
                "schema": "EvidencePack",
                "run_id": run_id,
                "evidence_profile": "release",
                "timestamp": "2026-03-07T00:00:00Z",
                "executor": {"user": "release-bot", "pid": 1},
                "environment": {"hostname": "localhost", "platform": "linux"},
                "context_checksum": context_checksum,
                "profile_version": profile_version,
                "intent_gate_version": intent_gate_version,
                "seed": deterministic_contract["seed"],
                "temperature_lock": deterministic_contract["temperature_lock"],
                "determinism_version": deterministic_contract["determinism_version"],
                "determinism_scope": deterministic_contract["determinism_scope"],
                "artifact": artifact,
            "tests": [{"name": "release_readiness", "passed": True}],
            "security_scans": [{"tool": "security-check", "path": ".omg/evidence/security-check.json"}],
            "diff_summary": {"files": 1},
            "reproducibility": {"cmd": "python3 scripts/omg.py release readiness --channel dual"},
            "unresolved_risks": [],
            "provenance": [{"source": "release-proof"}],
            "trust_scores": {"overall": 1.0},
            "claims": [
                {
                    "claim_type": "release_ready",
                    "run_id": run_id,
                    "evidence_profile": "release",
                    "artifacts": [
                        ".omg/evidence/junit.xml",
                        ".omg/evidence/coverage.xml",
                        ".omg/evidence/results.sarif",
                        ".omg/evidence/browser_trace.json",
                    ],
                    "trace_ids": [trace_id],
                }
            ],
            "trace_ids": [trace_id],
            "lineage": {"trace_id": trace_id, "path": ".omg/lineage/lineage-1.json"},
                "test_delta": {
                    "override": {"approved_by": "release-bot"},
                    "lock_id": lock_id,
                    "waiver_artifact": {
                        "artifact_path": ".omg/evidence/waiver-tests-lock-1.json",
                        "reason": "approved release fixture",
                    },
                },
                "intent_gate_state": {
                    "path": ".omg/state/intent_gate/run-1.json",
                    "run_id": run_id,
                },
                "profile_digest": {
                    "path": ".omg/state/profile.yaml",
                    "profile_version": profile_version,
                },
                "session_health_state": {
                    "path": ".omg/state/session_health/run-1.json",
                    "run_id": run_id,
                },
                "council_verdicts": {
                    "path": ".omg/state/council_verdicts/run-1.json",
                    "run_id": run_id,
                },
                "forge_starter_proof": {
                    "path": ".omg/evidence/forge-specialists-run-1.json",
                    "run_id": run_id,
                },
                "exec_kernel_state": {
                    "path": ".omg/state/exec-kernel/run-1.json",
                    "run_id": run_id,
                },
                "worker_watchdog_replay": {
                    "path": ".omg/evidence/subagents/run-1-replay.json",
                    "run_id": run_id,
                },
                "merge_writer_provenance": {
                    "path": ".omg/evidence/merge-writer-run-1.json",
                    "run_id": run_id,
                },
                "tool_fabric_ledger": {
                    "path": ".omg/state/ledger/tool-ledger.jsonl",
                    "run_id": run_id,
                },
                "budget_envelope_state": {
                    "path": ".omg/state/budget-envelopes/run-1.json",
                    "run_id": run_id,
                },
                "issue_report": {
                    "path": ".omg/evidence/issues/run-1.json",
                    "run_id": run_id,
                },
                "host_parity_report": {
                    "path": ".omg/evidence/host-parity-run-1.json",
                    "run_id": run_id,
                },
                "music_omr_testbed_evidence": {
                    "path": ".omg/evidence/music-omr-run-1.json",
                    "run_id": run_id,
                },
                "write_lease_provenance": {
                    "path": ".omg/evidence/merge-writer-run-1.json",
                    "run_id": run_id,
                },
                "proof_chain": {
                    "status": "ok",
                    "trace_id": trace_id,
                    "blockers": [],
                },
                "test_intent_lock": {
                    "status": "ok",
                    "lock_id": lock_id,
                    "run_id": run_id,
                },
            },
    )
    _write_json(
        forge_path,
        {
            "schema": "ForgeSpecialistDispatchEvidence",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "generated_at": "2026-03-07T00:00:00Z",
            "status": "ok",
            "proof_backed": True,
            "specialists_dispatched": ["training-architect"],
            "context_checksum": context_checksum,
            "profile_version": profile_version,
            "intent_gate_version": intent_gate_version,
        },
    )
    _write_json(
        release_run_path,
        {
            "schema": "ReleaseRunCoordinatorState",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "status": "ok",
            "phase": "finalize",
            "resolution_source": "fixtures",
            "resolution_reason": "deterministic_release_seed",
            "compliance_authority": "release",
            "compliance_reason": "compliance checks passed",
            "artifact_verdict": "allow",
            "artifact_alg": "ed25519-minisign",
            "artifact_key_id": _DEV_KEY_ID,
            "artifact_subject_sha256": artifact_digest,
            "updated_at": "2026-03-07T00:00:00Z",
            "context_checksum": context_checksum,
            "profile_version": profile_version,
            "intent_gate_version": intent_gate_version,
        },
    )
    _write_json(
        lock_path,
        {
            "schema": "TestIntentLock",
            "schema_version": "1.0.0",
            "lock_id": lock_id,
            "status": "ok",
            "intent": {"run_id": run_id},
            "context_checksum": context_checksum,
            "profile_version": profile_version,
            "intent_gate_version": intent_gate_version,
        },
    )
    _write_json(
        rollback_path,
        {
            "schema": "RollbackManifest",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "status": "ok",
            "step_id": "step-1",
            "local_restores": [],
            "compensating_actions": [],
            "side_effects": [],
            "updated_at": "2026-03-07T00:00:00Z",
        },
    )
    _write_json(
        session_health_path,
        {
            "schema": "SessionHealth",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "status": "ok",
            "contamination_risk": 0.0,
            "overthinking_score": 0.0,
            "context_health": 1.0,
            "verification_status": "ok",
            "recommended_action": "continue",
            "updated_at": "2026-03-07T00:00:00Z",
            "context_checksum": context_checksum,
            "profile_version": profile_version,
            "intent_gate_version": intent_gate_version,
        },
    )
    _write_json(
        council_verdicts_path,
        {
            "schema": "CouncilVerdicts",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "status": "ok",
            "verification_status": "ok",
            "context_checksum": context_checksum,
            "profile_version": profile_version,
            "intent_gate_version": intent_gate_version,
            "verdicts": {
                "skeptic": {"verdict": "pass"},
                "hallucination_auditor": {"verdict": "pass"},
                "evidence_completeness": {"verdict": "pass"},
            },
            "updated_at": "2026-03-07T00:00:00Z",
        },
    )
    _write_json(
        intent_gate_path,
        {
            "schema": "IntentGateDecision",
            "schema_version": intent_gate_version,
            "run_id": run_id,
            "intent_gate_version": intent_gate_version,
            "requires_clarification": False,
            "intent_class": "release_readiness",
            "clarification_prompt": "",
            "confidence": 0.98,
            "context_checksum": context_checksum,
            "profile_version": profile_version,
            "updated_at": "2026-03-07T00:00:00Z",
        },
    )
    _write_json(
        exec_kernel_path,
        {
            "schema": "ExecKernelRunState",
            "run_id": run_id,
            "status": "queued",
            "kernel_enabled": True,
        },
    )
    _write_json(
        watchdog_path,
        {
            "schema": "WorkerReplayEvidence",
            "run_id": run_id,
            "reason": "completed",
        },
    )
    _write_json(
        merge_writer_path,
        {
            "schema": "MergeWriterProvenance",
            "run_id": run_id,
            "acquired_at": "2026-03-07T00:00:00Z",
            "released_at": "2026-03-07T00:00:01Z",
        },
    )
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps({"ts": "2026-03-07T00:00:00Z", "tool": "ls", "run_id": run_id}) + "\n",
        encoding="utf-8",
    )
    _write_json(
        budget_path,
        {
            "schema": "BudgetEnvelopeState",
            "run_id": run_id,
            "usage": {"cpu_seconds_used": 0.1},
        },
    )
    _write_json(
        issue_report_path,
        {
            "schema": "IssueReport",
            "run_id": run_id,
            "issues": [],
        },
    )
    _write_json(
        host_parity_path,
        {
            "schema": "HostParityReport",
            "run_id": run_id,
            "timestamp": "2026-03-07T00:00:00Z",
            "canonical_hosts": ["claude", "codex", "gemini", "kimi"],
            "parity_results": {
                "passed": True,
                "drift_detected": False,
                "drift_details": [],
                "host_results": {
                    "claude": {
                        "present": True,
                        "passed": True,
                        "reason": "baseline",
                        "normalized": {
                            "source_class": "compiled_or_replayed",
                            "source_kind": "compiled_artifact",
                            "source_path": "settings.json",
                        },
                    },
                    "codex": {
                        "present": True,
                        "passed": True,
                        "reason": "structured-equivalent",
                        "normalized": {
                            "source_class": "compiled_or_replayed",
                            "source_kind": "compiled_artifact",
                            "source_path": ".agents/skills/omg/AGENTS.fragment.md",
                        },
                    },
                    "gemini": {
                        "present": True,
                        "passed": True,
                        "reason": "structured-equivalent",
                        "normalized": {
                            "source_class": "compiled_or_replayed",
                            "source_kind": "compiled_artifact",
                            "source_path": ".gemini/settings.json",
                        },
                    },
                    "kimi": {
                        "present": True,
                        "passed": True,
                        "reason": "structured-equivalent",
                        "normalized": {
                            "source_class": "compiled_or_replayed",
                            "source_kind": "compiled_artifact",
                            "source_path": ".kimi/mcp.json",
                        },
                    },
                }
            },
            "overall_status": "ok",
        },
    )
    _write_json(
        music_omr_path,
        {
            "schema": "MusicOMREvidence",
            "run_id": run_id,
            "results": {},
        },
    )
    _write_text(
        profile_path,
        """profile_version: profile-v1
preferences:
  architecture_requests:
    - release_readiness
  constraints:
    release_mode: dual
user_vector:
  tags:
    - proof
    - readiness
  summary: deterministic fixture profile digest
profile_provenance:
  checksum: profile-v1
""",
    )
    tracebank_path.parent.mkdir(parents=True, exist_ok=True)
    tracebank_path.write_text(
        json.dumps(
            {
                "schema": "TracebankRecord",
                "trace_id": trace_id,
                "timestamp": "2026-03-07T00:00:00Z",
                "executor": {"user": "release-bot", "pid": 1},
                "environment": {"hostname": "localhost", "platform": "linux"},
                "path": ".omg/tracebank/events.jsonl",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Write deterministic proof fixtures for release readiness.")
    parser.add_argument("--output-root", default=".", help="Root directory that should receive the .omg fixture tree.")
    args = parser.parse_args()
    prepare_release_proof_fixtures(Path(args.output_root).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
