from __future__ import annotations

import pytest

from control_plane import server


def test_validate_host_allows_loopback() -> None:
    assert server.validate_host("127.0.0.1") == "127.0.0.1"
    assert server.validate_host("localhost") == "localhost"
    assert server.validate_host("::1") == "::1"


def test_validate_host_rejects_non_loopback_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMG_CONTROL_PLANE_UNSAFE_BIND", raising=False)

    with pytest.raises(ValueError, match="loopback"):
        server.validate_host("0.0.0.0")


def test_validate_host_allows_non_loopback_with_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMG_CONTROL_PLANE_UNSAFE_BIND", "true")

    assert server.validate_host("0.0.0.0") == "0.0.0.0"
