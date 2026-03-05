import importlib.util
import os
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODULE_PATH = Path(PROJECT_ROOT) / "plugins" / "dephealth" / "vuln_analyzer.py"
SPEC = importlib.util.spec_from_file_location("vuln_analyzer", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Cannot load module from {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
analyze_reachability: Callable[[dict[str, Any], str], dict[str, Any]] = MODULE.analyze_reachability


def _write_files(root: Path, files: dict[str, str]) -> None:
    for rel_path, content in files.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(content, encoding="utf-8")


def _base_cve(summary: str = "high severity vulnerability") -> dict[str, Any]:
    return {
        "package": "requests",
        "id": "CVE-2026-1111",
        "summary": summary,
        "affected_versions": ["<2.32.0"],
        "fixed_version": "2.32.0",
    }


def test_imported_package_reachable(tmp_path: Path) -> None:
    _write_files(
        tmp_path,
        {
            "app.py": "import requests\nrequests.get('https://example.com')\n",
        },
    )

    result = analyze_reachability(_base_cve(), str(tmp_path))

    assert result["reachability"] == "REACHABLE"
    assert result["import_locations"] == ["app.py"]


def test_unimported_package_unreachable(tmp_path: Path) -> None:
    _write_files(tmp_path, {"app.py": "print('hello')\n"})

    result = analyze_reachability(_base_cve(), str(tmp_path))

    assert result["reachability"] == "UNREACHABLE"
    assert result["risk_level"] == "LOW"
    assert result["recommendation"] == "No action needed (unreachable)"


def test_imported_no_calls_potentially_reachable(tmp_path: Path) -> None:
    _write_files(tmp_path, {"worker.py": "import requests\nSESSION = requests\n"})

    result = analyze_reachability(_base_cve(), str(tmp_path))

    assert result["reachability"] == "POTENTIALLY_REACHABLE"
    assert result["risk_level"] == "MEDIUM"
    assert result["import_locations"] == ["worker.py"]


def test_risk_level_critical_for_reachable(tmp_path: Path) -> None:
    _write_files(tmp_path, {"service.py": "import requests\nrequests.post('https://example.com')\n"})

    result = analyze_reachability(_base_cve(summary="critical remote code execution"), str(tmp_path))

    assert result["reachability"] == "REACHABLE"
    assert result["risk_level"] == "CRITICAL"


def test_recommendation_includes_fix_version(tmp_path: Path) -> None:
    _write_files(tmp_path, {"client.py": "import requests\nrequests.get('https://example.com')\n"})

    result = analyze_reachability(_base_cve(), str(tmp_path))

    assert "2.32.0" in result["recommendation"]
    assert result["recommendation"] == "Upgrade requests to 2.32.0"


def test_empty_project_dir_no_crash(tmp_path: Path) -> None:
    result = analyze_reachability(_base_cve(), str(tmp_path))

    assert result["package"] == "requests"
    assert result["cve_id"] == "CVE-2026-1111"
    assert result["reachability"] == "UNREACHABLE"
    assert result["import_locations"] == []
    assert result["risk_level"] == "LOW"
    assert result["recommendation"] == "No action needed (unreachable)"
