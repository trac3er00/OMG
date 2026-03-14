from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lineage_db_path(project_dir: str) -> Path:
    return Path(project_dir) / ".omg" / "lineage" / "adjacency.sqlite3"


def _lineage_conn(project_dir: str) -> sqlite3.Connection:
    path = _lineage_db_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lineage_edges (
            edge_id TEXT PRIMARY KEY,
            parent_node TEXT NOT NULL,
            child_node TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            run_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_lineage_scope
        ON lineage_edges(run_id, profile_id, parent_node, child_node)
        """
    )
    conn.commit()
    return conn


def add_lineage_edge(
    project_dir: str,
    *,
    parent_node: str,
    child_node: str,
    edge_type: str,
    run_id: str,
    profile_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    edge_id = f"edge-{uuid4().hex}"
    payload = {
        "edge_id": edge_id,
        "parent_node": parent_node,
        "child_node": child_node,
        "edge_type": edge_type,
        "run_id": run_id,
        "profile_id": profile_id,
        "created_at": _now(),
        "metadata": metadata or {},
    }
    conn = _lineage_conn(project_dir)
    conn.execute(
        """
        INSERT INTO lineage_edges(
            edge_id, parent_node, child_node, edge_type, run_id, profile_id, created_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["edge_id"],
            payload["parent_node"],
            payload["child_node"],
            payload["edge_type"],
            payload["run_id"],
            payload["profile_id"],
            payload["created_at"],
            json.dumps(payload["metadata"], ensure_ascii=True),
        ),
    )
    conn.commit()
    conn.close()
    return payload


def traverse_lineage(
    project_dir: str,
    *,
    start_node: str,
    run_id: str,
    profile_id: str,
    max_depth: int = 3,
) -> dict[str, Any]:
    bounded_depth = max(1, min(int(max_depth), 16))
    conn = _lineage_conn(project_dir)
    queue: deque[tuple[str, int]] = deque([(start_node, 0)])
    nodes: set[str] = {start_node}
    seen_edges: set[str] = set()
    edges: list[dict[str, Any]] = []

    while queue:
        node, depth = queue.popleft()
        if depth >= bounded_depth:
            continue
        rows = conn.execute(
            """
            SELECT edge_id, parent_node, child_node, edge_type, run_id, profile_id, created_at, metadata_json
            FROM lineage_edges
            WHERE run_id = ? AND profile_id = ? AND parent_node = ?
            ORDER BY created_at ASC
            """,
            (run_id, profile_id, node),
        ).fetchall()
        for row in rows:
            edge_id = str(row["edge_id"])
            if edge_id in seen_edges:
                continue
            seen_edges.add(edge_id)
            child_node = str(row["child_node"])
            nodes.add(child_node)
            edges.append(
                {
                    "edge_id": edge_id,
                    "parent_node": str(row["parent_node"]),
                    "child_node": child_node,
                    "edge_type": str(row["edge_type"]),
                    "run_id": str(row["run_id"]),
                    "profile_id": str(row["profile_id"]),
                    "created_at": str(row["created_at"]),
                    "metadata": _parse_json_object(row["metadata_json"]),
                }
            )
            queue.append((child_node, depth + 1))

    conn.close()
    return {
        "schema": "LineageTraversalResult",
        "start_node": start_node,
        "run_id": run_id,
        "profile_id": profile_id,
        "max_depth": bounded_depth,
        "nodes": sorted(nodes),
        "edges": edges,
    }


def build_lineage_manifest(
    project_dir: str,
    *,
    artifact_type: str,
    sources: list[dict[str, Any]],
    privacy: str,
    license: str,
    derivation: dict[str, Any],
    trace_id: str | None = None,
) -> dict[str, Any]:
    lineage_id = f"lineage-{uuid4().hex}"
    payload = {
        "schema": "DataLineageManifest",
        "lineage_id": lineage_id,
        "generated_at": _now(),
        "artifact_type": artifact_type,
        "sources": sources,
        "privacy": privacy,
        "license": license,
        "derivation": derivation,
        "trace_id": trace_id or "",
    }
    validation = validate_lineage_manifest(payload)
    payload["status"] = validation["status"]
    payload["errors"] = validation["errors"]

    rel_path = Path(".omg") / "lineage" / f"{lineage_id}.json"
    path = Path(project_dir) / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["path"] = rel_path.as_posix()

    trace_node = str(payload.get("trace_id", "")).strip()
    if trace_node:
        add_lineage_edge(
            project_dir,
            parent_node=trace_node,
            child_node=lineage_id,
            edge_type="trace_to_lineage",
            run_id=trace_node,
            profile_id="",
            metadata={"artifact_type": artifact_type},
        )
    return payload


def validate_lineage_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not payload.get("artifact_type"):
        errors.append("artifact_type is required")
    if not payload.get("privacy"):
        errors.append("privacy is required")
    if not payload.get("license"):
        errors.append("license is required")
    sources = payload.get("sources", [])
    if not isinstance(sources, list) or not sources:
        errors.append("sources are required")
    else:
        for idx, source in enumerate(sources):
            if not isinstance(source, dict):
                errors.append(f"source {idx} must be an object")
                continue
            if not source.get("license"):
                errors.append(f"source {idx} missing license")
            if not source.get("path"):
                errors.append(f"source {idx} missing path")
    return {
        "schema": "DataLineageValidationResult",
        "status": "ok" if not errors else "error",
        "errors": errors,
    }


def _parse_json_object(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


__all__ = [
    "add_lineage_edge",
    "build_lineage_manifest",
    "traverse_lineage",
    "validate_lineage_manifest",
]
