"""Tests for unified OMG setup entrypoint."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import time
from typing import cast


ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "OMG-setup.sh"
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


def _run_script_with_tty_input(
    path: Path,
    args: list[str],
    user_input: str,
    env: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    """Run script with a pseudo-TTY so bash sees an interactive terminal.

    This is needed for tests that exercise the interactive start-action menu,
    which is suppressed when stdin is not a TTY (``[ ! -t 0 ]`` → true).
    """
    merged_env = dict(os.environ)
    if env is not None:
        merged_env.update(env)

    master_fd, slave_fd = pty.openpty()
    slave_closed = False
    returncode = 1
    try:
        proc = subprocess.Popen(
            ["bash", str(path), *args],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=merged_env,
            cwd=str(ROOT),
            close_fds=True,
        )
        os.close(slave_fd)
        slave_closed = True

        # Give the script time to reach the interactive prompt, then send input.
        if user_input:
            time.sleep(0.5)
            os.write(master_fd, user_input.encode())

        output_bytes = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            # Check if process has exited BEFORE blocking on select.
            if proc.poll() is not None:
                # Drain any remaining buffered output (short timeout).
                try:
                    while True:
                        r2, _, _ = select.select([master_fd], [], [], 0.1)
                        if not r2:
                            break
                        try:
                            chunk = os.read(master_fd, 4096)
                            if not chunk:
                                break  # EOF on macOS PTY
                            output_bytes += chunk
                        except OSError:
                            break
                except OSError:
                    pass
                break

            r, _, _ = select.select([master_fd], [], [], 0.1)
            if r:
                try:
                    chunk = os.read(master_fd, 4096)
                    if not chunk:
                        break  # EOF: slave side closed (macOS PTY behavior)
                    output_bytes += chunk
                except OSError:
                    break

        # Ensure the process terminates.
        try:
            returncode = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            returncode = proc.wait()

    finally:
        if not slave_closed:
            os.close(slave_fd)
        try:
            os.close(master_fd)
        except OSError:
            pass

    output = output_bytes.decode("utf-8", errors="replace")
    return subprocess.CompletedProcess(
        args=["bash", str(path), *args],
        returncode=returncode,
        stdout=output,
        stderr="",
    )


def _read_mcp_servers(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    return cast(dict[str, object], payload.get("mcpServers") or {})


def _read_hook_command_targets(settings_path: Path) -> set[str]:
    settings = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
    hooks = cast(dict[str, object], settings.get("hooks") or {})
    targets: set[str] = set()
    for entries in hooks.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            nested_hooks = entry.get("hooks") or []
            if not isinstance(nested_hooks, list):
                continue
            for hook in nested_hooks:
                if not isinstance(hook, dict):
                    continue
                command = hook.get("command")
                if not isinstance(command, str):
                    continue
                marker = '$HOME/.claude/hooks/'
                if marker not in command:
                    continue
                suffix = command.split(marker, 1)[1]
                filename = suffix.split('"', 1)[0]
                if filename.endswith(".py"):
                    targets.add(filename)
    return targets


def _assert_command_starts(command: str, args: list[str], cwd: Path) -> None:
    proc = subprocess.Popen(
        [command, *args],
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(1.0)
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=5)
            raise AssertionError(
                "MCP command exited immediately:\n"
                f"command={command!r} args={args!r}\n"
                f"stdout={stdout}\n"
                f"stderr={stderr}"
            )
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


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
    assert "--mode=omg-only|coexist" in out
    assert "--adopt=auto" in out
    assert "--preset=safe|balanced|interop|labs" in out
    assert "--clear-omc" not in out
    assert "--without-legacy-aliases" not in out


def test_setup_script_prompts_start_menu_when_no_action(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    proc = _run_script_with_tty_input(SETUP, [], "0\n", env=env)
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "Select OMG setup action" in out
    assert "Install standalone" in out
    assert "Install as plugin" in out
    assert "Uninstall" not in out
    assert "Update standalone" not in out
    assert "Update plugin install" not in out


def test_setup_script_dry_run_without_action_skips_start_menu(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    proc = _run_script_with_tty_input(SETUP, ["--dry-run"], "", env=env)
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "Select OMG setup action" not in out
    assert "*** DRY RUN" in out


def test_setup_script_menu_shows_update_options_when_installed(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    (claude_dir / "hooks").mkdir(parents=True)
    _ = (claude_dir / "hooks" / ".omg-version").write_text("omg-v1-old\n", encoding="utf-8")
    (claude_dir / "plugins" / "cache" / "omg" / "omg").mkdir(parents=True)
    _ = (claude_dir / "plugins" / "cache" / "omg" / "omg" / ".omg-plugin-bundle").write_text(
        "omg-plugin-bundle-v1\n",
        encoding="utf-8",
    )

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    proc = _run_script_with_tty_input(SETUP, [], "0\n", env=env)
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "Uninstall" in out
    assert "Update standalone" in out
    assert "Update plugin install" in out


def test_setup_script_interactive_merge_shows_prompt(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    _ = (claude_dir / "settings.json").write_text('{"enabledPlugins":{"existing@demo":true}}\n', encoding="utf-8")

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    proc = _run_script_with_tty_input(SETUP, ["install"], "n\n", env=env)
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "Merging settings.json..." in out
    assert "Apply merge? [Y/n]" in out


def test_setup_script_install_dry_run_non_interactive(tmp_path: Path):
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path / ".claude")}
    proc = _run_script(SETUP, ["install", "--dry-run", "--non-interactive"], env=env)
    assert proc.returncode == 0
    assert "DRY RUN" in (proc.stdout + proc.stderr)


def test_setup_script_install_non_tty_enables_non_interactive_merge(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    _ = (claude_dir / "settings.json").write_text(
        (ROOT / "settings.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    proc = _run_script(SETUP, ["install"], env=env)
    out = proc.stdout + proc.stderr

    assert proc.returncode == 0
    assert "Settings merged (auto)" in out
    assert "Apply merge?" not in out


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
    assert "OMG-setup.sh" in out


def test_setup_install_uses_omg_only_command_surface(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
    assert proc.returncode == 0

    commands_dir = claude_dir / "commands"
    installed = [p.name for p in commands_dir.glob("*.md")]
    assert installed
    assert all("omc" not in name.lower() for name in installed)


def test_setup_install_registers_primary_omg_commands(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
    assert proc.returncode == 0

    commands_dir = claude_dir / "commands"
    assert (commands_dir / "OMG:setup.md").exists()
    assert (commands_dir / "OMG:crazy.md").exists()


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


def test_setup_install_provisions_portable_omg_runtime(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
    assert proc.returncode == 0

    runtime_script = claude_dir / "omg-runtime" / "scripts" / "omg.py"
    dephealth_plugin = claude_dir / "omg-runtime" / "plugins" / "dephealth" / "cve_scanner.py"
    assert runtime_script.exists()
    assert dephealth_plugin.exists()

    run = subprocess.run(
        [sys.executable, "-S", str(runtime_script), "teams", "--target", "gemini", "--problem", "ui layout review"],
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

    plugin_cache_root = claude_dir / "plugins" / "cache" / "omg" / "omg"
    installed_versions = sorted([p for p in plugin_cache_root.iterdir() if p.is_dir()])
    assert installed_versions
    plugin_dir = installed_versions[-1]
    assert plugin_dir.name == "2.0.9"

    assert (plugin_dir / ".claude-plugin" / "plugin.json").exists()
    assert (plugin_dir / ".claude-plugin" / "marketplace.json").exists()
    assert (plugin_dir / ".claude-plugin" / "mcp.json").exists()
    assert (plugin_cache_root / ".omg-plugin-bundle").exists()
    assert (claude_dir / "hud" / "omg-hud.mjs").exists()

    plugin_servers = _read_mcp_servers(plugin_dir / ".claude-plugin" / "mcp.json")
    assert set(plugin_servers) == {"omg-control"}

    settings_path = claude_dir / "settings.json"
    settings = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
    enabled = cast(dict[str, object], settings.get("enabledPlugins") or {})
    assert enabled.get("omg@omg") is True
    status_line = cast(dict[str, object], settings.get("statusLine") or {})
    assert status_line.get("type") == "command"
    assert status_line.get("command") == f'node "{claude_dir / "hud" / "omg-hud.mjs"}"'

    mcp_servers = _read_mcp_servers(claude_dir / ".mcp.json")
    assert "filesystem" not in mcp_servers
    assert "omg-control" not in mcp_servers

    installed_plugins_path = claude_dir / "plugins" / "installed_plugins.json"
    installed_plugins = cast(dict[str, object], json.loads(installed_plugins_path.read_text(encoding="utf-8")))
    plugins = cast(dict[str, object], installed_plugins.get("plugins") or {})
    assert "omg@omg" in plugins


def test_setup_install_as_plugin_registers_known_marketplace(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip", "--install-as-plugin"],
        env=env,
    )
    assert proc.returncode == 0

    plugin_root = claude_dir / "plugins" / "cache" / "omg" / "omg" / "2.0.9"
    marketplaces_path = claude_dir / "plugins" / "known_marketplaces.json"
    assert marketplaces_path.exists()

    marketplaces = cast(dict[str, object], json.loads(marketplaces_path.read_text(encoding="utf-8")))
    omg_marketplace = cast(dict[str, object], marketplaces.get("omg") or {})
    source = cast(dict[str, object], omg_marketplace.get("source") or {})

    assert source.get("source") == "directory"
    assert source.get("path") == str(plugin_root)
    assert omg_marketplace.get("installLocation") == str(plugin_root)


def test_setup_install_configures_detected_cli_hosts(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    home_dir = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()

    for binary in ("codex", "gemini", "kimi"):
        script = fake_bin / binary
        _ = script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)

    env = {
        "CLAUDE_CONFIG_DIR": str(claude_dir),
        "HOME": str(home_dir),
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
    }

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip", "--install-as-plugin"],
        env=env,
    )
    assert proc.returncode == 0

    managed_python = claude_dir / "omg-runtime" / ".venv" / "bin" / "python"
    managed_launcher = claude_dir / "omg-runtime" / "bin" / "omg-mcp-server.py"

    codex_config = (home_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.omg-control]" in codex_config
    assert str(managed_python) in codex_config
    assert str(managed_launcher) in codex_config

    gemini_config = cast(
        dict[str, object],
        json.loads((home_dir / ".gemini" / "settings.json").read_text(encoding="utf-8")),
    )
    gemini_servers = cast(dict[str, object], gemini_config.get("mcpServers") or {})
    gemini_omg = cast(dict[str, object], gemini_servers.get("omg-control") or {})
    assert gemini_omg.get("command") == str(managed_python)
    assert gemini_omg.get("args") == [str(managed_launcher)]

    kimi_config = cast(
        dict[str, object],
        json.loads((home_dir / ".kimi" / "mcp.json").read_text(encoding="utf-8")),
    )
    kimi_servers = cast(dict[str, object], kimi_config.get("mcpServers") or {})
    kimi_omg = cast(dict[str, object], kimi_servers.get("omg-control") or {})
    assert kimi_omg.get("command") == str(managed_python)
    assert kimi_omg.get("args") == [str(managed_launcher)]


def test_setup_install_registers_session_start_hook(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=apply"],
        env=env,
    )
    assert proc.returncode == 0

    settings_path = claude_dir / "settings.json"
    settings = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
    hooks = cast(dict[str, object], settings.get("hooks") or {})
    session_start = cast(list[object], hooks.get("SessionStart") or [])
    commands = [
        hook.get("command")
        for entry in session_start
        if isinstance(entry, dict)
        for hook in cast(list[dict[str, object]], entry.get("hooks") or [])
        if isinstance(hook, dict)
    ]
    assert 'python3 "$HOME/.claude/hooks/session-start.py"' in commands


def test_setup_install_copies_all_registered_hook_command_targets(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=apply"],
        env=env,
    )
    assert proc.returncode == 0

    settings_path = claude_dir / "settings.json"
    targets = _read_hook_command_targets(settings_path)
    assert targets

    missing = sorted(name for name in targets if not (claude_dir / "hooks" / name).exists())
    assert not missing, f"Installed settings.json references missing hook files: {missing}"


def test_setup_uninstall_removes_plugin_bundle_and_plugin_mcp_servers(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    install_proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=apply", "--install-as-plugin"],
        env=env,
    )
    assert install_proc.returncode == 0

    mcp_servers = _read_mcp_servers(claude_dir / ".mcp.json")
    assert "filesystem" not in mcp_servers
    assert "omg-control" not in mcp_servers

    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    assert not (claude_dir / "plugins" / "cache" / "omg" / "omg").exists()
    assert not (claude_dir / "hud" / "omg-hud.mjs").exists()

    settings_path = claude_dir / "settings.json"
    settings_after = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
    enabled_after = cast(dict[str, object], settings_after.get("enabledPlugins") or {})
    assert "omg@omg" not in enabled_after
    assert "statusLine" not in settings_after

    mcp_after = _read_mcp_servers(claude_dir / ".mcp.json")
    assert "context7" not in mcp_after
    assert "filesystem" not in mcp_after
    assert "websearch" not in mcp_after
    assert "chrome-devtools" not in mcp_after

    installed_plugins_path = claude_dir / "plugins" / "installed_plugins.json"
    installed_plugins = cast(dict[str, object], json.loads(installed_plugins_path.read_text(encoding="utf-8")))
    plugins_after = cast(dict[str, object], installed_plugins.get("plugins") or {})
    assert "omg@omg" not in plugins_after


def test_setup_uninstall_removes_detected_cli_host_configs(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    home_dir = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()

    for binary in ("codex", "gemini", "kimi"):
        script = fake_bin / binary
        _ = script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)

    env = {
        "CLAUDE_CONFIG_DIR": str(claude_dir),
        "HOME": str(home_dir),
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
    }

    install_proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip", "--install-as-plugin"],
        env=env,
    )
    assert install_proc.returncode == 0

    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    codex_config = (home_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.omg-control]" not in codex_config

    gemini_config = cast(
        dict[str, object],
        json.loads((home_dir / ".gemini" / "settings.json").read_text(encoding="utf-8")),
    )
    gemini_servers = cast(dict[str, object], gemini_config.get("mcpServers") or {})
    assert "omg-control" not in gemini_servers

    kimi_config = cast(
        dict[str, object],
        json.loads((home_dir / ".kimi" / "mcp.json").read_text(encoding="utf-8")),
    )
    kimi_servers = cast(dict[str, object], kimi_config.get("mcpServers") or {})
    assert "omg-control" not in kimi_servers


def test_setup_install_as_plugin_prunes_duplicate_plugin_mcp_servers(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    mcp_path = claude_dir / ".mcp.json"
    _ = mcp_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]},
                    "omg-control": {"command": "python3", "args": ["-m", "runtime.omg_mcp_server"]},
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip", "--install-as-plugin"],
        env=env,
    )
    assert proc.returncode == 0

    merged = cast(dict[str, object], json.loads(mcp_path.read_text(encoding="utf-8")))
    servers = cast(dict[str, object], merged.get("mcpServers") or {})
    assert "filesystem" in servers
    assert "omg-control" not in servers


def test_setup_install_as_plugin_keeps_custom_status_line(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    settings_path = claude_dir / "settings.json"
    _ = settings_path.write_text(
        json.dumps(
            {
                "statusLine": {
                    "type": "command",
                    "command": "custom-statusline.sh",
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip", "--install-as-plugin"],
        env=env,
    )
    assert proc.returncode == 0

    settings = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
    status_line = cast(dict[str, object], settings.get("statusLine") or {})
    assert status_line.get("command") == "custom-statusline.sh"


def test_setup_uninstall_cleans_legacy_omg_registry_and_cache(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    legacy_cache = claude_dir / "plugins" / "cache" / "omg" / "omg"
    legacy_cache.mkdir(parents=True)
    _ = (legacy_cache / ".omg-plugin-bundle").write_text("omg-plugin-bundle-v1\n", encoding="utf-8")
    _ = (claude_dir / "hud").mkdir(parents=True)
    _ = (claude_dir / "hud" / "omg-hud.mjs").write_text("// hud\n", encoding="utf-8")

    settings_path = claude_dir / "settings.json"
    _ = settings_path.write_text(
        json.dumps(
            {
                "enabledPlugins": {
                    "omg@omg": True,
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

    mcp_path = claude_dir / ".mcp.json"
    _ = mcp_path.write_text(
        json.dumps(
            {
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
                    "omg@omg": [
                        {
                            "scope": "user",
                            "installPath": str(legacy_cache / "omg-v1-20260301"),
                            "version": "omg-v1-20260301",
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
    assert "omg@omg" not in enabled_after

    mcp_after_path = claude_dir / ".mcp.json"
    mcp_after_config = cast(dict[str, object], json.loads(mcp_after_path.read_text(encoding="utf-8")))
    mcp_after = cast(dict[str, object], mcp_after_config.get("mcpServers") or {})
    assert "context7" not in mcp_after
    assert "filesystem" not in mcp_after
    assert "websearch" not in mcp_after
    assert "chrome-devtools" not in mcp_after

    installed_after = cast(dict[str, object], json.loads(installed_plugins_path.read_text(encoding="utf-8")))
    plugins_after = cast(dict[str, object], installed_after.get("plugins") or {})
    assert "omg@omg" not in plugins_after


def test_setup_install_coexist_mode_writes_marker_file(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip", "--mode=coexist", "--preset=interop"],
        env=env,
    )
    assert proc.returncode == 0

    coexist_marker = claude_dir / "hooks" / ".omg-coexist"
    assert coexist_marker.exists()
    assert coexist_marker.read_text(encoding="utf-8").strip() == "coexist"


def test_setup_keeps_only_two_recent_backups(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    hooks_dir = claude_dir / "hooks"
    hooks_dir.mkdir(parents=True)
    _ = (hooks_dir / ".omg-version").write_text("omg-v1-old\n", encoding="utf-8")
    _ = (claude_dir / "settings.json").write_text("{}\n", encoding="utf-8")

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    for _ in range(3):
        proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
        assert proc.returncode == 0

    backups = sorted(p for p in claude_dir.iterdir() if p.is_dir() and p.name.startswith(".omg-backup-"))
    assert len(backups) <= 2


# --- npm plugin auto-registration tests ---


def test_setup_npm_context_enables_install_as_plugin(tmp_path: Path):
    """When npm_execpath env var is set, setup auto-enables plugin bundle mode."""
    env = {
        "npm_execpath": "/usr/local/lib/node_modules/npm/bin/npm-cli.js",
        "CLAUDE_CONFIG_DIR": str(tmp_path / ".claude"),
    }
    result = _run_script(SETUP, ["install", "--dry-run", "--non-interactive"], env=env)
    assert result.returncode == 0
    out = result.stdout + result.stderr
    assert "Plugin bundle mode enabled" in out


def test_postinstall_script_in_package_json():
    """package.json uses postinstall (not install) for npm lifecycle hook."""
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert "postinstall" in pkg["scripts"], "postinstall script missing from package.json"
    assert "install" not in pkg["scripts"], "plain 'install' script still present in package.json"


def test_npmignore_includes_hud_and_mcp():
    """.npmignore must NOT exclude plugin/runtime MCP or HUD assets from the npm package."""
    npmignore = (ROOT / ".npmignore").read_text(encoding="utf-8").splitlines()
    assert "hud/" not in npmignore, "hud/ should not be excluded from npm package"
    assert ".mcp.json" not in npmignore, ".mcp.json should not be excluded from npm package"
    assert ".claude-plugin/" not in npmignore, ".claude-plugin/ should not be excluded from npm package"


def test_plugin_bundle_assets_exist_for_npm_package():
    """The Claude plugin bundle must ship its own MCP manifest alongside the plugin manifest."""
    plugin_dir = ROOT / ".claude-plugin"
    assert (plugin_dir / "plugin.json").exists()
    assert (plugin_dir / "marketplace.json").exists()
    assert (plugin_dir / "mcp.json").exists()


def test_plugin_install_script_has_install_as_plugin_flag():
    """.claude-plugin/scripts/install.sh must pass --install-as-plugin --non-interactive."""
    install_sh = (ROOT / ".claude-plugin" / "scripts" / "install.sh").read_text(encoding="utf-8")
    assert "--install-as-plugin" in install_sh
    assert "--non-interactive" in install_sh


def test_plugin_uninstall_script_is_non_interactive():
    """.claude-plugin/scripts/uninstall.sh must pass --non-interactive."""
    uninstall_sh = (ROOT / ".claude-plugin" / "scripts" / "uninstall.sh").read_text(encoding="utf-8")
    assert "uninstall --non-interactive" in uninstall_sh


# --- Python version and managed runtime regression tests ---


def test_setup_rejects_python_below_3_10(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()

    fake_python = fake_bin / "python3"
    _ = fake_python.write_text(
        '#!/bin/bash\n'
        'if [[ "$1" == "-c" ]]; then\n'
        '  echo "3.9"\n'
        '  exit 0\n'
        'fi\n'
        'exit 1\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = {
        "CLAUDE_CONFIG_DIR": str(claude_dir),
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
    }
    proc = _run_script(SETUP, ["install", "--non-interactive"], env=env)
    assert proc.returncode != 0
    out = proc.stdout + proc.stderr
    assert "3.10" in out
    assert "3.9" in out
    assert "not supported" in out.lower() or "unsupported" in out.lower()


def test_setup_install_provisions_managed_venv(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip"],
        env=env,
    )
    assert proc.returncode == 0

    venv_python = claude_dir / "omg-runtime" / ".venv" / "bin" / "python"
    assert venv_python.exists(), "Managed venv python interpreter must exist"


def test_setup_plugin_install_patches_omg_control_to_managed_python(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip", "--install-as-plugin"],
        env=env,
    )
    assert proc.returncode == 0

    mcp_path = claude_dir / "plugins" / "cache" / "omg" / "omg" / "2.0.9" / ".claude-plugin" / "mcp.json"
    assert mcp_path.exists()
    mcp_config = cast(dict[str, object], json.loads(mcp_path.read_text(encoding="utf-8")))
    servers = cast(dict[str, object], mcp_config.get("mcpServers") or {})
    omg_control = cast(dict[str, object], servers.get("omg-control") or {})

    expected_python = str(claude_dir / "omg-runtime" / ".venv" / "bin" / "python")
    expected_launcher = str(claude_dir / "omg-runtime" / "bin" / "omg-mcp-server.py")
    assert omg_control.get("command") == expected_python, (
        f"omg-control command should be managed venv python, got: {omg_control.get('command')}"
    )
    assert omg_control.get("args") == [expected_launcher]


def test_setup_plugin_mcp_server_starts_outside_repo_root(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip", "--install-as-plugin"],
        env=env,
    )
    assert proc.returncode == 0

    mcp_path = claude_dir / "plugins" / "cache" / "omg" / "omg" / "2.0.9" / ".claude-plugin" / "mcp.json"
    mcp_config = cast(dict[str, object], json.loads(mcp_path.read_text(encoding="utf-8")))
    servers = cast(dict[str, object], mcp_config.get("mcpServers") or {})
    omg_control = cast(dict[str, object], servers.get("omg-control") or {})

    command = cast(str, omg_control.get("command"))
    args = cast(list[str], omg_control.get("args") or [])
    unrelated_cwd = tmp_path / "outside"
    unrelated_cwd.mkdir()
    _assert_command_starts(command, args, unrelated_cwd)
