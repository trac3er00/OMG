"""License compatibility checker for dependency health analysis.

Checks whether project dependencies have licenses compatible with
the project's own license using a static compatibility matrix.
No network access required.
"""

from __future__ import annotations
from typing import Any

# License categories (restrictiveness increases top to bottom)
_PERMISSIVE = frozenset({
    "MIT", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unlicense", "CC0-1.0",
})

_WEAK_COPYLEFT = frozenset({
    "Apache-2.0", "LGPL-2.1", "LGPL-3.0", "MPL-2.0",
})

_STRONG_COPYLEFT = frozenset({
    "GPL-2.0", "GPL-3.0",
})

_NETWORK_COPYLEFT = frozenset({
    "AGPL-3.0",
})

_ALL_KNOWN = _PERMISSIVE | _WEAK_COPYLEFT | _STRONG_COPYLEFT | _NETWORK_COPYLEFT


def _license_tier(license_id: str) -> int:
    """Return restrictiveness tier: 0=permissive, 1=weak, 2=strong, 3=network."""
    if license_id in _PERMISSIVE:
        return 0
    if license_id in _WEAK_COPYLEFT:
        return 1
    if license_id in _STRONG_COPYLEFT:
        return 2
    if license_id in _NETWORK_COPYLEFT:
        return 3
    return -1  # unknown


def check_license_compatibility(
    project_license: str,
    dependencies: list[dict[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    """Check license compatibility between project and its dependencies.

    Args:
        project_license: SPDX identifier for the project license (e.g. "MIT").
        dependencies: List of dicts with "name" and "license" keys.
            License may be None or "UNKNOWN".

    Returns:
        Dict with three lists:
            compatible: [{"pkg": str, "license": str}]
            incompatible: [{"pkg": str, "license": str, "reason": str}]
            unknown: [{"pkg": str}]
    """
    compatible: list[dict[str, str]] = []
    incompatible: list[dict[str, str]] = []
    unknown: list[dict[str, str]] = []

    project_tier = _license_tier(project_license)

    for dep in dependencies:
        name = dep.get("name", "")
        dep_license = dep.get("license")

        # Unknown / missing license
        if not dep_license or dep_license == "UNKNOWN":
            unknown.append({"pkg": name})
            continue

        dep_tier = _license_tier(dep_license)

        # Unrecognized license string
        if dep_tier == -1:
            unknown.append({"pkg": name})
            continue

        # AGPL dep in non-AGPL project is always incompatible
        if dep_tier == 3 and project_tier != 3:
            incompatible.append({
                "pkg": name,
                "license": dep_license,
                "reason": (
                    f"AGPL-3.0 dependency in {project_license} project: "
                    f"network copyleft requires entire project to be AGPL-3.0"
                ),
            })
            continue

        # Strong copyleft dep in permissive/weak-copyleft project
        if dep_tier == 2 and project_tier < 2:
            incompatible.append({
                "pkg": name,
                "license": dep_license,
                "reason": (
                    f"{dep_license} dependency in {project_license} project: "
                    f"copyleft contamination requires project to adopt {dep_license}"
                ),
            })
            continue

        # Everything else: permissive deps are always OK,
        # weak copyleft in permissive is OK (dynamic linking),
        # same-tier or higher-tier project can use lower-tier deps
        compatible.append({"pkg": name, "license": dep_license})

    return {
        "compatible": compatible,
        "incompatible": incompatible,
        "unknown": unknown,
    }
