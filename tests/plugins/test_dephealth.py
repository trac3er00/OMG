import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import URLError

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _kev_payload() -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "kev_sample.json").read_text())


def _epss_payload() -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "epss_sample.json").read_text())


class _MockHTTPResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def test_kev_listed_true_when_cve_in_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")
    from plugins.dephealth.cve_scanner import enrich_with_kev

    finding = {"id": "CVE-2023-0001", "summary": "test vuln"}
    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen") as mock:
        mock.return_value = _MockHTTPResponse(_kev_payload())
        result = enrich_with_kev(finding, str(tmp_path))

    assert result["kev_listed"] is True
    assert result["id"] == "CVE-2023-0001"


def test_kev_listed_false_when_cve_not_in_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")
    from plugins.dephealth.cve_scanner import enrich_with_kev

    finding = {"id": "CVE-2099-0000", "summary": "not in kev"}
    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen") as mock:
        mock.return_value = _MockHTTPResponse(_kev_payload())
        result = enrich_with_kev(finding, str(tmp_path))

    assert result["kev_listed"] is False


def test_kev_offline_degrades_gracefully(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")
    from plugins.dephealth.cve_scanner import enrich_with_kev

    finding = {"id": "CVE-2023-0001", "summary": "test"}
    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen", side_effect=URLError("offline")):
        result = enrich_with_kev(finding, str(tmp_path))

    assert "kev_listed" in result
    assert isinstance(result["kev_listed"], bool)


def test_kev_offline_uses_stale_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")
    from plugins.dephealth.cve_scanner import enrich_with_kev

    cache_path = tmp_path / ".omg" / "state" / "kev-cache.json"
    cache_path.parent.mkdir(parents=True)
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    cache_path.write_text(json.dumps({
        "fetched_at": stale_ts,
        "cve_ids": ["CVE-2023-0001", "CVE-2024-9999"],
    }))

    finding = {"id": "CVE-2023-0001"}
    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen", side_effect=URLError("offline")):
        result = enrich_with_kev(finding, str(tmp_path))

    assert result["kev_listed"] is True


def test_kev_cache_used_within_ttl(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")
    from plugins.dephealth.cve_scanner import enrich_with_kev

    cache_path = tmp_path / ".omg" / "state" / "kev-cache.json"
    cache_path.parent.mkdir(parents=True)
    fresh_ts = datetime.now(timezone.utc).isoformat()
    cache_path.write_text(json.dumps({
        "fetched_at": fresh_ts,
        "cve_ids": ["CVE-2023-0001"],
    }))

    finding = {"id": "CVE-2023-0001"}
    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen") as mock:
        result = enrich_with_kev(finding, str(tmp_path))

    mock.assert_not_called()
    assert result["kev_listed"] is True


def test_kev_disabled_returns_false(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "0")
    from plugins.dephealth.cve_scanner import enrich_with_kev

    finding = {"id": "CVE-2023-0001"}
    result = enrich_with_kev(finding, str(tmp_path))
    assert result["kev_listed"] is False


def test_epss_enriched_finding_has_float_score(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")
    from plugins.dephealth.cve_scanner import enrich_with_epss

    finding = {"id": "CVE-2023-0001", "summary": "test"}
    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen") as mock:
        mock.return_value = _MockHTTPResponse(_epss_payload())
        result = enrich_with_epss(finding, str(tmp_path))

    assert "epss_score" in result
    assert isinstance(result["epss_score"], float)
    assert 0.0 <= result["epss_score"] <= 1.0
    assert abs(result["epss_score"] - 0.92134) < 0.001


def test_epss_offline_degrades_gracefully(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")
    from plugins.dephealth.cve_scanner import enrich_with_epss

    finding = {"id": "CVE-2023-0001"}
    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen", side_effect=URLError("offline")):
        result = enrich_with_epss(finding, str(tmp_path))

    assert "epss_score" in result
    assert result["epss_score"] is None


def test_epss_offline_uses_stale_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")
    from plugins.dephealth.cve_scanner import enrich_with_epss

    cache_path = tmp_path / ".omg" / "state" / "epss-cache.json"
    cache_path.parent.mkdir(parents=True)
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    cache_path.write_text(json.dumps({
        "entries": {
            "CVE-2023-0001": {"epss": 0.85, "fetched_at": stale_ts},
        }
    }))

    finding = {"id": "CVE-2023-0001"}
    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen", side_effect=URLError("offline")):
        result = enrich_with_epss(finding, str(tmp_path))

    assert result["epss_score"] == 0.85


def test_epss_cache_used_within_ttl(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")
    from plugins.dephealth.cve_scanner import enrich_with_epss

    cache_path = tmp_path / ".omg" / "state" / "epss-cache.json"
    cache_path.parent.mkdir(parents=True)
    fresh_ts = datetime.now(timezone.utc).isoformat()
    cache_path.write_text(json.dumps({
        "entries": {
            "CVE-2023-0001": {"epss": 0.77, "fetched_at": fresh_ts},
        }
    }))

    finding = {"id": "CVE-2023-0001"}
    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen") as mock:
        result = enrich_with_epss(finding, str(tmp_path))

    mock.assert_not_called()
    assert result["epss_score"] == 0.77


def test_epss_disabled_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "0")
    from plugins.dephealth.cve_scanner import enrich_with_epss

    finding = {"id": "CVE-2023-0001"}
    result = enrich_with_epss(finding, str(tmp_path))
    assert result["epss_score"] is None


def test_epss_empty_cve_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")
    from plugins.dephealth.cve_scanner import enrich_with_epss

    finding = {"id": "", "summary": "no id"}
    result = enrich_with_epss(finding, str(tmp_path))
    assert result["epss_score"] is None


def test_vuln_analyzer_enriched_finding_has_kev_and_epss(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")
    from plugins.dephealth.vuln_analyzer import analyze_reachability

    # Write a Python file so reachability works
    (tmp_path / "app.py").write_text("import flask\nflask.Flask(__name__)\n")

    cve_result = {
        "package": "flask",
        "id": "CVE-2023-0001",
        "summary": "high severity vulnerability",
        "fixed_version": "2.0.1",
    }

    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen") as mock:
        mock.side_effect = [
            _MockHTTPResponse(_kev_payload()),
            _MockHTTPResponse(_epss_payload()),
        ]
        result = analyze_reachability(cve_result, str(tmp_path))

    assert "kev_listed" in result
    assert "epss_score" in result
    assert result["kev_listed"] is True
    assert isinstance(result["epss_score"], float)


def test_vuln_analyzer_offline_still_returns_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")
    from plugins.dephealth.vuln_analyzer import analyze_reachability

    cve_result = {
        "package": "flask",
        "id": "CVE-2099-0000",
        "summary": "test",
        "fixed_version": "",
    }

    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen", side_effect=URLError("offline")):
        result = analyze_reachability(cve_result, str(tmp_path))

    assert "kev_listed" in result
    assert "epss_score" in result
    assert result["kev_listed"] is False
    assert result["epss_score"] is None
