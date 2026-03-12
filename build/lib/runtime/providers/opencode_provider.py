from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast
from typing import Any

from runtime.cli_provider import CLIProvider, register_provider
from runtime.mcp_config_writers import _atomic_write_text  # pyright: ignore[reportPrivateUsage]

HOST_RULES = {
    "compilation_targets": ["opencode.json"],
    "mcp": ["omg-control"],
    "mcp_key": "mcp",
}


class OpenCodeProvider(CLIProvider):
    def get_name(self) -> str:  # pyright: ignore[reportImplicitOverride]
        return "opencode"

    def detect(self) -> bool:  # pyright: ignore[reportImplicitOverride]
        return shutil.which("opencode") is not None

    def check_auth(self) -> tuple[bool | None, str]:  # pyright: ignore[reportImplicitOverride]
        auth_path = Path(os.path.expanduser("~/.local/share/opencode/auth.json"))
        if not auth_path.exists():
            return False, f"auth not found: missing {auth_path}"
        try:
            parsed = cast(object, json.loads(auth_path.read_text()))
        except (json.JSONDecodeError, ValueError) as exc:
            return False, f"auth not found: invalid json: {exc}"
        except OSError as exc:
            return False, f"auth not found: unreadable file: {exc}"

        if not parsed:
            return False, "auth not found: empty auth content"
        return True, "auth found"

    def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny, reportImplicitOverride]
        try:
            result = self.run_tool(
                ["opencode", prompt],
                timeout=timeout,
                cwd=project_dir,
                env={"CLAUDE_PROJECT_DIR": project_dir},
            )
            return {
                "model": "opencode-cli",
                "output": result.stdout,
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "opencode-cli timeout", "fallback": "claude"}
        except FileNotFoundError:
            return {"error": "opencode-cli not found", "fallback": "claude"}
        except Exception as exc:
            return {"error": str(exc), "fallback": "claude"}

    def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny, reportImplicitOverride]
        return self.invoke(prompt, project_dir, timeout=timeout)

    def get_non_interactive_cmd(self, prompt: str) -> list[str]:  # pyright: ignore[reportImplicitOverride]
        return ["opencode", prompt]

    def get_config_path(self) -> str:  # pyright: ignore[reportImplicitOverride]
        return os.path.expanduser("~/.config/opencode/opencode.json")

    def get_project_config_path(self, root: str = ".") -> str:
        return str(Path(root) / "opencode.json")

    def get_plugin_dir(self, root: str = ".") -> str:
        return str(Path(root) / ".opencode" / "plugins")

    def write_mcp_config(self, server_url: str, server_name: str = "memory-server") -> None:  # pyright: ignore[reportImplicitOverride]
        config_path = Path(self.get_config_path())
        config: dict[str, object]
        if config_path.exists():
            try:
                loaded = cast(object, json.loads(config_path.read_text()))
                config = cast(dict[str, object], loaded) if isinstance(loaded, dict) else {}
            except (json.JSONDecodeError, ValueError):
                config = {}
        else:
            config = {}

        mcp = config.get("mcp")
        if not isinstance(mcp, dict):
            mcp = {}
            config["mcp"] = mcp

        mcp[server_name] = {"type": "http", "url": server_url}
        _atomic_write_text(config_path, json.dumps(config, indent=2) + "\n")


register_provider(OpenCodeProvider())
