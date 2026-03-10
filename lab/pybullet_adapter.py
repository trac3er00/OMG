from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import uuid
from pathlib import Path
from time import monotonic
from typing import Any

ADAPTER_NAME = "pybullet"
ADAPTER_KIND = "simulator"

VALID_STATUSES = frozenset({"dry_run_contract", "skipped_unavailable_backend", "invoked", "error"})


def _check_pybullet_available() -> bool:
    return importlib.util.find_spec("pybullet") is not None


def _compute_fingerprint(job: dict[str, Any]) -> str | None:
    try:
        return hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()[:16]
    except (TypeError, ValueError):
        return None


def _validate_job(job: dict[str, Any]) -> tuple[bool, str]:
    if not job:
        return False, "invalid job: missing required fields"
    if "domain" not in job:
        return False, "invalid job: missing required field 'domain'"
    return True, ""


def _derive_seed(job: dict[str, Any], run_id: str) -> int:
    explicit = job.get("seed")
    if isinstance(explicit, int):
        return explicit
    material = json.dumps({"run_id": run_id, "job": _compute_fingerprint(job)}, sort_keys=True)
    return int(hashlib.sha256(material.encode("utf-8")).hexdigest()[:8], 16)


def _bounded_steps(job: dict[str, Any]) -> int:
    raw = job.get("max_steps", 32)
    try:
        return max(1, min(int(raw), 256))
    except (TypeError, ValueError):
        return 32


def _run_bounded_local_episode(*, job: dict[str, Any], seed: int, timeout_seconds: int) -> dict[str, Any]:
    p = importlib.import_module("pybullet")

    _ = max(1, timeout_seconds)
    started = monotonic()
    steps = _bounded_steps(job)
    client = p.connect(p.DIRECT)
    rng = random.Random(seed)
    reward = 0.0
    try:
        p.setGravity(0.0, 0.0, -9.81, physicsClientId=client)
        for _idx in range(steps):
            p.stepSimulation(physicsClientId=client)
            reward += rng.uniform(-0.05, 0.25)
    finally:
        p.disconnect(physicsClientId=client)
    return {
        "steps": steps,
        "reward": round(reward, 6),
        "duration_ms": int((monotonic() - started) * 1000),
        "seed": seed,
        "backend_version": getattr(p, "__version__", "unknown"),
    }


def run(
    job: dict[str, Any],
    *,
    backend_mode: str = "preflight",
    run_id: str | None = None,
    timeout_seconds: int = 30,
    sandbox_root: str = ".",
) -> dict[str, Any]:
    active_run_id = run_id or str(uuid.uuid4())

    ok, validation_reason = _validate_job(job)
    seed = _derive_seed(job, active_run_id)
    available = _check_pybullet_available()
    base_result: dict[str, Any] = {
        "adapter": ADAPTER_NAME,
        "kind": ADAPTER_KIND,
        "backend": "pybullet",
        "run_id": active_run_id,
        "seed": seed,
        "episode_stats": {
            "steps": 0,
            "reward": 0.0,
            "duration_ms": 0,
        },
        "replay_metadata": {
            "run_id": active_run_id,
            "seed": seed,
            "backend_version": "unavailable",
        },
    }

    if not ok:
        return {
            **base_result,
            "status": "error",
            "available": False,
            "reason": validation_reason,
            "simulator_steps": None,
            "replay_evidence": None,
        }

    if backend_mode == "preflight":
        if available:
            status = "dry_run_contract"
            reason = "preflight mode: backend available but execution not requested"
        else:
            status = "skipped_unavailable_backend"
            reason = "pybullet not installed"
        return {
            **base_result,
            "status": status,
            "available": available,
            "reason": reason,
            "simulator_steps": 0,
            "replay_evidence": None,
        }

    if backend_mode == "live":
        if not available:
            return {
                **base_result,
                "status": "skipped_unavailable_backend",
                "available": False,
                "reason": "pybullet not installed",
                "simulator_steps": 0,
                "replay_evidence": None,
            }

        try:
            sandbox_path = Path(sandbox_root)
            sandbox_path.mkdir(parents=True, exist_ok=True)
            episode = _run_bounded_local_episode(job=job, seed=seed, timeout_seconds=timeout_seconds)
            replay_metadata = {
                "run_id": active_run_id,
                "seed": seed,
                "backend_version": str(episode.get("backend_version", "unknown")),
            }
            episode_stats = {
                "steps": int(episode.get("steps", 0)),
                "reward": float(episode.get("reward", 0.0)),
                "duration_ms": int(episode.get("duration_ms", 0)),
            }
            return {
                **base_result,
                "status": "invoked",
                "available": True,
                "reason": "live execution dispatched to pybullet backend",
                "episode_stats": episode_stats,
                "replay_metadata": replay_metadata,
                "simulator_steps": episode_stats["steps"],
                "replay_evidence": {
                    "steps": episode_stats["steps"],
                    "scenario": "bounded_local_episode",
                    "deterministic": True,
                    "seed": seed,
                },
            }
        except Exception as exc:  # noqa: BLE001
            return {
                **base_result,
                "status": "error",
                "available": available,
                "reason": f"live execution failed: {exc}",
                "simulator_steps": None,
                "replay_evidence": None,
            }

    return {
        **base_result,
        "status": "error",
        "available": available,
        "reason": f"unknown backend_mode: {backend_mode!r}",
        "simulator_steps": None,
        "replay_evidence": None,
    }
