from __future__ import annotations
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from runtime.adoption import CANONICAL_VERSION, PRESET_FEATURES
from runtime.canonical_taxonomy import (
    RELEASE_CHANNELS,
    CANONICAL_PRESETS,
    SUBSCRIPTION_TIERS,
    POLICY_PACK_IDS,
)
from runtime.canonical_surface import get_canonical_hosts, get_compat_hosts

GENERATED_ARTIFACTS: tuple[str, ...] = (
    "support-matrix.json",
    "preset-matrix.json",
    "host-tiers.json",
    "install-verification.json",
    "channel-guarantees.json",
    "SUPPORT-MATRIX.md",
    "PRESET-REFERENCE.md",
    "INSTALL-VERIFICATION-INDEX.md",
    "QUICK-REFERENCE.md",
)

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
            {"name": "doctor", "command": "omg doctor"},
            {"name": "validate", "command": "omg validate"},
        ],
        "cache_paths": [
            ".omg/cache",
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
    
    # 7. INSTALL-VERIFICATION-INDEX.md
    install_md = [
        "<!-- GENERATED: DO NOT EDIT MANUALLY -->",
        "# OMG Install Process Verification Index",
        "",
        "**Purpose:** Track all CLI adapter integration points, installation flows, and critical assumptions for end-to-end verification.",
        "",
        f"**Version:** OMG {CANONICAL_VERSION}",
        "",
        "---",
        "",
        "## 📖 Documentation Map",
        "",
        "### Primary References",
        "- **`CLI-ADAPTER-MAP.md`**",
        "- **`QUICK-REFERENCE.md`**",
        "",
        "### Source Files Referenced",
        "- `runtime/mcp_config_writers.py`",
        "- `runtime/adoption.py`",
        "- `OMG-setup.sh`",
        "",
        "---",
        "",
        "## 🎯 Installation Targets & Methods",
        "",
        "### Canonical Targets",
    ]
    
    target_configs = {
        "claude": ".mcp.json",
        "codex": "~/.codex/config.toml",
        "gemini": "~/.gemini/settings.json",
        "kimi": "~/.kimi/mcp.json",
    }
    
    for i, host in enumerate(canonical_hosts, 1):
        config_path = target_configs.get(host, "Unknown")
        install_md.extend([
            f"{i}. **{host.capitalize()}**",
            f"   - **Config:** `{config_path}`",
            "",
        ])
    
    install_md.extend([
        "---",
        "",
        "## 🔧 Verification Commands",
        "",
        "| Name | Command |",
        "| :--- | :--- |",
    ])
    verification_cmds = cast(list[dict[str, str]], install_verification["verification_commands"])
    for cmd in verification_cmds:
        name = cmd.get("name", "")
        command = cmd.get("command", "")
        install_md.append(f"| {name} | `{command}` |")
        
    install_md.extend([
        "",
        "## 📂 Cache Paths",
        "",
    ])
    for path in install_verification["cache_paths"]:
        install_md.append(f"- `{path}`")
        
    _write_text(output_root / "INSTALL-VERIFICATION-INDEX.md", "\n".join(install_md) + "\n")
    
    # 8. QUICK-REFERENCE.md
    quick_md = [
        "<!-- GENERATED: DO NOT EDIT MANUALLY -->",
        "# OMG CLI Adapter Quick Reference",
        "",
        "## 🎯 Core Integration Points",
        "",
        "### Canonical Hosts",
        "",
        "| Host | Config File |",
        "| :--- | :--- |",
    ]
    for host in canonical_hosts:
        config_path = target_configs.get(host, "Unknown")
        quick_md.append(f"| {host} | `{config_path}` |")
        
    quick_md.extend([
        "",
        "### Release Channels",
        "",
    ])
    for channel in RELEASE_CHANNELS:
        quick_md.append(f"- `{channel}`")
        
    quick_md.extend([
        "",
        "### Preset Quick Reference",
        "",
        "| Preset | Key Features |",
        "| :--- | :--- |",
    ])
    for preset in CANONICAL_PRESETS:
        features = [f for f, enabled in PRESET_FEATURES[preset].items() if enabled]
        feature_summary = ", ".join(features[:5]) + ("..." if len(features) > 5 else "")
        quick_md.append(f"| {preset} | {feature_summary or 'None'} |")
        
    quick_md.extend([
        "",
        "### Quick Commands",
        "",
        "| Task | Command |",
        "| :--- | :--- |",
        "| Install | `omg install --plan` |",
        "| Diagnostics | `omg doctor` |",
        "| Ship | `omg ship` |",
        "| Sign policy pack | `omg policy-pack sign <pack_id> --key-path <key>` |",
        "| Verify policy packs | `omg policy-pack verify --all` |",
        "| Generate signing key | `omg policy-pack keygen --output <path>` |",
    ])
    
    _write_text(output_root / "QUICK-REFERENCE.md", "\n".join(quick_md) + "\n")
    
    # 9. channel-guarantees.json
    channel_guarantees = {
        "generated_by": "omg docs generate",
        "version": CANONICAL_VERSION,
        "generated_at": timestamp,
        "channels": {
            "public": "Standard production channel. Guarantees behavior parity across canonical hosts and standard evidence-backed verification.",
            "enterprise": "Hardened production channel. Guarantees enhanced evidence (lineage, provenance), tier-gated policy enforcement, and compatibility with specialized policy packs (fintech, airgapped).",
        },
        "precedence_rule": "subscription tier → channel → policy pack → preset",
        "policy_pack_ids": list(POLICY_PACK_IDS),
    }
    _write_json(output_root / "channel-guarantees.json", channel_guarantees)
    
    return {
        "status": "ok",
        "output_root": str(output_root),
        "artifacts": list(GENERATED_ARTIFACTS),
    }


def check_docs(on_disk_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        result = generate_docs(tmp_path)
        if result["status"] != "ok":
            return {"status": "error", "drift": []}

        drift: list[str] = []
        for name in GENERATED_ARTIFACTS:
            target = on_disk_root / name
            if not target.exists():
                drift.append(f"Missing: {name}")
                continue
            if name.endswith(".json"):
                try:
                    gen_data = json.loads((tmp_path / name).read_text(encoding="utf-8"))
                    disk_data = json.loads(target.read_text(encoding="utf-8"))
                    gen_data.pop("generated_at", None)
                    disk_data.pop("generated_at", None)
                    if gen_data != disk_data:
                        drift.append(f"Drift: {name}")
                except (json.JSONDecodeError, ValueError):
                    drift.append(f"Drift: {name}")
            else:
                if (tmp_path / name).read_text(encoding="utf-8") != target.read_text(encoding="utf-8"):
                    drift.append(f"Drift: {name}")

        return {"status": "drift" if drift else "ok", "drift": drift}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    _ = path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

def _write_text(path: Path, content: str) -> None:
    _ = path.write_text(content, encoding="utf-8")
