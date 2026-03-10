from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from types import ModuleType
from typing import cast
from uuid import uuid4
import warnings

from runtime.defense_state import DefenseState
from runtime.interaction_journal import InteractionJournal
from runtime.compliance_governor import evaluate_release_compliance
from runtime.runtime_contracts import write_run_state
from runtime.session_health import compute_session_health
from runtime.verification_controller import VerificationController


class RunIdConflictError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedRunId:
    run_id: str
    source: str
    reason: str


class ReleaseRunCoordinator:
    project_dir: str
    _verification: VerificationController
    _journal: InteractionJournal

    def __init__(self, project_dir: str):
        self.project_dir = str(Path(project_dir).resolve())
        self._verification = VerificationController(self.project_dir)
        self._journal = InteractionJournal(self.project_dir)

    def begin(self, cli_run_id: str | None = None, release_evidence: dict[str, object] | None = None) -> dict[str, object]:
        resolved = self.resolve_run_id(cli_run_id=cli_run_id, release_evidence=release_evidence)
        run_id = resolved.run_id

        verification_state = self._verification.begin_run(run_id)
        self._write_active_run(run_id)
        self._write_release_evidence(run_id, release_evidence)
        self._write_state(
            run_id,
            {
                "status": "running",
                "phase": "begin",
                "resolution_source": resolved.source,
                "resolution_reason": resolved.reason,
                "release_evidence": dict(release_evidence) if isinstance(release_evidence, dict) else {},
                "verification_status": verification_state.get("status", "running"),
            },
        )
        return {
            "status": "running",
            "run_id": run_id,
            "resolution_source": resolved.source,
            "resolution_reason": resolved.reason,
        }

    def mutate(
        self,
        run_id: str | None,
        tool: str,
        metadata: dict[str, object],
        goal: str,
        available_tools: list[str],
        context_packet: dict[str, object] | None = None,
    ) -> dict[str, object]:
        resolved = self.resolve_run_id(cli_run_id=run_id)
        canonical_run_id = resolved.run_id

        tool_plan_module = cast(ModuleType, __import__("runtime.tool_plan_gate", fromlist=["build_tool_plan"]))
        build_tool_plan = cast(object, getattr(tool_plan_module, "build_tool_plan", None))
        if not callable(build_tool_plan):
            raise RuntimeError("build_tool_plan_unavailable")

        plan_obj = build_tool_plan(
            goal=goal,
            available_tools=available_tools,
            context_packet=context_packet,
            run_id=canonical_run_id,
        )
        plan = cast(dict[str, object], plan_obj) if isinstance(plan_obj, dict) else {}
        journal_metadata = dict(metadata)
        journal_metadata["run_id"] = canonical_run_id
        journal_result = self._journal.record_step(tool=tool, metadata=journal_metadata)

        DefenseState(self.project_dir).update()
        health = cast(dict[str, object], compute_session_health(self.project_dir, run_id=canonical_run_id))

        self._write_active_run(canonical_run_id)
        self._write_state(
            canonical_run_id,
            {
                "status": "running",
                "phase": "mutate",
                "tool": tool,
                "plan_id": str(plan.get("plan_id", "")),
                "journal_step_id": str(journal_result.get("step_id", "")),
                "health_action": str(health.get("recommended_action", "continue")),
            },
        )
        return {
            "status": "running",
            "run_id": canonical_run_id,
            "plan_id": str(plan.get("plan_id", "")),
            "journal_step_id": str(journal_result.get("step_id", "")),
        }

    def verify(self, run_id: str | None) -> dict[str, object]:
        resolved = self.resolve_run_id(cli_run_id=run_id)
        canonical_run_id = resolved.run_id

        DefenseState(self.project_dir).update()
        compat_path = self._verification.publish_compat_state(canonical_run_id)
        health = cast(dict[str, object], compute_session_health(self.project_dir, run_id=canonical_run_id))
        verification_state = self._verification.read_run(canonical_run_id)

        self._write_state(
            canonical_run_id,
            {
                "status": str(verification_state.get("status", "running")),
                "phase": "verify",
                "compat_path": compat_path,
                "health_path": self._health_state_path(canonical_run_id),
                "health_action": str(health.get("recommended_action", "continue")),
            },
        )
        return {
            "status": str(verification_state.get("status", "running")),
            "run_id": canonical_run_id,
            "compat_path": compat_path,
        }

    def finalize(
        self,
        run_id: str | None,
        status: str,
        blockers: list[str],
        evidence_links: list[str],
    ) -> dict[str, object]:
        resolved = self.resolve_run_id(cli_run_id=run_id)
        canonical_run_id = resolved.run_id

        release_evidence = self._read_release_evidence(canonical_run_id)
        compliance = evaluate_release_compliance(
            project_dir=self.project_dir,
            run_id=canonical_run_id,
            release_evidence=release_evidence,
        )
        resolved_status = status
        resolved_blockers = list(blockers)
        if compliance.get("status") == "blocked":
            resolved_status = "blocked"
            reason = str(compliance.get("reason", "compliance_governor_blocked")).strip()
            if reason:
                resolved_blockers.append(reason)
        deduped_blockers = list(dict.fromkeys(resolved_blockers))

        verification_state = self._verification.complete_run(
            run_id=canonical_run_id,
            status=resolved_status,
            blockers=deduped_blockers,
            evidence_links=list(evidence_links),
        )
        DefenseState(self.project_dir).update()
        compat_path = self._verification.publish_compat_state(canonical_run_id)
        health = cast(dict[str, object], compute_session_health(self.project_dir, run_id=canonical_run_id))

        council_path = self._write_fanout(
            canonical_run_id,
            "council",
            {
                "status": "recorded",
                "run_id": canonical_run_id,
                "verification_status": verification_state.get("status", status),
            },
        )
        rollback_path = self._write_fanout(
            canonical_run_id,
            "rollback",
            {
                "status": "recorded",
                "run_id": canonical_run_id,
                "latest_journal_step": self._latest_journal_step(),
            },
        )

        self._write_state(
            canonical_run_id,
            {
                "status": str(verification_state.get("status", resolved_status)),
                "phase": "finalize",
                "compat_path": compat_path,
                "health_path": self._health_state_path(canonical_run_id),
                "health_action": str(health.get("recommended_action", "continue")),
                "council_path": council_path,
                "rollback_path": rollback_path,
                "compliance_authority": str(compliance.get("authority", "")),
                "compliance_reason": str(compliance.get("reason", "")),
                "evidence_links": list(evidence_links),
            },
        )
        return {
            "status": str(verification_state.get("status", resolved_status)),
            "run_id": canonical_run_id,
            "compat_path": compat_path,
            "health_path": self._health_state_path(canonical_run_id),
            "council_path": council_path,
            "rollback_path": rollback_path,
        }

    def resolve_run_id(
        self,
        *,
        cli_run_id: str | None = None,
        release_evidence: dict[str, object] | None = None,
    ) -> ResolvedRunId:
        return resolve_canonical_run_id(self.project_dir, cli_run_id=cli_run_id, release_evidence=release_evidence)

    def _write_state(self, run_id: str, payload: dict[str, object]) -> None:
        _ = write_run_state(self.project_dir, "release_run_coordinator", run_id, payload)

    def _write_active_run(self, run_id: str) -> None:
        active_path = Path(self.project_dir) / ".omg" / "shadow" / "active-run"
        active_path.parent.mkdir(parents=True, exist_ok=True)
        _ = active_path.write_text(f"{run_id}\n", encoding="utf-8")

    def _health_state_path(self, run_id: str) -> str:
        return str(Path(".omg") / "state" / "session_health" / f"{run_id}.json")

    def _write_release_evidence(self, run_id: str, release_evidence: dict[str, object] | None) -> None:
        payload = dict(release_evidence) if isinstance(release_evidence, dict) else {}
        path = Path(self.project_dir) / ".omg" / "state" / "release_run_coordinator" / f"{run_id}-release-evidence.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        _ = tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        os.replace(tmp_path, path)

    def _read_release_evidence(self, run_id: str) -> dict[str, object]:
        path = Path(self.project_dir) / ".omg" / "state" / "release_run_coordinator" / f"{run_id}-release-evidence.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if isinstance(payload, dict):
            return payload
        return {}

    def _write_fanout(self, run_id: str, producer: str, payload: dict[str, object]) -> str:
        path = Path(self.project_dir) / ".omg" / "state" / "release_run_coordinator" / run_id / f"{producer}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        _ = tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        os.replace(tmp_path, path)
        return str(path.relative_to(self.project_dir)).replace("\\", "/")

    def _latest_journal_step(self) -> str:
        journal_dir = Path(self.project_dir) / ".omg" / "state" / "interaction_journal"
        if not journal_dir.exists():
            return ""
        candidates = sorted(journal_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            return ""
        return candidates[-1].stem


def resolve_canonical_run_id(
    project_dir: str,
    *,
    cli_run_id: str | None = None,
    release_evidence: dict[str, object] | None = None,
    generate_if_missing: bool = True,
) -> ResolvedRunId:
    cli = _clean(cli_run_id)
    env = _clean(os.environ.get("OMG_RUN_ID"))
    shadow = _read_shadow_run_id(project_dir)
    evidence = ""
    if isinstance(release_evidence, dict):
        evidence = _clean(release_evidence.get("run_id"))

    active = _read_active_coordinator_run(project_dir)
    sources: dict[str, str] = {
        "cli": cli,
        "env": env,
        "shadow": shadow,
        "evidence": evidence,
        "active": active,
    }
    unique = {value for value in sources.values() if value}

    selected_source = ""
    selected_run_id = ""
    for key in ("cli", "env", "shadow", "evidence", "active"):
        value = sources[key]
        if value:
            selected_source = key
            selected_run_id = value
            break

    reason = f"resolved_from_{selected_source}" if selected_run_id else "generated_new_run_id"
    strict = os.environ.get("OMG_RUN_COORDINATOR_STRICT", "0").strip() == "1"

    if len(unique) > 1:
        if strict:
            conflict = ",".join(f"{name}:{value}" for name, value in sources.items() if value)
            raise RunIdConflictError(f"fragmented_run_ids:{conflict}")
        reason = "fragmented_run_ids_normalized"
        warnings.warn(
            "fragmented_run_ids_normalized",
            RuntimeWarning,
            stacklevel=2,
        )

    if not selected_run_id and generate_if_missing:
        selected_source = "generated"
        selected_run_id = str(uuid4())
        reason = "generated_new_run_id"

    return ResolvedRunId(run_id=selected_run_id, source=selected_source, reason=reason)


def resolve_current_run_id(project_dir: str | None = None, cli_run_id: str | None = None) -> str | None:
    root = _project_dir(project_dir)
    resolved = resolve_canonical_run_id(str(root), cli_run_id=cli_run_id, generate_if_missing=False)
    return resolved.run_id or None


def _project_dir(project_dir: str | None = None) -> Path:
    if project_dir:
        return Path(project_dir)
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def _clean(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _read_shadow_run_id(project_dir: str) -> str:
    active_run = Path(project_dir) / ".omg" / "shadow" / "active-run"
    if not active_run.exists():
        return ""
    try:
        return active_run.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _read_active_coordinator_run(project_dir: str) -> str:
    state_dir = Path(project_dir) / ".omg" / "state" / "release_run_coordinator"
    if not state_dir.exists():
        return ""

    candidates = sorted(state_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for path in reversed(candidates):
        try:
            payload: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        payload_obj = cast(dict[str, object], payload)
        run_id = _clean(payload_obj.get("run_id"))
        if run_id:
            return run_id
        return _clean(path.stem)

    return ""
