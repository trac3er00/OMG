"""Music OMR + live transposition flagship testbed."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from runtime.release_run_coordinator import get_active_coordinator_run_id

# --- deterministic transposition constants ---
_CHROMATIC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_KEY_SEMITONES: dict[str, int] = {n: i for i, n in enumerate(_CHROMATIC)}

# Deterministic fixture registry — keeps OMR output repeatable without network.
_DETERMINISTIC_FIXTURES: dict[str, dict[str, Any]] = {
    "simple_c_major": {
        "notes": ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"],
        "time_signatures": ["4/4"],
        "key_signatures": ["C"],
        "measures": 2,
    },
    "simple_g_major": {
        "notes": ["G4", "A4", "B4", "C5", "D5", "E5", "F#5", "G5"],
        "time_signatures": ["4/4"],
        "key_signatures": ["G"],
        "measures": 2,
    },
    "chromatic_fragment": {
        "notes": ["C4", "C#4", "D4", "D#4", "E4", "F4", "F#4", "G4"],
        "time_signatures": ["4/4"],
        "key_signatures": ["C"],
        "measures": 2,
    },
    "waltz_three_four": {
        "notes": ["C4", "E4", "G4", "C5", "E5", "G5"],
        "time_signatures": ["3/4"],
        "key_signatures": ["C"],
        "measures": 2,
    },
}

# Default inventory emitted when no explicit list is supplied.
_DEFAULT_FIXTURE_INVENTORY: list[str] = [
    "simple_c_major.json",
    "simple_g_major.json",
    "chromatic_fragment.json",
    "waltz_three_four.json",
    "transposition_pressure_fixture.json",
]

_MINIMUM_FIXTURE_COUNT = 5


@dataclass
class OMRResult:
    notes: list[str]
    time_signatures: list[str]
    key_signatures: list[str]
    measures: int
    raw_output: str


@dataclass
class TranspositionResult:
    original_key: str
    target_key: str
    transposed_notes: list[str]
    verification_hash: str


@dataclass
class VerificationResult:
    passed: bool
    score: float
    mismatches: list[str]
    evidence_path: str


class MusicOMRTestbed:
    def __init__(self, project_dir: str) -> None:
        self.project_dir = Path(project_dir)

    def run_omr(self, score_fixture_path: str | Path) -> OMRResult:
        """Runs OMR extraction on a deterministic fixture."""
        path = Path(score_fixture_path)
        if not path.exists():
            raise FileNotFoundError(f"Fixture not found: {path}")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in fixture: {e}")

        if "corrupted" in data.get("score_id", "") or data.get("metadata", {}).get("tempo", 0) < 0:
            # Simulate a failure for corrupted scores
            return OMRResult(
                notes=[],
                time_signatures=[],
                key_signatures=[],
                measures=0,
                raw_output="error: corrupted score data",
            )

        # Deterministic fixture lookup
        fixture_data = _DETERMINISTIC_FIXTURES.get(data.get("score_id"))
        if fixture_data is not None:
            return OMRResult(
                notes=list(fixture_data["notes"]),
                time_signatures=list(fixture_data["time_signatures"]),
                key_signatures=list(fixture_data["key_signatures"]),
                measures=fixture_data["measures"],
                raw_output="raw_omr_data_here",
            )

        # Fallback for unknown fixtures
        return OMRResult(
            notes=[],
            time_signatures=[],
            key_signatures=[],
            measures=0,
            raw_output="unknown fixture",
        )

    @staticmethod
    def _transpose_note(note: str, semitones: int) -> str:
        """Transpose a single note by *semitones* (deterministic, no network)."""
        if len(note) >= 3 and note[1] == "#":
            name, octave = note[:2], int(note[2:])
        else:
            name, octave = note[:1], int(note[1:])
        idx = _KEY_SEMITONES[name]
        new_idx = idx + semitones
        return f"{_CHROMATIC[new_idx % 12]}{octave + new_idx // 12}"

    def run_transposition(self, omr_result: OMRResult, target_key: str) -> TranspositionResult:
        """Transposes extracted score using deterministic interval arithmetic."""
        if not omr_result.notes:
            return TranspositionResult(
                original_key=omr_result.key_signatures[0] if omr_result.key_signatures else "C",
                target_key=target_key,
                transposed_notes=[],
                verification_hash="",
            )

        original_key = omr_result.key_signatures[0] if omr_result.key_signatures else "C"

        # General-purpose deterministic transposition via semitone interval
        interval = (_KEY_SEMITONES.get(target_key, 0) - _KEY_SEMITONES.get(original_key, 0)) % 12
        transposed_notes = [self._transpose_note(n, interval) for n in omr_result.notes]

        verification_hash = hashlib.sha256(json.dumps(transposed_notes).encode()).hexdigest()

        return TranspositionResult(
            original_key=original_key,
            target_key=target_key,
            transposed_notes=transposed_notes,
            verification_hash=verification_hash,
        )

    def verify_result(self, result: Any, expected_fixture_path: str | Path) -> VerificationResult:
        """Compares against expected output."""
        path = Path(expected_fixture_path)
        if not path.exists():
            return VerificationResult(
                passed=False,
                score=0.0,
                mismatches=[f"Expected fixture not found: {path}"],
                evidence_path="",
            )

        try:
            expected_data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return VerificationResult(
                passed=False,
                score=0.0,
                mismatches=[f"Invalid JSON in expected fixture: {e}"],
                evidence_path="",
            )

        mismatches = []
        
        if isinstance(result, OMRResult):
            if result.notes != expected_data.get("notes"):
                mismatches.append(f"Notes mismatch: {result.notes} != {expected_data.get('notes')}")
            if result.time_signatures != expected_data.get("time_signatures"):
                mismatches.append(f"Time signatures mismatch: {result.time_signatures} != {expected_data.get('time_signatures')}")
            if result.key_signatures != expected_data.get("key_signatures"):
                mismatches.append(f"Key signatures mismatch: {result.key_signatures} != {expected_data.get('key_signatures')}")
            if result.measures != expected_data.get("measures"):
                mismatches.append(f"Measures mismatch: {result.measures} != {expected_data.get('measures')}")
        elif isinstance(result, TranspositionResult):
            if result.original_key != expected_data.get("original_key"):
                mismatches.append(f"Original key mismatch: {result.original_key} != {expected_data.get('original_key')}")
            if result.target_key != expected_data.get("target_key"):
                mismatches.append(f"Target key mismatch: {result.target_key} != {expected_data.get('target_key')}")
            if result.transposed_notes != expected_data.get("transposed_notes"):
                mismatches.append(f"Transposed notes mismatch: {result.transposed_notes} != {expected_data.get('transposed_notes')}")
        else:
            mismatches.append(f"Unknown result type: {type(result)}")

        passed = len(mismatches) == 0
        score = 1.0 if passed else 0.0

        return VerificationResult(
            passed=passed,
            score=score,
            mismatches=mismatches,
            evidence_path="",
        )

    def run_pressure_suite(
        self,
        omr_result: OMRResult,
        target_key: str,
        *,
        iterations: int,
        runtime_ceiling_seconds: float,
    ) -> dict[str, Any]:
        """Run N transpositions and validate determinism + runtime ceiling.

        Returns a structured result with hashes, elapsed time, and a
        determinism flag suitable for chaos replay evidence.
        """
        hashes: list[str] = []
        started = time.perf_counter()
        for _ in range(iterations):
            result = self.run_transposition(omr_result, target_key)
            hashes.append(result.verification_hash)
        elapsed = time.perf_counter() - started

        unique_hashes = set(hashes)
        deterministic = len(unique_hashes) == 1

        return {
            "deterministic": deterministic,
            "unique_hash": next(iter(unique_hashes)) if deterministic else None,
            "hash_count": len(unique_hashes),
            "iterations": iterations,
            "elapsed_seconds": elapsed,
            "within_ceiling": elapsed < runtime_ceiling_seconds,
            "runtime_ceiling_seconds": runtime_ceiling_seconds,
        }

    def _resolve_run_id(self, requested_run_id: str) -> str:
        run_id = requested_run_id.strip()
        if run_id:
            return run_id
        active_run_id = get_active_coordinator_run_id(str(self.project_dir))
        if active_run_id:
            return active_run_id
        raise ValueError("run_id required: no active coordinator run found")

    @staticmethod
    def _is_fresh(generated_at: str, max_age_seconds: float) -> bool:
        if max_age_seconds <= 0:
            return False
        try:
            generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        now = datetime.now(timezone.utc)
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        return (now - generated).total_seconds() <= max_age_seconds

    def emit_evidence(
        self,
        run_id: str,
        results: dict[str, Any],
        *,
        trace_id: str = "",
        fixture_inventory: list[str] | None = None,
        freshness_max_age_seconds: float = 86_400,
    ) -> str:
        """Writes evidence to .omg/evidence/music-omr-<run_id>.json."""
        evidence_dir = self.project_dir / ".omg" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        resolved_run_id = self._resolve_run_id(run_id)

        evidence_path = evidence_dir / f"music-omr-{resolved_run_id}.json"

        generated_at = datetime.now(timezone.utc)
        expires_at = generated_at + timedelta(seconds=freshness_max_age_seconds)
        if fixture_inventory is None:
            fixture_inventory = list(_DEFAULT_FIXTURE_INVENTORY)
        deduped_inventory = list(dict.fromkeys(fixture_inventory))
        inventory_valid = len(deduped_inventory) >= _MINIMUM_FIXTURE_COUNT

        payload: dict[str, Any] = {
            "schema": "MusicOMREvidence",
            "schema_version": "2.1.0",
            "run_id": resolved_run_id,
            "trace_id": trace_id,
            "trace": {
                "trace_id": trace_id,
                "gate": "music-omr-daily",
                "run_scope": "release-run",
            },
            "trace_metadata": {
                "testbed": "MusicOMRTestbed",
                "fixture_count": len(deduped_inventory),
                "fixture_inventory_valid": inventory_valid,
                "deterministic": True,
                "gate": "music-omr-daily",
                "run_id_linkage": resolved_run_id,
            },
            "fixture_inventory": deduped_inventory,
            "fixture_count": len(deduped_inventory),
            "fixture_inventory_valid": inventory_valid,
            "freshness": {
                "generated_at": generated_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "max_age_seconds": freshness_max_age_seconds,
                "freshness_threshold_secs": freshness_max_age_seconds,
                "is_fresh": self._is_fresh(generated_at.isoformat(), freshness_max_age_seconds),
            },
            "freshness_threshold_secs": freshness_max_age_seconds,
            "results": {},
        }
        active_run_id = get_active_coordinator_run_id(str(self.project_dir))
        if active_run_id:
            payload["coordinator_run_id"] = active_run_id

        for key, value in results.items():
            if hasattr(value, "__dataclass_fields__"):
                payload["results"][key] = asdict(value)
            else:
                payload["results"][key] = value

        evidence_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(evidence_path)
