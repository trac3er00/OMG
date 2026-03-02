"""Tests for unified OAL setup entrypoint."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import cast


ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "OAL-setup.sh"
LEGACY = ROOT / "install.sh"


def _run_script(path: Path, args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = dict(os.environ)
    if env is not None:
        merged_env.update(env)
    return subprocess.run(
        ["bash", str(path), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
    )


def _run_script_with_input(
    path: Path,
    args: list[str],
    user_input: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = dict(os.environ)
    if env is not None:
        merged_env.update(env)
    return subprocess.run(
        ["bash", str(path), *args],
        input=user_input,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
    )


def test_setup_script_exists_and_help_lists_subcommands():
    assert SETUP.exists()
    proc = _run_script(SETUP, ["--help"])
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "install" in out
    assert "update" in out
    assert "reinstall" in out
    assert "uninstall" in out
    assert "--install-as-plugin" in out
    assert "--clear-omc" not in out
    assert "--without-legacy-aliases" not in out


def test_setup_script_prompts_start_menu_when_no_action(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    proc = _run_script_with_input(SETUP, [], "0\n", env=env)
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "Select OAL setup action" in out
    assert "Install standalone" in out
    assert "Install as plugin" in out
    assert "Uninstall" in out
    assert "Update standalone" not in out
    assert "Update plugin install" not in out


def test_setup_script_menu_shows_update_options_when_installed(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    (claude_dir / "hooks").mkdir(parents=True)
    _ = (claude_dir / "hooks" / ".oal-version").write_text("oal-v1-old\n", encoding="utf-8")
    (claude_dir / "plugins" / "cache" / "oh-advanced-layer" / "oal").mkdir(parents=True)
    _ = (claude_dir / "plugins" / "cache" / "oh-advanced-layer" / "oal" / ".oal-plugin-bundle").write_text(
        "oal-plugin-bundle-v1\n",
        encoding="utf-8",
    )

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    proc = _run_script_with_input(SETUP, [], "0\n", env=env)
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "Update standalone" in out
    assert "Update plugin install" in out


def test_setup_script_install_dry_run_non_interactive(tmp_path: Path):
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path / ".claude")}
    proc = _run_script(SETUP, ["install", "--dry-run", "--non-interactive"], env=env)
    assert proc.returncode == 0
    assert "DRY RUN" in (proc.stdout + proc.stderr)


def test_setup_script_uninstall_dry_run_non_interactive(tmp_path: Path):
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path / ".claude")}
    proc = _run_script(SETUP, ["uninstall", "--dry-run", "--non-interactive"], env=env)
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "uninstall" in out.lower()


def test_legacy_install_wrapper_is_deprecated_and_forwards_help():
    proc = _run_script(LEGACY, ["--help"])
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "deprecated" in out.lower()
    assert "OAL-setup.sh" in out


def test_setup_install_uses_oal_only_command_surface(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
    assert proc.returncode == 0

    commands_dir = claude_dir / "commands"
    installed = [p.name for p in commands_dir.glob("*.md")]
    assert installed
    assert all("omc" not in name.lower() for name in installed)


def test_setup_install_preserves_existing_custom_deprecated_command_name(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    commands_dir = claude_dir / "commands"
    commands_dir.mkdir(parents=True)
    custom = commands_dir / "code-review.md"
    _ = custom.write_text("# custom code-review\nmy private review flow\n", encoding="utf-8")

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
    assert proc.returncode == 0

    content = custom.read_text(encoding="utf-8")
    assert "# custom code-review" in content
    assert "my private review flow" in content


def test_setup_install_provisions_portable_oal_runtime(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
    assert proc.returncode == 0

    runtime_script = claude_dir / "oal-runtime" / "scripts" / "oal.py"
    assert runtime_script.exists()

    run = subprocess.run(
        [sys.executable, str(runtime_script), "teams", "--target", "gemini", "--problem", "ui layout review"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0
    payload = cast(dict[str, object], json.loads(run.stdout))
    assert payload["status"] == "ok"
    evidence = cast(dict[str, object], payload["evidence"])
    assert evidence["target"] == "gemini"


def test_setup_install_as_plugin_installs_plugin_mcp_and_hud_together(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip", "--install-as-plugin"],
        env=env,
    )
    assert proc.returncode == 0

    plugin_cache_root = claude_dir / "plugins" / "cache" / "oh-advanced-layer" / "oal"
    installed_versions = sorted([p for p in plugin_cache_root.iterdir() if p.is_dir()])
    assert installed_versions
    plugin_dir = installed_versions[-1]

    assert (plugin_dir / ".claude-plugin" / "plugin.json").exists()
    assert (plugin_dir / ".mcp.json").exists()
    assert (plugin_cache_root / ".oal-plugin-bundle").exists()
    assert (claude_dir / "hud" / "oal-hud.mjs").exists()

    settings_path = claude_dir / "settings.json"
    settings = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
    enabled = cast(dict[str, object], settings.get("enabledPlugins") or {})
    mcp_servers = cast(dict[str, object], settings.get("mcpServers") or {})
    assert enabled.get("oal@oh-advanced-layer") is True
    assert "context7" in mcp_servers
    assert "filesystem" in mcp_servers
    assert "websearch" in mcp_servers
    assert "chrome-devtools" in mcp_servers

    installed_plugins_path = claude_dir / "plugins" / "installed_plugins.json"
    installed_plugins = cast(dict[str, object], json.loads(installed_plugins_path.read_text(encoding="utf-8")))
    plugins = cast(dict[str, object], installed_plugins.get("plugins") or {})
    assert "oal@oh-advanced-layer" in plugins


def test_setup_uninstall_removes_plugin_bundle_and_plugin_mcp_servers(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    install_proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=apply", "--install-as-plugin"],
        env=env,
    )
    assert install_proc.returncode == 0

    settings_path = claude_dir / "settings.json"
    settings = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
    mcp_servers = cast(dict[str, object], settings.get("mcpServers") or {})
    assert "context7" in mcp_servers
    assert "filesystem" in mcp_servers
    assert "websearch" in mcp_servers
    assert "chrome-devtools" in mcp_servers

    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    assert not (claude_dir / "plugins" / "cache" / "oh-advanced-layer" / "oal").exists()
    assert not (claude_dir / "hud" / "oal-hud.mjs").exists()

    settings_after = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
    mcp_after = cast(dict[str, object], settings_after.get("mcpServers") or {})
    enabled_after = cast(dict[str, object], settings_after.get("enabledPlugins") or {})
    assert "context7" not in mcp_after
    assert "filesystem" not in mcp_after
    assert "websearch" not in mcp_after
    assert "chrome-devtools" not in mcp_after
    assert "oal@oh-advanced-layer" not in enabled_after

    installed_plugins_path = claude_dir / "plugins" / "installed_plugins.json"
    installed_plugins = cast(dict[str, object], json.loads(installed_plugins_path.read_text(encoding="utf-8")))
    plugins_after = cast(dict[str, object], installed_plugins.get("plugins") or {})
    assert "oal@oh-advanced-layer" not in plugins_after


def test_setup_uninstall_cleans_legacy_oal_registry_and_cache(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    legacy_cache = claude_dir / "plugins" / "cache" / "oal" / "oal"
    legacy_cache.mkdir(parents=True)
    _ = (legacy_cache / ".oal-plugin-bundle").write_text("oal-plugin-bundle-v1\n", encoding="utf-8")
    _ = (claude_dir / "hud").mkdir(parents=True)
    _ = (claude_dir / "hud" / "oal-hud.mjs").write_text("// hud\n", encoding="utf-8")

    settings_path = claude_dir / "settings.json"
    _ = settings_path.write_text(
        json.dumps(
            {
                "enabledPlugins": {
                    "oal@oal": True,
                },
                "mcpServers": {
                    "context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
                    "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]},
                    "websearch": {"command": "npx", "args": ["-y", "exa-mcp-server"]},
                    "chrome-devtools": {"command": "npx", "args": ["-y", "chrome-devtools-mcp@latest"]},
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    installed_plugins_path = claude_dir / "plugins" / "installed_plugins.json"
    _ = installed_plugins_path.write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "oal@oal": [
                        {
                            "scope": "user",
                            "installPath": str(legacy_cache / "oal-v1-20260301"),
                            "version": "oal-v1-20260301",
                            "installedAt": "2026-03-01T18:19:00.632775+00:00",
                            "lastUpdated": "2026-03-01T18:19:00.632775+00:00",
                        }
                    ]
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    assert not legacy_cache.exists()
    settings_after = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
    enabled_after = cast(dict[str, object], settings_after.get("enabledPlugins") or {})
    mcp_after = cast(dict[str, object], settings_after.get("mcpServers") or {})
    assert "oal@oal" not in enabled_after
    assert "context7" not in mcp_after
    assert "filesystem" not in mcp_after
    assert "websearch" not in mcp_after
    assert "chrome-devtools" not in mcp_after

    installed_after = cast(dict[str, object], json.loads(installed_plugins_path.read_text(encoding="utf-8")))
    plugins_after = cast(dict[str, object], installed_after.get("plugins") or {})
    assert "oal@oal" not in plugins_after


def test_setup_keeps_only_two_recent_backups(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    hooks_dir = claude_dir / "hooks"
    hooks_dir.mkdir(parents=True)
    _ = (hooks_dir / ".oal-version").write_text("oal-v1-old\n", encoding="utf-8")
    _ = (claude_dir / "settings.json").write_text("{}\n", encoding="utf-8")

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    for _ in range(3):
        proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
        assert proc.returncode == 0

    backups = sorted(p for p in claude_dir.iterdir() if p.is_dir() and p.name.startswith(".oal-backup-"))
    assert len(backups) <= 2
