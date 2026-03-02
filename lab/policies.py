"""Policy checks for OAL lab train/eval pipeline."""
from __future__ import annotations

from typing import Any


ALLOWED_LICENSES = {"apache-2.0", "mit", "bsd-3-clause", "cc-by-4.0"}
BLOCKED_SOURCE_TOKENS = {"unknown", "leaked", "stolen", "unauthorized", "pirated"}


def validate_dataset_source(dataset: dict[str, Any]) -> tuple[bool, str]:
    license_name = str(dataset.get("license", "")).lower()
    source = str(dataset.get("source", "")).lower()

    if not license_name:
        return False, "dataset license missing"
    if license_name not in ALLOWED_LICENSES:
        return False, f"dataset license not allowed: {license_name}"
    if any(token in source for token in BLOCKED_SOURCE_TOKENS):
        return False, "dataset source violates policy"
    return True, "ok"


def validate_model_source(model: dict[str, Any]) -> tuple[bool, str]:
    source = str(model.get("source", "")).lower()
    allow_distill = bool(model.get("allow_distill", False))

    if any(token in source for token in BLOCKED_SOURCE_TOKENS):
        return False, "model source violates policy"
    if not allow_distill:
        return False, "model source disallows distillation"
    return True, "ok"


def validate_job_request(job: dict[str, Any]) -> tuple[bool, str]:
    dataset = job.get("dataset")
    model = job.get("base_model")

    if not isinstance(dataset, dict):
        return False, "dataset block missing"
    if not isinstance(model, dict):
        return False, "base_model block missing"

    ok, reason = validate_dataset_source(dataset)
    if not ok:
        return False, reason

    ok, reason = validate_model_source(model)
    if not ok:
        return False, reason

    return True, "ok"
