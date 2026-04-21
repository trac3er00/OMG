from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from runtime.cli_provider import CLIProvider, register_provider
from runtime.host_parity import normalize_output
from runtime.mcp_config_writers import write_kimi_mcp_config

_BASE_URL = "https://ollama.com/api"


def _attach_normalized_output(
    payload: dict[str, Any], *, prompt: str, project_dir: str
) -> dict[str, Any]:
    normalized = normalize_output(
        "ollama-cloud",
        payload,
        context={"prompt": prompt, "project_dir": project_dir},
    )
    merged = dict(payload)
    merged["normalized_output"] = normalized
    return merged


class OllamaCloudProvider(CLIProvider):
    def get_name(self) -> str:  # noqa: D401
        return "ollama-cloud"

    def detect(self) -> bool:
        return bool(os.environ.get("OLLAMA_API_KEY"))

    def check_auth(self) -> tuple[bool | None, str]:
        api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
        if not api_key:
            return False, "not authenticated — OLLAMA_API_KEY not set"
        return True, "authenticated"

    def _post_chat(self, payload: dict[str, Any], *, timeout: int) -> dict[str, Any]:
        api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
        if not api_key:
            return {"error": "OLLAMA_API_KEY not set", "fallback": "claude"}

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{_BASE_URL}/chat",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            reason = detail.strip() or str(exc.reason)
            return {
                "error": f"ollama-cloud http {exc.code}: {reason}",
                "fallback": "claude",
            }
        except urllib.error.URLError as exc:
            return {
                "error": f"ollama-cloud request failed: {exc.reason}",
                "fallback": "claude",
            }
        except TimeoutError:
            return {"error": "ollama-cloud timeout", "fallback": "claude"}
        except Exception as exc:
            return {"error": str(exc), "fallback": "claude"}

        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return {"response": parsed, "raw": raw}

    def invoke(
        self, prompt: str, project_dir: str, timeout: int = 120, **kwargs: Any
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": str(kwargs.get("model", "gpt-oss:20b")),
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if isinstance(kwargs.get("options"), dict):
            payload["options"] = kwargs["options"]

        result = self._post_chat(payload, timeout=timeout)
        if "error" in result:
            return {"error": result["error"], "fallback": "claude"}

        response_payload = result.get("response", {})
        raw_output = result.get("raw", "")
        message = ""
        if isinstance(response_payload, dict):
            response_model = str(response_payload.get("model") or payload["model"])
            message_payload = response_payload.get("message")
            if isinstance(message_payload, dict):
                message = str(message_payload.get("content", ""))
        else:
            response_model = str(payload["model"])

        output = message or str(raw_output)
        return _attach_normalized_output(
            {
                "model": response_model,
                "output": output,
                "exit_code": 0,
            },
            prompt=prompt,
            project_dir=project_dir,
        )

    def invoke_json(
        self, prompt: str, project_dir: str, timeout: int = 120, **kwargs: Any
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": str(kwargs.get("model", "gpt-oss:20b")),
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        if isinstance(kwargs.get("options"), dict):
            payload["options"] = kwargs["options"]

        result = self._post_chat(payload, timeout=timeout)
        if "error" in result:
            return {"error": result["error"], "fallback": "claude"}

        response_payload = result.get("response", {})
        response_model = str(payload["model"])
        if isinstance(response_payload, dict) and response_payload.get("model"):
            response_model = str(response_payload.get("model"))

        return _attach_normalized_output(
            {
                "model": response_model,
                "output": str(result.get("raw", "")),
                "exit_code": 0,
            },
            prompt=prompt,
            project_dir=project_dir,
        )

    def invoke_tmux(
        self, prompt: str, project_dir: str, timeout: int = 120
    ) -> dict[str, Any]:
        return self.invoke(prompt, project_dir, timeout=timeout)

    def get_non_interactive_cmd(self, prompt: str) -> list[str]:
        return ["ollama-cloud", "chat", prompt]

    def get_config_path(self) -> str:
        return os.path.expanduser("~/.ollama-cloud/mcp.json")

    def write_mcp_config(
        self, server_url: str, server_name: str = "memory-server"
    ) -> None:
        write_kimi_mcp_config(
            server_url, server_name, config_path=self.get_config_path()
        )


register_provider(OllamaCloudProvider())
