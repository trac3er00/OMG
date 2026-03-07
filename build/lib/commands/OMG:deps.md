---
description: "Scan project dependencies for CVEs, license issues, and outdated packages."
allowed-tools: Read, Bash(python*:*), Grep
argument-hint: "[cves|licenses|outdated]"
---

# /OMG:deps — Dependency Health

Scan project dependencies for CVEs, license compatibility issues, and outdated packages.

## Usage

```
/OMG:deps
/OMG:deps cves
/OMG:deps licenses
/OMG:deps outdated
```

## Sub-Commands

### `/OMG:deps` (default)

Full dependency health report combining CVE scan, license check, and outdated package detection.

Detects manifest files (package.json, requirements.txt, Cargo.toml, go.mod, Gemfile, pyproject.toml), then runs all three checks and prints a unified summary.

```python
from plugins.dephealth.manifest_detector import detect_manifests
from plugins.dephealth.cve_scanner import scan_for_cves
from plugins.dephealth.license_checker import check_license_compatibility
from plugins.dephealth.vuln_analyzer import analyze_reachability

deps = detect_manifests(".")
dep_dicts = [{"name": p.name, "version": p.version, "ecosystem": p.ecosystem} for p in deps.packages]

# CVE scan
cve_result = scan_for_cves(dep_dicts, ".")
reachability = analyze_reachability(cve_result, ".")

# License check
license_result = check_license_compatibility(dep_dicts, ".")

# Summary
print(f"Manifests:     {len(deps.manifests)} detected")
print(f"Packages:      {len(deps.packages)} total")
print(f"CVEs found:    {cve_result.get('total_vulns', 0)}")
print(f"  Critical:    {cve_result.get('by_severity', {}).get('CRITICAL', 0)}")
print(f"  High:        {cve_result.get('by_severity', {}).get('HIGH', 0)}")
print(f"Reachable:     {sum(1 for v in reachability.get('results', []) if v.get('reachability') == 'direct')}")
print(f"License issues: {license_result.get('issue_count', 0)}")
```

### `/OMG:deps cves`

CVE scan results only. Queries the OSV batch API for known vulnerabilities in project dependencies.

Results include severity classification (CRITICAL/HIGH/MODERATE/LOW) and reachability analysis showing whether vulnerable code paths are actually imported.

```python
from plugins.dephealth.manifest_detector import detect_manifests
from plugins.dephealth.cve_scanner import scan_for_cves
from plugins.dephealth.vuln_analyzer import analyze_reachability

deps = detect_manifests(".")
dep_dicts = [{"name": p.name, "version": p.version, "ecosystem": p.ecosystem} for p in deps.packages]

cve_result = scan_for_cves(dep_dicts, ".")
reachability = analyze_reachability(cve_result, ".")

print(f"Packages scanned: {len(dep_dicts)}")
print(f"Vulnerabilities:  {cve_result.get('total_vulns', 0)}")
print()

for vuln in cve_result.get("vulnerabilities", []):
    reach = next((r for r in reachability.get("results", []) if r.get("cve_id") == vuln.get("id")), {})
    reach_label = reach.get("reachability", "unknown")
    risk = reach.get("risk", "unknown")
    print(f"  [{vuln.get('severity', 'UNKNOWN')}] {vuln.get('id')}")
    print(f"    Package:      {vuln.get('package')}")
    print(f"    Fixed in:     {vuln.get('fixed_version', 'N/A')}")
    print(f"    Reachability: {reach_label}")
    print(f"    Risk:         {risk}")
    if reach.get("recommendation"):
        print(f"    Action:       {reach['recommendation']}")
    print()
```

### `/OMG:deps licenses`

License compatibility report only. Checks each dependency's license against a tiered compatibility model.

Tiers: permissive (MIT, Apache-2.0, BSD) > weak-copyleft (LGPL, MPL) > copyleft (GPL, AGPL). Flags packages with copyleft or unknown licenses.

```python
from plugins.dephealth.manifest_detector import detect_manifests
from plugins.dephealth.license_checker import check_license_compatibility

deps = detect_manifests(".")
dep_dicts = [{"name": p.name, "version": p.version, "ecosystem": p.ecosystem} for p in deps.packages]

result = check_license_compatibility(dep_dicts, ".")

print(f"Packages checked: {len(dep_dicts)}")
print(f"License issues:   {result.get('issue_count', 0)}")
print()

for pkg in result.get("packages", []):
    tier = pkg.get("tier", "unknown")
    marker = "!!" if tier in ("copyleft", "unknown") else "  "
    print(f"  {marker} {pkg.get('name')}: {pkg.get('license', 'UNKNOWN')} ({tier})")

if result.get("issues"):
    print()
    print("Issues:")
    for issue in result["issues"]:
        print(f"  - {issue}")
```

### `/OMG:deps outdated`

List packages with newer versions available. Compares locked versions against latest published versions.

```python
from plugins.dephealth.manifest_detector import detect_manifests

deps = detect_manifests(".")

print(f"Manifests: {len(deps.manifests)}")
print(f"Packages:  {len(deps.packages)}")
print()

print(f"{'Package':<40} {'Current':>12} {'Ecosystem':<12}")
print("-" * 66)
for pkg in deps.packages:
    version = pkg.version or "unpinned"
    print(f"  {pkg.name:<38} {version:>12} {pkg.ecosystem:<12}")

print()
print("Note: Outdated detection requires network access to registry APIs.")
print("Packages listed above are from detected manifests.")
```

## Feature Flag

- **Flag name**: `OMG_DEP_HEALTH_ENABLED`
- **Default**: `False` (disabled)
- **Enable**: `export OMG_DEP_HEALTH_ENABLED=1`

Or set in `settings.json`:

```json
{
  "_omg": {
    "features": {
      "DEP_HEALTH": true
    }
  }
}
```

## Output Example

```
============================================================
  OMG Dependency Health Report
============================================================

  Manifests:      3 detected
    - package.json (npm)
    - requirements.txt (pip)
    - pyproject.toml (pip)

  Packages:       87 total

  CVEs found:     4
    Critical:     1
    High:         2
    Moderate:     1
    Low:          0

  Reachable:      2 of 4 (direct import detected)

  License issues: 1
    !! node-ipc: UNKNOWN (unknown)

============================================================

  [CRITICAL] GHSA-xxxx-yyyy-zzzz
    Package:      lodash@4.17.20
    Fixed in:     4.17.21
    Reachability: direct
    Risk:         high
    Action:       Upgrade lodash to >=4.17.21

  [HIGH] GHSA-aaaa-bbbb-cccc
    Package:      requests@2.25.0
    Fixed in:     2.31.0
    Reachability: transitive
    Risk:         medium
    Action:       Upgrade requests to >=2.31.0

============================================================
```

## Supported Manifests

| Manifest | Ecosystem | Parser |
|----------|-----------|--------|
| `package.json` | npm | JSON dependencies + devDependencies |
| `requirements.txt` | pip | PEP 508 lines |
| `pyproject.toml` | pip | `[project.dependencies]` + `[tool.poetry.dependencies]` |
| `Cargo.toml` | crates.io | `[dependencies]` + `[dev-dependencies]` |
| `go.mod` | Go | `require` directives |
| `Gemfile` | RubyGems | `gem` declarations |

## Safety

- **Read-only**: All sub-commands only read manifest files and query external APIs
- **Feature-gated**: Requires `DEP_HEALTH` flag enabled
- **No mutations**: Never modifies dependency files, lock files, or project code
- **Crash-isolated**: All operations exit 0 on failure (graceful error handling)
- **Cache**: CVE scan results cached to `.omg/state/dephealth/cve-cache.json` (1-hour TTL)
- **Network**: `/deps cves` requires internet access for OSV API queries

## API

```python
from plugins.dephealth.manifest_detector import detect_manifests, DependencyList
from plugins.dephealth.cve_scanner import scan_for_cves
from plugins.dephealth.license_checker import check_license_compatibility
from plugins.dephealth.vuln_analyzer import analyze_reachability

# Detect all manifest files and parse dependencies
deps: DependencyList = detect_manifests(".")

# Convert to dicts for scanner/checker APIs
dep_dicts = [{"name": p.name, "version": p.version, "ecosystem": p.ecosystem} for p in deps.packages]

# CVE scan via OSV batch API
cve_result = scan_for_cves(dep_dicts, ".")

# Reachability analysis (import tracing)
reachability = analyze_reachability(cve_result, ".")

# License compatibility check
license_result = check_license_compatibility(dep_dicts, ".")
```
