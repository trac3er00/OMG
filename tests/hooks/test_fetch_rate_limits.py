from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "hooks" / "fetch-rate-limits.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("fetch_rate_limits_hook", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_non_darwin_skips_keychain_probe(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module.sys, "platform", "linux", raising=False)

    called = {"keychain": 0}

    def _keychain_probe():
        called["keychain"] += 1
        return None

    monkeypatch.setattr(module, "read_credentials_from_keychain", _keychain_probe)
    monkeypatch.setattr(
        module, "read_credentials_from_file", lambda: {"accessToken": "ok"}
    )

    creds = module.read_credentials()
    assert creds == {"accessToken": "ok"}
    assert called["keychain"] == 0
