from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-source-build-drift.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("check_source_build_drift", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_build_drift_report_is_clean_for_curated_modules():
    module = _load_script_module()

    report = module.build_drift_report(str(ROOT))

    assert report["status"] == "ok"
    assert report["build_only_unallowlisted"] == []
    assert report["source_only_unallowlisted"] == []
    assert "runtime/mcp_config_writers.py" in report["checked_modules"]
    assert "hooks/setup_wizard.py" in report["checked_modules"]


def test_source_build_drift_script_cli_outputs_json():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ok"
