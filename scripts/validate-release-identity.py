#!/usr/bin/env python3
"""Read-only release identity validator.

Usage:
    python3 scripts/validate-release-identity.py --scope all --forbid-version <forbid-version>
    python3 scripts/validate-release-identity.py --scope authored
    python3 scripts/validate-release-identity.py --scope derived
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from runtime.release_surfaces import AUTHORED_SURFACES, SCOPED_RESIDUE_TARGETS
from registry.verify_artifact import verify_artifact_statement

import importlib.util

_SYNC_SCRIPT = _REPO_ROOT / "scripts" / "sync-release-identity.py"
_sync_spec = importlib.util.spec_from_file_location("sync_release_identity", _SYNC_SCRIPT)
assert _sync_spec is not None and _sync_spec.loader is not None
_sync_mod = importlib.util.module_from_spec(_sync_spec)
_sync_spec.loader.exec_module(_sync_mod)

check_surface = _sync_mod.check_surface
extract_canonical_version = _sync_mod.extract_canonical_version


_DERIVED_JSON_SURFACES: list[tuple[str, list[str]]] = [
    ("dist/public/manifest.json", ["contract_version"]),
    ("dist/enterprise/manifest.json", ["contract_version"]),
    ("artifacts/release/dist/public/manifest.json", ["contract_version"]),
    ("artifacts/release/dist/enterprise/manifest.json", ["contract_version"]),
]

_DERIVED_AST_SURFACE = "build/lib/runtime/adoption.py"
_PROMOTION_MANIFEST_SURFACES = {
    "artifacts/release/dist/public/manifest.json",
    "artifacts/release/dist/enterprise/manifest.json",
}

_CHANGELOG_HISTORICAL_RE = re.compile(r"^## \[?\d+\.\d+\.\d+\]?")


def validate_authored(repo_root: Path, canonical: str) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    for surface in AUTHORED_SURFACES:
        drifts = check_surface(repo_root, surface, canonical)
        for label, found in drifts:
            blockers.append({
                "surface": label,
                "found": found if found is not None else "<not found>",
                "expected": canonical,
            })
    status = "fail" if blockers else "ok"
    return {"status": status, "blockers": blockers}


def validate_derived(repo_root: Path, canonical: str) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []

    for rel_path, key_path in _DERIVED_JSON_SURFACES:
        full_path = repo_root / rel_path
        if not full_path.exists():
            continue
        try:
            data = json.loads(full_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        current: Any = data
        for key in key_path:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                current = None
                break
        if current is not None and current != canonical:
            blockers.append({
                "surface": rel_path,
                "found": str(current),
                "expected": canonical,
            })

        if rel_path in _PROMOTION_MANIFEST_SURFACES:
            blockers.extend(_validate_promotion_manifest_attestations(rel_path=rel_path, payload=data))

    ast_path = repo_root / _DERIVED_AST_SURFACE
    if ast_path.exists():
        try:
            tree = ast.parse(ast_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "CANONICAL_VERSION":
                            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                                if node.value.value != canonical:
                                    blockers.append({
                                        "surface": _DERIVED_AST_SURFACE,
                                        "found": node.value.value,
                                        "expected": canonical,
                                    })
        except (OSError, SyntaxError):
            pass

    status = "fail" if blockers else "ok"
    return {"status": status, "blockers": blockers}


def _collect_attestations(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload.get("attestations")
    if not isinstance(rows, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        artifact_path = str(row.get("artifact_path", "")).strip()
        statement = row.get("statement")
        signer_pubkey = row.get("signer_pubkey")
        if not artifact_path or not isinstance(statement, dict) or not isinstance(signer_pubkey, str):
            continue
        indexed[artifact_path] = row
    return indexed


def _validate_promotion_manifest_attestations(*, rel_path: str, payload: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return blockers

    attestations = _collect_attestations(payload)
    if not attestations and artifacts:
        blockers.append({
            "surface": f"{rel_path}#missing_attestation",
            "found": "absent",
            "expected": "signed attestation records for promotion artifacts",
        })
        return blockers

    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_path = str(artifact.get("path", "")).strip()
        digest = str(artifact.get("sha256", "")).strip().lower()
        if not artifact_path or not digest:
            continue

        record = attestations.get(artifact_path)
        if record is None:
            blockers.append({
                "surface": f"{rel_path}#missing_attestation:{artifact_path}",
                "found": "absent",
                "expected": "signed attestation",
            })
            continue

        statement = record.get("statement")
        signer_pubkey = record.get("signer_pubkey")
        if not isinstance(statement, dict) or not isinstance(signer_pubkey, str):
            blockers.append({
                "surface": f"{rel_path}#invalid_attestation:{artifact_path}",
                "found": "malformed",
                "expected": "statement dict and signer_pubkey",
            })
            continue

        subject = statement.get("subject")
        subject_digest = ""
        if isinstance(subject, list) and subject and isinstance(subject[0], dict):
            digest_map = subject[0].get("digest")
            if isinstance(digest_map, dict):
                value = digest_map.get("sha256")
                if isinstance(value, str):
                    subject_digest = value.lower()
        if subject_digest != digest:
            blockers.append({
                "surface": f"{rel_path}#subject_digest_mismatch:{artifact_path}",
                "found": subject_digest or "<missing>",
                "expected": digest,
            })
            continue

        if not verify_artifact_statement(statement, signer_pubkey=signer_pubkey):
            blockers.append({
                "surface": f"{rel_path}#invalid_signature:{artifact_path}",
                "found": "verification_failed",
                "expected": "offline_hmac_valid_signature",
            })

    return blockers


def _is_changelog_historical(line: str, forbid_version: str) -> bool:
    return (
        _CHANGELOG_HISTORICAL_RE.match(line.strip()) is not None
        and forbid_version in line
    )


def _scan_file_for_residue(
    file_path: Path, rel_path: str, forbid_version: str,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return blockers

    for line_num, line in enumerate(lines, start=1):
        if forbid_version not in line:
            continue
        if file_path.name == "CHANGELOG.md" and _is_changelog_historical(line, forbid_version):
            continue
        blockers.append({
            "file": rel_path,
            "line": line_num,
            "content": line.strip(),
        })
    return blockers


def scan_scoped_residue(repo_root: Path, forbid_version: str) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []

    for target in SCOPED_RESIDUE_TARGETS:
        full_path = repo_root / target
        if not full_path.exists():
            continue

        if full_path.is_file():
            blockers.extend(_scan_file_for_residue(full_path, target, forbid_version))
        elif full_path.is_dir():
            for child in sorted(full_path.rglob("*")):
                if child.is_file():
                    rel = str(child.relative_to(repo_root))
                    blockers.extend(_scan_file_for_residue(child, rel, forbid_version))

    status = "fail" if blockers else "ok"
    return {"status": status, "forbid_version": forbid_version, "blockers": blockers}


def build_report(
    *,
    canonical: str,
    scope: str,
    forbid_version: str | None,
    authored: dict[str, Any] | None,
    derived: dict[str, Any] | None,
    scoped_residue: dict[str, Any] | None,
) -> dict[str, Any]:
    has_failure = False
    for section in (authored, derived, scoped_residue):
        if section is not None and section.get("status") == "fail":
            has_failure = True
            break

    report: dict[str, Any] = {
        "canonical_version": canonical,
        "scope": scope,
        "forbid_version": forbid_version,
    }

    if authored is not None:
        report["authored"] = authored
    if derived is not None:
        report["derived"] = derived
    if scoped_residue is not None:
        report["scoped_residue"] = scoped_residue

    report["overall_status"] = "fail" if has_failure else "ok"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only release identity validator")
    parser.add_argument("--scope", choices=["authored", "derived", "all"], default="all")
    parser.add_argument("--forbid-version", default=None)
    parser.add_argument("--output-json", default=None)
    args = parser.parse_args()

    adoption_file = _REPO_ROOT / "runtime" / "adoption.py"
    if not adoption_file.exists():
        print(json.dumps({"error": "runtime/adoption.py not found"}), file=sys.stderr)
        return 1

    canonical = extract_canonical_version(adoption_file)
    if canonical is None:
        print(json.dumps({"error": "CANONICAL_VERSION not found"}), file=sys.stderr)
        return 1

    authored_result = None
    derived_result = None
    residue_result = None

    if args.scope in ("authored", "all"):
        authored_result = validate_authored(_REPO_ROOT, canonical)
    else:
        authored_result = {"status": "skipped", "blockers": []}

    if args.scope in ("derived", "all"):
        derived_result = validate_derived(_REPO_ROOT, canonical)
    else:
        derived_result = {"status": "skipped", "blockers": []}

    if args.forbid_version and args.scope in ("derived", "all"):
        residue_result = scan_scoped_residue(_REPO_ROOT, args.forbid_version)

    report = build_report(
        canonical=canonical,
        scope=args.scope,
        forbid_version=args.forbid_version,
        authored=authored_result,
        derived=derived_result,
        scoped_residue=residue_result,
    )

    output = json.dumps(report, indent=2)

    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)

    return 1 if report["overall_status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
