from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey


_TOKEN_CACHE: dict[str, object] = {
    "token": "",
    "expires_at": 0.0,
}


def get_github_token(
    *,
    session: Any | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    max_retries: int = 2,
) -> dict[str, object]:
    source_env = env if env is not None else os.environ
    current_time = now or datetime.now(UTC)

    app_id = str(source_env.get("GITHUB_APP_ID", "")).strip()
    private_key = str(source_env.get("GITHUB_APP_PRIVATE_KEY", "")).strip()
    installation_id = str(source_env.get("GITHUB_INSTALLATION_ID", "")).strip()

    missing: list[str] = []
    if not app_id:
        missing.append("GITHUB_APP_ID")
    if not private_key:
        missing.append("GITHUB_APP_PRIVATE_KEY")
    if not installation_id:
        missing.append("GITHUB_INSTALLATION_ID")
    if missing:
        return {
            "status": "error",
            "error_code": "GITHUB_CREDENTIALS_MISSING",
            "message": "GitHub App credentials are missing.",
            "missing": missing,
        }

    if _token_is_valid(current_time):
        return {
            "status": "ok",
            "token": str(_TOKEN_CACHE["token"]),
            "expires_at": _TOKEN_CACHE["expires_at"],
            "source": "cache",
        }

    normalized_private_key = private_key.replace("\\n", "\n")
    jwt_result = _build_app_jwt(app_id=app_id, private_key_pem=normalized_private_key, now=current_time)
    if jwt_result.get("status") != "ok":
        return jwt_result

    client = session if session is not None else requests
    token_result = _exchange_installation_token(
        session=client,
        app_jwt=str(jwt_result["jwt"]),
        installation_id=installation_id,
        max_retries=max_retries,
    )
    if token_result.get("status") != "ok":
        return token_result

    token = str(token_result.get("token", "")).strip()
    expires_at_epoch = _to_float(token_result.get("expires_at_epoch"))
    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expires_at"] = expires_at_epoch
    return {
        "status": "ok",
        "token": token,
        "expires_at": expires_at_epoch,
        "source": "fresh",
    }


def _token_is_valid(now: datetime) -> bool:
    token = str(_TOKEN_CACHE.get("token", "")).strip()
    expires_at = _to_float(_TOKEN_CACHE.get("expires_at"))
    if not token or expires_at <= 0:
        return False
    return expires_at > now.timestamp() + 60.0


def _build_app_jwt(*, app_id: str, private_key_pem: str, now: datetime) -> dict[str, object]:
    try:
        key_obj = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    except Exception as exc:
        return {
            "status": "error",
            "error_code": "GITHUB_APP_PRIVATE_KEY_INVALID",
            "message": f"Unable to parse GitHub App private key: {exc}",
        }
    if not isinstance(key_obj, RSAPrivateKey):
        return {
            "status": "error",
            "error_code": "GITHUB_APP_PRIVATE_KEY_INVALID",
            "message": "GitHub App private key must be RSA.",
        }
    key = cast(RSAPrivateKey, key_obj)

    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iat": int((now - timedelta(seconds=60)).timestamp()),
        "exp": int((now + timedelta(minutes=9)).timestamp()),
        "iss": app_id,
    }
    signing_input = f"{_b64url_json(header)}.{_b64url_json(payload)}"
    try:
        signature = key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:
        return {
            "status": "error",
            "error_code": "GITHUB_JWT_SIGNING_FAILED",
            "message": f"Failed to sign GitHub App JWT: {exc}",
        }
    jwt_token = f"{signing_input}.{_b64url_bytes(signature)}"
    return {
        "status": "ok",
        "jwt": jwt_token,
    }


def _exchange_installation_token(
    *,
    session: Any,
    app_jwt: str,
    installation_id: str,
    max_retries: int,
) -> dict[str, object]:
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {app_jwt}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    attempts = max(0, int(max_retries)) + 1
    for attempt in range(1, attempts + 1):
        try:
            response = session.post(url, headers=headers, timeout=20)
        except Exception as exc:
            if attempt >= attempts:
                return {
                    "status": "error",
                    "error_code": "GITHUB_TOKEN_REQUEST_FAILED",
                    "message": f"Failed to request installation token: {exc}",
                }
            time.sleep(1.0)
            continue

        if _is_rate_limited(response) and attempt < attempts:
            delay = _retry_after_seconds(response)
            time.sleep(delay)
            continue

        if int(getattr(response, "status_code", 0)) >= 400:
            return {
                "status": "error",
                "error_code": "GITHUB_TOKEN_REQUEST_REJECTED",
                "http_status": int(getattr(response, "status_code", 0)),
                "message": "GitHub rejected installation token request.",
                "response_excerpt": str(getattr(response, "text", ""))[:300],
            }

        try:
            payload = response.json()
        except Exception:
            payload = None
        if not isinstance(payload, dict):
            return {
                "status": "error",
                "error_code": "GITHUB_TOKEN_RESPONSE_INVALID",
                "message": "GitHub token response was not valid JSON.",
            }

        token = str(payload.get("token", "")).strip()
        expires_at = str(payload.get("expires_at", "")).strip()
        if not token or not expires_at:
            return {
                "status": "error",
                "error_code": "GITHUB_TOKEN_RESPONSE_INVALID",
                "message": "GitHub token response missing token or expires_at.",
            }

        expires_at_epoch = _parse_iso8601(expires_at)
        return {
            "status": "ok",
            "token": token,
            "expires_at_epoch": expires_at_epoch,
        }

    return {
        "status": "error",
        "error_code": "GITHUB_TOKEN_REQUEST_FAILED",
        "message": "GitHub installation token request exhausted retries.",
    }


def _is_rate_limited(response: Any) -> bool:
    status = int(getattr(response, "status_code", 0))
    headers = getattr(response, "headers", {}) or {}
    remaining = str(headers.get("X-RateLimit-Remaining", "")).strip()
    return status == 429 or (status == 403 and remaining == "0")


def _retry_after_seconds(response: Any) -> float:
    headers = getattr(response, "headers", {}) or {}
    retry_after = str(headers.get("Retry-After", "")).strip()
    try:
        value = float(retry_after)
    except ValueError:
        value = 1.0
    return max(0.2, value)


def _parse_iso8601(value: str) -> float:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _b64url_json(payload: Mapping[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return _b64url_bytes(raw)


def _b64url_bytes(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _to_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


__all__ = ["get_github_token"]
