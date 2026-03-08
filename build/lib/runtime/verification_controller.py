from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime.background_verification import publish_verification_state
from runtime.runtime_contracts import read_run_state, write_run_state


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
        _ = write_run_state(self.project_dir, "verification_controller", run_id, state)
        payload = read_run_state(self.project_dir, "verification_controller", run_id)
        return dict(payload) if isinstance(payload, dict) else {"run_id": run_id, "status": status}

    def _build_progress(
        self, run_id: str, prior: dict[str, object] | None = None
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
