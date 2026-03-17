from __future__ import annotations

from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import uuid
from typing import Any, cast

from runtime.repro_pack import build_repro_pack
from runtime.rollback_manifest import (
    classify_side_effect,
    create_rollback_manifest,
    record_compensating_action,
    record_local_restore,
    record_side_effect,
    write_rollback_manifest,
)


_MUTATION_TOOLS = frozenset({"write", "edit", "multiedit"})

_REJECTED_SHELL_WRAPPERS: frozenset[str] = frozenset(
    {"sh", "bash", "zsh", "fish", "cmd", "cmd.exe", "powershell"}
)
_REJECTED_SHELL_TOKENS: frozenset[str] = frozenset(
    {";", "&&", "||", "|", ">", ">>", "<", "2>", "&"}
)


def _normalize_command_argv(command_or_argv: str | list[str]) -> list[str] | None:
    """Normalize a command string or argv list to a validated argv list.

    Returns the validated argv on success, or ``None`` when the input is
    empty, unparseable, or contains rejected shell execution patterns
    (shell wrapper executables, chaining operators).
    """
    if isinstance(command_or_argv, list):
        argv = [str(a) for a in command_or_argv]
    elif isinstance(command_or_argv, str):
        try:
            argv = shlex.split(command_or_argv)
        except ValueError:
            return None
    else:
        return None

    if not argv:
        return None

    # Reject shell wrapper executables as the program name.
    executable = os.path.basename(argv[0])
    if executable in _REJECTED_SHELL_WRAPPERS:
        return None

    # Reject standalone shell-control tokens in any position.
    for token in argv:
        if token in _REJECTED_SHELL_TOKENS:
            return None

    return argv


class InteractionJournal:
    project_dir: Path
    journal_dir: Path

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir).resolve()
        self.journal_dir = self.project_dir / ".omg" / "state" / "interaction_journal"
        self._pending_step_id = ""

    def record_step(self, tool: str, metadata: dict[str, object]) -> dict[str, object]:
        step_id = self._new_step_id()
        self._pending_step_id = step_id
        normalized_tool = tool.lower().strip()
        run_id = str(metadata.get("run_id", "")).strip()

        rollback_mode = "unsupported"
        if normalized_tool in _MUTATION_TOOLS:
            rollback_mode = self._rollback_mode()
        checkpoint_ref = self._checkpoint_reference(step_id)

        shadow_manifest_path = ""
        if normalized_tool in _MUTATION_TOOLS:
            shadow_manifest_path = self._capture_shadow_metadata(metadata)

        repro_pointer = self._build_repro_pointer(run_id)
        side_effect_scope = str(metadata.get("side_effect_scope", "")).strip()

        payload: dict[str, object] = {
            "schema": "InteractionJournalStep",
            "schema_version": "1.0.0",
            "step_id": step_id,
            "recorded_at": self._utc_now(),
            "tool": normalized_tool,
            "run_id": run_id,
            "metadata": dict(metadata),
            "rollback_mode": rollback_mode,
            "checkpoint_ref": checkpoint_ref,
            "shadow_manifest_path": shadow_manifest_path,
            "repro_pointer": repro_pointer,
        }
        if side_effect_scope:
            payload["side_effect_scope"] = side_effect_scope
        self._write_step(step_id, payload)
        self._pending_step_id = ""

        return {
            "step_id": step_id,
            "status": "recorded",
            "rollback_mode": rollback_mode,
            "repro_pointer": repro_pointer,
        }

    def undo(self, step_id: str, run_id: str | None = None) -> dict[str, object]:
        target_step_id = step_id.strip() or self._latest_step_id()
        if not target_step_id:
            return {"status": "noop", "reason": "no journal entries"}

        step = self._read_step(target_step_id)
        if step is None:
            return {"status": "noop", "reason": "step not found"}

        tool = str(step.get("tool", "")).strip()
        metadata = step.get("metadata")
        metadata_obj = cast(dict[str, object], metadata) if isinstance(metadata, dict) else {}
        manifest_run_id = (
            (run_id or "").strip()
            or str(step.get("run_id", "")).strip()
            or self._derive_run_id(step)
        )
        rollback_manifest = create_rollback_manifest(manifest_run_id, target_step_id)
        side_effect = classify_side_effect(tool, metadata_obj)
        record_side_effect(rollback_manifest, side_effect)
        compensating_actions = self._collect_compensating_actions(tool, metadata_obj, side_effect)

        local_restore: dict[str, object] = {"restored": [], "failed": [], "reason": "shadow restore unavailable"}
        if tool in _MUTATION_TOOLS:
            shadow_manifest_path = str(step.get("shadow_manifest_path", "")).strip()
            if shadow_manifest_path:
                local_restore = self._restore_shadow_entry(target_step_id, shadow_manifest_path)
                restored_value = local_restore.get("restored")
                restored_items = cast(list[object], restored_value) if isinstance(restored_value, list) else []
                for file_path in restored_items:
                    record_local_restore(rollback_manifest, str(file_path), "restored")
                failed_value = local_restore.get("failed")
                failed_items = cast(list[object], failed_value) if isinstance(failed_value, list) else []
                for failure in failed_items:
                    if not isinstance(failure, dict):
                        continue
                    record_local_restore(
                        rollback_manifest,
                        str(failure.get("file", "")),
                        "failed",
                        str(failure.get("reason", "")),
                    )
            else:
                local_restore = {"restored": [], "failed": [], "reason": "missing shadow manifest"}
        elif not compensating_actions:
            return self._finalize_undo(
                rollback_manifest,
                {
                    "status": "unsupported",
                    "reason": "external side effect scope",
                },
            )

        snapshot_restore = self._restore_checkpoint(step.get("checkpoint_ref"))

        action_results = self._execute_compensating_actions(compensating_actions)
        for action_result in action_results:
            _ar_argv = action_result.get("argv")
            record_compensating_action(
                rollback_manifest,
                str(action_result.get("effect_type", "external")),
                str(action_result.get("action", "")),
                str(action_result.get("command", "")),
                status=str(action_result.get("status", "failed")),
                argv=list(_ar_argv) if isinstance(_ar_argv, list) else None,
            )

        failed_actions = [row for row in action_results if str(row.get("status", "")) == "failed"]
        restored_files = cast(list[object], local_restore.get("restored", []))
        failed_restores = cast(list[object], local_restore.get("failed", []))
        restored_snapshot = snapshot_restore.get("status") == "restored"
        if failed_actions:
            return self._finalize_undo(
                rollback_manifest,
                {
                    "status": "rollback_failed",
                    "reason": "compensating actions failed",
                    "failed_actions": failed_actions,
                    "local_restore": local_restore,
                    "snapshot_restore": snapshot_restore,
                },
            )

        if failed_restores:
            return self._finalize_undo(
                rollback_manifest,
                {
                    "status": "partial",
                    "reason": str(local_restore.get("reason", "shadow restore partial")),
                    "local_restore": local_restore,
                    "snapshot_restore": snapshot_restore,
                },
            )

        if restored_files or restored_snapshot or action_results:
            return self._finalize_undo(
                rollback_manifest,
                {
                    "status": "ok",
                    "reason": "rollback complete",
                    "local_restore": local_restore,
                    "snapshot_restore": snapshot_restore,
                    "compensating_actions": action_results,
                },
            )
        return self._finalize_undo(
            rollback_manifest,
            {
                "status": "noop",
                "reason": str(local_restore.get("reason", "shadow restore unavailable")),
                "local_restore": local_restore,
                "snapshot_restore": snapshot_restore,
            },
        )

    def _write_step(self, step_id: str, payload: dict[str, object]) -> None:
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.journal_dir / f"{step_id}.json"
        tmp_path = out_path.with_name(f"{out_path.name}.tmp")
        _ = tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        os.rename(tmp_path, out_path)

    def _read_step(self, step_id: str) -> dict[str, object] | None:
        path = self.journal_dir / f"{step_id}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return cast(dict[str, object], payload) if isinstance(payload, dict) else None

    def _latest_step_id(self) -> str:
        if not self.journal_dir.exists():
            return ""
        candidates = sorted(self.journal_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            return ""
        return candidates[-1].stem

    def _capture_shadow_metadata(self, metadata: dict[str, object]) -> str:
        file_path = self._extract_file_path(metadata)
        if not file_path:
            return ""

        try:
            module = importlib.import_module("hooks.shadow_manager")
            begin_shadow_run = getattr(module, "begin_shadow_run", None)
            record_shadow_write = getattr(module, "record_shadow_write", None)
            if not callable(begin_shadow_run) or not callable(record_shadow_write):
                return ""

            run_id = cast(str, begin_shadow_run(str(self.project_dir), metadata={"source": "interaction_journal"}))
            _ = record_shadow_write(
                str(self.project_dir),
                run_id,
                str(file_path),
                source="interaction_journal",
                step_id=self._pending_step_id,
            )
            manifest_path = self.project_dir / ".omg" / "shadow" / run_id / "manifest.json"
            return str(manifest_path)
        except Exception:
            return ""

    def _restore_shadow_entry(self, step_id: str, shadow_manifest_path: str) -> dict[str, object]:
        manifest_path = Path(shadow_manifest_path)
        run_id = manifest_path.parent.name if manifest_path.name == "manifest.json" else ""
        if not run_id:
            return {"restored": [], "failed": [], "reason": "invalid shadow manifest path"}

        try:
            module = importlib.import_module("hooks.shadow_manager")
        except Exception:
            return {"restored": [], "failed": [], "reason": "shadow module unavailable"}

        restore_fn = getattr(module, "restore_shadow_entry", None)
        if not callable(restore_fn):
            return {"restored": [], "failed": [], "reason": "restore helper unavailable"}

        try:
            result = restore_fn(str(self.project_dir), run_id, step_id)
        except Exception:
            return {"restored": [], "failed": [], "reason": "shadow restore unavailable"}

        if not isinstance(result, dict):
            return {"restored": [], "failed": [], "reason": "shadow restore unavailable"}

        restored = result.get("restored") if isinstance(result.get("restored"), list) else []
        failed = result.get("failed") if isinstance(result.get("failed"), list) else []
        reason = str(result.get("reason", "shadow restore unavailable"))
        return {"restored": restored, "failed": failed, "reason": reason}

    def _derive_run_id(self, step: dict[str, object]) -> str:
        manifest_path = str(step.get("shadow_manifest_path", "")).strip()
        manifest = Path(manifest_path)
        if manifest.name == "manifest.json" and manifest.parent.name:
            return manifest.parent.name

        checkpoint_ref = step.get("checkpoint_ref")
        if isinstance(checkpoint_ref, dict):
            snapshot = checkpoint_ref.get("snapshot")
            if isinstance(snapshot, dict):
                snapshot_id = snapshot.get("id")
                if isinstance(snapshot_id, str) and snapshot_id.strip():
                    return snapshot_id.strip()
        return "unknown"

    def _checkpoint_reference(self, step_id: str) -> dict[str, object] | None:
        try:
            module = importlib.import_module("tools.session_snapshot")
        except Exception:
            return None

        create_snapshot = getattr(module, "create_snapshot", None)
        fork_branch = getattr(module, "fork_branch", None)
        if not callable(create_snapshot):
            return None

        try:
            state_dir = str(self.project_dir / ".omg" / "state")
            snapshot = create_snapshot(name=f"journal-{step_id}", state_dir=state_dir)
            reference: dict[str, object] = {"snapshot": snapshot}
            if callable(fork_branch) and isinstance(snapshot, dict):
                snapshot_id = str(snapshot.get("id", "")).strip()
                if snapshot_id:
                    branch_name = f"undo-{step_id[:12]}"
                    reference["branch"] = fork_branch(snapshot_id, branch_name, state_dir=state_dir)
            return reference
        except Exception:
            return None

    def _build_repro_pointer(self, run_id: str) -> str | None:
        normalized_run_id = run_id.strip()
        if not normalized_run_id:
            return None
        fallback = f".omg/evidence/repro-pack-{normalized_run_id}.json"
        try:
            result = build_repro_pack(str(self.project_dir), normalized_run_id)
        except Exception:
            evidence_path = self.project_dir / ".omg" / "evidence" / f"{normalized_run_id}.json"
            return fallback if evidence_path.exists() else None
        if result.get("status") != "ok":
            evidence_path = self.project_dir / ".omg" / "evidence" / f"{normalized_run_id}.json"
            return fallback if evidence_path.exists() else None
        path = result.get("path")
        return str(path) if isinstance(path, str) and path else None

    def _extract_file_path(self, metadata: dict[str, object]) -> str:
        candidates = (
            metadata.get("file"),
            metadata.get("file_path"),
            metadata.get("path"),
        )
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            value = candidate.strip()
            if not value:
                continue
            return value if os.path.isabs(value) else str(self.project_dir / value)
        return ""

    def _is_external_side_effect(self, tool: str, metadata: dict[str, object]) -> bool:
        if tool == "bash":
            scope = str(metadata.get("side_effect_scope", "")).strip().lower()
            if scope == "external":
                return True
            command = str(metadata.get("command", "")).lower()
            if any(token in command for token in ("npm publish", "git push", "pip install")):
                return True
        return False

    def _collect_compensating_actions(
        self,
        tool: str,
        metadata: dict[str, object],
        side_effect: dict[str, object],
    ) -> list[dict[str, object]]:
        action_rows: list[dict[str, object]] = []

        declared = metadata.get("compensating_action")
        if isinstance(declared, dict):
            action = str(declared.get("action", "")).strip()
            command = str(declared.get("command", "")).strip()
            if action and command:
                action_rows.append(
                    {
                        "effect_type": str(side_effect.get("category", "external")),
                        "action": action,
                        "command": command,
                    }
                )

        declared_list = metadata.get("compensating_actions")
        if isinstance(declared_list, list):
            for item in declared_list:
                if not isinstance(item, dict):
                    continue
                action = str(item.get("action", "")).strip()
                command = str(item.get("command", "")).strip()
                if not action or not command:
                    continue
                action_rows.append(
                    {
                        "effect_type": str(item.get("effect_type", side_effect.get("category", "external"))),
                        "action": action,
                        "command": command,
                    }
                )

        if tool == "bash" and not action_rows:
            default_command = str(side_effect.get("default_compensation", "")).strip()
            if default_command:
                action_rows.append(
                    {
                        "effect_type": str(side_effect.get("category", "external")),
                        "action": "default compensation",
                        "command": default_command,
                    }
                )
        return action_rows

    def _restore_checkpoint(self, checkpoint_ref: object) -> dict[str, object]:
        if not isinstance(checkpoint_ref, dict):
            return {"status": "skipped", "reason": "checkpoint unavailable"}

        snapshot = checkpoint_ref.get("snapshot")
        if not isinstance(snapshot, dict):
            return {"status": "skipped", "reason": "snapshot unavailable"}
        snapshot_id = str(snapshot.get("id", "")).strip()
        if not snapshot_id:
            return {"status": "skipped", "reason": "snapshot unavailable"}

        try:
            module = importlib.import_module("tools.session_snapshot")
        except Exception:
            return {"status": "failed", "reason": "snapshot module unavailable", "snapshot_id": snapshot_id}

        restore_snapshot = getattr(module, "restore_snapshot", None)
        if not callable(restore_snapshot):
            return {"status": "failed", "reason": "snapshot restore unavailable", "snapshot_id": snapshot_id}

        try:
            restored = bool(restore_snapshot(snapshot_id, state_dir=str(self.project_dir / ".omg" / "state")))
        except Exception:
            return {"status": "failed", "reason": "snapshot restore unavailable", "snapshot_id": snapshot_id}
        if restored:
            return {"status": "restored", "reason": "snapshot restore applied", "snapshot_id": snapshot_id}
        return {"status": "failed", "reason": "snapshot not found", "snapshot_id": snapshot_id}

    def _execute_compensating_actions(self, actions: list[dict[str, object]]) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for action in actions:
            raw_argv = action.get("argv")
            raw_command = str(action.get("command", "")).strip()
            if isinstance(raw_argv, list) and raw_argv:
                command_input: str | list[str] = raw_argv
                command_display = raw_command or " ".join(str(a) for a in raw_argv)
            elif raw_command:
                command_input = raw_command
                command_display = raw_command
            else:
                results.append(
                    {
                        "effect_type": str(action.get("effect_type", "external")),
                        "action": str(action.get("action", "")),
                        "command": raw_command,
                        "status": "failed",
                        "reason": "missing command",
                    }
                )
                continue
            argv = _normalize_command_argv(command_input)
            if argv is None:
                results.append(
                    {
                        "effect_type": str(action.get("effect_type", "external")),
                        "action": str(action.get("action", "")),
                        "command": command_display,
                        "status": "failed",
                        "reason": "rejected: shell execution pattern detected" if command_display else "rejected: empty or invalid command",
                    }
                )
                continue
            try:
                completed = subprocess.run(
                    argv,
                    cwd=str(self.project_dir),
                    shell=False,
                    check=False,
                    capture_output=True,
                    text=True,
                )
            except Exception as exc:
                results.append(
                    {
                        "effect_type": str(action.get("effect_type", "external")),
                        "action": str(action.get("action", "")),
                        "command": command_display,
                        "status": "failed",
                        "reason": f"execution error: {exc}",
                    }
                )
                continue

            if completed.returncode == 0:
                results.append(
                    {
                        "effect_type": str(action.get("effect_type", "external")),
                        "action": str(action.get("action", "")),
                        "command": command_display,
                        "argv": argv,
                        "status": "succeeded",
                    }
                )
                continue

            results.append(
                {
                    "effect_type": str(action.get("effect_type", "external")),
                    "action": str(action.get("action", "")),
                    "command": command_display,
                    "status": "failed",
                    "reason": (completed.stderr or completed.stdout or "command failed").strip() or "command failed",
                    "exit_code": completed.returncode,
                }
            )
        return results

    def _finalize_undo(self, rollback_manifest: dict[str, object], result: dict[str, object]) -> dict[str, object]:
        manifest_path = write_rollback_manifest(str(self.project_dir), rollback_manifest)
        merged = dict(result)
        merged["manifest_path"] = str(Path(manifest_path).relative_to(self.project_dir)).replace("\\", "/")
        return merged

    def _rollback_mode(self) -> str:
        if shutil.which("git"):
            return "branch+journal+repro"
        return "journal+repro"

    def _new_step_id(self) -> str:
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return f"{now}-{uuid.uuid4().hex[:8]}"

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
