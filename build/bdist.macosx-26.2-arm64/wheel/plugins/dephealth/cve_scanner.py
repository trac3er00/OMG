from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request


OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL_TEMPLATE = "https://api.first.org/data/v1/epss?cve={cve_id}"
CACHE_REL_PATH = Path(".omg") / "state" / "cve-cache.json"
KEV_CACHE_REL_PATH = Path(".omg") / "state" / "kev-cache.json"
EPSS_CACHE_REL_PATH = Path(".omg") / "state" / "epss-cache.json"
CACHE_TTL_HOURS = 24


def _dep_health_enabled() -> bool:
    env_val = os.environ.get("OMG_DEP_HEALTH_ENABLED", "").lower()
    if env_val in ("1", "true", "yes"):
        return True
    if env_val in ("0", "false", "no"):
        return False
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from hooks._common import get_feature_flag
        return get_feature_flag("DEP_HEALTH", default=False)
    except Exception:
        return False


def scan_for_cves(dependency_list: list[dict[str, str]], project_dir: str = ".") -> dict[str, Any]:
    if not _dep_health_enabled():
        return {"results": {}, "cached": False, "scan_ts": datetime.now(timezone.utc).isoformat()}
    
    now = datetime.now(timezone.utc)
    cache_path = Path(project_dir) / CACHE_REL_PATH
    cached_payload = _load_cache(cache_path)

    if not dependency_list:
        return {
            "results": {},
            "cached": False,
            "scan_ts": now.isoformat(),
        }

    if cached_payload and _is_cache_fresh(cached_payload.get("scan_ts")):
        return {
            "results": cached_payload.get("results", {}),
            "cached": True,
            "scan_ts": cached_payload.get("scan_ts", now.isoformat()),
        }

    try:
        osv_response = _query_osv_batch(dependency_list)
    except urllib.error.URLError:
        if cached_payload:
            return {
                "results": cached_payload.get("results", {}),
                "cached": True,
                "scan_ts": cached_payload.get("scan_ts", now.isoformat()),
            }
        return {"status": "offline", "results": {}, "cached": False}

    structured_results = _normalize_results(dependency_list, osv_response)
    scan_result = {
        "results": structured_results,
        "cached": False,
        "scan_ts": now.isoformat(),
    }
    _save_cache(cache_path, scan_result)
    return scan_result


def enrich_with_kev(finding: dict[str, Any], cache_dir: str) -> dict[str, Any]:
    result = dict(finding)
    if not _dep_health_enabled():
        result["kev_listed"] = False
        return result

    cve_id = str(finding.get("id", "")).strip()
    if not cve_id:
        result["kev_listed"] = False
        return result

    cache_path = Path(cache_dir) / KEV_CACHE_REL_PATH
    cached = _load_cache(cache_path)

    if cached and _is_cache_fresh(cached.get("fetched_at")):
        result["kev_listed"] = cve_id in cached.get("cve_ids", [])
        return result

    try:
        kev_data = _fetch_kev_catalog()
        kev_ids = [v.get("cveID", "") for v in kev_data.get("vulnerabilities", [])]
        _save_cache(cache_path, {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "cve_ids": kev_ids,
        })
        result["kev_listed"] = cve_id in kev_ids
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        if cached:
            result["kev_listed"] = cve_id in cached.get("cve_ids", [])
        else:
            result["kev_listed"] = False
    return result


def enrich_with_epss(finding: dict[str, Any], cache_dir: str) -> dict[str, Any]:
    result = dict(finding)
    if not _dep_health_enabled():
        result["epss_score"] = None
        return result

    cve_id = str(finding.get("id", "")).strip()
    if not cve_id:
        result["epss_score"] = None
        return result

    cache_path = Path(cache_dir) / EPSS_CACHE_REL_PATH
    cached = _load_cache(cache_path) or {}
    entries = cached.get("entries", {})

    entry = entries.get(cve_id)
    if entry and _is_cache_fresh(entry.get("fetched_at")):
        result["epss_score"] = entry.get("epss")
        return result

    try:
        epss_data = _fetch_epss_score(cve_id)
        data_list = epss_data.get("data", [])
        score = float(data_list[0].get("epss", 0)) if data_list else None
        entries[cve_id] = {
            "epss": score,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_cache(cache_path, {"entries": entries})
        result["epss_score"] = score
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError, TypeError):
        if entry:
            result["epss_score"] = entry.get("epss")
        else:
            result["epss_score"] = None
    return result


def _fetch_kev_catalog() -> dict[str, Any]:
    request = urllib.request.Request(KEV_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def _fetch_epss_score(cve_id: str) -> dict[str, Any]:
    url = EPSS_URL_TEMPLATE.format(cve_id=cve_id)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def _query_osv_batch(dependency_list: list[dict[str, str]]) -> dict[str, Any]:
    payload = {
        "queries": [
            {
                "package": {
                    "name": dependency["name"],
                    "ecosystem": dependency["ecosystem"],
                },
                "version": dependency["version"],
            }
            for dependency in dependency_list
        ]
    }

    request = urllib.request.Request(
        OSV_BATCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def _normalize_results(
    dependency_list: list[dict[str, str]], osv_response: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    response_results = osv_response.get("results", [])

    for index, dependency in enumerate(dependency_list):
        pkg_name = dependency.get("name", "")
        query_result = response_results[index] if index < len(response_results) else {}
        vulns = query_result.get("vulns", [])

        normalized_vulns: list[dict[str, Any]] = []
        for vuln in vulns:
            affected_versions, fixed_version = _extract_affected(vuln)
            normalized_vulns.append(
                {
                    "id": vuln.get("id", ""),
                    "severity": _extract_severity(vuln),
                    "summary": vuln.get("summary", ""),
                    "affected_versions": affected_versions,
                    "fixed_version": fixed_version,
                }
            )

        output[pkg_name] = normalized_vulns

    return output


def _extract_severity(vuln: dict[str, Any]) -> str:
    severities = vuln.get("severity") or []
    if severities and isinstance(severities[0], dict):
        score = severities[0].get("score")
        if score:
            return str(score)
    return "UNKNOWN"


def _extract_affected(vuln: dict[str, Any]) -> tuple[list[str], str]:
    affected_versions: list[str] = []
    fixed_version = ""

    for affected in vuln.get("affected", []) or []:
        for version in affected.get("versions", []) or []:
            affected_versions.append(str(version))

        for version_range in affected.get("ranges", []) or []:
            for event in version_range.get("events", []) or []:
                introduced = event.get("introduced")
                fixed = event.get("fixed")
                if introduced:
                    affected_versions.append(str(introduced))
                if fixed and not fixed_version:
                    fixed_version = str(fixed)

    deduped_versions = list(dict.fromkeys(affected_versions))
    return deduped_versions, fixed_version


def _load_cache(cache_path: Path) -> dict[str, Any] | None:
    if not cache_path.exists():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_cache(cache_path: Path, payload: dict[str, Any]) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    except OSError:
        return


def _is_cache_fresh(scan_ts: str | None) -> bool:
    if not scan_ts:
        return False
    try:
        scanned_at = datetime.fromisoformat(scan_ts)
    except ValueError:
        return False

    if scanned_at.tzinfo is None:
        scanned_at = scanned_at.replace(tzinfo=timezone.utc)

    return datetime.now(timezone.utc) - scanned_at < timedelta(hours=CACHE_TTL_HOURS)
