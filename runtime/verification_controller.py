from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import socket
from pathlib import Path
from typing import Any, cast

from runtime.background_verification import (
    publish_verification_state,
    skipped_stages_for_profile,
)
from runtime.evidence_narrator import matches_completion_claim
from runtime.proof_chain import build_proof_gate_input
from runtime.proof_gate import evaluate_proof_gate
from runtime.proof_score import compute_score
from runtime.runtime_contracts import read_run_state, write_run_state


_AUTO_VERIFY_TERMINAL_STATUSES = {"ok", "error", "blocked"}


class VerificationController:
    project_dir: str

    def __init__(self, project_dir: str):
        self.project_dir = project_dir

    def begin_run(self, run_id: str) -> dict[str, object]:
        state: dict[str, object] = {
            "status": "running",
            "blockers": [],
            "evidence_links": [],
            "progress": self._build_progress(run_id),
        }
        _ = write_run_state(self.project_dir, "verification_controller", run_id, state)
        payload = read_run_state(self.project_dir, "verification_controller", run_id)
        return dict(payload) if isinstance(payload, dict) else {"run_id": run_id, "status": "running"}

    def read_run(self, run_id: str) -> dict[str, object]:
        payload = read_run_state(self.project_dir, "verification_controller", run_id)
        if payload is None:
            return {"status": "not_found", "run_id": run_id}
        return cast(dict[str, object], dict(payload))

    def publish_compat_state(self, run_id: str) -> str:
        run_state = self.read_run(run_id)
        status = str(run_state.get("status", "error"))
        blockers = _as_string_list(run_state.get("blockers"))
        evidence_links = _as_string_list(run_state.get("evidence_links"))
        raw_progress = run_state.get("progress")
        progress = cast(dict[str, object], raw_progress) if isinstance(raw_progress, dict) else {}

        if status == "not_found":
            status = "error"
            blockers = ["verification_controller_run_not_found"]
            evidence_links = []
            progress = {"run_id": run_id, "found": False}

        return publish_verification_state(
            project_dir=self.project_dir,
            run_id=run_id,
            status=status,
            blockers=blockers,
            evidence_links=evidence_links,
            progress=progress,
        )

    def complete_run(
        self,
        run_id: str,
        status: str,
        blockers: list[str],
        evidence_links: list[str],
    ) -> dict[str, object]:
        current = self.read_run(run_id)
        raw_previous_progress = current.get("progress")
        previous_progress = (
            cast(dict[str, object], raw_previous_progress)
            if isinstance(raw_previous_progress, dict)
            else {}
        )

        merged_evidence = list(dict.fromkeys([*evidence_links, *_as_string_list(current.get("evidence_links"))]))
        state: dict[str, object] = {
            "status": status,
            "blockers": list(blockers),
            "evidence_links": merged_evidence,
            "progress": self._build_progress(run_id, previous_progress),
        }

        if status in _AUTO_VERIFY_TERMINAL_STATUSES and _proof_by_default_enabled(self.project_dir):
            enable_proof_by_default(self.project_dir)
            auto_result = auto_verify({**state, "run_id": run_id}, self.project_dir)
            auto_evidence_links = [
                str(auto_result.get("evidence_path", "")).strip(),
                str(auto_result.get("compat_evidence_path", "")).strip(),
                str(auto_result.get("proof_gate_path", "")).strip(),
            ]
            state["evidence_links"] = list(
                dict.fromkeys([*merged_evidence, *[item for item in auto_evidence_links if item]])
            )
            state["progress"] = self._build_progress(run_id, previous_progress)
            state["auto_verification"] = {
                "verified": bool(auto_result.get("verified")),
                "evidence_path": str(auto_result.get("evidence_path", "")).strip(),
                "proof_score": int(auto_result.get("proof_score", 0)),
            }

        _ = write_run_state(self.project_dir, "verification_controller", run_id, state)
        payload = read_run_state(self.project_dir, "verification_controller", run_id)
        return dict(payload) if isinstance(payload, dict) else {"run_id": run_id, "status": status}

    def begin_run_with_profile(
        self, run_id: str, evidence_profile: str | None = None
    ) -> dict[str, object]:
        """Start a run with evidence-profile-driven skip logic.

        Computes which validation stages to skip based on the profile,
        and includes step/total progress for HUD consumption.
        """
        from runtime.evidence_requirements import requirements_for_profile

        required = requirements_for_profile(evidence_profile)
        skipped = skipped_stages_for_profile(evidence_profile)

        state: dict[str, object] = {
            "status": "running",
            "blockers": [],
            "evidence_links": [],
            "progress": self._build_progress(
                run_id,
                step_total={
                    "step": 0,
                    "total": len(required),
                    "current_stage": required[0] if required else "",
                    "evidence_profile": evidence_profile or "code-change",
                    "skipped_stages": skipped,
                },
            ),
        }
        _ = write_run_state(self.project_dir, "verification_controller", run_id, state)
        payload = read_run_state(self.project_dir, "verification_controller", run_id)
        return dict(payload) if isinstance(payload, dict) else {"run_id": run_id, "status": "running"}

    def _build_progress(
        self,
        run_id: str,
        prior: dict[str, object] | None = None,
        step_total: dict[str, object] | None = None,
    ) -> dict[str, object]:
        progress = dict(prior) if isinstance(prior, dict) else {}
        proof_artifacts = self._collect_run_artifacts("proof-gate", run_id)
        claim_judge_artifacts = self._collect_run_artifacts("claim-judge", run_id)

        progress["run_id"] = run_id
        progress["test_intent_lock"] = self._collect_test_intent_lock(run_id)
        progress["claim_judge"] = {
            "artifact_count": len(claim_judge_artifacts),
            "artifact_paths": claim_judge_artifacts,
        }
        progress["proof_artifacts"] = {
            "artifact_count": len(proof_artifacts),
            "artifact_paths": proof_artifacts,
        }
        progress["tool_ledger"] = self._collect_tool_ledger(run_id)

        # Merge step/total from explicit input or preserve prior values
        if isinstance(step_total, dict):
            progress["step"] = step_total.get("step", 0)
            progress["total"] = step_total.get("total", 0)
            if "current_stage" in step_total:
                progress["current_stage"] = step_total["current_stage"]
            if "evidence_profile" in step_total:
                progress["evidence_profile"] = step_total["evidence_profile"]
            if "skipped_stages" in step_total:
                progress["skipped_stages"] = step_total["skipped_stages"]
        return progress

    def _collect_test_intent_lock(self, run_id: str) -> dict[str, object]:
        lock_dir = Path(self.project_dir) / ".omg" / "state" / "test-intent-lock"
        if not lock_dir.exists():
            return {"status": "missing", "matches": []}

        matches: list[str] = []
        for path in sorted(lock_dir.glob("*.json")):
            payload = _load_json(path)
            if not isinstance(payload, dict):
                continue
            intent = payload.get("intent")
            intent_run_id = ""
            if isinstance(intent, dict):
                intent_payload = cast(dict[str, object], intent)
                intent_run_id = str(intent_payload.get("run_id", "")).strip()
            if intent_run_id == run_id:
                matches.append(str(path.relative_to(self.project_dir)).replace("\\", "/"))

        status = "ok" if matches else "missing"
        return {"status": status, "matches": matches}

    def _collect_run_artifacts(self, prefix: str, run_id: str) -> list[str]:
        evidence_dir = Path(self.project_dir) / ".omg" / "evidence"
        if not evidence_dir.exists():
            return []

        paths: list[str] = []
        for artifact in sorted(evidence_dir.glob(f"{prefix}-*.json")):
            payload = _load_json(artifact)
            if not isinstance(payload, dict):
                continue
            artifact_run_id = str(payload.get("run_id", "")).strip()
            if artifact_run_id == run_id:
                paths.append(str(artifact.relative_to(self.project_dir)).replace("\\", "/"))
        return paths

    def _collect_tool_ledger(self, run_id: str) -> dict[str, object]:
        ledger_path = Path(self.project_dir) / ".omg" / "state" / "ledger" / "tool-ledger.jsonl"
        if not ledger_path.exists():
            return {"entries": 0, "evidence_paths": []}

        entries = 0
        evidence_paths: list[str] = []
        try:
            for line in ledger_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                payload = cast(object, json.loads(line))
                row = cast(dict[str, object], payload) if isinstance(payload, dict) else None
                if not isinstance(row, dict):
                    continue
                if str(row.get("run_id", "")).strip() != run_id:
                    continue
                entries += 1
                evidence_path = str(row.get("evidence_path", "")).strip()
                if evidence_path:
                    evidence_paths.append(evidence_path)
        except (OSError, json.JSONDecodeError):
            return {"entries": entries, "evidence_paths": evidence_paths}

        return {"entries": entries, "evidence_paths": list(dict.fromkeys(evidence_paths))}


def enable_proof_by_default(project_dir: str) -> None:
    root = Path(project_dir)
    for path in (
        root / ".omg" / "evidence",
        root / ".omg" / "state" / "proof_gate",
        root / ".omg" / "state" / "verification_controller",
    ):
        path.mkdir(parents=True, exist_ok=True)

    config_path = root / ".omg" / "state" / "verification_controller" / "proof-by-default.json"
    payload = _load_json(config_path) or {}
    payload["schema"] = "VerificationControllerAutoVerify"
    payload["schema_version"] = 1
    payload["enabled"] = True
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(config_path, payload)


def auto_verify(result: dict, project_dir: str) -> dict:
    root = Path(project_dir)
    enable_proof_by_default(project_dir)

    run_id = _infer_run_id(result)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    auto_file_name = f"{timestamp}-auto.json"
    auto_rel_path = f".omg/evidence/{auto_file_name}"
    auto_path = root / auto_rel_path

    trace_id = _infer_trace_id(result)
    evidence_profile = _infer_evidence_profile(result)
    artifact_trace_id = trace_id or f"unverified:{run_id or 'auto'}"
    artifacts, score_inputs = _collect_result_artifacts(
        result=result,
        project_root=root,
        trace_id=artifact_trace_id,
    )
    claims = _build_completion_claims(
        result=result,
        run_id=run_id,
        evidence_profile=evidence_profile,
        trace_id=trace_id,
        artifacts=artifacts,
    )

    evidence_payload: dict[str, Any] = {
        "schema": "EvidencePack",
        "schema_version": 2,
        "run_id": run_id,
        "generator": "runtime.verification_controller.auto_verify",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "claims": claims,
        "artifacts": artifacts,
        "executor": {
            "user": os.environ.get("USER", "unknown"),
            "pid": os.getpid(),
        },
        "environment": {
            "hostname": socket.gethostname(),
            "platform": os.name,
        },
        "result": _json_safe_copy(result),
    }
    if evidence_profile:
        evidence_payload["evidence_profile"] = evidence_profile
    if trace_id:
        evidence_payload["trace_ids"] = [trace_id]
        evidence_payload["lineage"] = {"trace_id": trace_id}

    security_scans = result.get("security_scans")
    if isinstance(security_scans, list):
        evidence_payload["security_scans"] = security_scans

    _write_json(auto_path, evidence_payload)

    compat_rel_path = ""
    if run_id:
        compat_rel_path = f".omg/evidence/{run_id}.json"
        _write_json(root / compat_rel_path, evidence_payload)

    gate_input = build_proof_gate_input(project_dir, evidence_path=auto_rel_path)
    proof_result = evaluate_proof_gate(gate_input if isinstance(gate_input, dict) else {})
    proof_state_path = _write_proof_gate_state(
        project_root=root,
        run_id=run_id,
        timestamp=timestamp,
        evidence_path=auto_rel_path,
        proof_result=proof_result,
    )
    proof_score = compute_score(score_inputs)["score"]

    return {
        "verified": str(proof_result.get("verdict", "fail")).strip().lower() == "pass",
        "evidence_path": auto_rel_path,
        "proof_score": int(proof_score),
        "compat_evidence_path": compat_rel_path,
        "proof_gate_path": proof_state_path,
    }


def _load_json(path: Path) -> dict[str, object] | None:
    try:
        payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return cast(dict[str, object], payload)
    return None


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    values = cast(list[object], value)
    items: list[str] = []
    for item in values:
        cleaned = str(item).strip()
        if cleaned:
            items.append(cleaned)
    return items


def _proof_by_default_enabled(project_dir: str) -> bool:
    config_path = (
        Path(project_dir) / ".omg" / "state" / "verification_controller" / "proof-by-default.json"
    )
    payload = _load_json(config_path)
    if not isinstance(payload, dict):
        return True
    return bool(payload.get("enabled", True))


def _infer_run_id(result: dict[str, Any]) -> str:
    run_id = str(result.get("run_id", "")).strip()
    if run_id:
        return run_id
    progress = result.get("progress")
    if isinstance(progress, dict):
        nested_run_id = str(progress.get("run_id", "")).strip()
        if nested_run_id:
            return nested_run_id
    return f"auto-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def _infer_trace_id(result: dict[str, Any]) -> str:
    trace_id = str(result.get("trace_id", "")).strip()
    if trace_id:
        return trace_id
    progress = result.get("progress")
    if isinstance(progress, dict):
        nested_trace_id = str(progress.get("trace_id", "")).strip()
        if nested_trace_id:
            return nested_trace_id
    return ""


def _infer_evidence_profile(result: dict[str, Any]) -> str:
    evidence_profile = str(result.get("evidence_profile", "")).strip()
    if evidence_profile:
        return evidence_profile
    progress = result.get("progress")
    if isinstance(progress, dict):
        nested_profile = str(progress.get("evidence_profile", "")).strip()
        if nested_profile:
            return nested_profile
    return ""


def _collect_result_artifacts(
    *,
    result: dict[str, Any],
    project_root: Path,
    trace_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    artifacts: list[dict[str, Any]] = []
    score_inputs: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for raw_path in _as_string_list(result.get("evidence_links")):
        resolved_path = _resolve_project_path(project_root, raw_path)
        normalized = str(resolved_path)
        if normalized in seen_paths:
            continue
        seen_paths.add(normalized)

        exists = resolved_path.exists() and resolved_path.is_file()
        score_inputs.append(
            {
                "type": _artifact_kind_from_path(raw_path),
                "valid": exists,
                "path": raw_path if exists else "",
            }
        )
        if not exists:
            continue

        rel_path = _relative_to_project(project_root, resolved_path)
        artifacts.append(
            {
                "kind": _artifact_kind_from_path(rel_path),
                "path": rel_path,
                "sha256": _hash_file(resolved_path),
                "parser": _parser_from_path(resolved_path),
                "summary": f"auto-collected result artifact: {resolved_path.name}",
                "trace_id": trace_id,
            }
        )

    return artifacts, score_inputs


def _build_completion_claims(
    *,
    result: dict[str, Any],
    run_id: str,
    evidence_profile: str,
    trace_id: str,
    artifacts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    subject = _completion_subject(result)
    claim_type = "completion" if matches_completion_claim(subject) else "task_completion"
    claim: dict[str, Any] = {
        "claim_type": claim_type,
        "subject": subject,
        "run_id": run_id,
        "evidence": {"artifacts": artifacts},
    }
    if trace_id:
        claim["trace_ids"] = [trace_id]
    if evidence_profile:
        claim["evidence_profile"] = evidence_profile
    return [claim]


def _completion_subject(result: dict[str, Any]) -> str:
    for key in ("message", "summary", "status"):
        value = str(result.get(key, "")).strip()
        if value:
            if matches_completion_claim(value):
                return value
            if key == "status":
                return f"completed with status {value}"
            return value
    run_id = str(result.get("run_id", "")).strip()
    if run_id:
        return f"completed run {run_id}"
    return "completed task"


def _resolve_project_path(project_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else project_root / path


def _relative_to_project(project_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _artifact_kind_from_path(path: str) -> str:
    normalized = path.lower()
    if normalized.endswith(".sarif"):
        return "sarif"
    if normalized.endswith(".xml"):
        return "junit"
    if normalized.endswith(".json"):
        return "json"
    if normalized.endswith(".log") or normalized.endswith(".txt"):
        return "test_output"
    if "trace" in normalized or normalized.endswith(".zip"):
        return "browser_trace"
    return "artifact"


def _parser_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".xml":
        return "xml"
    if suffix in {".log", ".txt"}:
        return "text"
    if suffix == ".sarif":
        return "sarif"
    if suffix == ".zip":
        return "zip"
    return suffix.lstrip(".") or "file"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_proof_gate_state(
    *,
    project_root: Path,
    run_id: str,
    timestamp: str,
    evidence_path: str,
    proof_result: dict[str, Any],
) -> str:
    proof_dir = project_root / ".omg" / "state" / "proof_gate"
    proof_dir.mkdir(parents=True, exist_ok=True)
    proof_state = {
        "schema": "ProofGateResult",
        "run_id": run_id,
        "evidence_path": evidence_path,
        **proof_result,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if run_id:
        _write_json(proof_dir / f"{run_id}.json", proof_state)

    artifact_rel_path = f".omg/evidence/proof-gate-{run_id or timestamp}.json"
    _write_json(project_root / artifact_rel_path, proof_state)
    return artifact_rel_path


def _json_safe_copy(value: object) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=True, default=str))
    except TypeError:
        return str(value)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
