from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import cast

from runtime.evidence_query import (
    JsonObject,
    JsonValue,
    get_eval,
    get_evidence_pack,
    get_lineage,
    get_trace,
    get_verification_state,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> JsonObject | None:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return cast(JsonObject, payload)


def _hash_path(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8192)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _as_object_list(value: JsonValue | None) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_string_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_field(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _artifact_ref(*, kind: str, path: str, sha256: str = "", extras: JsonObject | None = None) -> JsonObject:
    artifact: JsonObject = {
        "kind": kind,
        "path": path,
        "sha256": sha256,
    }
    if extras:
        artifact.update(extras)
    return artifact


def _trace_reference(root: Path, trace_ids: list[str]) -> JsonObject | None:
    trace_path = root / ".omg" / "tracebank" / "events.jsonl"
    if not trace_path.exists():
        return None

    requested = sorted({trace_id for trace_id in trace_ids if trace_id})
    matched: list[str] = []
    matched_count = 0
    try:
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row: object = json.loads(line)  # pyright: ignore[reportAny]
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            row_payload = cast(JsonObject, row)
            trace_id = _string_field(row_payload, "trace_id")
            if trace_id in requested:
                matched_count += 1
                if trace_id not in matched:
                    matched.append(trace_id)
    except OSError:
        return None

    return _artifact_ref(
        kind="trace_events",
        path=".omg/tracebank/events.jsonl",
        sha256=_hash_path(trace_path),
        extras=cast(JsonObject, {"trace_ids": sorted(matched), "event_count": matched_count}),
    )


def _find_lineage_path(root: Path, lineage_id: str) -> str:
    if not lineage_id:
        return ""
    lineage_dir = root / ".omg" / "lineage"
    if not lineage_dir.exists():
        return ""

    for path in sorted(lineage_dir.glob("*.json")):
        payload = _load_json(path)
        if payload is None:
            continue
        if _string_field(payload, "lineage_id") == lineage_id:
            return _rel(path, root)
    return ""


def _security_artifacts(root: Path, scans: JsonValue | None) -> list[JsonObject]:
    artifacts: list[JsonObject] = []
    for item in _as_object_list(scans):
        path = _string_field(item, "path").strip()
        if not path:
            continue
        artifacts.append(
            _artifact_ref(
                kind="security_evidence",
                path=path,
                sha256=_hash_path(root / path),
                extras={"schema": _string_field(item, "schema")},
            )
        )
    return artifacts


def _browser_artifacts(root: Path, records: JsonValue | None) -> list[JsonObject]:
    artifacts: list[JsonObject] = []
    for item in _as_object_list(records):
        if _string_field(item, "kind") != "browser_trace":
            continue
        path = _string_field(item, "path").strip()
        if not path:
            continue
        artifacts.append(
            _artifact_ref(
                kind="browser_trace",
                path=path,
                sha256=_hash_path(root / path),
                extras={"trace_id": _string_field(item, "trace_id")},
            )
        )
    return artifacts


def _incident_artifacts(root: Path, records: JsonValue | None) -> list[JsonObject]:
    artifacts: list[JsonObject] = []
    for item in _as_object_list(records):
        kind = _string_field(item, "kind")
        if "incident" not in kind:
            continue
        path = _string_field(item, "path").strip()
        if not path:
            continue
        artifacts.append(
            _artifact_ref(
                kind=kind,
                path=path,
                sha256=_hash_path(root / path),
                extras={"trace_id": _string_field(item, "trace_id")},
            )
        )
    return artifacts


def _dedupe_artifacts(artifacts: list[JsonObject]) -> list[JsonObject]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[JsonObject] = []
    sorted_items = sorted(artifacts, key=lambda item: (_string_field(item, "kind"), _string_field(item, "path")))
    for artifact in sorted_items:
        key = (
            _string_field(artifact, "kind"),
            _string_field(artifact, "path"),
            _string_field(artifact, "sha256"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(artifact)
    return deduped


def build_repro_pack(project_dir: str, run_id: str) -> dict[str, str]:
    root = Path(project_dir)
    evidence_pack = get_evidence_pack(project_dir, run_id)
    if evidence_pack is None:
        return {
            "status": "error",
            "run_id": run_id,
            "reason": "evidence_pack_not_found",
        }

    evidence_pack_path = f".omg/evidence/{run_id}.json"
    artifacts: list[JsonObject] = [
        _artifact_ref(kind="evidence_pack", path=evidence_pack_path, sha256=_hash_path(root / evidence_pack_path))
    ]

    trace_ids = sorted(set(_as_string_list(evidence_pack.get("trace_ids"))))
    trace_file = root / ".omg" / "tracebank" / "events.jsonl"
    for trace_id in trace_ids:
        if get_trace(project_dir, trace_id) is None:
            continue
        artifacts.append(
            _artifact_ref(
                kind="trace",
                path=".omg/tracebank/events.jsonl",
                sha256=_hash_path(trace_file),
                extras={"trace_id": trace_id},
            )
        )
    trace_reference = _trace_reference(root, trace_ids)
    if trace_reference is not None:
        artifacts.append(trace_reference)

    eval_path = root / ".omg" / "evals" / "latest.json"
    if get_eval(project_dir) is not None and eval_path.exists():
        artifacts.append(_artifact_ref(kind="eval", path=".omg/evals/latest.json", sha256=_hash_path(eval_path)))

    lineage_payload = evidence_pack.get("lineage")
    lineage_id = ""
    if isinstance(lineage_payload, dict):
        lineage_payload_obj = cast(JsonObject, lineage_payload)
        lineage_id = _string_field(lineage_payload_obj, "lineage_id")
    if lineage_id and get_lineage(project_dir, lineage_id) is not None:
        lineage_path = _find_lineage_path(root, lineage_id)
        if lineage_path:
            artifacts.append(
                _artifact_ref(
                    kind="lineage",
                    path=lineage_path,
                    sha256=_hash_path(root / lineage_path),
                    extras={"lineage_id": lineage_id},
                )
            )

    artifacts.extend(_security_artifacts(root, evidence_pack.get("security_scans")))
    artifacts.extend(_browser_artifacts(root, evidence_pack.get("artifacts")))
    artifacts.extend(_incident_artifacts(root, evidence_pack.get("artifacts")))

    verification_path = root / ".omg" / "state" / "background-verification.json"
    if get_verification_state(project_dir) is not None and verification_path.exists():
        artifacts.append(
            _artifact_ref(
                kind="verification_state",
                path=".omg/state/background-verification.json",
                sha256=_hash_path(verification_path),
            )
        )

    unresolved_risks = _as_string_list(evidence_pack.get("unresolved_risks"))
    manifest: dict[str, object] = {
        "schema": "ReproPack",
        "schema_version": 1,
        "run_id": run_id,
        "evidence_pack_path": evidence_pack_path,
        "artifacts": _dedupe_artifacts(artifacts),
        "unresolved_risks": unresolved_risks,
        "assembled_at": _now(),
    }

    out_path = root / ".omg" / "evidence" / f"repro-pack-{run_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _ = out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return {
        "status": "ok",
        "run_id": run_id,
        "path": _rel(out_path, root),
    }
