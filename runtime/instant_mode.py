from __future__ import annotations

import os
from importlib import import_module
from pathlib import Path
from typing import Callable, Protocol, TypedDict, cast

import yaml

from runtime.mutation_gate import check_mutation_allowed

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKS_ROOT = PROJECT_ROOT / "packs" / "domains"


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
    silent_safety: bool
    silent_safety_restored: str | None


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
        resolved_target, warning = _prepare_target_dir(Path(target_dir), intent_type)

        emit("scaffold", f"Generating {intent_type} scaffold")
        file_count = 0
        for relative_path in _extract_scaffold_files(pack):
            full_path = resolved_target / relative_path
            _assert_mutation_allowed(full_path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            _ = full_path.write_text(
                _render_scaffold_file(relative_path, intent_type, prompt),
                encoding="utf-8",
            )
            file_count += 1

        emit("verify", "Computing evidence score")
        evidence: list[dict[str, object]] = [
            {
                "type": "scaffold",
                "valid": file_count > 0,
                "path": str(resolved_target),
            }
        ]
        proof = compute_score(evidence)

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
        }
        if warning is not None:
            result["warning"] = warning
            result["subdirectory"] = str(resolved_target)

        emit("done", f"Created {file_count} files in {resolved_target}")
        return result
    finally:
        if previous_silent_safety is None:
            _ = os.environ.pop("SILENT_SAFETY", None)
        else:
            os.environ["SILENT_SAFETY"] = previous_silent_safety


def _load_pack(intent_type: str) -> dict[object, object]:
    pack_path = PACKS_ROOT / intent_type / "pack.yaml"
    if not pack_path.exists():
        raise FileNotFoundError(f"Instant mode pack not found: {pack_path}")

    loaded = cast(object, yaml.safe_load(pack_path.read_text(encoding="utf-8")))
    if not isinstance(loaded, dict):
        raise ValueError(f"Invalid pack payload in {pack_path}")
    return cast(dict[object, object], loaded)


def _prepare_target_dir(target_dir: Path, intent_type: str) -> tuple[Path, str | None]:
    target_dir.mkdir(parents=True, exist_ok=True)
    if any(target_dir.iterdir()):
        nested_target = _next_available_subdirectory(
            target_dir, f"instant-{intent_type}"
        )
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
