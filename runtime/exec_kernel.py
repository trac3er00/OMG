from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4


_DEFAULT_EVIDENCE_HOOKS = (
    ".omg/evidence/subagents",
    ".omg/state/release_run_coordinator",
)


def _project_dir(project_dir: str | None = None) -> Path:
    if project_dir:
        return Path(project_dir).resolve()
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())).resolve()


def _is_enabled_from_env() -> bool:
    raw = str(os.environ.get("OMG_EXEC_KERNEL_ENABLED", "false")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class KernelRun:
    run_id: str
    isolation_mode: str
    evidence_hooks: tuple[str, ...]
    attach_log: str


class ExecKernel:
    def __init__(self, project_dir: str | None = None):
        self.project_dir = _project_dir(project_dir)

    @property
    def enabled(self) -> bool:
        return _is_enabled_from_env()

    def attach_log(self, run_id: str) -> str:
        return str(Path(".omg") / "state" / "exec-kernel" / f"{run_id}.log").replace("\\", "/")

    def _state_path(self, run_id: str) -> Path:
        return self.project_dir / ".omg" / "state" / "exec-kernel" / f"{run_id}.json"

    def _write_state(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = self._state_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        previous = self.get_run_state(run_id)
        merged: dict[str, Any] = dict(previous)
        merged.update(payload)
        merged["schema"] = "ExecKernelRunState"
        merged["run_id"] = run_id
        merged["kernel_enabled"] = self.enabled
        merged["state_path"] = str(path.relative_to(self.project_dir)).replace("\\", "/")
        tmp_path = path.with_name(f"{path.name}.tmp")
        tmp_path.write_text(json.dumps(merged, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        os.replace(tmp_path, path)
        return merged

    def get_run_state(self, run_id: str) -> dict[str, Any]:
        path = self._state_path(run_id)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def normalize_isolation(self, isolation_mode: str) -> dict[str, Any]:
        normalized = str(isolation_mode or "none").strip().lower() or "none"
        if normalized == "worktree":
            return {
                "requested": "worktree",
                "effective": "worktree",
                "status": "supported",
                "read_only": False,
            }
        if normalized == "container":
            return {
                "requested": "container",
                "effective": "none",
                "status": "deferred",
                "reason": "container isolation is deferred/unsupported",
                "read_only": True,
            }
        return {
            "requested": "none",
            "effective": "none",
            "status": "read-only",
            "reason": "none isolation permits read-only execution",
            "read_only": True,
        }

    def register_run(
        self,
        run_id: str | None,
        *,
        isolation_mode: str = "none",
        evidence_hooks: list[str] | tuple[str, ...] | None = None,
        source: str = "runtime",
        reason: str = "",
    ) -> KernelRun:
        resolved_run_id = str(run_id or uuid4())
        isolation = self.normalize_isolation(isolation_mode)
        hooks = tuple(evidence_hooks or _DEFAULT_EVIDENCE_HOOKS)
        kernel_run = KernelRun(
            run_id=resolved_run_id,
            isolation_mode=str(isolation["requested"]),
            evidence_hooks=hooks,
            attach_log=self.attach_log(resolved_run_id),
        )
        self._write_state(
            resolved_run_id,
            {
                "status": "registered",
                "source": source,
                "reason": reason,
                "kernel_run": asdict(kernel_run),
                "isolation": isolation,
                "evidence_hooks": list(hooks),
                "attach_log": kernel_run.attach_log,
            },
        )
        return kernel_run

    def submit_worker(
        self,
        *,
        run_id: str,
        agent_name: str,
        task_text: str,
        isolation_mode: str = "none",
        evidence_hooks: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        kernel_run = self.register_run(
            run_id,
            isolation_mode=isolation_mode,
            evidence_hooks=evidence_hooks,
            source="submit_worker",
        )
        isolation = self.normalize_isolation(kernel_run.isolation_mode)
        if isolation["requested"] == "container":
            state = self._write_state(
                run_id,
                {
                    "status": "deferred",
                    "dispatch": {
                        "status": "deferred",
                        "reason": isolation["reason"],
                        "agent_name": agent_name,
                    },
                },
            )
            return {
                "status": "deferred",
                "run_id": run_id,
                "job_id": None,
                "isolation": isolation,
                "kernel_enabled": self.enabled,
                "state_path": state.get("state_path", ""),
                "reason": isolation["reason"],
            }

        from runtime import subagent_dispatcher

        dispatch_isolation = "worktree" if isolation["effective"] == "worktree" else "none"
        job_id = subagent_dispatcher.submit_job(
            agent_name,
            task_text,
            isolation=dispatch_isolation,
            run_id=run_id,
            evidence_hooks=list(kernel_run.evidence_hooks),
            attach_log=kernel_run.attach_log,
        )
        state = self._write_state(
            run_id,
            {
                "status": "queued",
                "dispatch": {
                    "status": "queued",
                    "job_id": job_id,
                    "agent_name": agent_name,
                    "task_text": task_text,
                    "isolation": isolation,
                    "passthrough": not self.enabled,
                },
            },
        )
        return {
            "status": "queued",
            "run_id": run_id,
            "job_id": job_id,
            "isolation": isolation,
            "kernel_enabled": self.enabled,
            "attach_log": kernel_run.attach_log,
            "evidence_hooks": list(kernel_run.evidence_hooks),
            "state_path": state.get("state_path", ""),
            "passthrough": not self.enabled,
        }

    def record_supervisor_session(self, run_id: str, session_payload: dict[str, Any]) -> dict[str, Any]:
        return self._write_state(
            run_id,
            {
                "supervisor_session": dict(session_payload),
                "supervisor_status": str(session_payload.get("status", "ok")),
            },
        )


def get_exec_kernel(project_dir: str | None = None) -> ExecKernel:
    return ExecKernel(project_dir)
