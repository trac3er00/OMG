from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.adoption import CANONICAL_VERSION, PRESET_FEATURES
from runtime.canonical_taxonomy import (
    RELEASE_CHANNELS,
    CANONICAL_PRESETS,
    SUBSCRIPTION_TIERS,
    POLICY_PACK_IDS,
)
from runtime.canonical_surface import get_canonical_hosts, get_compat_hosts

def generate_docs(output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    
    canonical_hosts = list(get_canonical_hosts())
    compat_hosts = list(get_compat_hosts())
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # 1. support-matrix.json
    support_matrix = {
        "generated_by": "omg docs generate",
        "version": CANONICAL_VERSION,
        "generated_at": timestamp,
        "canonical_hosts": canonical_hosts,
        "compatibility_hosts": compat_hosts,
        "channels": list(RELEASE_CHANNELS),
        "presets": list(CANONICAL_PRESETS),
        "subscription_tiers": list(SUBSCRIPTION_TIERS),
        "policy_packs": list(POLICY_PACK_IDS),
    }
    _write_json(output_root / "support-matrix.json", support_matrix)
    
    # 2. preset-matrix.json
    preset_matrix = {
        "generated_by": "omg docs generate",
        "version": CANONICAL_VERSION,
        "generated_at": timestamp,
        "presets": PRESET_FEATURES,
    }
    _write_json(output_root / "preset-matrix.json", preset_matrix)
    
    # 3. host-tiers.json
    host_tiers = {
        "generated_by": "omg docs generate",
        "version": CANONICAL_VERSION,
        "generated_at": timestamp,
        "tiers": {
            "canonical": canonical_hosts,
            "compatibility": compat_hosts,
        }
    }
    _write_json(output_root / "host-tiers.json", host_tiers)
    
    # 4. install-verification.json
    install_verification = {
        "generated_by": "omg docs generate",
        "version": CANONICAL_VERSION,
        "generated_at": timestamp,
        "verification_commands": [
            {"name": "doctor", "command": "python3 scripts/omg.py doctor"},
            {"name": "validate", "command": "python3 scripts/omg.py validate"},
        ],
        "cache_paths": [
            ".omg/cache",
            ".sisyphus/tmp",
        ]
    }
    _write_json(output_root / "install-verification.json", install_verification)
    
    # 5. SUPPORT-MATRIX.md
    support_md = [
        "<!-- GENERATED: DO NOT EDIT MANUALLY -->",
        "# OMG Support Matrix",
        "",
        "## Canonical Hosts",
        "",
        "| Host | Tier |",
        "| :--- | :--- |",
    ]
    for host in canonical_hosts:
        support_md.append(f"| {host} | Canonical |")
    
    support_md.extend([
        "",
        "## Compatibility Hosts",
        "",
        "| Host | Tier |",
        "| :--- | :--- |",
    ])
    for host in compat_hosts:
        support_md.append(f"| {host} | Compatibility |")
    
    _write_text(output_root / "SUPPORT-MATRIX.md", "\n".join(support_md) + "\n")
    
    # 6. PRESET-REFERENCE.md
    preset_md = [
        "<!-- GENERATED: DO NOT EDIT MANUALLY -->",
        "# OMG Preset Reference",
        "",
    ]
    
    # Get all unique flags
    all_flags = sorted(next(iter(PRESET_FEATURES.values())).keys())
    
    header = "| Feature | " + " | ".join(CANONICAL_PRESETS) + " |"
    separator = "| :--- | " + " | ".join([":---:"] * len(CANONICAL_PRESETS)) + " |"
    preset_md.append(header)
    preset_md.append(separator)
    
    for flag in all_flags:
        row = f"| {flag} | "
        row += " | ".join(["✅" if PRESET_FEATURES[p].get(flag) else "❌" for p in CANONICAL_PRESETS])
        row += " |"
        preset_md.append(row)
    
    _write_text(output_root / "PRESET-REFERENCE.md", "\n".join(preset_md) + "\n")
    
    return {
        "status": "ok",
        "output_root": str(output_root),
        "artifacts": [
            "support-matrix.json",
            "preset-matrix.json",
            "host-tiers.json",
            "install-verification.json",
            "SUPPORT-MATRIX.md",
            "PRESET-REFERENCE.md",
        ]
    }

def _write_json(path: Path, data: dict[str, Any]) -> None:
    _ = path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

def _write_text(path: Path, content: str) -> None:
    _ = path.write_text(content, encoding="utf-8")
