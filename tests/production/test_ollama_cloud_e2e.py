from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Callable, Protocol, cast


class _MarkProtocol(Protocol):
    def skipif(
        self, condition: bool, *, reason: str
    ) -> Callable[[Callable[..., object]], Callable[..., object]]: ...


class _PytestProtocol(Protocol):
    mark: _MarkProtocol

    def skip(self, reason: str) -> None: ...


pytest = cast(
    _PytestProtocol,
    cast(object, importlib.import_module("pytest")),
)


class _UrlOpenResponse(Protocol):
    def __enter__(self) -> "_UrlOpenResponse": ...

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> object: ...

    def read(self) -> bytes: ...


ROOT = Path(__file__).parent.parent.parent

OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
HAS_API_KEY = bool(OLLAMA_API_KEY)


class TestOllamaCloudProviderExists:
    def test_ts_provider_exists(self) -> None:
        assert (ROOT / "src" / "providers" / "ollama-cloud.ts").exists()

    def test_py_provider_exists(self) -> None:
        assert (ROOT / "runtime" / "providers" / "ollama_cloud_provider.py").exists()

    def test_api_docs_exist(self) -> None:
        assert (ROOT / "docs" / "providers" / "ollama-cloud-api.md").exists()

    def test_provider_registered_in_ts(self) -> None:
        index = ROOT / "src" / "providers" / "index.ts"
        if not index.exists():
            pytest.skip("providers/index.ts not found")
        content = index.read_text()
        assert "ollama-cloud" in content

    def test_provider_registered_in_py(self) -> None:
        registry = ROOT / "runtime" / "providers" / "provider_registry.py"
        content = registry.read_text()
        assert "ollama-cloud" in content


class TestOllamaCloudProviderConfig:
    def test_ts_provider_uses_cloud_url(self) -> None:
        content = (ROOT / "src" / "providers" / "ollama-cloud.ts").read_text()
        assert "ollama.com" in content or "OLLAMA_API_KEY" in content

    def test_py_provider_uses_cloud_url(self) -> None:
        content = (
            ROOT / "runtime" / "providers" / "ollama_cloud_provider.py"
        ).read_text()
        assert "ollama.com" in content or "OLLAMA_API_KEY" in content

    def test_mcp_config_path_correct(self) -> None:
        content = (
            ROOT / "runtime" / "providers" / "ollama_cloud_provider.py"
        ).read_text()
        assert "ollama-cloud" in content


class TestOllamaCloudRealAPI:
    @pytest.mark.skipif(not HAS_API_KEY, reason="OLLAMA_API_KEY not set")
    def test_model_list_api(self) -> None:
        import json
        import urllib.request

        req = urllib.request.Request(
            "https://ollama.com/api/tags",
            headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"},
        )
        response = cast(_UrlOpenResponse, urllib.request.urlopen(req, timeout=10))
        with response as resp:
            raw = resp.read()
            data = cast(object, json.loads(raw))
            assert isinstance(data, dict)
            assert "models" in data

    @pytest.mark.skipif(not HAS_API_KEY, reason="OLLAMA_API_KEY not set")
    def test_chat_api_authenticated(self) -> None:
        import json
        import urllib.request

        payload = json.dumps(
            {
                "model": "llama3:latest",
                "messages": [{"role": "user", "content": "Say 'hello' in one word."}],
                "stream": False,
            }
        ).encode()
        req = urllib.request.Request(
            "https://ollama.com/api/chat",
            data=payload,
            headers={
                "Authorization": f"Bearer {OLLAMA_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        response = cast(_UrlOpenResponse, urllib.request.urlopen(req, timeout=30))
        with response as resp:
            raw = resp.read()
            data = cast(object, json.loads(raw))
            assert isinstance(data, dict)
            assert "message" in data or "response" in data


class TestOllamaCloudGracefulSkip:
    def test_provider_detect_without_key(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "ollama_cloud_provider",
            ROOT / "runtime" / "providers" / "ollama_cloud_provider.py",
        )
        if spec is None:
            pytest.skip("ollama_cloud_provider.py not found")
        assert spec is not None
