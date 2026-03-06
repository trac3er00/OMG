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
    assert "Uninstall" in out
    assert "Update standalone" not in out
    assert "Update plugin install" not in out


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
    assert "Update standalone" in out
    assert "Update plugin install" in out


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

    plugin_cache_root = claude_dir / "plugins" / "cache" / "omg" / "omg"
    installed_versions = sorted([p for p in plugin_cache_root.iterdir() if p.is_dir()])
    assert installed_versions
    plugin_dir = installed_versions[-1]

    assert (plugin_dir / ".claude-plugin" / "plugin.json").exists()
    assert (plugin_dir / ".mcp.json").exists()
    assert (plugin_cache_root / ".omg-plugin-bundle").exists()
    assert (claude_dir / "hud" / "omg-hud.mjs").exists()

    settings_path = claude_dir / "settings.json"
    settings = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
    enabled = cast(dict[str, object], settings.get("enabledPlugins") or {})
    assert enabled.get("omg@omg") is True

    mcp_path = claude_dir / ".mcp.json"
    mcp_config = cast(dict[str, object], json.loads(mcp_path.read_text(encoding="utf-8")))
    mcp_servers = cast(dict[str, object], mcp_config.get("mcpServers") or {})
    assert "context7" in mcp_servers
    assert "filesystem" in mcp_servers
    assert "websearch" in mcp_servers
    assert "chrome-devtools" in mcp_servers

    installed_plugins_path = claude_dir / "plugins" / "installed_plugins.json"
    installed_plugins = cast(dict[str, object], json.loads(installed_plugins_path.read_text(encoding="utf-8")))
    plugins = cast(dict[str, object], installed_plugins.get("plugins") or {})
    assert "omg@omg" in plugins


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


def test_setup_uninstall_removes_plugin_bundle_and_plugin_mcp_servers(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    install_proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=apply", "--install-as-plugin"],
        env=env,
    )
    assert install_proc.returncode == 0

    mcp_path = claude_dir / ".mcp.json"
    mcp_config = cast(dict[str, object], json.loads(mcp_path.read_text(encoding="utf-8")))
    mcp_servers = cast(dict[str, object], mcp_config.get("mcpServers") or {})
    assert "context7" in mcp_servers
    assert "filesystem" in mcp_servers
    assert "websearch" in mcp_servers
    assert "chrome-devtools" in mcp_servers

    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    assert not (claude_dir / "plugins" / "cache" / "omg" / "omg").exists()
    assert not (claude_dir / "hud" / "omg-hud.mjs").exists()

    settings_path = claude_dir / "settings.json"
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

    installed_plugins_path = claude_dir / "plugins" / "installed_plugins.json"
    installed_plugins = cast(dict[str, object], json.loads(installed_plugins_path.read_text(encoding="utf-8")))
    plugins_after = cast(dict[str, object], installed_plugins.get("plugins") or {})
    assert "omg@omg" not in plugins_after


def test_setup_install_as_plugin_refreshes_stale_plugin_mcp_servers(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    mcp_path = claude_dir / ".mcp.json"
    _ = mcp_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
                    "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]},
                    "websearch": {"command": "npx", "args": ["-y", "@zhafron/mcp-web-search"]},
                    "chrome-devtools": {"command": "npx", "args": ["-y", "chrome-devtools-mcp@latest"]},
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
    source = cast(dict[str, object], json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8")))
    source_servers = cast(dict[str, object], source.get("mcpServers") or {})

    assert servers["context7"] == source_servers["context7"]
    assert servers["filesystem"] == source_servers["filesystem"]
    assert servers["websearch"] == source_servers["websearch"]
    assert servers["chrome-devtools"] == source_servers["chrome-devtools"]


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
    """.npmignore must NOT exclude hud/ or .mcp.json from the npm package."""
    npmignore = (ROOT / ".npmignore").read_text(encoding="utf-8").splitlines()
    assert "hud/" not in npmignore, "hud/ should not be excluded from npm package"
    assert ".mcp.json" not in npmignore, ".mcp.json should not be excluded from npm package"


def test_plugin_install_script_has_install_as_plugin_flag():
    """.claude-plugin/scripts/install.sh must pass --install-as-plugin --non-interactive."""
    install_sh = (ROOT / ".claude-plugin" / "scripts" / "install.sh").read_text(encoding="utf-8")
    assert "--install-as-plugin" in install_sh
    assert "--non-interactive" in install_sh
