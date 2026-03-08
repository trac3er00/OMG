from __future__ import annotations

from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import shutil
import uuid
from typing import Any, cast

from runtime.repro_pack import build_repro_pack


class InteractionJournal:
    project_dir: Path
    journal_dir: Path

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir).resolve()
        self.journal_dir = self.project_dir / ".omg" / "state" / "interaction_journal"

    def record_step(self, tool: str, metadata: dict[str, object]) -> dict[str, object]:
        step_id = self._new_step_id()
        rollback_mode = "unsupported"
        if tool in {"write", "edit"}:
            rollback_mode = self._rollback_mode()
        checkpoint_ref = self._checkpoint_reference(step_id)

        shadow_manifest_path = ""
        if tool in {"write", "edit"}:
            shadow_manifest_path = self._capture_shadow_metadata(metadata)

        repro_pointer = self._build_repro_pointer(step_id)

        payload: dict[str, object] = {
            "schema": "InteractionJournalStep",
            "schema_version": "1.0.0",
            "step_id": step_id,
            "recorded_at": self._utc_now(),
            "tool": tool,
            "metadata": dict(metadata),
            "rollback_mode": rollback_mode,
            "checkpoint_ref": checkpoint_ref,
            "shadow_manifest_path": shadow_manifest_path,
            "repro_pointer": repro_pointer,
        }
        self._write_step(step_id, payload)

        return {
            "step_id": step_id,
            "status": "recorded",
            "rollback_mode": rollback_mode,
            "repro_pointer": repro_pointer,
        }

    def undo(self, step_id: str) -> dict[str, str]:
        target_step_id = step_id.strip() or self._latest_step_id()
        if not target_step_id:
            return {"status": "noop", "reason": "no journal entries"}

        step = self._read_step(target_step_id)
        if step is None:
            return {"status": "noop", "reason": "step not found"}

        tool = str(step.get("tool", "")).strip()
        metadata = step.get("metadata")
        metadata_obj = cast(dict[str, object], metadata) if isinstance(metadata, dict) else {}

        if tool not in {"write", "edit"}:
            if self._is_external_side_effect(tool, metadata_obj):
                return {"status": "unsupported", "reason": "external side effect scope"}
            return {"status": "unsupported", "reason": "external side effect scope"}

        shadow_manifest_path = str(step.get("shadow_manifest_path", "")).strip()
        if not shadow_manifest_path:
            return {"status": "noop", "reason": "missing shadow manifest"}

        restore_result = self._restore_shadow_entry(shadow_manifest_path)
        if restore_result:
            return {"status": "ok", "reason": "shadow restore applied"}
        return {"status": "noop", "reason": "shadow restore unavailable"}

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
            _ = record_shadow_write(str(self.project_dir), run_id, str(file_path), source="interaction_journal")
            manifest_path = self.project_dir / ".omg" / "shadow" / run_id / "manifest.json"
            return str(manifest_path)
        except Exception:
            return ""

    def _restore_shadow_entry(self, shadow_manifest_path: str) -> bool:
        try:
            module = importlib.import_module("hooks.shadow_manager")
        except Exception:
            return False

        restore_fn = getattr(module, "restore_shadow_entry", None)
        if not callable(restore_fn):
            return False

        call_variants: list[tuple[tuple[Any, ...], dict[str, Any]]] = [
            ((), {"project_dir": str(self.project_dir), "manifest_path": shadow_manifest_path}),
            ((), {"project_dir": str(self.project_dir), "shadow_manifest_path": shadow_manifest_path}),
            ((), {"manifest_path": shadow_manifest_path}),
            ((str(self.project_dir), shadow_manifest_path), {}),
            ((shadow_manifest_path,), {}),
        ]
        for args, kwargs in call_variants:
            try:
                _ = restore_fn(*args, **kwargs)
                return True
            except TypeError:
                continue
            except Exception:
                return False
        return False

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

    def _build_repro_pointer(self, step_id: str) -> str | None:
        try:
            result = build_repro_pack(str(self.project_dir), step_id)
        except Exception:
            return None
        if result.get("status") != "ok":
            return None
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

    def _rollback_mode(self) -> str:
        if shutil.which("git"):
            return "branch+journal+repro"
        return "journal+repro"

    def _new_step_id(self) -> str:
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return f"{now}-{uuid.uuid4().hex[:8]}"

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
