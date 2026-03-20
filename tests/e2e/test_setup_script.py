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
import pytest

from runtime.adoption import CANONICAL_VERSION


ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "OMG-setup.sh"
LEGACY = ROOT / "install.sh"

pytestmark = pytest.mark.xdist_group("setup-script-e2e")


@pytest.fixture(scope="session", autouse=True)
def _shared_setup_install_artifacts(tmp_path_factory: pytest.TempPathFactory):
    wheel_cache = ROOT / ".context" / "e2e-wheelhouse"
    cached_wheels = sorted(wheel_cache.glob("oh_my_god-*.whl")) if wheel_cache.exists() else []
    if cached_wheels:
        wheel_path = cached_wheels[-1]
    else:
        wheelhouse = tmp_path_factory.mktemp("omg-wheelhouse")
        subprocess.run(
            [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheelhouse), str(ROOT)],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        wheel_path = next(wheelhouse.glob("oh_my_god-*.whl"))

    pip_cache = tmp_path_factory.mktemp("pip-cache")
    prewarmed_venv = tmp_path_factory.mktemp("omg-prewarmed-venv") / ".venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(prewarmed_venv)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    subprocess.run(
        [str(prewarmed_venv / "bin" / "pip"), "install", "--quiet", f"{wheel_path}[mcp]"],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("OMG_SETUP_PACKAGE_SPEC", str(wheel_path))
    monkeypatch.setenv("OMG_SETUP_PREWARMED_VENV", str(prewarmed_venv))
    monkeypatch.setenv("PIP_CACHE_DIR", str(pip_cache))
    monkeypatch.setenv("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    monkeypatch.setenv("PIP_NO_INPUT", "1")
    try:
        yield
    finally:
        monkeypatch.undo()


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
        timeout=120,
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
        timeout=120,
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
    assert "--preset=safe|balanced|interop|labs|buffet|production" in out
    assert "--clear-omc" not in out
    assert "--without-legacy-aliases" not in out


def test_setup_script_supports_package_spec_override():
    script = SETUP.read_text(encoding="utf-8")
    assert "OMG_SETUP_PACKAGE_SPEC" in script


def test_setup_script_supports_prewarmed_venv_override():
    script = SETUP.read_text(encoding="utf-8")
    assert "OMG_SETUP_PREWARMED_VENV" in script


def test_setup_script_sets_safe_ifs():
    script = SETUP.read_text(encoding="utf-8")
    assert "IFS=$'\\n\\t'" in script


def test_setup_uninstall_cleans_settings_before_runtime_deletion():
    script = SETUP.read_text(encoding="utf-8")
    function_body = script.split("remove_omg_files() {", 1)[1].split("install_plugin_bundle()", 1)[0]

    sentinel_idx = function_body.index('echo "uninstalling" > "$CLAUDE_DIR/.omg-uninstalling"')
    remove_hooks_idx = function_body.index("remove_omg_hooks_from_settings")
    remove_metadata_idx = function_body.index("remove_omg_metadata_from_settings")
    remove_runtime_idx = function_body.index('rm -rf "$CLAUDE_DIR/omg-runtime"')
    clear_sentinel_idx = function_body.index('rm -f "$CLAUDE_DIR/.omg-uninstalling"')

    assert sentinel_idx < remove_hooks_idx < remove_runtime_idx
    assert sentinel_idx < remove_metadata_idx < remove_runtime_idx
    assert remove_runtime_idx < clear_sentinel_idx


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


def test_setup_script_auto_merge_on_existing_settings(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    _ = (claude_dir / "settings.json").write_text('{"enabledPlugins":{"existing@demo":true}}\n', encoding="utf-8")

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    proc = _run_script(SETUP, ["install"], env=env)
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "Settings merged (auto)" in out


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
    assert (commands_dir / "OMG:preset.md").exists()


def test_setup_install_accepts_buffet_preset(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip", "--preset=buffet"],
        env=env,
    )
    assert proc.returncode == 0


def test_setup_install_accepts_production_preset(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip", "--preset=production"],
        env=env,
    )
    assert proc.returncode == 0


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


def test_setup_install_provisions_runtime_registry_and_doctor_outside_repo(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir), "HOME": str(home_dir)}

    proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
    assert proc.returncode == 0

    registry_dir = claude_dir / "omg-runtime" / "registry"
    assert registry_dir.is_dir()
    assert (registry_dir / "verify_artifact.py").exists()

    doctor = subprocess.run(
        [sys.executable, "-S", str(claude_dir / "omg-runtime" / "scripts" / "omg.py"), "doctor"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert "ModuleNotFoundError" not in doctor.stderr
    assert "Traceback" not in doctor.stderr
    assert doctor.stdout.strip()


def test_setup_install_hooks_can_import_portable_runtime_outside_repo(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
    assert proc.returncode == 0

    merged_env = dict(os.environ)
    merged_env["CLAUDE_PROJECT_DIR"] = str(tmp_path)

    firewall_payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "tool_response": {},
    }
    firewall_run = subprocess.run(
        [sys.executable, str(claude_dir / "hooks" / "firewall.py")],
        cwd=str(tmp_path),
        input=json.dumps(firewall_payload),
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
    )

    assert firewall_run.returncode == 0
    assert "policy_engine import failed" not in firewall_run.stderr
    assert firewall_run.stdout.strip() == ""

    read_payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": "README.md"},
        "tool_response": {},
    }
    secret_guard_run = subprocess.run(
        [sys.executable, str(claude_dir / "hooks" / "secret-guard.py")],
        cwd=str(tmp_path),
        input=json.dumps(read_payload),
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
    )

    assert secret_guard_run.returncode == 0
    assert "policy_engine import failed" not in secret_guard_run.stderr
    assert secret_guard_run.stdout.strip() == ""


def test_setup_install_enables_optional_browser_capability(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    playwright = fake_bin / "playwright"
    _ = playwright.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    playwright.chmod(0o755)

    env = {
        "CLAUDE_CONFIG_DIR": str(claude_dir),
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
    }

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip", "--enable-browser"],
        env=env,
    )
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "browser capability enabled" in out.lower()

    browser_state_path = claude_dir / "omg-runtime" / "browser" / "capability.json"
    assert browser_state_path.exists()
    browser_state = cast(dict[str, object], json.loads(browser_state_path.read_text(encoding="utf-8")))
    assert browser_state["enabled"] is True
    assert browser_state["command"] == ["playwright"]


def test_setup_install_leaves_browser_capability_disabled_by_default(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip"],
        env=env,
    )
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "browser capability enabled" not in out.lower()
    assert not (claude_dir / "omg-runtime" / "browser" / "capability.json").exists()


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
    assert plugin_dir.name == CANONICAL_VERSION

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

    plugin_root = claude_dir / "plugins" / "cache" / "omg" / "omg" / CANONICAL_VERSION
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
    assert '"$HOME/.claude/omg-runtime/.venv/bin/python" "$HOME/.claude/hooks/session-start.py"' in commands


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

    for binary in ("codex", "gemini", "kimi", "opencode"):
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

    opencode_path = home_dir / ".config" / "opencode" / "opencode.json"
    if opencode_path.exists():
        opencode_config = cast(
            dict[str, object],
            json.loads(opencode_path.read_text(encoding="utf-8")),
        )
        opencode_servers = cast(dict[str, object], opencode_config.get("mcp") or {})
        assert "omg-control" not in opencode_servers


def test_setup_uninstall_preserves_opencode_plugin_entries(tmp_path: Path):
    """OpenCode host cleanup must remove OMG MCP only, not third-party plugin entries."""
    claude_dir = tmp_path / ".claude"
    home_dir = tmp_path / "home"
    opencode_dir = home_dir / ".config" / "opencode"
    opencode_dir.mkdir(parents=True)
    (opencode_dir / "opencode.json").write_text(
        json.dumps(
            {
                "plugin": ["oh-my-opencode@latest"],
                "mcp": {
                    "omg-control": {"type": "stdio", "command": "python3", "args": ["-m", "runtime.omg_mcp_server"]},
                    "other-server": {"type": "stdio", "command": "node", "args": ["server.js"]},
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir), "HOME": str(home_dir)}
    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    opencode_config = cast(dict[str, object], json.loads((opencode_dir / "opencode.json").read_text(encoding="utf-8")))
    assert opencode_config.get("plugin") == ["oh-my-opencode@latest"]
    opencode_servers = cast(dict[str, object], opencode_config.get("mcp") or {})
    assert "omg-control" not in opencode_servers
    assert "other-server" in opencode_servers


def test_setup_uninstall_removes_omg_metadata_from_claude_settings(tmp_path: Path):
    """Verify Claude settings.json no longer keeps the _omg metadata block after uninstall."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "enabledPlugins": {"linear@claude-plugins-official": True},
                "_omg": {"_version": "2.2.7", "preset": "safe"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir), "HOME": str(tmp_path / "home")}
    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    settings = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
    assert "_omg" not in settings
    enabled_plugins = cast(dict[str, object], settings.get("enabledPlugins") or {})
    assert enabled_plugins == {"linear@claude-plugins-official": True}


def test_setup_uninstall_removes_codex_managed_residue(tmp_path: Path):
    """Verify Codex OMG state, HUD, and managed skills are removed on uninstall."""
    claude_dir = tmp_path / ".claude"
    home_dir = tmp_path / "home"
    codex_dir = home_dir / ".codex"

    (codex_dir / ".omg").mkdir(parents=True)
    (codex_dir / "hud").mkdir(parents=True)
    (codex_dir / "bin").mkdir(parents=True)
    managed_skill = codex_dir / "skills" / "omg-orchestrator"
    managed_skill.mkdir(parents=True)
    (managed_skill / ".omg-managed-skill").write_text("managed\n", encoding="utf-8")
    (codex_dir / "hud" / "omg-codex-hud.py").write_text("# hud\n", encoding="utf-8")
    (codex_dir / "bin" / "omg-codex-hud").write_text("#!/bin/sh\n", encoding="utf-8")

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir), "HOME": str(home_dir)}
    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    assert not (codex_dir / ".omg").exists()
    assert not (codex_dir / "hud" / "omg-codex-hud.py").exists()
    assert not (codex_dir / "bin" / "omg-codex-hud").exists()
    assert not managed_skill.exists()


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


def test_setup_keeps_only_three_recent_backups(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    hooks_dir = claude_dir / "hooks"
    hooks_dir.mkdir(parents=True)
    _ = (hooks_dir / ".omg-version").write_text("omg-v1-old\n", encoding="utf-8")
    _ = (claude_dir / "settings.json").write_text("{}\n", encoding="utf-8")

    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}
    for _ in range(5):
        proc = _run_script(SETUP, ["install", "--non-interactive"], env=env)
        assert proc.returncode == 0

    backups = sorted(p for p in claude_dir.iterdir() if p.is_dir() and p.name.startswith(".omg-backup-"))
    assert len(backups) <= 3




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


@pytest.mark.parametrize("pattern,reason", [
    ("hud/", "hud/ should not be excluded from npm package"),
    (".mcp.json", ".mcp.json should not be excluded from npm package"),
    (".claude-plugin/", ".claude-plugin/ should not be excluded from npm package"),
    ("omg_natives/", "omg_natives/ should not be excluded from npm package"),
    ("install.sh", "bare install.sh pattern would exclude nested plugin install scripts"),
])
def test_npmignore_must_not_exclude_runtime_assets(pattern: str, reason: str):
    """.npmignore must NOT exclude plugin/runtime MCP or HUD assets from the npm package."""
    npmignore = (ROOT / ".npmignore").read_text(encoding="utf-8").splitlines()
    assert pattern not in npmignore, reason


def test_npmignore_excludes_root_install_script():
    """.npmignore must explicitly exclude the root install.sh with a root-anchored pattern."""
    npmignore = (ROOT / ".npmignore").read_text(encoding="utf-8").splitlines()
    assert "/install.sh" in npmignore, "root install.sh should be ignored explicitly with a root-anchored pattern"


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


def test_plugin_update_script_runs_plugin_bundle_update_non_interactive():
    update_sh = (ROOT / ".claude-plugin" / "scripts" / "update.sh").read_text(encoding="utf-8")
    assert "update --install-as-plugin --non-interactive" in update_sh


def test_plugin_update_script_checks_npm_latest_before_local_update():
    update_sh = (ROOT / ".claude-plugin" / "scripts" / "update.sh").read_text(encoding="utf-8")
    assert "npm view \"$PKG_NAME\" version" in update_sh
    assert "npm install --prefix" in update_sh




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

    mcp_path = claude_dir / "plugins" / "cache" / "omg" / "omg" / CANONICAL_VERSION / ".claude-plugin" / "mcp.json"
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

    mcp_path = claude_dir / "plugins" / "cache" / "omg" / "omg" / CANONICAL_VERSION / ".claude-plugin" / "mcp.json"
    mcp_config = cast(dict[str, object], json.loads(mcp_path.read_text(encoding="utf-8")))
    servers = cast(dict[str, object], mcp_config.get("mcpServers") or {})
    omg_control = cast(dict[str, object], servers.get("omg-control") or {})

    command = cast(str, omg_control.get("command"))
    args = cast(list[str], omg_control.get("args") or [])
    unrelated_cwd = tmp_path / "outside"
    unrelated_cwd.mkdir()
    _assert_command_starts(command, args, unrelated_cwd)




# --- Pre-install integrity verification tests ---


def test_setup_install_proceeds_when_no_integrity_manifest(tmp_path: Path):
    """Install completes normally when no INSTALL_INTEGRITY.sha256 manifest exists."""
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    # Should note that no manifest was found, but not block
    assert "no integrity manifest" in out.lower() or "integrity" in out.lower()


def test_setup_install_proceeds_with_valid_integrity_manifest(tmp_path: Path):
    """Install completes when integrity manifest exists and all hashes match."""
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    # Create a valid manifest with real hashes of files in SCRIPT_DIR
    manifest_path = ROOT / "INSTALL_INTEGRITY.sha256"
    try:
        # Hash a known file that always exists
        import hashlib
        target_file = ROOT / "OMG-setup.sh"
        file_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()
        manifest_path.write_text(f"{file_hash}  OMG-setup.sh\n", encoding="utf-8")

        proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
        assert proc.returncode == 0
        out = proc.stdout + proc.stderr
        assert "integrity verified" in out.lower()
    finally:
        manifest_path.unlink(missing_ok=True)


def test_setup_install_blocked_on_integrity_hash_mismatch(tmp_path: Path):
    """Install is blocked with actionable output when hash mismatch is detected."""
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    manifest_path = ROOT / "INSTALL_INTEGRITY.sha256"
    try:
        # Write a manifest with a bogus hash
        manifest_path.write_text(
            "0000000000000000000000000000000000000000000000000000000000000000  OMG-setup.sh\n",
            encoding="utf-8",
        )

        proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
        assert proc.returncode != 0, "Install must fail on hash mismatch"
        out = proc.stdout + proc.stderr
        assert "integrity" in out.lower()
        assert "mismatch" in out.lower() or "failed" in out.lower()
        assert "OMG-setup.sh" in out
    finally:
        manifest_path.unlink(missing_ok=True)


def test_setup_install_blocked_on_missing_manifest_file(tmp_path: Path):
    """Install is blocked when manifest references a file that doesn't exist."""
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    manifest_path = ROOT / "INSTALL_INTEGRITY.sha256"
    try:
        # Reference a file that doesn't exist
        manifest_path.write_text(
            "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890  nonexistent-file.txt\n",
            encoding="utf-8",
        )

        proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
        assert proc.returncode != 0, "Install must fail when manifest references missing file"
        out = proc.stdout + proc.stderr
        assert "integrity" in out.lower()
        assert "nonexistent-file.txt" in out
    finally:
        manifest_path.unlink(missing_ok=True)


def test_setup_integrity_check_runs_before_host_mutation(tmp_path: Path):
    """Integrity check must run before any host config files are created."""
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    manifest_path = ROOT / "INSTALL_INTEGRITY.sha256"
    try:
        # Write a bad manifest to trigger failure
        manifest_path.write_text(
            "0000000000000000000000000000000000000000000000000000000000000000  OMG-setup.sh\n",
            encoding="utf-8",
        )

        proc = _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
        assert proc.returncode != 0

        # No host mutation should have happened
        assert not (claude_dir / "hooks").exists(), "hooks dir should not exist after integrity failure"
        assert not (claude_dir / "rules").exists(), "rules dir should not exist after integrity failure"
        assert not (claude_dir / "agents").exists(), "agents dir should not exist after integrity failure"
    finally:
        manifest_path.unlink(missing_ok=True)


def test_setup_integrity_check_dry_run_still_verifies(tmp_path: Path):
    """Integrity check runs even in dry-run mode — invalid source should still be caught."""
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    manifest_path = ROOT / "INSTALL_INTEGRITY.sha256"
    try:
        manifest_path.write_text(
            "0000000000000000000000000000000000000000000000000000000000000000  OMG-setup.sh\n",
            encoding="utf-8",
        )

        proc = _run_script(SETUP, ["install", "--dry-run", "--non-interactive"], env=env)
        assert proc.returncode != 0, "Dry-run must also fail on integrity mismatch"
        out = proc.stdout + proc.stderr
        assert "integrity" in out.lower()
    finally:
        manifest_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Post-install validation (Task 8)
# ---------------------------------------------------------------------------

def test_setup_install_runs_post_install_validation(tmp_path: Path):
    """Install flow runs post-install validation and emits artifact on success."""
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip"],
        env=env,
    )
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "Post-install validation" in out
    assert "passed" in out.lower()
    # Artifact should be mentioned
    assert "post-install-validation.json" in out


def test_preset_features_single_source_of_truth():
    from runtime.adoption import PRESET_FEATURES, VALID_PRESETS, PRESET_ORDER, PRESET_LEVEL

    assert "buffet" in VALID_PRESETS
    assert "buffet" in PRESET_FEATURES
    assert "buffet" in PRESET_LEVEL
    assert "production" in VALID_PRESETS
    assert "production" in PRESET_FEATURES
    assert "production" in PRESET_LEVEL

    buffet = PRESET_FEATURES["buffet"]
    assert buffet["DATA_ENFORCEMENT"] is True
    assert buffet["WEB_ENFORCEMENT"] is True
    assert buffet["TERMS_ENFORCEMENT"] is True
    assert buffet["COUNCIL_ROUTING"] is True
    assert buffet["FORGE_ALL_DOMAINS"] is True
    assert buffet["NOTEBOOKLM"] is True

    for p in ("safe", "balanced", "interop", "labs"):
        features = PRESET_FEATURES[p]
        for flag in ("DATA_ENFORCEMENT", "WEB_ENFORCEMENT", "TERMS_ENFORCEMENT",
                      "COUNCIL_ROUTING", "FORGE_ALL_DOMAINS", "NOTEBOOKLM"):
            assert features[flag] is False, f"{p} must not enable {flag}"

    production = PRESET_FEATURES["production"]
    for flag in (
        "SETUP",
        "SETUP_WIZARD",
        "MEMORY_AUTOSTART",
        "SESSION_ANALYTICS",
        "CONTEXT_MANAGER",
        "COST_TRACKING",
        "GIT_WORKFLOW",
        "TEST_GENERATION",
        "DEP_HEALTH",
        "DATA_ENFORCEMENT",
        "WEB_ENFORCEMENT",
        "TERMS_ENFORCEMENT",
        "COUNCIL_ROUTING",
    ):
        assert production[flag] is True, f"production must enable {flag}"

    for i, name in enumerate(PRESET_ORDER):
        assert PRESET_LEVEL[name] == i

    from hooks.setup_wizard import PRESET_ORDER as wizard_order
    assert wizard_order is PRESET_ORDER


def test_buffet_preset_get_preset_features():
    from runtime.adoption import get_preset_features
    features = get_preset_features("buffet")
    assert all(v is True for v in features.values()), (
        f"All buffet flags must be True, got: {features}"
    )


def test_production_preset_get_preset_features():
    from runtime.adoption import get_preset_features

    features = get_preset_features("production")
    for key in (
        "TEST_GENERATION",
        "CONTEXT_MANAGER",
        "DATA_ENFORCEMENT",
        "TERMS_ENFORCEMENT",
        "COUNCIL_ROUTING",
    ):
        assert features[key] is True, (key, features)


def test_setup_install_post_install_validation_failure_structured(tmp_path: Path):
    """Install fails with structured output when post-install validation detects blockers."""
    plugin_json = ROOT / "plugins" / "core" / "plugin.json"
    plugin_json_bak = ROOT / "plugins" / "core" / "plugin.json._test_bak"

    try:
        plugin_json.rename(plugin_json_bak)

        claude_dir = tmp_path / ".claude"
        env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

        proc = _run_script(
            SETUP,
            ["install", "--non-interactive", "--merge-policy=skip"],
            env=env,
        )
        assert proc.returncode != 0, "Install must fail when post-install validation has blockers"
        out = proc.stdout + proc.stderr
        assert "FAILED" in out or "failed" in out
        assert "blocker" in out.lower() or "plugin" in out.lower()
    finally:
        if plugin_json_bak.exists():
            plugin_json_bak.rename(plugin_json)


def test_setup_uninstall_next_session_claude_config_clean(tmp_path: Path):
    """Verify no omg-runtime references remain in Claude config after uninstall."""
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    # Install OMG
    install_proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip"],
        env=env,
    )
    assert install_proc.returncode == 0

    # Uninstall OMG
    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    # Verify settings.json has no omg-runtime references in hook commands
    settings_path = claude_dir / "settings.json"
    if settings_path.exists():
        settings = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
        hooks = cast(dict[str, object], settings.get("hooks") or {})

        for hook_type, entries in hooks.items():
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
                    command = hook.get("command", "")
                    assert "omg-runtime" not in command, (
                        f"Hook command still references omg-runtime: {command}"
                    )

    # Verify .mcp.json has no omg-control after uninstall
    mcp_path = claude_dir / ".mcp.json"
    if mcp_path.exists():
        mcp_servers = _read_mcp_servers(mcp_path)
        assert "omg-control" not in mcp_servers, (
            "omg-control should not be in mcpServers after uninstall"
        )

    # Run doctor to verify next-session state is clean
    doctor_proc = subprocess.run(
        ["python3", "scripts/omg.py", "doctor", "--format=json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "CLAUDE_CONFIG_DIR": str(claude_dir)},
    )
    assert doctor_proc.returncode == 0
    doctor_output = json.loads(doctor_proc.stdout)

    # Verify no orphaned_runtime blocker in doctor output
    checks = cast(dict[str, object], doctor_output.get("checks") or {})
    if "orphaned_runtime" in checks:
        orphan_check = cast(dict[str, object], checks["orphaned_runtime"])
        status = orphan_check.get("status")
        assert status != "blocker", (
            f"orphaned_runtime check should not be blocker after clean uninstall, got: {status}"
        )


def test_setup_uninstall_detected_hosts_clean(tmp_path: Path):
    """Verify omg-control is absent from detected host configs after uninstall."""
    claude_dir = tmp_path / ".claude"
    home_dir = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()

    # Create fake binaries for detected hosts
    for binary in ("codex", "gemini", "kimi"):
        script = fake_bin / binary
        _ = script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)

    env = {
        "CLAUDE_CONFIG_DIR": str(claude_dir),
        "HOME": str(home_dir),
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
    }

    # Install OMG with detected hosts on PATH
    install_proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip"],
        env=env,
    )
    assert install_proc.returncode == 0

    # Verify omg-control was registered in detected hosts
    codex_config_before = (home_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.omg-control]" in codex_config_before, (
        "omg-control should be registered in Codex after install"
    )

    # Uninstall OMG
    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    # Verify omg-control is removed from Codex config
    codex_config_after = (home_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.omg-control]" not in codex_config_after, (
        "omg-control should be removed from Codex after uninstall"
    )

    # Verify omg-control is removed from Gemini config
    gemini_config_path = home_dir / ".gemini" / "settings.json"
    if gemini_config_path.exists():
        gemini_config = cast(
            dict[str, object],
            json.loads(gemini_config_path.read_text(encoding="utf-8")),
        )
        gemini_servers = cast(dict[str, object], gemini_config.get("mcpServers") or {})
        assert "omg-control" not in gemini_servers, (
            "omg-control should be removed from Gemini after uninstall"
        )

    # Verify omg-control is removed from Kimi config
    kimi_config_path = home_dir / ".kimi" / "mcp.json"
    if kimi_config_path.exists():
        kimi_config = cast(
            dict[str, object],
            json.loads(kimi_config_path.read_text(encoding="utf-8")),
        )
        kimi_servers = cast(dict[str, object], kimi_config.get("mcpServers") or {})
        assert "omg-control" not in kimi_servers, (
            "omg-control should be removed from Kimi after uninstall"
        )


def test_setup_uninstall_removes_hook_settings_entries(tmp_path: Path):
    """Install → write settings.json with omg-runtime hook → uninstall → verify no omg-runtime hooks remain."""
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    install_proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip"],
        env=env,
    )
    assert install_proc.returncode == 0

    # Inject an omg-runtime hook entry into settings.json
    settings_path = claude_dir / "settings.json"
    settings: dict[str, object] = {}
    if settings_path.exists():
        try:
            settings = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
        except Exception:
            settings = {}
    settings["hooks"] = {
        "PreToolUse": [
            {"command": str(claude_dir / "omg-runtime" / "bin" / "omg-hook.py"), "type": "command"},
            {"command": "/usr/local/bin/my-custom-hook", "type": "command"},
        ]
    }
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    # Verify no omg-runtime hook entries remain
    assert settings_path.exists(), "settings.json should still exist after uninstall"
    settings_after = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))
    hooks_after = cast(dict[str, object], settings_after.get("hooks") or {})
    for _event, entries in hooks_after.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            cmd = entry.get("command", "")
            assert "omg-runtime" not in str(cmd), (
                f"omg-runtime hook entry should have been removed from settings.json, found: {cmd}"
            )

    # Non-OMG hook should still be present
    pre_tool_entries = cast(list[object], hooks_after.get("PreToolUse") or [])
    custom_cmds = [
        e.get("command", "") for e in pre_tool_entries if isinstance(e, dict)
    ]
    assert any("/my-custom-hook" in str(c) for c in custom_cmds), (
        "Non-OMG hook should be preserved after uninstall"
    )


def test_setup_uninstall_emits_receipt(tmp_path: Path):
    """Install → uninstall → verify .omg-uninstall-receipt.json exists with status == 'ok'."""
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    install_proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip"],
        env=env,
    )
    assert install_proc.returncode == 0

    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    receipt_path = claude_dir / ".omg-uninstall-receipt.json"
    assert receipt_path.exists(), (
        f".omg-uninstall-receipt.json should exist after uninstall at {receipt_path}"
    )

    receipt = cast(dict[str, object], json.loads(receipt_path.read_text(encoding="utf-8")))
    assert receipt.get("schema") == "UninstallReceipt", "Receipt schema field must be 'UninstallReceipt'"
    assert receipt.get("status") == "ok", f"Receipt status must be 'ok', got: {receipt.get('status')}"
    assert "timestamp" in receipt, "Receipt must have a timestamp field"
    assert "version" in receipt, "Receipt must have a version field"
    assert isinstance(receipt.get("removed_paths"), list), "Receipt removed_paths must be a list"
    assert isinstance(receipt.get("preserved_paths"), list), "Receipt preserved_paths must be a list"
    assert isinstance(receipt.get("host_configs_cleaned"), list), "Receipt host_configs_cleaned must be a list"


def test_setup_uninstall_preserves_non_omg_settings(tmp_path: Path):
    """Verify non-OMG settings.json keys survive uninstall."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    # Pre-populate settings.json with non-OMG keys
    settings_path = claude_dir / "settings.json"
    pre_settings: dict[str, object] = {
        "theme": "dark",
        "fontSize": 14,
        "customKey": {"nested": True},
        "hooks": {
            "PreToolUse": [
                {"command": "/usr/local/bin/my-linter", "type": "command"},
            ]
        },
    }
    settings_path.write_text(json.dumps(pre_settings, indent=2) + "\n", encoding="utf-8")

    install_proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip"],
        env=env,
    )
    assert install_proc.returncode == 0

    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    assert settings_path.exists(), "settings.json should still exist after uninstall"
    settings_after = cast(dict[str, object], json.loads(settings_path.read_text(encoding="utf-8")))

    # Non-OMG top-level keys must be preserved
    assert settings_after.get("theme") == "dark", "theme key should be preserved"
    assert settings_after.get("fontSize") == 14, "fontSize key should be preserved"
    assert settings_after.get("customKey") == {"nested": True}, "customKey should be preserved"

    # Non-OMG hook entry must be preserved
    hooks_after = cast(dict[str, object], settings_after.get("hooks") or {})
    pre_tool_entries = cast(list[object], hooks_after.get("PreToolUse") or [])
    custom_cmds = [
        e.get("command", "") for e in pre_tool_entries if isinstance(e, dict)
    ]
    assert any("/my-linter" in str(c) for c in custom_cmds), (
        "Non-OMG hook /my-linter should be preserved after uninstall"
    )


def test_setup_uninstall_verify_clean_dry_run(tmp_path: Path):
    """--verify-clean --dry-run --non-interactive exits 0 and stdout contains host_configs_cleaned."""
    claude_dir = tmp_path / ".claude"
    env = {"CLAUDE_CONFIG_DIR": str(claude_dir)}

    # Install first so there's something to uninstall
    install_proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip"],
        env=env,
    )
    assert install_proc.returncode == 0

    proc = _run_script(
        SETUP,
        ["uninstall", "--verify-clean", "--non-interactive", "--dry-run"],
        env=env,
    )
    assert proc.returncode == 0, f"exit {proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    combined = proc.stdout + proc.stderr
    assert "verification_status" in combined, (
        f"verify-clean output must contain verification_status, got:\n{combined}"
    )


def test_setup_uninstall_host_configs_cleaned_non_empty(tmp_path: Path):
    """After install with detected hosts, uninstall receipt has real paths in host_configs_cleaned."""
    claude_dir = tmp_path / ".claude"
    home_dir = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()

    # Create fake binaries for detected hosts
    for binary in ("codex", "gemini", "kimi"):
        script = fake_bin / binary
        _ = script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)

    env = {
        "CLAUDE_CONFIG_DIR": str(claude_dir),
        "HOME": str(home_dir),
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
    }

    # Install OMG with detected hosts on PATH
    install_proc = _run_script(
        SETUP,
        ["install", "--non-interactive", "--merge-policy=skip"],
        env=env,
    )
    assert install_proc.returncode == 0

    # Uninstall OMG
    uninstall_proc = _run_script(SETUP, ["uninstall", "--non-interactive"], env=env)
    assert uninstall_proc.returncode == 0

    receipt_path = claude_dir / ".omg-uninstall-receipt.json"
    assert receipt_path.exists(), "Uninstall receipt should exist"

    receipt = cast(dict[str, object], json.loads(receipt_path.read_text(encoding="utf-8")))
    host_configs = receipt.get("host_configs_cleaned")
    assert isinstance(host_configs, list), "host_configs_cleaned must be a list"
    assert len(host_configs) > 0, (
        f"host_configs_cleaned must not be empty when hosts were detected, got: {host_configs}"
    )
    # Must contain real paths, not literal "[]"
    assert all(isinstance(p, str) and len(p) > 2 for p in host_configs), (
        f"host_configs_cleaned must contain real paths, got: {host_configs}"
    )


# ---------------------------------------------------------------------------
# verify-clean ownership-aware audit + repair
# ---------------------------------------------------------------------------


def test_setup_verify_clean_detects_all_owned_surfaces(tmp_path: Path):
    """Dry-run verify-clean detects residue across all OMG-owned surfaces."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    home_dir = tmp_path / "home"

    # Claude file residue
    hooks_dir = claude_dir / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / ".omg-version").write_text("1.0.0", encoding="utf-8")

    # Claude settings.json with omg-runtime hook + statusLine
    settings: dict[str, object] = {
        "hooks": {
            "PreToolUse": [
                {"command": str(claude_dir / "omg-runtime" / "bin" / "omg-hook.py"), "type": "command"},
            ]
        },
        "statusLine": {"command": str(claude_dir / "hud" / "omg-hud.mjs")},
    }
    (claude_dir / "settings.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    # Codex config.toml with omg-control
    codex_dir = home_dir / ".codex"
    codex_dir.mkdir(parents=True)
    (codex_dir / "config.toml").write_text(
        '[mcp_servers.omg-control]\ncommand = "python3"\nargs = ["-m", "runtime.omg_mcp_server"]\n',
        encoding="utf-8",
    )

    # Gemini settings.json with omg-control
    gemini_dir = home_dir / ".gemini"
    gemini_dir.mkdir(parents=True)
    (gemini_dir / "settings.json").write_text(
        json.dumps({"mcpServers": {"omg-control": {"command": "python3"}}}) + "\n",
        encoding="utf-8",
    )

    # Kimi mcp.json with omg-control
    kimi_dir = home_dir / ".kimi"
    kimi_dir.mkdir(parents=True)
    (kimi_dir / "mcp.json").write_text(
        json.dumps({"mcpServers": {"omg-control": {"command": "python3"}}}) + "\n",
        encoding="utf-8",
    )

    # OpenCode config with omg-control
    opencode_dir = home_dir / ".config" / "opencode"
    opencode_dir.mkdir(parents=True)
    (opencode_dir / "opencode.json").write_text(
        json.dumps({"mcp": {"omg-control": {"command": "python3"}}}) + "\n",
        encoding="utf-8",
    )

    env = {
        "CLAUDE_CONFIG_DIR": str(claude_dir),
        "HOME": str(home_dir),
    }
    proc = _run_script(
        SETUP,
        ["uninstall", "--verify-clean", "--non-interactive", "--dry-run"],
        env=env,
    )
    assert proc.returncode == 0, f"exit {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    combined = proc.stdout + proc.stderr

    # Must audit every owned surface
    for surface in (
        "claude_file_residue",
        "claude_hooks",
        "claude_status_line",
        "codex_mcp",
        "gemini_mcp",
        "kimi_mcp",
        "opencode_mcp",
    ):
        assert surface in combined, (
            f"verify-clean must audit surface '{surface}', got:\n{combined}"
        )

    # Must report residue_found (not empty)
    assert "residue_found" in combined, f"must contain residue_found:\n{combined}"


def test_setup_verify_clean_repair_removes_owned_residue(tmp_path: Path):
    """--repair combined with --verify-clean removes OMG-owned residue and preserves non-OMG config."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    home_dir = tmp_path / "home"

    # Codex: omg-control section + user section
    codex_dir = home_dir / ".codex"
    codex_dir.mkdir(parents=True)
    codex_toml = codex_dir / "config.toml"
    codex_toml.write_text(
        '[mcp_servers.my-tool]\ncommand = "my-tool"\n\n'
        '[mcp_servers.omg-control]\ncommand = "python3"\nargs = ["-m", "runtime.omg_mcp_server"]\n',
        encoding="utf-8",
    )

    # Gemini: omg-control + user server
    gemini_dir = home_dir / ".gemini"
    gemini_dir.mkdir(parents=True)
    gemini_settings = gemini_dir / "settings.json"
    gemini_settings.write_text(
        json.dumps({
            "mcpServers": {
                "my-server": {"command": "my-server"},
                "omg-control": {"command": "python3"},
            },
            "otherKey": "preserved",
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    # Kimi: omg-control + user server
    kimi_dir = home_dir / ".kimi"
    kimi_dir.mkdir(parents=True)
    kimi_mcp = kimi_dir / "mcp.json"
    kimi_mcp.write_text(
        json.dumps({
            "mcpServers": {
                "other-server": {"command": "other"},
                "omg-control": {"command": "python3"},
            },
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    # OpenCode: omg-control + user MCP
    opencode_dir = home_dir / ".config" / "opencode"
    opencode_dir.mkdir(parents=True)
    opencode_cfg = opencode_dir / "opencode.json"
    opencode_cfg.write_text(
        json.dumps({
            "mcp": {
                "my-mcp": {"command": "my-mcp"},
                "omg-control": {"command": "python3"},
            },
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    # Claude settings.json with omg-runtime hook + non-OMG hook + statusLine
    settings: dict[str, object] = {
        "hooks": {
            "PreToolUse": [
                {"command": str(claude_dir / "omg-runtime" / "bin" / "omg-hook.py"), "type": "command"},
                {"command": "/usr/local/bin/my-linter", "type": "command"},
            ]
        },
        "statusLine": {"command": str(claude_dir / "hud" / "omg-hud.mjs")},
        "theme": "dark",
    }
    (claude_dir / "settings.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    env = {
        "CLAUDE_CONFIG_DIR": str(claude_dir),
        "HOME": str(home_dir),
    }
    proc = _run_script(
        SETUP,
        ["uninstall", "--verify-clean", "--repair", "--non-interactive"],
        env=env,
    )
    assert proc.returncode == 0, f"exit {proc.returncode}\n{proc.stdout}\n{proc.stderr}"

    # Codex: omg-control removed, my-tool preserved
    codex_content = codex_toml.read_text(encoding="utf-8")
    assert "[mcp_servers.omg-control]" not in codex_content, "omg-control must be removed from Codex"
    assert "[mcp_servers.my-tool]" in codex_content, "my-tool must be preserved in Codex"

    # Gemini: omg-control removed, my-server + otherKey preserved
    gemini_data = cast(dict[str, object], json.loads(gemini_settings.read_text(encoding="utf-8")))
    gemini_servers = cast(dict[str, object], gemini_data.get("mcpServers") or {})
    assert "omg-control" not in gemini_servers, "omg-control must be removed from Gemini"
    assert "my-server" in gemini_servers, "my-server must be preserved in Gemini"
    assert gemini_data.get("otherKey") == "preserved", "otherKey must be preserved in Gemini"

    # Kimi: omg-control removed, other-server preserved
    kimi_data = cast(dict[str, object], json.loads(kimi_mcp.read_text(encoding="utf-8")))
    kimi_servers = cast(dict[str, object], kimi_data.get("mcpServers") or {})
    assert "omg-control" not in kimi_servers, "omg-control must be removed from Kimi"
    assert "other-server" in kimi_servers, "other-server must be preserved in Kimi"

    # OpenCode: omg-control removed, my-mcp preserved
    oc_data = cast(dict[str, object], json.loads(opencode_cfg.read_text(encoding="utf-8")))
    oc_servers = cast(dict[str, object], oc_data.get("mcp") or {})
    assert "omg-control" not in oc_servers, "omg-control must be removed from OpenCode"
    assert "my-mcp" in oc_servers, "my-mcp must be preserved in OpenCode"

    # Receipt must exist and contain repaired_surfaces
    receipt_path = claude_dir / ".omg-verify-clean-receipt.json"
    assert receipt_path.exists(), "verify-clean receipt must be written"
    receipt = cast(dict[str, object], json.loads(receipt_path.read_text(encoding="utf-8")))
    repaired = receipt.get("repaired_surfaces")
    assert isinstance(repaired, list), f"repaired_surfaces must be a list, got: {repaired}"
    assert receipt.get("verification_status") == "clean", receipt
    remaining = receipt.get("remaining_blockers")
    assert isinstance(remaining, list) and not remaining, f"remaining_blockers must be empty, got: {remaining}"


def test_setup_verify_clean_receipt_schema(tmp_path: Path):
    """Verify-clean receipt contains all required fields."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    home_dir = tmp_path / "home"
    home_dir.mkdir(parents=True)

    env = {
        "CLAUDE_CONFIG_DIR": str(claude_dir),
        "HOME": str(home_dir),
    }

    # Install then uninstall to get a clean state
    _run_script(SETUP, ["install", "--non-interactive", "--merge-policy=skip"], env=env)
    proc = _run_script(
        SETUP,
        ["uninstall", "--verify-clean", "--non-interactive"],
        env=env,
    )
    assert proc.returncode == 0

    receipt_path = claude_dir / ".omg-verify-clean-receipt.json"
    assert receipt_path.exists(), "verify-clean receipt must be written"
    receipt = cast(dict[str, object], json.loads(receipt_path.read_text(encoding="utf-8")))

    required_keys = {"audited_surfaces", "residue_found", "repaired_surfaces", "preserved_surfaces", "remaining_blockers"}
    missing = required_keys - set(receipt.keys())
    assert not missing, f"Receipt missing required keys: {missing}, got: {list(receipt.keys())}"

    # All values must be lists
    for key in required_keys:
        assert isinstance(receipt[key], list), f"receipt['{key}'] must be a list, got: {type(receipt[key])}"

    # audited_surfaces must include all canonical surfaces
    audited = cast(list[str], receipt["audited_surfaces"])
    for surface in ("claude_file_residue", "claude_hooks", "claude_status_line", "codex_mcp", "gemini_mcp", "kimi_mcp", "opencode_mcp"):
        assert surface in audited, f"'{surface}' must be in audited_surfaces, got: {audited}"

    # backward compat
    assert "verification_status" in receipt, "verification_status must be present for backward compat"


def test_setup_verify_clean_codex_structural_removal(tmp_path: Path):
    """Codex TOML cleanup uses structural section removal, preserving adjacent sections."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    home_dir = tmp_path / "home"

    codex_dir = home_dir / ".codex"
    codex_dir.mkdir(parents=True)
    codex_toml = codex_dir / "config.toml"
    # Adjacent sections with omg-control in the middle
    codex_toml.write_text(
        '[mcp_servers.before-tool]\ncommand = "before"\n\n'
        '[mcp_servers.omg-control]\ncommand = "python3"\nargs = ["-m", "runtime.omg_mcp_server"]\n\n'
        '[mcp_servers.after-tool]\ncommand = "after"\n',
        encoding="utf-8",
    )

    env = {
        "CLAUDE_CONFIG_DIR": str(claude_dir),
        "HOME": str(home_dir),
    }
    proc = _run_script(
        SETUP,
        ["uninstall", "--verify-clean", "--repair", "--non-interactive"],
        env=env,
    )
    assert proc.returncode == 0

    codex_content = codex_toml.read_text(encoding="utf-8")
    assert "[mcp_servers.omg-control]" not in codex_content, "omg-control must be structurally removed"
    assert "[mcp_servers.before-tool]" in codex_content, "before-tool must survive structural removal"
    assert "[mcp_servers.after-tool]" in codex_content, "after-tool must survive structural removal"
