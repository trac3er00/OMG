from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Protocol, TypedDict, cast
from uuid import uuid4

import yaml

from runtime.evidence_narrator import (
    check_completion_claim_validity,
    narrate_missing_evidence,
)
from runtime.mutation_gate import check_mutation_allowed
from runtime.rollback_manifest import (
    classify_side_effect,
    create_rollback_manifest,
    record_local_restore,
    record_side_effect,
    write_rollback_manifest,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKS_ROOT = PROJECT_ROOT / "packs"
GOAL_PACKS_ROOT = PACKS_ROOT / "goals"
DOMAIN_PACKS_ROOT = PACKS_ROOT / "domains"


class ProofScoreBreakdown(TypedDict):
    completeness: float
    validity: float
    diversity: float
    traceability: float


class ProofScoreResult(TypedDict):
    score: int
    band: str
    breakdown: ProofScoreBreakdown


class InstantResult(TypedDict, total=False):
    success: bool
    type: str
    confidence: float
    clarification_needed: bool
    clarification_prompt: str | None
    target_dir: str
    file_count: int
    pack_loaded: bool
    evidence: dict[str, ProofScoreResult]
    warning: str
    subdirectory: str
    skipped_files: list[dict[str, str]]
    silent_safety: bool
    silent_safety_restored: str | None
    dry_run: bool
    rollback_manifest_path: str
    evidence_bundle_path: str
    completion_claim: dict[str, Any]


class IntentResult(TypedDict):
    type: str
    confidence: float
    clarification_needed: bool
    clarification_prompt: str | None


class PackLoaderProtocol(Protocol):
    def load_pack(self, pack_name: str) -> bool: ...


ProgressCallback = Callable[[dict[str, str]], None]


def run_instant(
    prompt: str,
    target_dir: str,
    on_progress: ProgressCallback | None = None,
) -> InstantResult:
    return _run_instant(prompt, target_dir, on_progress=on_progress, dry_run=False)


def _run_instant(
    prompt: str,
    target_dir: str,
    *,
    on_progress: ProgressCallback | None = None,
    dry_run: bool,
) -> InstantResult:
    classify_intent = cast(
        Callable[[str], IntentResult],
        getattr(import_module("runtime.intent_classifier"), "classify_intent"),
    )
    pack_loader_cls = cast(
        type[PackLoaderProtocol],
        getattr(import_module("runtime.pack_loader"), "PackLoader"),
    )
    compute_score = cast(
        Callable[[list[dict[str, object]] | None], ProofScoreResult],
        getattr(import_module("runtime.proof_score"), "compute_score"),
    )

    def emit(phase: str, message: str) -> None:
        if on_progress is not None:
            on_progress({"phase": phase, "message": message})

    emit("classify", f"Analyzing: {prompt}")
    intent = classify_intent(prompt)
    if intent["clarification_needed"]:
        return {
            "success": False,
            "type": intent["type"],
            "confidence": intent["confidence"],
            "clarification_needed": True,
            "clarification_prompt": intent["clarification_prompt"],
        }

    previous_silent_safety = os.environ.get("SILENT_SAFETY")
    os.environ["SILENT_SAFETY"] = "true"

    try:
        intent_type = str(intent["type"])
        emit("pack", f"Loading {intent_type} template")
        pack_loaded = pack_loader_cls().load_pack(intent_type)
        pack = _load_pack(intent_type)

        emit("target", f"Preparing target directory: {target_dir}")
        resolved_target, warning = _prepare_target_dir(
            Path(target_dir), intent_type, dry_run=dry_run
        )

        rollback_manifest: dict[str, Any] | None = None
        rollback_manifest_path: str | None = None
        run_id = _build_run_id(intent_type)
        if not dry_run:
            emit("rollback", "Creating rollback point")
            rollback_manifest = create_rollback_manifest(
                run_id=run_id,
                step_id=f"instant-{intent_type}",
            )
            record_side_effect(rollback_manifest, classify_side_effect("write"))
            rollback_manifest_path = write_rollback_manifest(
                str(resolved_target), rollback_manifest
            )

        emit("scaffold", f"Generating {intent_type} scaffold")
        file_count = 0
        skipped_files: list[dict[str, str]] = []
        generated_files: list[str] = []
        for relative_path in _extract_scaffold_files(pack):
            full_path = resolved_target / relative_path
            try:
                _assert_mutation_allowed(full_path)
                if not dry_run:
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    _ = full_path.write_text(
                        _render_scaffold_file(relative_path, intent_type, prompt),
                        encoding="utf-8",
                    )
                    generated_files.append(str(full_path))
                    if rollback_manifest is not None:
                        record_local_restore(
                            rollback_manifest,
                            str(full_path),
                            "planned",
                            "delete generated scaffold file to roll back instant mode output",
                        )
                file_count += 1
            except PermissionError as exc:
                skipped_files.append({"path": relative_path, "reason": str(exc)})

        if rollback_manifest is not None:
            rollback_manifest_path = write_rollback_manifest(
                str(resolved_target), rollback_manifest
            )

        emit("verify", "Computing evidence score")
        evidence: list[dict[str, object]] = [
            {
                "type": "scaffold",
                "valid": file_count > 0,
                "path": str(resolved_target),
            }
        ]
        if rollback_manifest_path:
            evidence.append(
                {
                    "type": "rollback_manifest",
                    "valid": True,
                    "path": rollback_manifest_path,
                }
            )
        proof = compute_score(evidence)

        evidence_bundle_path: str | None = None
        completion_claim: dict[str, Any] | None = None
        if not dry_run:
            emit("evidence", "Collecting completion evidence")
            evidence_bundle_path, completion_claim = _collect_completion_evidence(
                project_dir=resolved_target,
                run_id=run_id,
                prompt=prompt,
                intent_type=intent_type,
                target_dir=resolved_target,
                file_count=file_count,
                generated_files=generated_files,
                rollback_manifest_path=rollback_manifest_path,
                skipped_files=skipped_files,
            )

        result: InstantResult = {
            "success": True,
            "type": intent_type,
            "confidence": intent["confidence"],
            "target_dir": str(resolved_target),
            "file_count": file_count,
            "pack_loaded": pack_loaded,
            "evidence": {"proofScore": proof},
            "silent_safety": True,
            "silent_safety_restored": previous_silent_safety,
            "dry_run": dry_run,
        }
        if warning is not None:
            result["warning"] = warning
            result["subdirectory"] = str(resolved_target)
        if skipped_files:
            result["skipped_files"] = skipped_files
        if rollback_manifest_path is not None:
            result["rollback_manifest_path"] = rollback_manifest_path
        if evidence_bundle_path is not None:
            result["evidence_bundle_path"] = evidence_bundle_path
        if completion_claim is not None:
            result["completion_claim"] = completion_claim

        emit("done", f"Created {file_count} files in {resolved_target}")
        return result
    finally:
        if previous_silent_safety is None:
            _ = os.environ.pop("SILENT_SAFETY", None)
        else:
            os.environ["SILENT_SAFETY"] = previous_silent_safety


def _load_pack(intent_type: str) -> dict[object, object]:
    pack_path = _resolve_pack_path(intent_type)
    if not pack_path.exists():
        raise FileNotFoundError(f"Instant mode pack not found: {pack_path}")

    loaded = cast(object, yaml.safe_load(pack_path.read_text(encoding="utf-8")))
    if not isinstance(loaded, dict):
        raise ValueError(f"Invalid pack payload in {pack_path}")
    return cast(dict[object, object], loaded)


def _resolve_pack_path(intent_type: str) -> Path:
    for root in (GOAL_PACKS_ROOT, DOMAIN_PACKS_ROOT):
        candidate = root / intent_type / "pack.yaml"
        if candidate.exists():
            return candidate
    return GOAL_PACKS_ROOT / intent_type / "pack.yaml"


def _prepare_target_dir(
    target_dir: Path,
    intent_type: str,
    *,
    dry_run: bool,
) -> tuple[Path, str | None]:
    if not target_dir.exists():
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir, None

    if not target_dir.is_dir():
        raise NotADirectoryError(f"Target path is not a directory: {target_dir}")

    if any(target_dir.iterdir()):
        nested_target = _next_available_subdirectory(
            target_dir, f"instant-{intent_type}"
        )
        if not dry_run:
            nested_target.mkdir(parents=True, exist_ok=True)
        return (
            nested_target,
            f"Target was non-empty, using subdirectory: {nested_target}",
        )
    return target_dir, None


def _next_available_subdirectory(target_dir: Path, base_name: str) -> Path:
    candidate = target_dir / base_name
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = target_dir / f"{base_name}-{index}"
        if not candidate.exists():
            return candidate
        index += 1


def _extract_scaffold_files(pack: dict[object, object]) -> list[str]:
    scaffold = pack.get("scaffold", [])
    if isinstance(scaffold, dict):
        scaffold_mapping = cast(dict[object, object], scaffold)
        raw_files = scaffold_mapping.get("files", [])
    else:
        raw_files = scaffold

    files: list[str] = []
    if isinstance(raw_files, list):
        for item in cast(list[object], raw_files):
            if not isinstance(item, str):
                continue
            normalized = item.strip()
            if not normalized or not _looks_like_scaffold_file(normalized):
                continue
            if normalized not in files:
                files.append(normalized)

    if files:
        return files
    return ["README.md"]


def _looks_like_scaffold_file(value: str) -> bool:
    return "/" in value or "." in Path(value).name


def _assert_mutation_allowed(path: Path) -> None:
    gate_result = check_mutation_allowed(
        tool="Write",
        file_path=str(path),
        project_dir=str(PROJECT_ROOT),
        lock_id=None,
    )
    if not bool(gate_result.get("allowed")):
        raise PermissionError(str(gate_result.get("reason", "mutation_blocked")))


def _build_run_id(intent_type: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"instant-{intent_type}-{timestamp}-{uuid4().hex[:8]}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _collect_completion_evidence(
    *,
    project_dir: Path,
    run_id: str,
    prompt: str,
    intent_type: str,
    target_dir: Path,
    file_count: int,
    generated_files: list[str],
    rollback_manifest_path: str | None,
    skipped_files: list[dict[str, str]],
) -> tuple[str, dict[str, Any]]:
    evidence_dir = project_dir / ".omg" / "evidence"
    evidence_path = evidence_dir / f"{run_id}.json"
    missing: list[str] = []
    if file_count == 0:
        missing.append("generated files")
    if rollback_manifest_path is None:
        missing.append("rollback manifest")

    artifacts: list[dict[str, Any]] = []
    if rollback_manifest_path is not None:
        artifacts.append(
            {
                "kind": "rollback_manifest",
                "path": rollback_manifest_path,
            }
        )
    for file_path in generated_files:
        artifacts.append({"kind": "generated_file", "path": file_path})

    evidence_payload = {
        "schema": "EvidencePack",
        "schema_version": 1,
        "run_id": run_id,
        "generator": "runtime.instant_mode",
        "intent_type": intent_type,
        "prompt": prompt,
        "target_dir": str(target_dir),
        "file_count": file_count,
        "skipped_files": skipped_files,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": artifacts,
    }
    _write_json(evidence_path, evidence_payload)

    completion_claim = check_completion_claim_validity(str(project_dir))
    completion_claim["narrative"] = narrate_missing_evidence(
        cast(list[str], completion_claim.get("missing", []))
    )
    completion_claim["evidence_artifacts"] = artifacts
    return str(evidence_path), completion_claim


def _render_scaffold_file(relative_path: str, intent_type: str, prompt: str) -> str:
    return "\n".join(
        [
            f"# {relative_path}",
            "# Generated by OMG Instant Mode",
            f"# Type: {intent_type}",
            f"# Prompt: {prompt}",
            "",
        ]
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m runtime.instant_mode",
        description="Run OMG instant mode scaffold generation",
    )
    parser.add_argument("--prompt", required=True, help="Goal prompt for instant mode")
    parser.add_argument(
        "--target-dir",
        default=".",
        help="Directory where instant mode should scaffold files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print JSON result to stdout",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview scaffold generation without writing files",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = _run_instant(
            args.prompt,
            args.target_dir,
            dry_run=bool(args.dry_run),
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Instant mode type: {result.get('type', 'unknown')}")
        print(f"Target dir: {result.get('target_dir', args.target_dir)}")
        print(f"Files: {result.get('file_count', 0)}")
        if result.get("dry_run"):
            print("Mode: dry-run")
        if result.get("warning"):
            print(f"Warning: {result['warning']}")
        if result.get("clarification_needed"):
            prompt = result.get("clarification_prompt") or "Clarification required"
            print(prompt)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
