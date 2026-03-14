from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from runtime.github_integration import _TOKEN_CACHE, get_github_token


def _mock_response(*, status_code: int, payload: dict[str, object], headers: dict[str, str] | None = None) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    response.headers = headers or {}
    response.text = "payload"
    return response


def _private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def test_get_github_token_success_and_cache(monkeypatch):
    _TOKEN_CACHE["token"] = ""
    _TOKEN_CACHE["expires_at"] = 0.0

    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", _private_key_pem())
    monkeypatch.setenv("GITHUB_INSTALLATION_ID", "999")

    expires_at = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    response = _mock_response(
        status_code=201,
        payload={"token": "ghs_example_token", "expires_at": expires_at},
    )

    with patch("runtime.github_integration.requests.post", return_value=response) as post_mock:
        first = get_github_token()
        second = get_github_token()

    assert first["status"] == "ok"
    assert first["token"] == "ghs_example_token"
    assert first["source"] == "fresh"
    assert second["status"] == "ok"
    assert second["source"] == "cache"
    assert post_mock.call_count == 1


def test_get_github_token_missing_credentials_safe_failure(monkeypatch):
    _TOKEN_CACHE["token"] = ""
    _TOKEN_CACHE["expires_at"] = 0.0

    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_INSTALLATION_ID", raising=False)

    result = get_github_token()

    assert result["status"] == "error"
    assert result["error_code"] == "GITHUB_CREDENTIALS_MISSING"
    missing = result.get("missing")
    assert isinstance(missing, list)
    assert set(str(item) for item in missing) == {
        "GITHUB_APP_ID",
        "GITHUB_APP_PRIVATE_KEY",
        "GITHUB_INSTALLATION_ID",
    }


def test_get_github_token_retries_rate_limit(monkeypatch):
    _TOKEN_CACHE["token"] = ""
    _TOKEN_CACHE["expires_at"] = 0.0

    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", _private_key_pem())
    monkeypatch.setenv("GITHUB_INSTALLATION_ID", "999")

    rate_limited = _mock_response(
        status_code=429,
        payload={"message": "rate limited"},
        headers={"Retry-After": "0"},
    )
    ok_response = _mock_response(
        status_code=201,
        payload={
            "token": "ghs_after_retry",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        },
    )

    with patch("runtime.github_integration.requests.post", side_effect=[rate_limited, ok_response]) as post_mock:
        with patch("runtime.github_integration.time.sleep") as sleep_mock:
            result = get_github_token(max_retries=2)

    assert result["status"] == "ok"
    assert result["token"] == "ghs_after_retry"
    assert post_mock.call_count == 2
    assert sleep_mock.call_count == 1
