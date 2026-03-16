from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN_OMG = ROOT / "bin" / "omg"
PKG_JSON = ROOT / "package.json"


class TestLauncherFileStructure:
    def test_bin_omg_exists(self):
        assert BIN_OMG.exists(), f"bin/omg not found at {BIN_OMG}"

    def test_shebang_line(self):
        first_line = BIN_OMG.read_text().splitlines()[0]
        assert first_line == "#!/usr/bin/env node"

    def test_file_is_executable(self):
        assert os.access(BIN_OMG, os.X_OK), "bin/omg must be executable"


class TestPackageJson:
    @pytest.fixture(autouse=True)
    def _load_pkg(self):
        self.pkg = json.loads(PKG_JSON.read_text())

    def test_bin_omg_field(self):
        assert self.pkg.get("bin", {}).get("omg") == "bin/omg"

    def test_files_array_contains_bin(self):
        assert "bin/" in self.pkg.get("files", [])

    def test_files_array_contains_scripts(self):
        assert "scripts/" in self.pkg.get("files", [])

    def test_engines_node(self):
        assert self.pkg.get("engines", {}).get("node") == ">=18.0.0"


class TestLauncherExecution:
    def test_version_exits_zero(self):
        r = subprocess.run(
            ["node", str(BIN_OMG), "--version"],
            capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0, f"exit {r.returncode}: {r.stderr}"

    def test_version_prints_string(self):
        r = subprocess.run(
            ["node", str(BIN_OMG), "--version"],
            capture_output=True, text=True, timeout=30,
        )
        output = (r.stdout + r.stderr).strip()
        assert output and any(c.isdigit() for c in output)

    def test_help_exits_zero(self):
        r = subprocess.run(
            ["node", str(BIN_OMG), "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0, f"exit {r.returncode}: {r.stderr}"


class TestPythonNotFound:
    def test_emits_clear_error_when_python_missing(self):
        node_bin = subprocess.run(
            ["which", "node"], capture_output=True, text=True,
        ).stdout.strip()

        with tempfile.TemporaryDirectory() as isolated:
            os.symlink(node_bin, os.path.join(isolated, "node"))
            env = os.environ.copy()
            env["PATH"] = isolated

            r = subprocess.run(
                ["node", str(BIN_OMG), "--help"],
                capture_output=True, text=True, timeout=30,
                env=env,
            )
            assert r.returncode != 0
            assert "python" in (r.stdout + r.stderr).lower()
