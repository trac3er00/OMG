"""Domain Pack Framework for OMG.

Combines high-risk vertical contracts with project-specific pack
discovery, loading, and scaffold generation.

Format: packs/domains/{name}/ with pack.yaml, scaffold/, rules/, prompts/
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

try:
    import yaml as _yaml
except ImportError:
    _yaml = None  # type: ignore[assignment]

from runtime.canonical_surface import DOMAIN_DEFAULTS


DOMAIN_PACKS: dict[str, dict[str, Any]] = {
    "robotics": {
        "name": "robotics",
        "required_approvals": ["actuation-approval"],
        "required_evidence": ["simulator-replay", "kill-switch-check"],
        "policy_modules": ["safe-actuation", "simulator-gate"],
        "eval_hooks": ["robotics-sim"],
        "replay_hooks": ["incident-replay"],
    },
    "vision": {
        "name": "vision",
        "required_approvals": [],
        "required_evidence": ["dataset-provenance", "drift-check", "vision-artifacts"],
        "policy_modules": ["dataset-lineage", "drift-gate"],
        "eval_hooks": ["vision-regression"],
        "replay_hooks": ["incident-replay"],
    },
    "algorithms": {
        "name": "algorithms",
        "required_approvals": [],
        "required_evidence": ["benchmark-harness", "determinism-check"],
        "policy_modules": ["benchmark-gate", "determinism-gate"],
        "eval_hooks": ["algorithm-benchmarks"],
        "replay_hooks": ["incident-replay"],
    },
    "health": {
        "name": "health",
        "required_approvals": ["human-review"],
        "required_evidence": ["audit-trail", "restricted-tools", "provenance"],
        "policy_modules": ["human-review", "privacy-gate"],
        "eval_hooks": ["health-safety"],
        "replay_hooks": ["incident-replay"],
    },
    "cybersecurity": {
        "name": "cybersecurity",
        "required_approvals": [],
        "required_evidence": ["security-scan", "threat-model", "sarif-report"],
        "policy_modules": ["security-gate", "threat-gate"],
        "eval_hooks": ["security-regression"],
        "replay_hooks": ["incident-replay"],
    },
}

if set(DOMAIN_PACKS) != set(DOMAIN_DEFAULTS["all_domain_packs"]):
    raise ValueError("domain pack definitions drifted from canonical defaults")


def get_domain_pack_contract(name: str) -> dict[str, Any]:
    if name not in DOMAIN_PACKS:
        raise KeyError(name)
    return dict(DOMAIN_PACKS[name])


def get_required_approvals(name: str) -> list[str]:
    contract = get_domain_pack_contract(name)
    raw = contract.get("required_approvals")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def get_required_evidence(name: str) -> list[str]:
    contract = get_domain_pack_contract(name)
    raw = contract.get("required_evidence")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


_DEFAULT_PACKS_DIR = Path(__file__).parent.parent / "packs" / "domains"


def _load_pack_yaml(pack_dir: Path) -> dict[str, Any]:
    pack_yaml = pack_dir / "pack.yaml"
    if not pack_yaml.exists():
        return {}
    if _yaml is None:
        return {"name": pack_dir.name}
    try:
        return _yaml.safe_load(pack_yaml.read_text()) or {}
    except Exception:
        return {}


def list_packs(packs_dir: Path | str | None = None) -> list[dict[str, Any]]:
    base = Path(packs_dir) if packs_dir else _DEFAULT_PACKS_DIR
    if not base.exists():
        return []
    packs = []
    for pack_dir in sorted(base.iterdir()):
        if not pack_dir.is_dir():
            continue
        info = _load_pack_yaml(pack_dir)
        packs.append(
            {
                "name": info.get("name", pack_dir.name),
                "description": info.get("description", ""),
                "category": info.get("category", "general"),
                "path": str(pack_dir),
            }
        )
    return packs


def scaffold_project(
    pack_name: str,
    target_dir: str | Path,
    packs_dir: Path | str | None = None,
) -> dict[str, Any]:
    base = Path(packs_dir) if packs_dir else _DEFAULT_PACKS_DIR
    pack_dir = base / pack_name

    if not pack_dir.exists():
        return {"success": False, "error": f"Pack '{pack_name}' not found", "files": []}

    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    copied_files: list[str] = []

    scaffold_dir = pack_dir / "scaffold"
    if scaffold_dir.exists():
        for src_file in scaffold_dir.rglob("*"):
            if src_file.is_file():
                rel = src_file.relative_to(scaffold_dir)
                dest = target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dest)
                copied_files.append(str(rel))

    rules_dir = target / ".omg" / "knowledge" / "rules"
    rules_source = pack_dir / "rules"
    installed_rules: list[str] = []
    if rules_source.exists():
        rules_dir.mkdir(parents=True, exist_ok=True)
        for rule_file in rules_source.glob("*.md"):
            dest = rules_dir / rule_file.name
            shutil.copy2(rule_file, dest)
            installed_rules.append(rule_file.name)

    return {
        "success": True,
        "pack": pack_name,
        "target": str(target),
        "files": copied_files,
        "rules": installed_rules,
    }
