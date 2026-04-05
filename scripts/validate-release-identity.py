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
import logging
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from runtime.release_surfaces import AUTHORED_SURFACES, SCOPED_RESIDUE_TARGETS
from registry.verify_artifact import verify_artifact_statement
from runtime.release_surface_compiler import compile_release_surfaces
from runtime.doc_generator import check_docs

import importlib.util


_logger = logging.getLogger(__name__)

_SYNC_SCRIPT = _REPO_ROOT / "scripts" / "sync-release-identity.py"
if not _SYNC_SCRIPT.exists() or not _SYNC_SCRIPT.resolve().is_relative_to(_REPO_ROOT):
    raise FileNotFoundError(f"sync-release-identity.py not found at {_SYNC_SCRIPT}")
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
_VERSION_HEADER_RE = re.compile(r"^##\s+\[?(\d+\.\d+\.\d+)\]?\b")

_REQUIRED_GENERATED_MARKERS: dict[str, tuple[str, ...]] = {
    "README.md": (
        "install-intro",
        "why-omg",
    ),
    "CHANGELOG.md": (),
    "docs/proof.md": ("proof-quickstart",),
    "QUICK-REFERENCE.md": ("quick-reference-hosts",),
    "INSTALL-VERIFICATION-INDEX.md": ("verification-index-targets",),
}

_EXPECTED_EXPLAIN_COMMANDS: dict[str, str] = {
    "docs/proof.md": "npx omg explain run --run-id <id>",
    "QUICK-REFERENCE.md": "npx omg explain run --run-id <id>",
}

_POSITIONAL_EXPLAIN_COMMAND = "omg explain run <id>"

_INSTALL_GUIDES = (
    "docs/install/claude-code.md",
    "docs/install/codex.md",
    "docs/install/gemini.md",
    "docs/install/kimi.md",
    "docs/install/opencode.md",
)

_BAD_LOCAL_INSTALL = "npm install @trac3r/oh-my-god"

_NPX_FRONT_DOOR_TARGETS: dict[str, tuple[str, ...]] = {
    "README.md": (
        "npx omg env doctor",
        "npx omg install --plan",
        "npx omg install --apply",
        "npx omg ship",
    ),
    "docs/install/claude-code.md": (
        "npx omg env doctor",
        "npx omg install --plan",
        "npx omg install --apply",
    ),
    "docs/install/codex.md": (
        "npx omg env doctor",
        "npx omg install --plan",
        "npx omg install --apply",
    ),
    "docs/install/opencode.md": (
        "npx omg env doctor",
        "npx omg install --plan",
        "npx omg install --apply",
    ),
}


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
        except (OSError, SyntaxError) as exc:
            _logger.debug("Failed to parse derived AST surface %s: %s", ast_path, exc, exc_info=True)

    status = "fail" if blockers else "ok"
    return {"status": status, "blockers": blockers}


_KNOWN_ATTESTATION_ALGORITHMS = {"ed25519-minisign"}


def _collect_attestations(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload.get("attestations")
    if not isinstance(rows, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        artifact_path = str(row.get("artifact_path", "")).strip()
        if not artifact_path:
            continue
        # New detached shape: statement_path + signature_path + signer_key_id + algorithm
        if row.get("statement_path") is not None or row.get("signature_path") is not None:
            indexed[artifact_path] = row
            continue
        # Inline shape: statement dict + signer_pubkey string
        statement = row.get("statement")
        signer_pubkey = row.get("signer_pubkey")
        if isinstance(statement, dict) and isinstance(signer_pubkey, str):
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

        if record.get("statement_path") is not None or record.get("signature_path") is not None:
            statement_path = record.get("statement_path")
            if not isinstance(statement_path, str) or not statement_path.strip():
                blockers.append({
                    "surface": f"{rel_path}#missing_statement_path:{artifact_path}",
                    "found": "absent",
                    "expected": "non-empty statement_path",
                })
                continue
            signature_path = record.get("signature_path")
            if not isinstance(signature_path, str) or not signature_path.strip():
                blockers.append({
                    "surface": f"{rel_path}#missing_signature_path:{artifact_path}",
                    "found": "absent",
                    "expected": "non-empty signature_path",
                })
                continue
            algorithm = str(record.get("algorithm", "")).strip()
            if algorithm not in _KNOWN_ATTESTATION_ALGORITHMS:
                blockers.append({
                    "surface": f"{rel_path}#unknown_algorithm:{artifact_path}",
                    "found": algorithm or "<missing>",
                    "expected": "known attestation algorithm",
                })
                continue
            signer_key_id = str(record.get("signer_key_id", "")).strip()
            if not signer_key_id:
                blockers.append({
                    "surface": f"{rel_path}#missing_signer_key_id:{artifact_path}",
                    "found": "absent",
                    "expected": "non-empty signer_key_id",
                })
            continue

        statement = record.get("statement")
        signer_pubkey = record.get("signer_pubkey")
        if not isinstance(statement, dict) or not isinstance(signer_pubkey, str):
            blockers.append({
                "surface": f"{rel_path}#invalid_attestation:{artifact_path}",
                "found": "malformed",
                "expected": "valid detached or inline attestation",
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
                "expected": "valid_detached_signature",
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


def _latest_changelog_version(repo_root: Path) -> str:
    changelog = repo_root / "CHANGELOG.md"
    if not changelog.exists():
        return ""
    for raw_line in changelog.read_text(encoding="utf-8").splitlines():
        match = _VERSION_HEADER_RE.match(raw_line.strip())
        if match:
            return match.group(1)
    return ""


def _find_explain_command_blockers(repo_root: Path) -> list[str]:
    blockers: list[str] = []
    for rel_path, expected in _EXPECTED_EXPLAIN_COMMANDS.items():
        path = repo_root / rel_path
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if _POSITIONAL_EXPLAIN_COMMAND in content:
            blockers.append(f"explain_command:{rel_path}:uses positional explain syntax")
        if expected not in content:
            blockers.append(f"explain_command:{rel_path}:missing expected syntax")
    return blockers


def _find_install_launcher_blockers(repo_root: Path) -> list[str]:
    blockers: list[str] = []
    for rel_path in _INSTALL_GUIDES:
        path = repo_root / rel_path
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if _BAD_LOCAL_INSTALL in content:
            blockers.append(f"install_launcher:{rel_path}:uses local npm install")
    return blockers


def _find_npx_front_door_blockers(repo_root: Path) -> list[str]:
    blockers: list[str] = []
    bare_commands = (
        "omg env doctor",
        "omg install --plan",
        "omg install --apply",
        "omg ship",
    )
    for rel_path, required_commands in _NPX_FRONT_DOOR_TARGETS.items():
        path = repo_root / rel_path
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for command in required_commands:
            if command not in content:
                blockers.append(f"npx_front_door:{rel_path}:missing '{command}'")
        for command in bare_commands:
            if re.search(rf"(?m)^{re.escape(command)}$", content):
                blockers.append(f"npx_front_door:{rel_path}:uses bare '{command}'")
    return blockers


def validate_release_surface(repo_root: Path, canonical: str) -> dict[str, Any]:
    blockers: list[str] = []
    checks: dict[str, Any] = {}

    release_surface_result = compile_release_surfaces(repo_root, check_only=True)
    checks["release_surface_drift"] = release_surface_result
    for item in release_surface_result.get("drift", []):
        if isinstance(item, dict):
            surface = str(item.get("surface", "unknown"))
            reason = str(item.get("reason", "drift"))
            blockers.append(f"release_surface_drift:{surface}:{reason}")
        else:
            blockers.append(f"release_surface_drift:{item}")

    docs_result = check_docs(repo_root)
    checks["docs_drift"] = docs_result
    for item in docs_result.get("drift", []):
        blockers.append(f"docs_drift:{item}")

    explain_blockers = _find_explain_command_blockers(repo_root)
    checks["explain_commands"] = explain_blockers
    blockers.extend(explain_blockers)

    install_launcher_blockers = _find_install_launcher_blockers(repo_root)
    checks["install_launchers"] = install_launcher_blockers
    blockers.extend(install_launcher_blockers)

    npx_front_door_blockers = _find_npx_front_door_blockers(repo_root)
    checks["npx_front_door"] = npx_front_door_blockers
    blockers.extend(npx_front_door_blockers)

    latest_version = _latest_changelog_version(repo_root)
    checks["latest_changelog_version"] = latest_version
    if latest_version != canonical:
        blockers.append(
            f"latest_changelog_version:{latest_version or '<missing>'}:expected:{canonical}"
        )

    readme_path = repo_root / "README.md"
    if not readme_path.exists():
        blockers.append("front_door:README.md not found")
        return {"status": "fail", "blockers": blockers, "checks": checks}
    readme = readme_path.read_text(encoding="utf-8")
    line = next((raw for raw in readme.splitlines() if "Claude front door:" in raw), "")
    checks["readme_claude_front_door"] = line
    if not line or "omg " not in line:
        blockers.append("front_door:README Claude front door must use launcher syntax")
    elif "/OMG:" in line and line.index("omg ") > line.index("/OMG:"):
        blockers.append("front_door:README Claude front door lists slash commands before launcher")

    command_idx = readme.find("## Command Surface")
    next_section = readme.find("\n## ", command_idx + 1) if command_idx >= 0 else -1
    command_surface = readme[command_idx : next_section if next_section > 0 else len(readme)] if command_idx >= 0 else ""
    checks["readme_command_surface"] = command_idx >= 0
    launcher_pos = command_surface.find("omg ")
    slash_pos = command_surface.find("/OMG:")
    if launcher_pos < 0:
        blockers.append("front_door:README Command Surface must mention launcher commands")
    elif slash_pos >= 0 and launcher_pos > slash_pos:
        blockers.append("front_door:README Command Surface must lead with launcher commands")

    pkg_path = repo_root / "package.json"
    if not pkg_path.exists():
        blockers.append("install_truthfulness:package.json not found")
        return {"status": "fail", "blockers": blockers, "checks": checks}
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    postinstall = str(pkg.get("scripts", {}).get("postinstall", ""))
    checks["postinstall"] = postinstall
    if "--plan" not in postinstall or "--apply" in postinstall:
        blockers.append("install_truthfulness:package.json postinstall must stay plan-only")

    truthfulness_targets = [
        repo_root / "README.md",
        repo_root / "docs" / "install" / "claude-code.md",
        repo_root / "docs" / "install" / "codex.md",
        repo_root / "docs" / "install" / "gemini.md",
        repo_root / "docs" / "install" / "kimi.md",
        repo_root / "docs" / "install" / "opencode.md",
    ]
    truthfulness_hits: dict[str, bool] = {}
    for path in truthfulness_targets:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8").lower()
        rel = str(path.relative_to(repo_root))
        truthfulness_hits[rel] = "no mutations" in content
        if "no mutations" not in content:
            blockers.append(f"install_truthfulness:{rel}:missing 'no mutations'")
        if "`npm install` is equivalent for omg" in content:
            blockers.append(f"install_truthfulness:{rel}:claims npm install equivalence")
    checks["install_truthfulness"] = truthfulness_hits

    marker_checks: dict[str, list[str]] = {}
    for rel_path, markers in _REQUIRED_GENERATED_MARKERS.items():
        path = repo_root / rel_path
        if not path.exists():
            blockers.append(f"generated_surface:{rel_path}:missing file")
            continue
        content = path.read_text(encoding="utf-8")
        expected_markers = list(markers)
        if rel_path == "CHANGELOG.md":
            expected_markers = [f"changelog-v{canonical}"]
        marker_checks[rel_path] = expected_markers
        for marker in expected_markers:
            if f"<!-- OMG:GENERATED:{marker} -->" not in content:
                blockers.append(f"generated_surface:{rel_path}:missing marker {marker}")
    checks["generated_markers"] = marker_checks

    return {
        "status": "fail" if blockers else "ok",
        "blockers": blockers,
        "checks": checks,
    }


def build_report(
    *,
    canonical: str,
    scope: str,
    forbid_version: str | None,
    authored: dict[str, Any] | None,
    derived: dict[str, Any] | None,
    scoped_residue: dict[str, Any] | None,
    release_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    has_failure = False
    for section in (authored, derived, scoped_residue, release_surface):
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
    if release_surface is not None:
        report["release_surface"] = release_surface

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
    release_surface_result = None

    if args.scope in ("authored", "all"):
        authored_result = validate_authored(_REPO_ROOT, canonical)
    else:
        authored_result = {"status": "skipped", "blockers": []}

    if args.scope in ("derived", "all"):
        derived_result = validate_derived(_REPO_ROOT, canonical)
    else:
        derived_result = {"status": "skipped", "blockers": []}

    if args.forbid_version and args.scope in ("derived", "all"):
        if args.forbid_version == canonical:
            residue_result = {
                "status": "ok",
                "forbid_version": args.forbid_version,
                "blockers": [],
            }
        else:
            residue_result = scan_scoped_residue(_REPO_ROOT, args.forbid_version)

    if args.scope == "all":
        release_surface_result = validate_release_surface(_REPO_ROOT, canonical)

    report = build_report(
        canonical=canonical,
        scope=args.scope,
        forbid_version=args.forbid_version,
        authored=authored_result,
        derived=derived_result,
        scoped_residue=residue_result,
        release_surface=release_surface_result,
    )

    output = json.dumps(report, indent=2)

    if args.output_json:
        out_path = Path(args.output_json).resolve()
        if not out_path.is_relative_to(_REPO_ROOT):
            print(json.dumps({"error": f"--output-json must be within repo root: {_REPO_ROOT}"}), file=sys.stderr)
            return 1
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)

    return 1 if report["overall_status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
