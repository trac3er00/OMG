"""Bounded context packet compiler.

Reads the live context_engine_packet.json and emits provenance-only, bounded
summaries for each canonical host.  Raw transcript and session bodies are never
written to compiled output.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PACKET_REL_PATH = Path(".omg") / "state" / "context_engine_packet.json"
_ALLOWED_PACKET_KEYS = frozenset({
    "packet_version", "summary", "artifact_pointers", "provenance_pointers",
    "artifact_handles", "clarification_status", "ambiguity_state",
    "provenance_only", "governance", "release_metadata", "coordinator_run_id",
    "profile_digest", "budget", "delta_only", "run_id",
    "deterministic_contract",
})


def _resolve_root(root_dir) -> Path:
    return Path(root_dir).resolve() if root_dir else Path.cwd()


def _resolve_output_root(root: Path, output_root) -> Path:
    if output_root:
        out = Path(output_root).resolve()
        out.mkdir(parents=True, exist_ok=True)
        return out
    return root


def _load_packet(root: Path) -> dict[str, Any]:
    packet_path = root / _PACKET_REL_PATH
    if packet_path.exists():
        try:
            raw = json.loads(packet_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {k: v for k, v in raw.items() if k in _ALLOWED_PACKET_KEYS}
        except Exception:
            pass
    return {
        "packet_version": "1.0",
        "summary": "no active context signals",
        "artifact_pointers": [],
        "provenance_pointers": [],
        "artifact_handles": [],
        "provenance_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def compile_context_packets(
    *,
    root_dir=None,
    output_root=None,
    hosts=None,
) -> dict[str, Any]:
    root = _resolve_root(root_dir)
    output = _resolve_output_root(root, output_root)
    selected_hosts = list(hosts or ["claude", "codex", "gemini", "kimi"])
    packet = _load_packet(root)
    issued_at = datetime.now(timezone.utc).isoformat()

    packet["context_compile_issued_at"] = issued_at
    packet["hosts"] = selected_hosts

    packet_path = output / _PACKET_REL_PATH
    _write_json(packet_path, packet)
    emitted: list[str] = [str(packet_path.relative_to(output))]

    if "codex" in selected_hosts:
        frag_src = root / ".agents" / "skills" / "omg" / "AGENTS.fragment.md"
        frag_dst = output / ".agents" / "skills" / "omg" / "AGENTS.fragment.md"
        frag_dst.parent.mkdir(parents=True, exist_ok=True)
        if frag_src.exists():
            frag_dst.write_bytes(frag_src.read_bytes())
        else:
            frag_dst.write_text("# OMG Codex Context\n\n_No context signals available._\n", encoding="utf-8")
        emitted.append(str(frag_dst.relative_to(output)))

    if "gemini" in selected_hosts:
        gemini_src = root / ".gemini" / "settings.json"
        gemini_dst = output / ".gemini" / "settings.json"
        gemini_dst.parent.mkdir(parents=True, exist_ok=True)
        if gemini_src.exists():
            try:
                gemini_data = json.loads(gemini_src.read_text(encoding="utf-8"))
            except Exception:
                gemini_data = {}
        else:
            gemini_data = {}
        gemini_data.setdefault("_omg", {})["context_packet"] = {
            "summary": packet.get("summary", ""),
            "issued_at": issued_at,
        }
        _write_json(gemini_dst, gemini_data)
        emitted.append(str(gemini_dst.relative_to(output)))

    if "kimi" in selected_hosts:
        kimi_src = root / ".kimi" / "mcp.json"
        kimi_dst = output / ".kimi" / "mcp.json"
        kimi_dst.parent.mkdir(parents=True, exist_ok=True)
        if kimi_src.exists():
            try:
                kimi_data = json.loads(kimi_src.read_text(encoding="utf-8"))
            except Exception:
                kimi_data = {}
        else:
            kimi_data = {}
        kimi_data.setdefault("_omg", {})["context_packet"] = {
            "summary": packet.get("summary", ""),
            "issued_at": issued_at,
        }
        _write_json(kimi_dst, kimi_data)
        emitted.append(str(kimi_dst.relative_to(output)))

    return {
        "schema": "OmgContextCompileResult",
        "status": "ok",
        "hosts": selected_hosts,
        "artifacts": emitted,
        "packet": str(packet_path.relative_to(output)),
    }
