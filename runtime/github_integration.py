from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


def get_github_token(
    *,
    session: Any | None = None,
    env: Mapping[str, str] | None = None,
    now: object | None = None,
    max_retries: int = 2,
) -> dict[str, object]:
    _ = session
    _ = now
    _ = max_retries

    source_env = env if env is not None else os.environ
    token = str(source_env.get("OMG_GITHUB_TOKEN", "")).strip()
    if not token:
        return {
            "status": "error",
            "error_code": "GITHUB_TOKEN_MISSING",
            "message": "OMG_GITHUB_TOKEN is not configured.",
            "missing": ["OMG_GITHUB_TOKEN"],
        }

    return {
        "status": "ok",
        "token": token,
        "source": "env",
    }


__all__ = ["get_github_token"]
