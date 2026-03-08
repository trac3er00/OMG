"""Bounded context engine — composes per-run context packets.

Reads architecture signals, defense state, verification pointers, and
context pressure into a compact packet with artifact pointers (never raw
content), delta-only refresh support, and explicit budget limits.

Crash-isolated: ``build_packet`` never raises.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_MAX_SUMMARY_CHARS = 1000
_PACKET_REL_PATH = Path(".omg") / "state" / "context_engine_packet.json"

_STATE_PATHS = {
    "architecture_signal": Path(".omg") / "state" / "architecture_signal" / "latest.json",
    "defense_state": Path(".omg") / "state" / "defense_state" / "current.json",
    "background_verification": Path(".omg") / "state" / "background-verification.json",
    "context_pressure": Path(".omg") / "state" / ".context-pressure.json",
}


class ContextEngine:
    """Composes bounded context packets for downstream consumers."""

    def __init__(self, project_dir: str) -> None:
        self.project_dir = Path(project_dir)
        self._last_snapshot: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_packet(
        self,
        run_id: str,
        *,
        delta_only: bool = False,
    ) -> dict[str, Any]:
        """Build a compact context packet.

        Returns a dict with keys:
          - ``summary``: bounded text (<=1000 chars)
          - ``artifact_pointers``: list of relative paths to state artifacts
          - ``budget``: ``{max_chars: int, used_chars: int}``
          - ``delta_only``: bool
          - ``run_id``: str
        """
        try:
            return self._build(run_id, delta_only=delta_only)
        except Exception:
            return self._fallback(run_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build(self, run_id: str, *, delta_only: bool) -> dict[str, Any]:
        raw = self._read_all_state()
        artifact_pointers = self._collect_artifact_pointers()

        if not artifact_pointers and all(v == {} for v in raw.values()):
            pkt = self._fallback(run_id)
            pkt["delta_only"] = delta_only
            self._persist_packet(pkt)
            return pkt

        summary = self._compose_summary(raw)
        current_snapshot = self._snapshot_key(raw)

        if delta_only and self._last_snapshot is not None:
            changed_keys: list[str] = []
            for key in current_snapshot:
                if current_snapshot.get(key) != self._last_snapshot.get(key):
                    changed_keys.append(key)

            if not changed_keys:
                summary = "no changes since last packet"
                artifact_pointers = []

        self._last_snapshot = current_snapshot

        packet: dict[str, Any] = {
            "summary": summary,
            "artifact_pointers": artifact_pointers,
            "budget": {
                "max_chars": _MAX_SUMMARY_CHARS,
                "used_chars": len(summary),
            },
            "delta_only": delta_only,
            "run_id": run_id,
        }

        self._persist_packet(packet)
        return packet

    def _read_all_state(self) -> dict[str, Any]:
        """Read all state files, returning empty dicts for missing ones."""
        result: dict[str, Any] = {}
        for name, rel_path in _STATE_PATHS.items():
            result[name] = self._read_json(self.project_dir / rel_path)
        return result

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _collect_artifact_pointers(self) -> list[str]:
        """Collect relative paths to existing state artifacts — NO raw content."""
        pointers: list[str] = []
        for rel_path in _STATE_PATHS.values():
            full = self.project_dir / rel_path
            if full.exists():
                pointers.append(str(rel_path))
        return pointers

    def _compose_summary(self, raw: dict[str, Any]) -> str:
        """Compose a bounded summary from state signals."""
        parts: list[str] = []

        # Architecture signal
        arch = raw.get("architecture_signal", {})
        arch_summary = arch.get("summary", "")
        if arch_summary and arch_summary != "no architecture signals available":
            parts.append(f"arch: {arch_summary[:500]}")

        # Defense state
        defense = raw.get("defense_state", {})
        risk = defense.get("risk_level", "")
        actions = defense.get("actions", [])
        if risk:
            action_str = ", ".join(actions) if actions else "none"
            parts.append(f"defense: risk={risk} actions=[{action_str}]")

        # Background verification
        verif = raw.get("background_verification", {})
        v_status = verif.get("status", "")
        blockers = verif.get("blockers", [])
        if v_status:
            blocker_str = f" blockers={len(blockers)}" if blockers else ""
            parts.append(f"verification: status={v_status}{blocker_str}")

        # Context pressure
        pressure = raw.get("context_pressure", {})
        tool_count = pressure.get("tool_count")
        is_high = pressure.get("is_high")
        if tool_count is not None:
            parts.append(f"pressure: tools={tool_count} high={is_high}")

        if not parts:
            return "no context signals available"

        summary = " | ".join(parts)
        return summary[:_MAX_SUMMARY_CHARS]

    def _snapshot_key(self, raw: dict[str, Any]) -> dict[str, str]:
        """Create a hashable snapshot of raw state for delta comparison."""
        snap: dict[str, str] = {}
        for key, value in raw.items():
            snap[key] = json.dumps(value, sort_keys=True, ensure_ascii=True)
        return snap

    def _persist_packet(self, packet: dict[str, Any]) -> None:
        """Write packet to .omg/state/context_engine_packet.json atomically."""
        path = self.project_dir / _PACKET_REL_PATH
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.tmp")
            tmp.write_text(
                json.dumps(packet, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
            os.rename(tmp, path)
        except Exception:
            pass  # crash isolation

    def _fallback(self, run_id: str) -> dict[str, Any]:
        return {
            "summary": "no context signals available",
            "artifact_pointers": [],
            "budget": {"max_chars": _MAX_SUMMARY_CHARS, "used_chars": 0},
            "delta_only": False,
            "run_id": run_id,
        }
