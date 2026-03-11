"""Canonical run identity generation and validation for Forge."""
from __future__ import annotations

from datetime import datetime, timezone


def generate_run_id() -> str:
    """Generate a compact UTC timestamp-based run ID.
    
    Format: YYYYMMDDTHHMMSSfffffZ (e.g., 20260309T143022123456Z)
    
    Returns:
        str: Compact UTC format run ID.
    """
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def validate_run_id(run_id: str) -> tuple[bool, str]:
    """Validate run ID format and constraints.
    
    Valid run IDs:
    - Non-empty
    - Alphanumeric + hyphens only (no spaces, special chars)
    - Max 128 characters
    
    Args:
        run_id: The run ID to validate.
        
    Returns:
        tuple[bool, str]: (is_valid, reason). If valid, reason is empty string.
    """
    if not run_id:
        return False, "run_id must be non-empty"
    
    if len(run_id) > 128:
        return False, f"run_id exceeds 128 characters: {len(run_id)}"
    
    # Allow alphanumeric and hyphens only
    if not all(c.isalnum() or c == "-" for c in run_id):
        return False, "run_id must contain only alphanumeric characters and hyphens"
    
    return True, ""


def normalize_run_id(run_id: str | None) -> str:
    """Normalize run ID: use provided if valid, else generate new one.
    
    Args:
        run_id: Optional run ID. If None or invalid, a new one is generated.
        
    Returns:
        str: Valid run ID (either the provided one or a newly generated one).
    """
    if run_id:
        is_valid, _ = validate_run_id(run_id)
        if is_valid:
            return run_id
    
    return generate_run_id()
