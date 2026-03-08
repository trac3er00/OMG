#!/usr/bin/env python3
"""OMG v1 Shadow Manager

Maintains overlay-style shadow writes and evidence artifacts.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import shutil
import socket
import sys
from datetime import datetime, timezone
from typing import Any

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)
try:
    from hooks._common import _resolve_project_dir
    from hooks.security_validators import ensure_path_within_dir, validate_opaque_identifier
except ImportError:
    _common = importlib.import_module("_common")
    security_validators = importlib.import_module("security_validators")
    _resolve_project_dir = _common._resolve_project_dir
    ensure_path_within_dir = security_validators.ensure_path_within_dir
    validate_opaque_identifier = security_validators.validate_opaque_identifier


def _project_dir() -> str:
    return _resolve_project_dir()


def _shadow_root(project_dir: str) -> str:
    return os.path.join(project_dir, ".omg", "shadow")


def _evidence_root(project_dir: str) -> str:
    return os.path.join(project_dir, ".omg", "evidence")


def _active_run_path(project_dir: str) -> str:
    return os.path.join(_shadow_root(project_dir), "active-run")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _validated_run_id(run_id: str) -> str:
    return validate_opaque_identifier(run_id, "run_id")


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def ensure_shadow_dirs(project_dir: str) -> None:
    os.makedirs(_shadow_root(project_dir), exist_ok=True)
    os.makedirs(_evidence_root(project_dir), exist_ok=True)


def set_active_run_id(project_dir: str, run_id: str) -> None:
    ensure_shadow_dirs(project_dir)
    run_id = _validated_run_id(run_id)
    with open(_active_run_path(project_dir), "w", encoding="utf-8") as f:
        f.write(run_id)


def get_active_run_id(project_dir: str) -> str | None:
    env_id = os.environ.get("OMG_RUN_ID")
    if env_id:
        return env_id
    path = _active_run_path(project_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = f.read().strip()
            return value or None
    except Exception:
        return None


def begin_shadow_run(project_dir: str, metadata: dict[str, Any] | None = None) -> str:
    run_id = _validated_run_id(get_active_run_id(project_dir) or _new_run_id())
    run_dir = os.path.join(_shadow_root(project_dir), run_id)
    os.makedirs(run_dir, exist_ok=True)

    manifest_path = os.path.join(run_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        manifest = {
            "run_id": run_id,
            "created_at": _utc_now(),
            "status": "open",
            "files": [],
            "metadata": metadata or {},
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    set_active_run_id(project_dir, run_id)
    return run_id


def _load_manifest(run_dir: str) -> dict[str, Any]:
    path = os.path.join(run_dir, "manifest.json")
    if not os.path.exists(path):
        return {"files": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("files", [])
                return data
            return {"files": []}
    except Exception:
        return {"files": []}


def _save_manifest(run_dir: str, manifest: dict[str, Any]) -> None:
    path = os.path.join(run_dir, "manifest.json")
    manifest["updated_at"] = _utc_now()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def map_shadow_path(project_dir: str, run_id: str, file_path: str) -> str:
    run_id = _validated_run_id(run_id)
    rel = os.path.relpath(os.path.abspath(file_path), os.path.abspath(project_dir))
    rel = rel.replace("..", "_up_")
    return os.path.join(_shadow_root(project_dir), run_id, "overlay", rel)


def record_shadow_write(project_dir: str, run_id: str, file_path: str, source: str = "tool") -> dict[str, Any]:
    run_id = _validated_run_id(run_id)
    run_dir = os.path.join(_shadow_root(project_dir), run_id)
    os.makedirs(run_dir, exist_ok=True)

    shadow_path = map_shadow_path(project_dir, run_id, file_path)
    os.makedirs(os.path.dirname(shadow_path), exist_ok=True)

    abs_file = file_path if os.path.isabs(file_path) else os.path.join(project_dir, file_path)
    if os.path.exists(abs_file):
        shutil.copy2(abs_file, shadow_path)
        file_hash = _hash_file(abs_file)
    else:
        file_hash = ""

    manifest = _load_manifest(run_dir)
    rel = os.path.relpath(abs_file, project_dir)
    entry = {
        "file": rel,
        "shadow_file": os.path.relpath(shadow_path, run_dir),
        "recorded_at": _utc_now(),
        "source": source,
        "sha256": file_hash,
    }

    files = manifest.get("files", [])
    # Replace existing entry for same file.
    files = [f for f in files if f.get("file") != rel]
    files.append(entry)
    manifest["files"] = files
    _save_manifest(run_dir, manifest)

    return entry


def create_evidence_pack(
    project_dir: str,
    run_id: str,
    tests: list[dict[str, Any]] | None = None,
    security_scans: list[dict[str, Any]] | None = None,
    diff_summary: dict[str, Any] | None = None,
    reproducibility: dict[str, Any] | None = None,
    unresolved_risks: list[str] | None = None,
    provenance: list[dict[str, Any]] | None = None,
    trust_scores: dict[str, Any] | None = None,
    api_twin: dict[str, Any] | None = None,
    route_metadata: dict[str, Any] | None = None,
    trace_ids: list[str] | None = None,
    lineage: dict[str, Any] | None = None,
    executor: dict[str, Any] | None = None,
    environment: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
) -> str:
    ensure_shadow_dirs(project_dir)
    run_id = _validated_run_id(run_id)
    
    # Default executor if not provided
    if executor is None:
        executor = {
            "user": os.getenv("USER", "unknown"),
            "pid": str(os.getpid()),
        }
    
    # Default environment if not provided
    if environment is None:
        environment = {
            "hostname": socket.gethostname(),
            "platform": platform.system(),
        }
    
    evidence = {
        "schema": "EvidencePack",
        "schema_version": 2,
        "run_id": run_id,
        "created_at": _utc_now(),
        "tests": tests or [],
        "security_scans": security_scans or [],
        "diff_summary": diff_summary or {},
        "reproducibility": reproducibility or {},
        "unresolved_risks": unresolved_risks or [],
        "provenance": provenance or [],
        "trust_scores": trust_scores or {},
        "api_twin": api_twin or {},
        "route_metadata": route_metadata or {},
        "trace_ids": trace_ids or [],
        "lineage": lineage or {},
        "executor": executor,
        "environment": environment,
        "artifacts": artifacts or [],
    }
    evidence_path = ensure_path_within_dir(
        _evidence_root(project_dir),
        os.path.join(_evidence_root(project_dir), f"{run_id}.json"),
    )
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)
    return evidence_path


def has_recent_evidence(project_dir: str, hours: int = 24) -> bool:
    ev_dir = _evidence_root(project_dir)
    if not os.path.isdir(ev_dir):
        return False

    now = datetime.now(timezone.utc).timestamp()
    max_age = hours * 3600

    for name in os.listdir(ev_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(ev_dir, name)
        try:
            age = now - os.path.getmtime(path)
            if age <= max_age:
                return True
        except OSError:
            continue
    return False


def apply_shadow(project_dir: str, run_id: str) -> dict[str, Any]:
    run_id = _validated_run_id(run_id)
    run_dir = os.path.join(_shadow_root(project_dir), run_id)
    manifest = _load_manifest(run_dir)
    applied = []

    for item in manifest.get("files", []):
        rel = item.get("file")
        shadow_rel = item.get("shadow_file")
        if not rel or not shadow_rel:
            continue
        src = os.path.join(run_dir, shadow_rel)
        dst = os.path.join(project_dir, rel)
        if not os.path.exists(src):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        applied.append(rel)

    manifest["status"] = "applied"
    manifest["applied_at"] = _utc_now()
    _save_manifest(run_dir, manifest)

    return {"run_id": run_id, "applied": applied}


def drop_shadow(project_dir: str, run_id: str) -> dict[str, Any]:
    run_id = _validated_run_id(run_id)
    run_dir = os.path.join(_shadow_root(project_dir), run_id)
    if os.path.isdir(run_dir):
        print(f"[OMG] Deleting: {run_dir}", file=sys.stderr)
        shutil.rmtree(run_dir, ignore_errors=True)

    active = get_active_run_id(project_dir)
    if active == run_id:
        try:
            os.remove(_active_run_path(project_dir))
        except OSError:
            pass

    return {"run_id": run_id, "dropped": True}


def _handle_post_tool_use(payload: dict[str, Any]) -> None:
    tool = payload.get("tool_name", "")
    if tool not in ("Write", "Edit", "MultiEdit"):
        return

    tool_input = payload.get("tool_input", {}) if isinstance(payload.get("tool_input"), dict) else {}
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    tool_resp = payload.get("tool_response", {})
    success = None
    if isinstance(tool_resp, dict):
        success = tool_resp.get("success")

    if success is False:
        return

    project_dir = _project_dir()
    run_id = begin_shadow_run(project_dir, metadata={"source": "post-tool-use"})
    record_shadow_write(project_dir, run_id, file_path)


def _main() -> int:
    # Early-exit: skip all work if shadow/evidence mode is not enabled
    project_dir = _project_dir()
    policy_path = os.path.join(project_dir, ".omg", "policy.yaml")
    if not os.path.exists(policy_path) and os.environ.get("OMG_EVIDENCE_REQUIRED", "0") != "1":
        return 0

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    try:
        _handle_post_tool_use(payload)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
