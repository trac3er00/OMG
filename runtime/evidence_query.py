from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import cast

from runtime.context_engine import load_profile_digest
from runtime.evidence_requirements import (
    EVIDENCE_REQUIREMENTS_BY_PROFILE,
    requirements_for_profile,
    resolve_profile,
)

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]


_EVIDENCE_DIRS = (
    Path(".omg") / "evidence",
    Path(".omg") / "tracebank",
    Path(".omg") / "evals",
    Path(".omg") / "lineage",
    Path(".omg") / "state",
)


def _iter_json_files(root: Path, rel_dir: Path) -> list[Path]:
    directory = root / rel_dir
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def _load_json(path: Path) -> JsonObject | None:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return cast(JsonObject, payload)


def _json_checksum(payload: JsonObject) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8", errors="ignore")).hexdigest()


def _record_copy_with_context_metadata(root: Path, record: JsonObject) -> JsonObject:
    run_id = _record_string(record, "run_id")
    if not run_id:
        return record

    profile_digest = load_profile_digest(root)
    existing_profile_version = _record_string(record, "profile_version")
    profile_version = existing_profile_version or str(profile_digest.get("profile_version", "")).strip()
    evidence_profile = _record_string(record, "evidence_profile").strip()
    try:
        resolved = resolve_profile(evidence_profile if evidence_profile else None)
        evidence_requirements = requirements_for_profile(evidence_profile if evidence_profile else None)
        profile_is_known = True
        if resolved is not None:
            evidence_profile = resolved  # use canonical name
    except ValueError:
        evidence_requirements = requirements_for_profile(None)
        profile_is_known = False

    intent_gate_payload = _load_json(root / ".omg" / "state" / "intent_gate" / f"{run_id}.json") or {}
    existing_intent_gate_version = _record_string(record, "intent_gate_version")
    intent_gate_version = existing_intent_gate_version or (
        _record_string(intent_gate_payload, "intent_gate_version")
        or _record_string(intent_gate_payload, "schema_version")
        or _record_string(intent_gate_payload, "version")
    )

    packet_payload = _load_json(root / ".omg" / "state" / "context_engine_packet.json") or {}
    packet_run_id = _record_string(packet_payload, "run_id")
    scoped_packet = packet_payload if packet_run_id == run_id else {}
    context_material: JsonObject = {
        "run_id": run_id,
        "profile_version": profile_version,
        "intent_gate_version": intent_gate_version,
    }
    if scoped_packet:
        context_material["context_packet"] = scoped_packet
    if intent_gate_payload:
        context_material["intent_gate"] = intent_gate_payload

    existing_context_checksum = _record_string(record, "context_checksum")
    context_checksum = existing_context_checksum or _json_checksum(context_material)
    enriched = dict(record)
    enriched["context_checksum"] = context_checksum
    enriched["profile_version"] = profile_version
    enriched["intent_gate_version"] = intent_gate_version
    enriched["evidence_profile"] = evidence_profile
    enriched["evidence_requirements"] = cast(JsonValue, [str(item) for item in evidence_requirements])
    enriched["evidence_profile_known"] = profile_is_known
    if evidence_profile and not profile_is_known:
        enriched["evidence_profile_error"] = f"unknown_evidence_profile:{evidence_profile}"
    return enriched


def _read_jsonl(path: Path) -> list[JsonObject]:
    if not path.exists():
        return []
    rows: list[JsonObject] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item: object = json.loads(line)  # pyright: ignore[reportAny]
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(cast(JsonObject, item))
    except OSError:
        return []
    return rows


def _record_string(record: JsonObject, key: str) -> str:
    value = record.get(key)
    return value if isinstance(value, str) else ""


def _record_string_list(record: JsonObject, key: str) -> list[str]:
    value = record.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _record_matches(
    record: JsonObject,
    *,
    run_id: str | None,
    profile_id: str | None,
    trace_id: str | None,
    schema: str | None,
    kind: str | None,
) -> bool:
    if run_id is not None and _record_string(record, "run_id") != run_id:
        return False
    if profile_id is not None and _record_string(record, "profile_id") != profile_id:
        return False
    if trace_id is not None:
        direct_trace_id = _record_string(record, "trace_id")
        trace_ids = _record_string_list(record, "trace_ids")
        if direct_trace_id != trace_id and trace_id not in trace_ids:
            return False
    if schema is not None and _record_string(record, "schema") != schema:
        return False
    if kind is not None:
        direct_kind = _record_string(record, "kind")
        artifacts = record.get("artifacts")
        artifact_kinds: list[str] = []
        if isinstance(artifacts, list):
            for item in artifacts:
                if isinstance(item, dict):
                    item_kind = item.get("kind")
                    if isinstance(item_kind, str):
                        artifact_kinds.append(item_kind)
        if direct_kind != kind and kind not in artifact_kinds:
            return False
    return True


def _artifact_handles_only(record: JsonObject) -> JsonObject:
    artifacts_raw = record.get("artifacts")
    if not isinstance(artifacts_raw, list):
        return record

    artifact_handles: list[JsonObject] = []
    for item in artifacts_raw:
        if not isinstance(item, dict):
            continue
        handle: JsonObject = {
            "kind": _record_string(item, "kind"),
            "path": _record_string(item, "path"),
            "summary": _record_string(item, "summary"),
        }
        size_value = item.get("size_bytes")
        if isinstance(size_value, int):
            handle["size_bytes"] = size_value
        payload = item.get("payload")
        if payload is not None:
            handle["omitted_payload"] = True
        artifact_handles.append(handle)

    enriched = dict(record)
    enriched["artifacts"] = cast(JsonValue, artifact_handles)
    return enriched


def get_evidence_pack(project_dir: str, run_id: str) -> JsonObject | None:
    root = Path(project_dir)
    evidence_files = _iter_json_files(root, Path(".omg") / "evidence")
    for path in evidence_files:
        payload = _load_json(path)
        if payload is None:
            continue
        if payload.get("schema") != "EvidencePack":
            continue
        if _record_string(payload, "run_id") == run_id:
            return _record_copy_with_context_metadata(root, payload)
    return None


def query_evidence(
    project_dir: str,
    *,
    run_id: str | None = None,
    profile_id: str | None = None,
    trace_id: str | None = None,
    schema: str | None = None,
    kind: str | None = None,
) -> list[JsonObject]:
    root = Path(project_dir)
    records: list[JsonObject] = []

    for rel_dir in _EVIDENCE_DIRS:
        for path in _iter_json_files(root, rel_dir):
            payload = _load_json(path)
            if payload is None:
                continue
            if _record_matches(
                payload,
                run_id=run_id,
                profile_id=profile_id,
                trace_id=trace_id,
                schema=schema,
                kind=kind,
            ):
                records.append(_record_copy_with_context_metadata(root, _artifact_handles_only(payload)))

        for row in _read_jsonl(root / rel_dir / "events.jsonl"):
            if _record_matches(
                row,
                run_id=run_id,
                profile_id=profile_id,
                trace_id=trace_id,
                schema=schema,
                kind=kind,
            ):
                records.append(_record_copy_with_context_metadata(root, _artifact_handles_only(row)))

    return records


def list_evidence_packs(project_dir: str) -> list[JsonObject]:
    root = Path(project_dir)
    evidence_files = _iter_json_files(root, Path(".omg") / "evidence")
    payloads: list[tuple[float, JsonObject]] = []

    for path in evidence_files:
        payload = _load_json(path)
        if payload is None or payload.get("schema") != "EvidencePack":
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        payloads.append((mtime, _record_copy_with_context_metadata(root, payload)))

    payloads.sort(key=lambda item: item[0], reverse=True)
    return [payload for _, payload in payloads]


def get_trace(project_dir: str, trace_id: str) -> JsonObject | None:
    trace_rows = _read_jsonl(Path(project_dir) / ".omg" / "tracebank" / "events.jsonl")
    for row in trace_rows:
        if _record_string(row, "trace_id") == trace_id:
            return row
    return None


def get_eval(project_dir: str) -> JsonObject | None:
    return _load_json(Path(project_dir) / ".omg" / "evals" / "latest.json")


def get_lineage(project_dir: str, lineage_id: str) -> JsonObject | None:
    root = Path(project_dir)
    lineage_files = _iter_json_files(root, Path(".omg") / "lineage")
    for path in lineage_files:
        payload = _load_json(path)
        if payload is None:
            continue
        if _record_string(payload, "lineage_id") == lineage_id:
            return payload
    return None


def get_verification_state(project_dir: str) -> JsonObject | None:
    payload = _load_json(Path(project_dir) / ".omg" / "state" / "background-verification.json")
    if payload is None:
        return None
    if payload.get("schema") != "BackgroundVerificationState":
        return None
    return payload
