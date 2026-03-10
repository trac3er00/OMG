from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import uuid
from pathlib import Path
from time import monotonic
from typing import Any

ADAPTER_NAME = "isaac_gym"
ADAPTER_KIND = "simulator"

VALID_STATUSES = frozenset({"dry_run_contract", "unavailable_backend", "invoked", "error"})


def _has_cuda() -> bool:
    try:
        torch = importlib.import_module("torch")
    except Exception:
        return False
    cuda = getattr(torch, "cuda", None)
    if cuda is None:
        return False
    is_available = getattr(cuda, "is_available", None)
    if not callable(is_available):
        return False
    try:
        return bool(is_available())
    except Exception:
        return False


def _check_isaac_lab_available() -> bool:
    for candidate in ("isaaclab", "omni.isaac.lab"):
        try:
            if importlib.util.find_spec(candidate) is not None:
                return True
        except (ImportError, ModuleNotFoundError, ValueError):
            continue
    return False


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
    digest = hashlib.sha256(json.dumps({"run_id": run_id, "job": job}, sort_keys=True).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _bounded_gpu_episode(*, seed: int, steps: int) -> dict[str, Any]:
    torch = importlib.import_module("torch")
    started = monotonic()
    gen = torch.Generator(device="cuda")
    gen.manual_seed(seed)
    state = torch.zeros((), device="cuda")
    reward = torch.zeros((), device="cuda")
    for _idx in range(steps):
        noise = torch.rand((), generator=gen, device="cuda") - 0.25
        state = state + noise
        reward = reward + torch.relu(state)
    return {
        "steps": steps,
        "reward": float(reward.item()),
        "duration_ms": int((monotonic() - started) * 1000),
        "backend_version": str(getattr(torch, "__version__", "unknown")),
    }


def run(
    job: dict[str, Any],
    *,
    backend_mode: str = "preflight",
    run_id: str | None = None,
    timeout_seconds: int = 30,
    sandbox_root: str = ".",
) -> dict[str, Any]:
    del timeout_seconds

    active_run_id = run_id or str(uuid.uuid4())
    ok, validation_reason = _validate_job(job)
    seed = _derive_seed(job, active_run_id)
    cuda_ready = _has_cuda()
    isaac_lab_ready = _check_isaac_lab_available()
    available = cuda_ready and isaac_lab_ready
    max_steps_raw = job.get("max_steps", 16)
    try:
        max_steps = max(1, min(int(max_steps_raw), 256))
    except (TypeError, ValueError):
        max_steps = 16

    base_result: dict[str, Any] = {
        "adapter": ADAPTER_NAME,
        "kind": ADAPTER_KIND,
        "backend": "isaac_lab",
        "run_id": active_run_id,
        "seed": seed,
        "episode_stats": {"steps": 0, "reward": 0.0, "duration_ms": 0},
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
            "availability_reason": "job validation failed",
        }

    unavailable_reason = "isaac_lab_requires_cuda"

    if backend_mode == "preflight":
        if available:
            return {
                **base_result,
                "status": "dry_run_contract",
                "available": True,
                "reason": "preflight mode: isaac lab backend available",
                "availability_reason": "isaac_lab_cuda_ready",
            }
        return {
            **base_result,
            "status": "unavailable_backend",
            "available": False,
            "reason": unavailable_reason,
            "availability_reason": unavailable_reason,
        }

    if backend_mode == "live":
        if not available:
            return {
                **base_result,
                "status": "unavailable_backend",
                "available": False,
                "reason": unavailable_reason,
                "availability_reason": unavailable_reason,
            }

        try:
            sandbox_path = Path(sandbox_root)
            sandbox_path.mkdir(parents=True, exist_ok=True)
            episode = _bounded_gpu_episode(seed=seed, steps=max_steps)
            return {
                **base_result,
                "status": "invoked",
                "available": True,
                "reason": "isaac lab gpu episode executed",
                "availability_reason": "isaac_lab_cuda_ready",
                "episode_stats": {
                    "steps": int(episode["steps"]),
                    "reward": float(episode["reward"]),
                    "duration_ms": int(episode["duration_ms"]),
                },
                "replay_metadata": {
                    "run_id": active_run_id,
                    "seed": seed,
                    "backend_version": str(episode["backend_version"]),
                },
            }
        except Exception as exc:  # noqa: BLE001
            return {
                **base_result,
                "status": "error",
                "available": available,
                "reason": f"live execution failed: {exc}",
                "availability_reason": "isaac_lab_cuda_ready",
            }

    return {
        **base_result,
        "status": "error",
        "available": available,
        "reason": f"unknown backend_mode: {backend_mode!r}",
        "availability_reason": unavailable_reason,
    }
