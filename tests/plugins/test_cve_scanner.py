import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import URLError
from unittest.mock import patch
import importlib


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_cve_scanner = importlib.import_module("plugins.dephealth.cve_scanner")
scan_for_cves = _cve_scanner.scan_for_cves


class _MockHTTPResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def _deps() -> list[dict[str, str]]:
    return [
        {"name": "flask", "version": "2.0.0", "ecosystem": "PyPI"},
        {"name": "requests", "version": "2.19.0", "ecosystem": "PyPI"},
    ]


def _osv_payload() -> dict[str, Any]:
    return {
        "results": [
            {
                "vulns": [
                    {
                        "id": "CVE-2023-0001",
                        "summary": "Sample vulnerability",
                        "affected": [
                            {
                                "ranges": [
                                    {
                                        "events": [
                                            {"introduced": "0"},
                                            {"fixed": "2.0.1"},
                                        ]
                                    }
                                ]
                            }
                        ],
                        "severity": [{"type": "CVSS_V3", "score": "HIGH"}],
                    }
                ]
            },
            {"vulns": []},
        ]
    }


def _cache_path(project_dir) -> str:
    return str(project_dir / ".omg" / "state" / "cve-cache.json")


def test_batch_query_format(tmp_path):
    deps = _deps()

    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _MockHTTPResponse(_osv_payload())

        scan_for_cves(deps, project_dir=str(tmp_path))

        request_obj = mock_urlopen.call_args.args[0]
        assert request_obj.full_url == "https://api.osv.dev/v1/querybatch"
        assert request_obj.get_method() == "POST"

        body = json.loads(request_obj.data.decode("utf-8"))
        assert "queries" in body
        assert len(body["queries"]) == 2
        assert body["queries"][0] == {
            "package": {"name": "flask", "ecosystem": "PyPI"},
            "version": "2.0.0",
        }


def test_returns_structured_results(tmp_path):
    deps = _deps()

    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _MockHTTPResponse(_osv_payload())

        result = scan_for_cves(deps, project_dir=str(tmp_path))

    assert "results" in result
    assert "cached" in result
    assert "scan_ts" in result
    assert "flask" in result["results"]
    assert isinstance(result["results"]["flask"], list)
    assert result["results"]["flask"][0]["id"] == "CVE-2023-0001"
    assert result["results"]["flask"][0]["summary"] == "Sample vulnerability"
    assert "affected_versions" in result["results"]["flask"][0]
    assert "fixed_version" in result["results"]["flask"][0]


def test_cache_written_after_scan(tmp_path):
    deps = _deps()
    cache_file = _cache_path(tmp_path)

    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _MockHTTPResponse(_osv_payload())
        scan_for_cves(deps, project_dir=str(tmp_path))

    assert os.path.exists(cache_file)
    cache_payload = json.loads((tmp_path / ".omg" / "state" / "cve-cache.json").read_text())
    assert "scan_ts" in cache_payload
    assert "results" in cache_payload


def test_cache_used_within_ttl(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    cached_data = {"results": {"flask": []}, "cached": False, "scan_ts": now}
    cache_file = tmp_path / ".omg" / "state" / "cve-cache.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text(json.dumps(cached_data))

    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen") as mock_urlopen:
        result = scan_for_cves(_deps(), project_dir=str(tmp_path))

    mock_urlopen.assert_not_called()
    assert result["cached"] is True
    assert result["results"] == {"flask": []}


def test_cache_expired_triggers_rescan(tmp_path):
    expired = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    cache_file = tmp_path / ".omg" / "state" / "cve-cache.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text(json.dumps({"results": {"old": []}, "scan_ts": expired}))

    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _MockHTTPResponse(_osv_payload())
        result = scan_for_cves(_deps(), project_dir=str(tmp_path))

    mock_urlopen.assert_called_once()
    assert result["cached"] is False
    assert "flask" in result["results"]


def test_offline_fallback_returns_cached(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    cache_file = tmp_path / ".omg" / "state" / "cve-cache.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text(json.dumps({"results": {"flask": [{"id": "CVE-1"}]}, "scan_ts": now}))

    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen", side_effect=URLError("offline")):
        result = scan_for_cves(_deps(), project_dir=str(tmp_path))

    assert result["cached"] is True
    assert result["results"] == {"flask": [{"id": "CVE-1"}]}


def test_offline_no_cache_returns_status(tmp_path):
    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen", side_effect=URLError("offline")):
        result = scan_for_cves(_deps(), project_dir=str(tmp_path))

    assert result == {"status": "offline", "results": {}, "cached": False}


def test_empty_dependency_list(tmp_path):
    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen") as mock_urlopen:
        result = scan_for_cves([], project_dir=str(tmp_path))

    mock_urlopen.assert_not_called()
    assert result["results"] == {}
    assert result["cached"] is False
    assert "scan_ts" in result
