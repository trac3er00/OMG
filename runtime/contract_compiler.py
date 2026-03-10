"""Canonical OMG contract registry, compiler, and release-readiness checks."""
from __future__ import annotations

import hashlib
import asyncio
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable
from urllib.parse import urlparse
import zipfile

import yaml

from runtime.asset_loader import resolve_asset, resolve_assets
from runtime.proof_chain import _normalize_evidence_pack
from runtime.evidence_requirements import requirements_for_profile
from runtime.runtime_contracts import schema_versions
from runtime.adoption import (
    CANONICAL_MARKETPLACE_ID,
    CANONICAL_PACKAGE_NAME,
    CANONICAL_PLUGIN_ID,
    CANONICAL_REPO_URL,
    CANONICAL_VERSION,
)


CONTRACT_DOC_PATH = Path("OMG_COMPAT_CONTRACT.md")
SCHEMA_PATH = Path("registry") / "omg-capability.schema.json"
BUNDLES_DIR = Path("registry") / "bundles"
SUPPORTED_HOSTS = ("claude", "codex", "gemini", "kimi")
SUPPORTED_CHANNELS = ("public", "enterprise")
DEFAULT_REQUIRED_BUNDLES = (
    "control-plane",
    "plan-council",
    "claim-judge",
    "test-intent-lock",
    "proof-gate",
    "hook-governor",
    "mcp-fabric",
    "lsp-pack",
    "secure-worktree-pipeline",
    "security-check",
    "api-twin",
    "preflight",
    "robotics",
    "vision",
    "algorithms",
    "health",
    "tracebank",
    "eval-gate",
    "delta-classifier",
    "incident-replay",
    "data-lineage",
    "remote-supervisor",
)
TRUTH_COUNCIL_BUNDLES = (
    "plan-council",
    "claim-judge",
    "test-intent-lock",
    "proof-gate",
)
REQUIRED_ADVANCED_PLUGIN_ARTIFACTS = (
    "bundle/plugins/advanced/plugin.json",
    "bundle/plugins/advanced/commands/OMG:deep-plan.md",
    "bundle/plugins/advanced/commands/OMG:security-review.md",
)
REQUIRED_DOC_TOKENS = (
    "execution_contract",
    "tool_policy",
    "invocation_policy",
    "host_compilation_rules",
    "local_supervisor",
)
REQUIRED_BUNDLE_FIELDS = (
    "id",
    "kind",
    "version",
    "title",
    "description",
    "hosts",
    "assets",
    "invocation_policy",
    "tool_policy",
    "lifecycle_hooks",
    "mcp_contract",
    "lsp_contract",
    "evidence_outputs",
    "execution_contract",
    "channel_overrides",
)
REQUIRED_POLICY_MODEL_FIELDS = (
    "trust_tiers",
    "tool_policies",
    "protected_paths",
    "evidence_contract",
    "host_rules",
)
REQUIRED_CLAUDE_HOOK_EVENTS = (
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "InstructionsLoaded",
)
REQUIRED_CLAUDE_SUBAGENT_NAMES = ("security-reviewer", "release-manager")
REQUIRED_CODEX_AGENTS_SECTIONS = (
    "## Build & Test",
    "## Protected Paths",
    "## Evidence Contract",
    "## Required Skills",
    "## Web Search Policy",
    "## Approval Constraints",
)
REQUIRED_CODEX_OUTPUTS = (
    "AGENTS.fragment.md",
    "codex-rules.md",
    "codex-mcp.toml",
)
HOST_COMPILED_ARTIFACTS = {
    "claude": (
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        ".mcp.json",
        "settings.json",
    ),
    "codex": (
        ".agents/skills/omg/AGENTS.fragment.md",
        ".agents/skills/omg/codex-rules.md",
        ".agents/skills/omg/codex-mcp.toml",
    ),
    "gemini": (
        ".gemini/settings.json",
    ),
    "kimi": (
        ".kimi/mcp.json",
    ),
}

_REQUIRED_EXECUTION_PRIMITIVES = (
    "release_run_coordinator_state",
    "tdd_proof_chain_lock",
    "rollback_manifest",
    "intent_gate_state",
    "profile_digest",
    "session_health_state",
    "council_verdicts",
    "forge_starter_proof",
)

_REQUIRED_CONTEXT_METADATA = (
    "context_checksum",
    "profile_version",
    "intent_gate_version",
)


def _ensure_list(
    *,
    bundle_id: str,
    path: str,
    value: Any,
    errors: list[str],
    min_items: int = 1,
) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{bundle_id}: {path} must be a list")
        return []
    if len(value) < min_items:
        errors.append(f"{bundle_id}: {path} must contain at least {min_items} item(s)")
    return value


def _ensure_dict(*, bundle_id: str, path: str, value: Any, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{bundle_id}: {path} must be an object")
        return {}
    return value


def _validate_host_rule(
    *,
    bundle_id: str,
    host_name: str,
    host_rule: Any,
    required_fields: tuple[str, ...],
    errors: list[str],
) -> None:
    path = f"policy_model.host_rules.{host_name}"
    host_payload = _ensure_dict(bundle_id=bundle_id, path=path, value=host_rule, errors=errors)
    if not host_payload:
        return
    for field in required_fields:
        if field not in host_payload:
            errors.append(f"{bundle_id}: malformed host_rules entry for {host_name}: missing '{field}'")
            continue
        _ensure_list(
            bundle_id=bundle_id,
            path=f"{path}.{field}",
            value=host_payload[field],
            errors=errors,
            min_items=1,
        )


def _validate_policy_model(
    bundle_id: str,
    policy_model: Any,
    *,
    bundle_hosts: Iterable[str] = (),
) -> list[str]:
    errors: list[str] = []
    payload = _ensure_dict(bundle_id=bundle_id, path="policy_model", value=policy_model, errors=errors)
    if not payload:
        return errors

    for field in REQUIRED_POLICY_MODEL_FIELDS:
        if field not in payload:
            errors.append(f"{bundle_id}: policy_model missing field {field}")

    tier_names: set[str] = set()
    for index, tier in enumerate(
        _ensure_list(
            bundle_id=bundle_id,
            path="policy_model.trust_tiers",
            value=payload.get("trust_tiers", []),
            errors=errors,
        )
    ):
        tier_payload = _ensure_dict(
            bundle_id=bundle_id,
            path=f"policy_model.trust_tiers[{index}]",
            value=tier,
            errors=errors,
        )
        if not tier_payload:
            continue
        for field in ("name", "level", "label", "allowed_sources"):
            if field not in tier_payload:
                errors.append(f"{bundle_id}: policy_model.trust_tiers[{index}] missing field {field}")
        if isinstance(tier_payload.get("name"), str) and tier_payload["name"].strip():
            tier_names.add(tier_payload["name"].strip())
        if "allowed_sources" in tier_payload:
            _ensure_list(
                bundle_id=bundle_id,
                path=f"policy_model.trust_tiers[{index}].allowed_sources",
                value=tier_payload.get("allowed_sources"),
                errors=errors,
                min_items=1,
            )

    for index, tool in enumerate(
        _ensure_list(
            bundle_id=bundle_id,
            path="policy_model.tool_policies",
            value=payload.get("tool_policies", []),
            errors=errors,
        )
    ):
        tool_payload = _ensure_dict(
            bundle_id=bundle_id,
            path=f"policy_model.tool_policies[{index}]",
            value=tool,
            errors=errors,
        )
        if not tool_payload:
            continue
        for field in ("tool_name", "allowed_tiers", "requires_approval"):
            if field not in tool_payload:
                errors.append(f"{bundle_id}: policy_model.tool_policies[{index}] missing field {field}")
        allowed_tiers = _ensure_list(
            bundle_id=bundle_id,
            path=f"policy_model.tool_policies[{index}].allowed_tiers",
            value=tool_payload.get("allowed_tiers", []),
            errors=errors,
            min_items=1,
        )
        if tier_names:
            unknown_tiers = sorted(
                tier_name
                for tier_name in allowed_tiers
                if isinstance(tier_name, str) and tier_name not in tier_names
            )
            if unknown_tiers:
                errors.append(
                    f"{bundle_id}: policy_model.tool_policies[{index}] references unknown tiers {unknown_tiers}"
                )

    for index, item in enumerate(
        _ensure_list(
            bundle_id=bundle_id,
            path="policy_model.protected_paths",
            value=payload.get("protected_paths", []),
            errors=errors,
        )
    ):
        path_payload = _ensure_dict(
            bundle_id=bundle_id,
            path=f"policy_model.protected_paths[{index}]",
            value=item,
            errors=errors,
        )
        if not path_payload:
            continue
        for field in ("path_pattern", "required_tier"):
            if field not in path_payload:
                errors.append(f"{bundle_id}: policy_model.protected_paths[{index}] missing field {field}")
        required_tier = path_payload.get("required_tier")
        if tier_names and isinstance(required_tier, str) and required_tier not in tier_names:
            errors.append(
                f"{bundle_id}: policy_model.protected_paths[{index}] references unknown tier '{required_tier}'"
            )

    evidence_contract = _ensure_dict(
        bundle_id=bundle_id,
        path="policy_model.evidence_contract",
        value=payload.get("evidence_contract", {}),
        errors=errors,
    )
    for field in ("timestamp", "executor", "trace_id", "lineage"):
        if field not in evidence_contract:
            errors.append(f"{bundle_id}: policy_model.evidence_contract missing field {field}")

    host_rules = _ensure_dict(
        bundle_id=bundle_id,
        path="policy_model.host_rules",
        value=payload.get("host_rules", {}),
        errors=errors,
    )
    declared_hosts = {str(host).strip() for host in bundle_hosts if str(host).strip()}

    _validate_host_rule(
        bundle_id=bundle_id,
        host_name="claude",
        host_rule=host_rules.get("claude"),
        required_fields=("compilation_targets", "hooks", "subagents", "skills"),
        errors=errors,
    )
    _validate_host_rule(
        bundle_id=bundle_id,
        host_name="codex",
        host_rule=host_rules.get("codex"),
        required_fields=("compilation_targets", "skills", "agents_fragments", "rules", "automations"),
        errors=errors,
    )
    for host_name in ("gemini", "kimi"):
        if host_name in host_rules or host_name in declared_hosts:
            _validate_host_rule(
                bundle_id=bundle_id,
                host_name=host_name,
                host_rule=host_rules.get(host_name),
                required_fields=("compilation_targets", "mcp", "skills", "automations"),
                errors=errors,
            )
    return errors


def _policy_model_for_bundle(bundles: Iterable[dict[str, Any]], bundle_id: str) -> dict[str, Any] | None:
    for bundle in bundles:
        if str(bundle.get("id", "")) == bundle_id and isinstance(bundle.get("policy_model"), dict):
            return dict(bundle["policy_model"])
    return None


def _policy_protected_paths(policy_model: dict[str, Any] | None, *, channel: str) -> list[str]:
    if not policy_model:
        return _protected_paths_for_channel(channel)
    values: list[str] = []
    for item in policy_model.get("protected_paths", []):
        if isinstance(item, dict):
            pattern = str(item.get("path_pattern", "")).strip()
            if pattern:
                values.append(pattern)
    return values or _protected_paths_for_channel(channel)


def _resolve_root(root_dir: str | Path | None) -> Path:
    if root_dir is None:
        return Path(__file__).resolve().parents[1]
    return Path(root_dir).resolve()


def _resolve_output_root(root_dir: Path, output_root: str | Path | None) -> Path:
    if output_root is None or str(output_root).strip() == "":
        return root_dir
    return Path(output_root).resolve()


def _load_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return parsed


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_contract_doc(root_dir: str | Path | None = None) -> str:
    if root_dir is not None:
        root = _resolve_root(root_dir)
        candidate = root / CONTRACT_DOC_PATH
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return resolve_asset(CONTRACT_DOC_PATH).read_text(encoding="utf-8")


def load_contract_schema(root_dir: str | Path | None = None) -> dict[str, Any]:
    if root_dir is not None:
        root = _resolve_root(root_dir)
        candidate = root / SCHEMA_PATH
        if candidate.exists():
            return _load_json(candidate)
    return _load_json(resolve_asset(SCHEMA_PATH))


def load_contract_bundles(root_dir: str | Path | None = None) -> list[dict[str, Any]]:
    root = _resolve_root(root_dir)
    bundles: list[dict[str, Any]] = []
    paths = sorted((root / BUNDLES_DIR).glob("*.yaml")) if (root / BUNDLES_DIR).exists() else resolve_assets(BUNDLES_DIR, suffix=".yaml")
    for path in paths:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected mapping bundle manifest in {path}")
        bundle = dict(parsed)
        try:
            bundle["_path"] = str(path.relative_to(root))
        except ValueError:
            bundle["_path"] = str(Path(BUNDLES_DIR) / path.name)
        bundles.append(bundle)
    return bundles


def _bundle_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": bundle.get("id", ""),
        "kind": bundle.get("kind", ""),
        "version": bundle.get("version", ""),
        "title": bundle.get("title", ""),
        "hosts": list(bundle.get("hosts", [])),
        "path": bundle.get("_path", ""),
    }


def validate_contract_registry(root_dir: str | Path | None = None) -> dict[str, Any]:
    root = _resolve_root(root_dir)
    errors: list[str] = []

    try:
        doc_text = load_contract_doc(root)
    except FileNotFoundError:
        errors.append(f"missing contract doc: {CONTRACT_DOC_PATH}")
        doc_text = ""
    else:
        for token in REQUIRED_DOC_TOKENS:
            if token not in doc_text:
                errors.append(f"contract doc missing token: {token}")
        if CANONICAL_VERSION not in doc_text:
            errors.append(f"contract doc missing version: {CANONICAL_VERSION}")

    try:
        schema_payload = load_contract_schema(root)
    except FileNotFoundError:
        errors.append(f"missing contract schema: {SCHEMA_PATH}")
        schema_payload: dict[str, Any] = {}
    else:
        if str(schema_payload.get("version", "")) != CANONICAL_VERSION:
            errors.append(f"contract schema version drift: {schema_payload.get('version')!r}")

    bundles = load_contract_bundles(root)
    if not bundles:
        errors.append(f"missing bundles directory: {BUNDLES_DIR}")

    bundle_ids = set()
    bundle_summaries: list[dict[str, Any]] = []
    for bundle in bundles:
        bundle_summaries.append(_bundle_summary(bundle))
        bundle_id = str(bundle.get("id", "")).strip()
        if not bundle_id:
            errors.append(f"bundle missing id: {bundle.get('_path', '<unknown>')}")
            continue
        if bundle_id in bundle_ids:
            errors.append(f"duplicate bundle id: {bundle_id}")
        bundle_ids.add(bundle_id)
        for field in REQUIRED_BUNDLE_FIELDS:
            if field not in bundle:
                errors.append(f"{bundle_id}: missing field {field}")
        if bundle.get("version") != CANONICAL_VERSION:
            errors.append(f"{bundle_id}: version drift {bundle.get('version')!r}")
        hosts = bundle.get("hosts", [])
        if not isinstance(hosts, list) or not hosts:
            errors.append(f"{bundle_id}: hosts must be a non-empty list")
        else:
            bad_hosts = [host for host in hosts if host not in SUPPORTED_HOSTS]
            if bad_hosts:
                errors.append(f"{bundle_id}: unsupported hosts {bad_hosts}")
        if "policy_model" in bundle:
            errors.extend(_validate_policy_model(bundle_id, bundle.get("policy_model"), bundle_hosts=hosts))

    missing_bundles = [bundle_id for bundle_id in DEFAULT_REQUIRED_BUNDLES if bundle_id not in bundle_ids]
    for bundle_id in missing_bundles:
        errors.append(f"missing required bundle: {bundle_id}")

    contract = {
        "path": str(CONTRACT_DOC_PATH),
        "schema_path": str(SCHEMA_PATH),
        "version": CANONICAL_VERSION,
        "bundle_count": len(bundle_summaries),
    }
    return {
        "schema": "OmgContractValidationResult",
        "status": "ok" if not errors else "error",
        "contract": contract,
        "bundles": bundle_summaries,
        "errors": errors,
    }


def _copy_contract_inputs(root: Path, output_root: Path) -> list[Path]:
    copied: list[Path] = []
    for rel_path in [CONTRACT_DOC_PATH, SCHEMA_PATH]:
        src = resolve_asset(rel_path)
        dst = output_root / rel_path
        _write_text(dst, src.read_text(encoding="utf-8"))
        copied.append(dst)
    for bundle in load_contract_bundles(root):
        rel_path = Path(str(bundle["_path"]))
        src = resolve_asset(rel_path)
        dst = output_root / rel_path
        _write_text(dst, src.read_text(encoding="utf-8"))
        copied.append(dst)

    # Copy advanced plugin artifacts (plugin.json + all command markdown files)
    advanced_plugin_json = Path("plugins") / "advanced" / "plugin.json"
    try:
        src = resolve_asset(advanced_plugin_json)
        dst = output_root / advanced_plugin_json
        _write_text(dst, src.read_text(encoding="utf-8"))
        copied.append(dst)
    except FileNotFoundError:
        pass

    advanced_commands = resolve_assets(Path("plugins") / "advanced" / "commands", suffix=".md")
    for src in advanced_commands:
        rel = Path("plugins") / "advanced" / "commands" / src.name
        dst = output_root / rel
        _write_text(dst, src.read_text(encoding="utf-8"))
        copied.append(dst)

    return copied


def _base_mcp_servers() -> dict[str, Any]:
    return {
        "filesystem": {
            "command": "npx",
            "args": ["@modelcontextprotocol/server-filesystem@2026.1.14", "."],
        },
        "omg-control": {
            "command": "python3",
            "args": ["-m", "runtime.omg_mcp_server"],
        },
    }


def _plugin_mcp_servers() -> dict[str, Any]:
    return {
        "omg-control": {
            "command": "python3",
            "args": ["-m", "runtime.omg_mcp_server"],
        },
    }


def _build_claude_plugin() -> dict[str, Any]:
    return {
        "name": CANONICAL_PLUGIN_ID,
        "version": CANONICAL_VERSION,
        "description": "OMG plugin layer for Claude Code with native setup, orchestration, and interop.",
        "author": {"name": "trac3er00"},
        "repository": CANONICAL_REPO_URL,
        "homepage": CANONICAL_REPO_URL,
        "license": "MIT",
        "keywords": [
            "claude-code",
            "plugin",
            "orchestration",
            "multi-agent",
            "omg",
            "codex",
            "gemini",
            "crazy-mode",
            "escalation",
        ],
        "mcpServers": "./.claude-plugin/mcp.json",
    }


def _build_claude_marketplace() -> dict[str, Any]:
    return {
        "name": CANONICAL_MARKETPLACE_ID,
        "description": "Marketplace metadata for the OMG Claude plugin",
        "owner": {"name": "trac3er00"},
        "metadata": {
            "description": "OMG - Oh-My-God for Claude Code and supported agent hosts",
            "version": CANONICAL_VERSION,
            "homepage": CANONICAL_REPO_URL,
            "repository": CANONICAL_REPO_URL,
        },
        "plugins": [
            {
                "name": CANONICAL_PLUGIN_ID,
        "description": "OMG plugin layer for Claude Code and supported agent hosts with native setup, orchestration, and interop.",
                "version": CANONICAL_VERSION,
                "source": "./",
                "author": {"name": "trac3er00"},
                "license": "MIT",
                "category": "productivity",
                "tags": [
                    "orchestration",
                    "automation",
                    "multi-agent",
                    "omg",
                    "codex",
                    "gemini",
                    "crazy-mode",
                ],
            }
        ],
        "version": CANONICAL_VERSION,
    }


def _bundle_map(bundles: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(bundle["id"]): bundle for bundle in bundles}


def _compile_hook_settings(bundle: dict[str, Any]) -> dict[str, Any]:
    events = bundle.get("compiled_hooks", {})
    if not isinstance(events, dict):
        return {}

    compiled: dict[str, Any] = {}
    for event_name, items in events.items():
        if not isinstance(items, list):
            continue
        compiled_entries: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            command = str(item.get("command", "")).strip()
            if not command:
                continue
            hook_payload: dict[str, Any] = {"type": "command", "command": command}
            timeout = item.get("timeout")
            if isinstance(timeout, int):
                hook_payload["timeout"] = timeout
            entry: dict[str, Any] = {"hooks": [hook_payload]}
            if "matcher" in item:
                entry["matcher"] = str(item.get("matcher", ""))
            compiled_entries.append(entry)
        if compiled_entries:
            compiled[str(event_name)] = compiled_entries
    return compiled


def _protected_paths_for_channel(channel: str) -> list[str]:
    paths = [".omg/**", ".agents/**", ".codex/**", ".claude/**"]
    if channel == "enterprise":
        paths.extend(["registry/**", "dist/**"])
    return paths


def _default_claude_hook_registrations() -> dict[str, list[dict[str, Any]]]:
    """Default OMG hook registrations for each required Claude event."""
    return {
        "UserPromptSubmit": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": 'python3 "$HOME/.claude/hooks/user-prompt-submit.py"',
                        "timeout": 10,
                    }
                ],
            }
        ],
        "PreToolUse": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": 'python3 "$HOME/.claude/hooks/firewall.py"',
                        "timeout": 10,
                    }
                ],
                "matcher": "Bash",
            },
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": 'python3 "$HOME/.claude/hooks/secret-guard.py"',
                        "timeout": 10,
                    }
                ],
                "matcher": "Read|Write|Edit|MultiEdit",
            },
        ],
        "PostToolUse": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": 'python3 "$HOME/.claude/hooks/tool-ledger.py"',
                        "timeout": 10,
                    }
                ],
                "matcher": "Write|Edit|MultiEdit",
            },
        ],
        "PostToolUseFailure": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": 'python3 "$HOME/.claude/hooks/post-tool-failure.py"',
                    }
                ],
            }
        ],
        "InstructionsLoaded": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": 'python3 "$HOME/.claude/hooks/instructions-loaded.py"',
                        "timeout": 10,
                    }
                ],
            }
        ],
    }


def _build_claude_subagents(protected_paths: list[str]) -> list[dict[str, Any]]:
    """Build narrow-tool Claude subagent definitions. No bypassPermissions allowed."""
    return [
        {
            "name": "security-reviewer",
            "description": "Read-only security review subagent with scoped tool access.",
            "tools": [
                "Read",
                "Grep",
                "Glob",
                "Bash(grep *)",
                "Bash(find *)",
                "Bash(git log *)",
                "Bash(git diff *)",
            ],
            "bypassPermissions": False,
        },
        {
            "name": "release-manager",
            "description": "Release management subagent with write access governed by protected-path policy.",
            "tools": [
                "Read",
                "Write",
                "Edit",
                "Grep",
                "Glob",
                "Bash(git *)",
                "Bash(python3 scripts/omg.py *)",
            ],
            "bypassPermissions": False,
            "protectedPaths": protected_paths,
        },
    ]


def _build_claude_skills(policy_model: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build Claude skill definitions from the policy model host_rules."""
    skill_refs: list[str] = []
    if isinstance(policy_model, dict):
        host_rules = policy_model.get("host_rules", {})
        if isinstance(host_rules, dict):
            claude_rules = host_rules.get("claude", {})
            if isinstance(claude_rules, dict):
                skill_refs = [str(s) for s in claude_rules.get("skills", []) if str(s).strip()]
    skills: list[dict[str, Any]] = []
    for ref in skill_refs:
        skills.append({"name": ref, "source": f".agents/skills/{ref}/"})
    return skills


def _validate_compiled_claude_output(output_root: Path) -> list[str]:
    """Validate compiled Claude settings.json contains required hooks and subagents."""
    settings_path = output_root / "settings.json"
    if not settings_path.exists():
        return ["claude: missing compiled settings.json"]

    settings = _load_json(settings_path)
    errors: list[str] = []

    hooks = settings.get("hooks", {})
    for event in REQUIRED_CLAUDE_HOOK_EVENTS:
        if event not in hooks or not hooks[event]:
            errors.append(f"claude: missing required hook event '{event}'")

    omg = settings.get("_omg", {})
    generated = omg.get("generated", {})
    subagents = generated.get("subagents", [])
    subagent_names = {sa.get("name") for sa in subagents if isinstance(sa, dict)}
    for name in REQUIRED_CLAUDE_SUBAGENT_NAMES:
        if name not in subagent_names:
            errors.append(f"claude: missing required subagent '{name}'")

    for sa in subagents:
        if isinstance(sa, dict) and sa.get("bypassPermissions"):
            errors.append(
                f"claude: subagent '{sa.get('name', '<unknown>')}' has bypassPermissions enabled"
            )

    return errors


def _compile_claude_outputs(
    *,
    root: Path,
    output_root: Path,
    bundles: list[dict[str, Any]],
    channel: str,
    policy_model: dict[str, Any] | None,
) -> list[Path]:
    artifacts: list[Path] = []

    _write_json(output_root / ".claude-plugin" / "plugin.json", _build_claude_plugin())
    artifacts.append(output_root / ".claude-plugin" / "plugin.json")

    _write_json(output_root / ".claude-plugin" / "marketplace.json", _build_claude_marketplace())
    artifacts.append(output_root / ".claude-plugin" / "marketplace.json")

    _write_json(output_root / ".claude-plugin" / "mcp.json", {"mcpServers": _plugin_mcp_servers()})
    artifacts.append(output_root / ".claude-plugin" / "mcp.json")

    mcp_payload = {"mcpServers": _base_mcp_servers()}
    _write_json(output_root / ".mcp.json", mcp_payload)
    artifacts.append(output_root / ".mcp.json")

    settings_path = root / "settings.json"
    if not settings_path.exists():
        settings_path = resolve_asset("settings.json")
    settings = _load_json(settings_path)
    hook_bundle = _bundle_map(bundles)["hook-governor"]
    compiled_hooks = _compile_hook_settings(hook_bundle)
    defaults = _default_claude_hook_registrations()
    for event in REQUIRED_CLAUDE_HOOK_EVENTS:
        if event not in compiled_hooks or not compiled_hooks[event]:
            compiled_hooks[event] = defaults[event]
    settings["hooks"] = compiled_hooks

    protected_paths = _policy_protected_paths(policy_model, channel=channel)
    subagents = _build_claude_subagents(protected_paths)
    skills = _build_claude_skills(policy_model)

    omg_settings = dict(settings.get("_omg", {}))
    omg_settings["_version"] = CANONICAL_VERSION
    omg_settings["generated"] = {
        "contract_version": CANONICAL_VERSION,
        "channel": channel,
        "required_bundles": list(DEFAULT_REQUIRED_BUNDLES),
        "protected_paths": protected_paths,
        "emulated_events": list(hook_bundle.get("lifecycle_hooks", {}).get("emulated", [])),
        "policy_model": policy_model or {},
        "subagents": subagents,
        "skills": skills,
    }
    settings["_omg"] = omg_settings
    _write_json(output_root / "settings.json", settings)
    artifacts.append(output_root / "settings.json")

    return artifacts


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _render_codex_skill(bundle: dict[str, Any], channel: str) -> str:
    execution_modes = ", ".join(str(mode) for mode in bundle.get("execution_contract", {}).get("modes", []))
    mcp_servers = ", ".join(str(name) for name in bundle.get("mcp_contract", {}).get("servers", []))
    return (
        f"---\n"
        f"name: omg-{bundle['id']}\n"
        f"description: {_yaml_string(str(bundle['description']))}\n"
        f"---\n\n"
        f"# {bundle['title']}\n\n"
        f"- Channel: `{channel}`\n"
        f"- Execution modes: `{execution_modes}`\n"
        f"- MCP servers: `{mcp_servers}`\n"
        f"- Evidence outputs: `{', '.join(bundle.get('evidence_outputs', {}).get('artifacts', []))}`\n"
    )


def _render_openai_yaml(bundle: dict[str, Any], channel: str) -> str:
    invocation = bundle.get("invocation_policy", {})
    servers = bundle.get("mcp_contract", {}).get("servers", [])
    tools = bundle.get("tool_policy", {}).get("allowed_tools", {}).get("codex", [])
    lines = [
        f"name: omg-{bundle['id']}",
        f"description: {_yaml_string(str(bundle['description']))}",
        f"allow_implicit_invocation: {'true' if invocation.get('allow_implicit_invocation') else 'false'}",
        "metadata:",
        f"  channel: {channel}",
        f"  bundle_id: {bundle['id']}",
        f"  title: {_yaml_string(str(bundle['title']))}",
        "mcp_servers:",
    ]
    for server in servers:
        lines.append(f"  - {server}")
    lines.append("allowed_tools:")
    for tool in tools:
        lines.append(f"  - {_yaml_string(str(tool))}")
    return "\n".join(lines) + "\n"


def _codex_skill_refs(policy_model: dict[str, Any] | None) -> list[str]:
    """Extract skill references from policy_model.host_rules.codex.skills."""
    if not isinstance(policy_model, dict):
        return []
    host_rules = policy_model.get("host_rules", {})
    if not isinstance(host_rules, dict):
        return []
    codex_rules = host_rules.get("codex", {})
    if not isinstance(codex_rules, dict):
        return []
    return [str(s) for s in codex_rules.get("skills", []) if str(s).strip()]


def _codex_evidence_fields(policy_model: dict[str, Any] | None) -> list[str]:
    """Extract required evidence contract fields from the policy model."""
    if not isinstance(policy_model, dict):
        return []
    ec = policy_model.get("evidence_contract", {})
    if not isinstance(ec, dict):
        return []
    return sorted(ec.keys())


def _codex_protected_planning_skills(bundles: Iterable[dict[str, Any]]) -> list[str]:
    protected: list[str] = []
    for bundle in bundles:
        if "codex" not in bundle.get("hosts", []):
            continue
        if str(bundle.get("kind", "")).strip().lower() != "planning":
            continue
        invocation = bundle.get("invocation_policy", {})
        if not isinstance(invocation, dict):
            continue
        if invocation.get("allow_implicit_invocation") is False:
            protected.append(f"omg/{bundle['id']}")
    return sorted(set(protected))


def _render_codex_agents_fragment(
    *,
    channel: str,
    protected_paths: list[str],
    codex_rules: list[str],
    codex_automations: list[str],
    codex_skills: list[str],
    evidence_fields: list[str],
    protected_planning_skills: list[str],
) -> str:
    """Render a comprehensive AGENTS.fragment.md for Codex host."""
    sections: list[str] = []

    # Header
    sections.append(f"# OMG Codex Governance (channel: {channel})\n")

    # Build & Test
    sections.append("## Build & Test\n")
    sections.append("```bash")
    sections.append("python3 -m pytest tests -q")
    sections.append("python3 scripts/omg.py contract validate")
    sections.append(f"python3 scripts/omg.py contract compile --host codex --channel {channel}")
    sections.append("```\n")

    # Protected Paths
    sections.append("## Protected Paths\n")
    sections.append("The following paths require tier-gated review before mutation:\n")
    for path in protected_paths:
        sections.append(f"- `{path}`")
    sections.append("")

    # Evidence Contract
    sections.append("## Evidence Contract\n")
    sections.append("Every production action must emit evidence containing these fields:\n")
    if evidence_fields:
        for field in evidence_fields:
            sections.append(f"- `{field}`")
    else:
        sections.append("- `timestamp`")
        sections.append("- `executor`")
        sections.append("- `trace_id`")
        sections.append("- `lineage`")
    sections.append("")

    # Required Skills
    sections.append("## Required Skills\n")
    if codex_skills:
        for skill in codex_skills:
            sections.append(f"- `{skill}`")
    else:
        sections.append("- `omg/control-plane`")
    sections.append("")

    sections.append("## Protected Planning Surface\n")
    if protected_planning_skills:
        sections.append("Council planning skills are protected and explicit-invocation only:")
        sections.append("")
        for skill in protected_planning_skills:
            sections.append(f"- `{skill}`")
    else:
        sections.append("- No protected planning skills configured.")
    sections.append("")

    # Web Search Policy
    sections.append("## Web Search Policy\n")
    sections.append("- Prefer cached results over live network requests.")
    sections.append("- Do NOT initiate live web searches unless explicitly instructed.")
    sections.append("- Use `context7` or local documentation before external lookups.")
    sections.append("- Set `cached_web_search: prefer_cached` as the default.\n")

    # Approval Constraints
    sections.append("## Approval Constraints\n")
    sections.append("- Destructive file operations require explicit user approval.")
    sections.append("- `git push --force` and branch deletions require explicit approval.")
    sections.append("- Production deployments require explicit approval.")
    sections.append("- Mutations to protected paths require tier-gated approval.\n")

    # Rules & Automations (compact summary)
    sections.append("## Rules & Automations\n")
    rules_str = ", ".join(codex_rules) if codex_rules else "protected_paths, explicit_invocation"
    auto_str = ", ".join(codex_automations) if codex_automations else "contract-compile"
    sections.append(f"- Rules: `{rules_str}`")
    sections.append(f"- Automations: `{auto_str}`")
    sections.append("- Require explicit invocation for protected production planning skills.")
    sections.append("")

    return "\n".join(sections)


def _render_codex_rules(
    *,
    channel: str,
    protected_paths: list[str],
    codex_skills: list[str],
    protected_planning_skills: list[str],
) -> str:
    """Render a codex-rules.md config fragment encoding defaults."""
    lines: list[str] = []
    lines.append(f"# OMG Codex Rules (channel: {channel})\n")

    lines.append("## Defaults\n")
    lines.append("- `cached_web_search: prefer_cached`")
    lines.append("- `live_network: deny_by_default`")
    lines.append("- `destructive_approval: required`\n")

    lines.append("## Protected Paths\n")
    for path in protected_paths:
        lines.append(f"- `{path}`")
    lines.append("")

    lines.append("## Required Skills\n")
    for skill in (codex_skills or ["omg/control-plane"]):
        lines.append(f"- `{skill}`")
    lines.append("")

    lines.append("## Protected Planning Surface\n")
    if protected_planning_skills:
        for skill in protected_planning_skills:
            lines.append(f"- `{skill}` (explicit invocation only)")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Approval Matrix\n")
    lines.append("| Action | Approval Required |")
    lines.append("|--------|------------------|")
    lines.append("| Read / Grep | No |")
    lines.append("| Write to protected paths | Yes |")
    lines.append("| Bash (python3:*) | Yes (balanced+ tier) |")
    lines.append("| git push --force | Yes |")
    lines.append("| Production deploy | Yes |")
    lines.append("")

    return "\n".join(lines)


def _validate_compiled_codex_output(output_root: Path) -> list[str]:
    """Validate compiled Codex output contains required AGENTS sections and artifacts."""
    errors: list[str] = []
    shared_dir = output_root / ".agents" / "skills" / "omg"

    for required_file in REQUIRED_CODEX_OUTPUTS:
        path = shared_dir / required_file
        if not path.exists():
            errors.append(f"codex: missing required output '{required_file}'")

    agents_path = shared_dir / "AGENTS.fragment.md"
    if agents_path.exists():
        content = agents_path.read_text(encoding="utf-8")
        for section in REQUIRED_CODEX_AGENTS_SECTIONS:
            if section not in content:
                errors.append(f"codex: AGENTS.fragment.md missing required section '{section}'")
    else:
        errors.append("codex: cannot validate AGENTS.fragment.md — file missing")

    return errors


def _compile_codex_outputs(
    *,
    output_root: Path,
    bundles: list[dict[str, Any]],
    channel: str,
    policy_model: dict[str, Any] | None,
) -> list[Path]:
    artifacts: list[Path] = []
    shared_dir = output_root / ".agents" / "skills" / "omg"
    shared_dir.mkdir(parents=True, exist_ok=True)

    protected_paths = _policy_protected_paths(policy_model, channel=channel)
    codex_rules: list[str] = []
    codex_automations: list[str] = []
    if isinstance(policy_model, dict):
        host_rules = policy_model.get("host_rules", {})
        if isinstance(host_rules, dict):
            codex_policy = host_rules.get("codex", {})
            if isinstance(codex_policy, dict):
                codex_rules = [str(item) for item in codex_policy.get("rules", []) if str(item).strip()]
                codex_automations = [
                    str(item) for item in codex_policy.get("automations", []) if str(item).strip()
                ]

    codex_skills = _codex_skill_refs(policy_model)
    evidence_fields = _codex_evidence_fields(policy_model)
    protected_planning_skills = _codex_protected_planning_skills(bundles)

    agents_fragment = _render_codex_agents_fragment(
        channel=channel,
        protected_paths=protected_paths,
        codex_rules=codex_rules,
        codex_automations=codex_automations,
        codex_skills=codex_skills,
        evidence_fields=evidence_fields,
        protected_planning_skills=protected_planning_skills,
    )
    _write_text(shared_dir / "AGENTS.fragment.md", agents_fragment)
    artifacts.append(shared_dir / "AGENTS.fragment.md")

    rules_content = _render_codex_rules(
        channel=channel,
        protected_paths=protected_paths,
        codex_skills=codex_skills,
        protected_planning_skills=protected_planning_skills,
    )
    _write_text(shared_dir / "codex-rules.md", rules_content)
    artifacts.append(shared_dir / "codex-rules.md")

    from runtime.mcp_config_writers import write_codex_mcp_stdio_config

    codex_mcp_path = shared_dir / "codex-mcp.toml"
    write_codex_mcp_stdio_config(
        command="python3",
        args=["-m", "runtime.omg_mcp_server"],
        server_name="omg-control",
        config_path=codex_mcp_path,
    )
    artifacts.append(codex_mcp_path)

    for bundle in bundles:
        if "codex" not in bundle.get("hosts", []):
            continue
        skill_dir = shared_dir / str(bundle["id"])
        _write_text(skill_dir / "SKILL.md", _render_codex_skill(bundle, channel))
        _write_text(skill_dir / "openai.yaml", _render_openai_yaml(bundle, channel))
        artifacts.extend([skill_dir / "SKILL.md", skill_dir / "openai.yaml"])

    return artifacts


def _compile_gemini_outputs(output_root: Path, channel: str) -> dict[str, Any]:
    del channel
    from runtime.mcp_config_writers import write_gemini_mcp_stdio_config

    config_path = output_root / ".gemini" / "settings.json"
    write_gemini_mcp_stdio_config(
        command="python3",
        args=["-m", "runtime.omg_mcp_server"],
        server_name="omg-control",
        config_path=config_path,
    )
    return {"host": "gemini", "artifacts": [config_path]}


def _compile_kimi_outputs(output_root: Path, channel: str) -> dict[str, Any]:
    del channel
    from runtime.mcp_config_writers import write_kimi_mcp_stdio_config

    config_path = output_root / ".kimi" / "mcp.json"
    write_kimi_mcp_stdio_config(
        command="python3",
        args=["-m", "runtime.omg_mcp_server"],
        server_name="omg-control",
        config_path=config_path,
    )
    return {"host": "kimi", "artifacts": [config_path]}


def _copy_release_bundle(
    *,
    output_root: Path,
    channel: str,
    artifacts: list[Path],
) -> list[Path]:
    bundle_root = output_root / "dist" / channel / "bundle"
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    copied: list[Path] = []
    for path in sorted(set(artifacts)):
        rel_path = path.relative_to(output_root)
        dst = bundle_root / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
        copied.append(dst)
    return copied


def _build_dist_manifest(output_root: Path, *, channel: str, hosts: list[str], artifacts: list[Path]) -> Path:
    dist_root = output_root / "dist" / channel
    payload = {
        "schema": "OmgCompiledArtifactManifest",
        "channel": channel,
        "hosts": list(hosts),
        "contract_version": CANONICAL_VERSION,
        "artifacts": [
            {
                "path": str(path.relative_to(dist_root)),
                "sha256": _sha256_file(path),
            }
            for path in sorted(set(artifacts))
        ],
    }
    out_path = dist_root / "manifest.json"
    _write_json(out_path, payload)
    return out_path


def compile_contract_outputs(
    *,
    root_dir: str | Path | None = None,
    output_root: str | Path | None = None,
    hosts: list[str] | tuple[str, ...] | None = None,
    channel: str = "public",
) -> dict[str, Any]:
    root = _resolve_root(root_dir)
    output = _resolve_output_root(root, output_root)
    validation = validate_contract_registry(root)
    if validation["status"] != "ok":
        return {
            "schema": "OmgContractCompileResult",
            "status": "error",
            "channel": channel,
            "hosts": list(hosts or SUPPORTED_HOSTS),
            "errors": validation["errors"],
            "artifacts": [],
        }

    if channel not in SUPPORTED_CHANNELS:
        return {
            "schema": "OmgContractCompileResult",
            "status": "error",
            "channel": channel,
            "hosts": list(hosts or SUPPORTED_HOSTS),
            "errors": [f"unsupported channel: {channel}"],
            "artifacts": [],
        }

    selected_hosts = list(hosts or SUPPORTED_HOSTS)
    bad_hosts = [host for host in selected_hosts if host not in SUPPORTED_HOSTS]
    if bad_hosts:
        return {
            "schema": "OmgContractCompileResult",
            "status": "error",
            "channel": channel,
            "hosts": selected_hosts,
            "errors": [f"unsupported hosts: {bad_hosts}"],
            "artifacts": [],
        }

    bundles = load_contract_bundles(root)
    policy_model = _policy_model_for_bundle(bundles, "control-plane")
    artifacts = _copy_contract_inputs(root, output)

    if "claude" in selected_hosts:
        artifacts.extend(
            _compile_claude_outputs(
                root=root,
                output_root=output,
                bundles=bundles,
                channel=channel,
                policy_model=policy_model,
            )
        )
        claude_errors = _validate_compiled_claude_output(output)
        if claude_errors:
            return {
                "schema": "OmgContractCompileResult",
                "status": "error",
                "channel": channel,
                "hosts": selected_hosts,
                "errors": claude_errors,
                "artifacts": [],
            }
    if "codex" in selected_hosts:
        artifacts.extend(
            _compile_codex_outputs(
                output_root=output,
                bundles=bundles,
                channel=channel,
                policy_model=policy_model,
            )
        )
        codex_errors = _validate_compiled_codex_output(output)
        if codex_errors:
            return {
                "schema": "OmgContractCompileResult",
                "status": "error",
                "channel": channel,
                "hosts": selected_hosts,
                "errors": codex_errors,
                "artifacts": [],
            }

    if "gemini" in selected_hosts:
        artifacts.extend(_compile_gemini_outputs(output, channel)["artifacts"])

    if "kimi" in selected_hosts:
        artifacts.extend(_compile_kimi_outputs(output, channel)["artifacts"])

    bundled_artifacts = _copy_release_bundle(output_root=output, channel=channel, artifacts=artifacts)
    manifest_path = _build_dist_manifest(output, channel=channel, hosts=selected_hosts, artifacts=bundled_artifacts)
    artifacts.append(manifest_path)

    return {
        "schema": "OmgContractCompileResult",
        "status": "ok",
        "channel": channel,
        "hosts": selected_hosts,
        "artifacts": [str(path.relative_to(output)) for path in artifacts],
        "manifest": str(manifest_path.relative_to(output)),
    }


def _provider_statuses() -> dict[str, dict[str, Any]]:
    ready_override = {
        item.strip()
        for item in os.environ.get("OMG_RELEASE_READY_PROVIDERS", "").split(",")
        if item.strip()
    }
    statuses: dict[str, dict[str, Any]] = {}

    for provider_name in SUPPORTED_HOSTS:
        if provider_name in ready_override:
            statuses[provider_name] = {"ready": True, "source": "env"}
            continue

        if provider_name == "claude":
            claude_bin = os.environ.get("OMG_CLAUDE_BIN", "claude")
            cmd = os.environ.get("OMG_CLAUDE_WORKER_CMD", "").strip()
            ready = bool(cmd) or shutil.which(claude_bin) is not None
            statuses[provider_name] = {
                "ready": ready,
                "source": "env-cmd" if cmd else "path",
                "detail": cmd or claude_bin,
            }
            continue

        if provider_name == "gemini":
            import runtime.providers.gemini_provider  # noqa: F401
        elif provider_name == "kimi":
            import runtime.providers.kimi_provider  # noqa: F401
        else:
            import runtime.providers.codex_provider  # noqa: F401
        from runtime.cli_provider import get_provider

        provider = get_provider(provider_name)
        ready = bool(provider and provider.detect())
        statuses[provider_name] = {"ready": ready, "source": "provider"}

    return statuses


def _check_mcp_fabric() -> dict[str, Any]:
    import runtime.omg_mcp_server as omg_mcp_server

    prompts = asyncio.run(omg_mcp_server.mcp.list_prompts())
    resources = asyncio.run(omg_mcp_server.mcp.list_resources())
    instructions = getattr(omg_mcp_server.mcp, "instructions", "")
    return {
        "ready": isinstance(instructions, str) and bool(instructions.strip()) and len(prompts) >= 1 and len(resources) >= 1,
        "prompt_count": len(prompts),
        "resource_count": len(resources),
    }


def _check_plugin_command_paths(root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {}

    plugin_specs: list[tuple[str, Path, Path]] = [
        ("core", root / "plugins" / "core" / "plugin.json", root),
        ("advanced", root / "plugins" / "advanced" / "plugin.json", root / "plugins" / "advanced"),
    ]

    for plugin_name, manifest_path, resolve_root in plugin_specs:
        plugin_detail: dict[str, Any] = {"manifest": str(manifest_path), "commands": {}}
        if not manifest_path.exists():
            blockers.append(f"plugin_command_paths: missing manifest {manifest_path.relative_to(root)}")
            plugin_detail["status"] = "error"
            details[plugin_name] = plugin_detail
            continue

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            blockers.append(f"plugin_command_paths: unreadable manifest {manifest_path.relative_to(root)}: {exc}")
            plugin_detail["status"] = "error"
            details[plugin_name] = plugin_detail
            continue

        commands = manifest.get("commands", {})
        missing: list[str] = []
        for cmd_name, cmd_config in commands.items():
            cmd_path = cmd_config.get("path", "")
            resolved = resolve_root / cmd_path
            plugin_detail["commands"][cmd_name] = str(cmd_path)
            if not resolved.exists():
                missing.append(cmd_path)
                blockers.append(
                    f"plugin_command_paths: {plugin_name} command '{cmd_name}' missing source {cmd_path}"
                )

        plugin_detail["missing"] = missing
        plugin_detail["status"] = "ok" if not missing else "error"
        details[plugin_name] = plugin_detail

    return {
        "status": "ok" if not blockers else "error",
        "blockers": blockers,
        "details": details,
    }


def _check_version_identity_drift(root: Path) -> dict[str, Any]:
    canonical_version = CANONICAL_VERSION
    blockers: list[str] = []
    drift_details: dict[str, str] = {}

    from runtime.release_surfaces import AUTHORED_SURFACES

    sync_script = Path(__file__).resolve().parents[1] / "scripts" / "sync-release-identity.py"
    if not sync_script.exists():
        return {
            "status": "error",
            "canonical_version": canonical_version,
            "blockers": ["version_drift: missing scripts/sync-release-identity.py"],
            "drift_details": {},
        }

    spec = importlib.util.spec_from_file_location("sync_release_identity", sync_script)
    if spec is None or spec.loader is None:
        return {
            "status": "error",
            "canonical_version": canonical_version,
            "blockers": ["version_drift: unable to load scripts/sync-release-identity.py"],
            "drift_details": {},
        }

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    check_surface = getattr(module, "check_surface", None)
    if not callable(check_surface):
        return {
            "status": "error",
            "canonical_version": canonical_version,
            "blockers": ["version_drift: scripts/sync-release-identity.py missing check_surface"],
            "drift_details": {},
        }

    for surface in AUTHORED_SURFACES:
        raw_drifts = check_surface(root, surface, canonical_version)
        if not isinstance(raw_drifts, list):
            blockers.append(
                f"version_drift: {surface.file_path} has version <invalid drift payload>, expected {canonical_version}"
            )
            continue
        for drift in raw_drifts:
            if not isinstance(drift, (tuple, list)) or len(drift) != 2:
                continue
            label, found = drift
            found_value = "<not found>" if found is None else str(found)
            blockers.append(
                f"version_drift: {label} has version {found_value}, expected {canonical_version}"
            )
            drift_details[str(label)] = found_value

    return {
        "status": "ok" if not blockers else "error",
        "canonical_version": canonical_version,
        "blockers": blockers,
        "drift_details": drift_details,
    }


def _check_doctor_output(output_root: Path) -> dict[str, Any]:
    evidence_dir = output_root / ".omg" / "evidence"
    doctor_path = evidence_dir / "doctor.json"
    if not doctor_path.exists():
        return {
            "status": "error",
            "path": "",
            "doctor": {},
            "blockers": ["doctor_check_missing: missing .omg/evidence/doctor.json"],
        }
    try:
        payload = _load_json(doctor_path)
    except Exception as exc:
        return {
            "status": "error",
            "path": str(doctor_path.relative_to(output_root)),
            "doctor": {},
            "blockers": [f"doctor_check_missing: invalid doctor output ({exc})"],
        }

    blockers: list[str] = []
    if payload.get("schema") != "DoctorResult":
        blockers.append("doctor_check_missing: doctor evidence schema mismatch")
    if payload.get("status") != "pass":
        blockers.append("doctor_check_missing: doctor status is not pass")
    checks = payload.get("checks", [])
    if not isinstance(checks, list) or not checks:
        blockers.append("doctor_check_missing: doctor checks missing")

    return {
        "status": "ok" if not blockers else "error",
        "path": str(doctor_path.relative_to(output_root)),
        "doctor": payload,
        "blockers": blockers,
    }


def _check_proof_surface(root: Path) -> dict[str, Any]:
    proof_path = root / "docs" / "proof.md"
    if not proof_path.exists():
        return {
            "status": "error",
            "path": "docs/proof.md",
            "blockers": ["prose_only_proof: docs/proof.md missing"],
        }

    content = proof_path.read_text(encoding="utf-8")
    lowered = content.lower()
    hardcoded_counts = bool(
        re.search(r"\b\d+\s*/\s*\d+\b", lowered)
        or re.search(r"\b\d+\s+(tests?|checks?|providers?)\s+(passed|pass|green|successful)\b", lowered)
        or re.search(r"\ball\s+tests?\s+passed\b", lowered)
    )
    artifact_refs = (
        ".omg/evidence/",
        ".omg/tracebank/",
        ".omg/evals/",
        ".omg/lineage/",
    )
    has_artifact_refs = any(token in content for token in artifact_refs)

    blockers: list[str] = []
    if hardcoded_counts and not has_artifact_refs:
        blockers.append("prose_only_proof: hardcoded proof counts without machine artifact references")

    return {
        "status": "ok" if not blockers else "error",
        "path": str(proof_path.relative_to(root)),
        "hardcoded_counts": hardcoded_counts,
        "has_artifact_refs": has_artifact_refs,
        "blockers": blockers,
    }


def _is_loopback_hostname(hostname: str) -> bool:
    lowered = hostname.strip().lower()
    return lowered in {"localhost", "127.0.0.1", "::1"}


def _collect_http_urls(line: str) -> list[str]:
    return re.findall(r"https?://[^\s)\]>'\"]+", line)


def _check_same_machine_scope(root: Path, output_root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    scanned: list[str] = []

    for rel_path in ("README.md", "docs/proof.md", "OMG_COMPAT_CONTRACT.md"):
        path = root / rel_path
        if not path.exists():
            continue
        scanned.append(rel_path)
        for line in path.read_text(encoding="utf-8").splitlines():
            if "production" not in line.lower():
                continue
            for url in _collect_http_urls(line):
                parsed = urlparse(url)
                if parsed.scheme != "http":
                    continue
                host = parsed.hostname or ""
                if host and not _is_loopback_hostname(host):
                    blockers.append(
                        f"same_machine_scope_violation: {rel_path} claims production over non-loopback HTTP ({url})"
                    )

    mcp_path = output_root / ".mcp.json"
    if mcp_path.exists():
        scanned.append(str(mcp_path.relative_to(output_root)))
        mcp_payload = _load_json(mcp_path)
        servers = mcp_payload.get("mcpServers", {})
        if isinstance(servers, dict):
            for server_name, server_cfg in servers.items():
                if not isinstance(server_cfg, dict):
                    continue
                for key in ("url", "httpUrl"):
                    raw_url = str(server_cfg.get(key, "")).strip()
                    if not raw_url:
                        continue
                    parsed = urlparse(raw_url)
                    if parsed.scheme != "http":
                        continue
                    host = parsed.hostname or ""
                    if host and not _is_loopback_hostname(host):
                        blockers.append(
                            "same_machine_scope_violation: "
                            f".mcp.json server '{server_name}' uses non-loopback HTTP endpoint ({raw_url})"
                        )

    return {
        "status": "ok" if not blockers else "error",
        "scanned": scanned,
        "blockers": blockers,
    }


def _check_provider_host_parity(output_root: Path, providers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    blockers: list[str] = []
    required_for_provider = {
        "claude": (
            output_root / "settings.json",
            output_root / ".claude-plugin" / "plugin.json",
        ),
        "codex": (
            output_root / ".agents" / "skills" / "omg" / "AGENTS.fragment.md",
            output_root / ".agents" / "skills" / "omg" / "codex-mcp.toml",
        ),
        "gemini": (
            output_root / ".gemini" / "settings.json",
        ),
        "kimi": (
            output_root / ".kimi" / "mcp.json",
        ),
    }
    for provider, status in providers.items():
        if not status.get("ready"):
            continue
        for required_path in required_for_provider.get(provider, ()):
            if not required_path.exists():
                blockers.append(
                    "provider_host_parity: "
                    f"provider '{provider}' ready but host artifact missing {required_path.relative_to(output_root)}"
                )
    return {
        "status": "ok" if not blockers else "error",
        "blockers": blockers,
    }


def _has_waiver(risk: dict[str, Any]) -> bool:
    return bool(
        risk.get("waived")
        or risk.get("waiver")
        or risk.get("waiver_id")
        or risk.get("waiver_evidence")
    )


def _check_high_risk_security_waivers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    unresolved = payload.get("unresolved_risks", [])
    if isinstance(unresolved, list):
        for item in unresolved:
            if isinstance(item, dict):
                severity = str(item.get("severity") or item.get("risk_level") or "").lower()
                if severity in {"high", "critical"} and not _has_waiver(item):
                    blockers.append("security_blocker_unwaived: unresolved high-risk item without waiver evidence")
                    break
            elif isinstance(item, str):
                lowered = item.lower()
                is_high = "high" in lowered or "critical" in lowered
                waived = "waiv" in lowered
                if is_high and not waived:
                    blockers.append("security_blocker_unwaived: unresolved high-risk item without waiver evidence")
                    break

    scans = payload.get("security_scans", [])
    if isinstance(scans, list):
        for scan in scans:
            if not isinstance(scan, dict):
                continue
            findings = scan.get("findings", [])
            if not isinstance(findings, list):
                continue
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                severity = str(finding.get("severity", "")).lower()
                if severity in {"high", "critical"} and not _has_waiver(finding):
                    blockers.append("security_blocker_unwaived: high-risk security finding without waiver evidence")
                    return blockers
    return blockers


def build_release_readiness(
    *,
    root_dir: str | Path | None = None,
    output_root: str | Path | None = None,
    channel: str = "dual",
) -> dict[str, Any]:
    root = _resolve_root(root_dir)
    output = _resolve_output_root(root, output_root)
    blockers: list[str] = []
    checks: dict[str, Any] = {}
    required_provider_hosts: set[str] = set()

    validation = validate_contract_registry(root)
    checks["contract_validation"] = validation
    if validation["status"] != "ok":
        blockers.extend(validation["errors"])

    required_channels = ["public", "enterprise"] if channel == "dual" else [channel]
    for required_channel in required_channels:
        dist_root = output / "dist" / required_channel
        manifest_path = dist_root / "manifest.json"
        if not manifest_path.exists():
            blockers.append(f"missing compiled manifest: dist/{required_channel}/manifest.json")
            continue
        manifest = _load_json(manifest_path)
        manifest_errors: list[str] = []
        for artifact in manifest.get("artifacts", []):
            if not isinstance(artifact, dict):
                continue
            rel_path = str(artifact.get("path", ""))
            expected_sha = str(artifact.get("sha256", ""))
            artifact_path = dist_root / rel_path
            if not artifact_path.exists():
                manifest_errors.append(f"{required_channel}: missing bundled artifact {rel_path}")
                continue
            if _sha256_file(artifact_path) != expected_sha:
                manifest_errors.append(f"{required_channel}: sha mismatch for {rel_path}")
        manifest_paths = {str(a.get("path", "")) for a in manifest.get("artifacts", []) if isinstance(a, dict)}
        declared_hosts = [str(host) for host in manifest.get("hosts", []) if str(host).strip()]
        if not declared_hosts:
            declared_hosts = ["claude", "codex"]
        required_provider_hosts.update(declared_hosts)
        for host_name in declared_hosts:
            for host_path in HOST_COMPILED_ARTIFACTS.get(host_name, ()):
                bundled_host_path = f"bundle/{host_path}"
                if bundled_host_path not in manifest_paths:
                    manifest_errors.append(
                        f"{required_channel}: host_parity_missing {host_name} {bundled_host_path}"
                    )
        for req_path in REQUIRED_ADVANCED_PLUGIN_ARTIFACTS:
            if req_path not in manifest_paths:
                manifest_errors.append(f"{required_channel}: advanced_plugin_missing {req_path}")
        if manifest_errors:
            blockers.extend(manifest_errors)
        manifest["integrity_errors"] = manifest_errors
        checks[f"dist_{required_channel}"] = manifest

    required_outputs = [
        output / ".claude-plugin" / "plugin.json",
        output / ".claude-plugin" / "marketplace.json",
        output / ".mcp.json",
        output / "settings.json",
        output / ".agents" / "skills" / "omg" / "control-plane" / "SKILL.md",
        output / ".agents" / "skills" / "omg" / "control-plane" / "openai.yaml",
    ]
    missing_outputs = [str(path.relative_to(output)) for path in required_outputs if not path.exists()]
    if missing_outputs:
        blockers.append(f"missing compiled outputs: {', '.join(missing_outputs)}")
    checks["compiled_outputs"] = {"missing": missing_outputs}

    required_bundle_outputs: list[Path] = []
    for bundle_id in DEFAULT_REQUIRED_BUNDLES:
        required_bundle_outputs.extend(
            [
                output / ".agents" / "skills" / "omg" / bundle_id / "SKILL.md",
                output / ".agents" / "skills" / "omg" / bundle_id / "openai.yaml",
            ]
        )
    missing_bundle_outputs = [str(path.relative_to(output)) for path in required_bundle_outputs if not path.exists()]
    if missing_bundle_outputs:
        blockers.append(f"missing bundle outputs: {', '.join(missing_bundle_outputs)}")
    checks["bundle_outputs"] = {"missing": missing_bundle_outputs}

    evidence_check = _check_recent_evidence(output)
    checks["evidence"] = evidence_check
    blockers.extend(evidence_check.get("blockers", []))

    doctor_check = _check_doctor_output(output)
    checks["doctor"] = doctor_check
    blockers.extend(doctor_check.get("blockers", []))

    eval_check = _check_eval_gate(output)
    checks["eval_gate"] = eval_check
    blockers.extend(eval_check.get("blockers", []))

    proof_chain_check = _check_proof_chain(output)
    checks["proof_chain"] = proof_chain_check
    blockers.extend(proof_chain_check.get("blockers", []))

    execution_primitives = _check_execution_primitives(output_root=output, evidence_profile="release")
    checks["execution_primitives"] = execution_primitives
    blockers.extend(execution_primitives.get("blockers", []))

    security_blockers = [
        blocker
        for blocker in evidence_check.get("blockers", [])
        if isinstance(blocker, str) and blocker.startswith("security_blocker_unwaived:")
    ]
    checks["security_blocker_unwaived"] = {
        "status": "ok" if not security_blockers else "error",
        "blockers": security_blockers,
    }

    proof_surface_check = _check_proof_surface(root)
    checks["proof_surface"] = proof_surface_check
    blockers.extend(proof_surface_check.get("blockers", []))

    same_machine_scope = _check_same_machine_scope(root, output)
    checks["same_machine_scope"] = same_machine_scope
    blockers.extend(same_machine_scope.get("blockers", []))

    package_check = _check_packaged_install_smoke(root)
    checks["package_smoke"] = package_check
    blockers.extend(package_check.get("blockers", []))

    plugin_cmd_check = _check_plugin_command_paths(root)
    checks["plugin_command_paths"] = plugin_cmd_check
    blockers.extend(plugin_cmd_check.get("blockers", []))

    version_drift_check = _check_version_identity_drift(root)
    checks["version_identity_drift"] = version_drift_check
    blockers.extend(version_drift_check.get("blockers", []))

    if channel == "dual":
        bundle_promotion_parity = _check_bundle_promotion_parity(root, output)
        checks["bundle_promotion_parity"] = bundle_promotion_parity
        blockers.extend(bundle_promotion_parity.get("blockers", []))

    providers = _provider_statuses()
    checks["providers"] = providers
    for provider_name, status in providers.items():
        if provider_name not in required_provider_hosts:
            continue
        if not status.get("ready"):
            blockers.append(f"provider not ready: {provider_name}")

    required_providers = {
        provider_name: status
        for provider_name, status in providers.items()
        if provider_name in required_provider_hosts
    }
    provider_parity = _check_provider_host_parity(output, required_providers)
    checks["provider_host_parity"] = provider_parity
    blockers.extend(provider_parity.get("blockers", []))

    worktree_ready = shutil.which("git") is not None and (root / ".git").exists()
    checks["worktree"] = {"ready": worktree_ready}
    if not worktree_ready:
        blockers.append("git worktree support not available")

    mcp_status = _check_mcp_fabric()
    checks["mcp_fabric"] = mcp_status
    if not mcp_status.get("ready"):
        blockers.append("mcp fabric incomplete")

    return {
        "schema": "OmgReleaseReadinessResult",
        "status": "ok" if not blockers else "error",
        "channel": channel,
        "blockers": blockers,
        "checks": checks,
    }


def _check_recent_evidence(output_root: Path) -> dict[str, Any]:
    latest = _latest_evidence_pack(output_root)
    if latest is None:
        return {"status": "missing", "blockers": []}

    evidence_path, payload = latest
    blockers: list[str] = []
    if not payload.get("security_scans"):
        blockers.append("cosmetic evidence: security_scans is empty")
    if not payload.get("provenance"):
        blockers.append("cosmetic evidence: provenance is empty")
    if not payload.get("timestamp") and not payload.get("created_at"):
        blockers.append("missing_attribution: evidence missing timestamp")
    if not payload.get("executor"):
        blockers.append("missing_attribution: evidence missing executor")
    if not payload.get("environment"):
        blockers.append("missing_attribution: evidence missing environment")
    if not payload.get("trace_ids"):
        blockers.append("missing trace ids in evidence")
    if not payload.get("trace_id") and not payload.get("trace_ids"):
        blockers.append("missing trace_id in evidence")
    if not payload.get("lineage"):
        blockers.append("missing lineage in evidence")
    tests = payload.get("tests", [])
    if isinstance(tests, list):
        for item in tests:
            if isinstance(item, dict) and item.get("name") == "worker_implementation" and not item.get("passed", False):
                blockers.append("simulated worker evidence detected")
                break
    blockers.extend(_check_test_intent_claims(payload))
    blockers.extend(_check_high_risk_security_waivers(payload))
    return {
        "status": "ok" if not blockers else "error",
        "evidence_file": str(evidence_path.relative_to(output_root)),
        "run_id": str(payload.get("run_id", "")).strip(),
        "blockers": blockers,
    }


def _latest_evidence_pack(output_root: Path) -> tuple[Path, dict[str, Any]] | None:
    evidence_dir = output_root / ".omg" / "evidence"
    if not evidence_dir.exists():
        return None

    evidence_files = sorted(path for path in evidence_dir.glob("*.json") if path.is_file())
    evidence_payloads: list[tuple[Path, dict[str, Any]]] = []
    for path in evidence_files:
        try:
            payload = _load_json(path)
        except Exception:
            continue
        if payload.get("schema") != "EvidencePack":
            continue
        try:
            payload = _normalize_evidence_pack(payload)
        except ValueError as exc:
            return path, {"schema": "EvidencePack", "invalid": f"invalid evidence pack: {exc}"}
        evidence_payloads.append((path, payload))

    if not evidence_payloads:
        return None
    return evidence_payloads[-1]


def _required_fields_for_module(module: str) -> list[str]:
    metadata = schema_versions().get(module, {})
    required = metadata.get("required_fields", []) if isinstance(metadata, dict) else []
    if isinstance(required, list):
        return [str(field) for field in required if str(field).strip()]
    return []


def _missing_context_metadata(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in _REQUIRED_CONTEXT_METADATA:
        value = str(payload.get(key, "")).strip()
        if not value:
            missing.append(key)
    return missing


def _check_execution_primitives(*, output_root: Path, evidence_profile: str | None = None) -> dict[str, Any]:
    blockers: list[str] = []
    missing: list[str] = []
    invalid: list[str] = []
    evidence_paths: dict[str, str] = {key: "" for key in _REQUIRED_EXECUTION_PRIMITIVES}
    resolved_profile = (evidence_profile or "").strip()
    required_evidence_requirements = requirements_for_profile(resolved_profile)

    latest = _latest_evidence_pack(output_root)
    if latest is None:
        missing.extend(list(_REQUIRED_EXECUTION_PRIMITIVES))
        blockers.extend(f"missing_execution_primitive: {item}" for item in missing)
        return {
            "status": "error",
            "run_id": "",
            "evidence_profile": resolved_profile,
            "required_evidence_requirements": list(required_evidence_requirements),
            "required": list(_REQUIRED_EXECUTION_PRIMITIVES),
            "missing": missing,
            "invalid": invalid,
            "evidence_paths": evidence_paths,
            "blockers": blockers,
        }

    evidence_path, evidence_payload = latest
    invalid_evidence = str(evidence_payload.get("invalid", "")).strip()
    if invalid_evidence:
        invalid.append(f"release_evidence_pack:{invalid_evidence}")
        blockers.append(f"invalid_execution_primitive: release_evidence_pack: {invalid_evidence}")
        return {
            "status": "error",
            "run_id": "",
            "evidence_profile": resolved_profile,
            "required_evidence_requirements": list(required_evidence_requirements),
            "required": list(_REQUIRED_EXECUTION_PRIMITIVES),
            "missing": list(_REQUIRED_EXECUTION_PRIMITIVES),
            "invalid": invalid,
            "evidence_paths": evidence_paths,
            "blockers": blockers,
        }

    if not resolved_profile:
        resolved_profile = str(evidence_payload.get("evidence_profile", "")).strip()
        required_evidence_requirements = requirements_for_profile(resolved_profile)

    run_id = str(evidence_payload.get("run_id", "")).strip()
    if not run_id:
        invalid.append("run_id_unresolved")
        blockers.append("invalid_execution_primitive: run_id_unresolved")

    evidence_metadata_missing = _missing_context_metadata(evidence_payload)
    if evidence_metadata_missing:
        invalid.append("release_evidence_pack:missing_context_metadata")
        blockers.append(
            "invalid_execution_primitive: release_evidence_pack: "
            f"missing_context_metadata={','.join(sorted(evidence_metadata_missing))}"
        )

    checks: list[tuple[str, str, str]] = [
        ("release_run_coordinator_state", "release_run_coordinator", "ReleaseRunCoordinatorState"),
        ("rollback_manifest", "rollback_manifest", "RollbackManifest"),
        ("intent_gate_state", "intent_gate", "IntentGateDecision"),
        ("session_health_state", "session_health", "SessionHealth"),
        ("council_verdicts", "council_verdicts", "CouncilVerdicts"),
    ]
    for token, module, schema_name in checks:
        matched_path, matched_payload = _find_state_for_run(output_root=output_root, module=module, run_id=run_id)
        if matched_path is None or matched_payload is None:
            missing.append(token)
            blockers.append(f"missing_execution_primitive: {token}")
            continue
        evidence_paths[token] = str(matched_path.relative_to(output_root)).replace("\\", "/")
        schema = str(matched_payload.get("schema", "")).strip()
        if schema != schema_name:
            invalid.append(f"{token}:schema_mismatch")
            blockers.append(f"invalid_execution_primitive: {token}: schema_mismatch")
            continue
        required_fields = _required_fields_for_module(module)
        missing_fields = [field for field in required_fields if field not in matched_payload]
        if missing_fields:
            invalid.append(f"{token}:missing_fields")
            blockers.append(
                f"invalid_execution_primitive: {token}: missing_fields={','.join(sorted(missing_fields))}"
            )
        if token in {"intent_gate_state", "session_health_state", "council_verdicts"}:
            metadata_missing = _missing_context_metadata(matched_payload)
            if metadata_missing:
                invalid.append(f"{token}:missing_context_metadata")
                blockers.append(
                    f"invalid_execution_primitive: {token}: "
                    f"missing_context_metadata={','.join(sorted(metadata_missing))}"
                )

    profile_path = output_root / ".omg" / "state" / "profile.yaml"
    if not profile_path.exists():
        missing.append("profile_digest")
        blockers.append("missing_execution_primitive: profile_digest")
    else:
        evidence_paths["profile_digest"] = str(profile_path.relative_to(output_root)).replace("\\", "/")
        try:
            profile_payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        except Exception:
            profile_payload = None
        profile_version = ""
        if isinstance(profile_payload, dict):
            profile_version = str(
                profile_payload.get("profile_version")
                or profile_payload.get("version")
                or ""
            ).strip()
            if not profile_version:
                provenance = profile_payload.get("profile_provenance")
                if isinstance(provenance, dict):
                    profile_version = str(
                        provenance.get("checksum")
                        or provenance.get("version")
                        or ""
                    ).strip()
        if not profile_version:
            invalid.append("profile_digest:missing_profile_version")
            blockers.append("invalid_execution_primitive: profile_digest: missing_profile_version")

    lock_path, lock_payload = _find_test_intent_lock(output_root=output_root, run_id=run_id, evidence_payload=evidence_payload)
    if lock_path is None or lock_payload is None:
        missing.append("tdd_proof_chain_lock")
        blockers.append("missing_execution_primitive: tdd_proof_chain_lock")
    else:
        evidence_paths["tdd_proof_chain_lock"] = str(lock_path.relative_to(output_root)).replace("\\", "/")
        lock_status = str(lock_payload.get("status", "")).strip().lower()
        if lock_status in {"", "error", "blocked"}:
            invalid.append("tdd_proof_chain_lock:status_invalid")
            blockers.append("invalid_execution_primitive: tdd_proof_chain_lock: status_invalid")

    forge_path, forge_payload = _find_forge_starter_proof(output_root=output_root, run_id=run_id)
    if forge_path is None or forge_payload is None:
        missing.append("forge_starter_proof")
        blockers.append("missing_execution_primitive: forge_starter_proof")
    else:
        evidence_paths["forge_starter_proof"] = str(forge_path.relative_to(output_root)).replace("\\", "/")
        forge_schema = str(forge_payload.get("schema", "")).strip()
        if forge_schema != "ForgeSpecialistDispatchEvidence":
            invalid.append("forge_starter_proof:schema_mismatch")
            blockers.append("invalid_execution_primitive: forge_starter_proof: schema_mismatch")
        if forge_payload.get("proof_backed") is not True:
            invalid.append("forge_starter_proof:not_proof_backed")
            blockers.append("invalid_execution_primitive: forge_starter_proof: proof_backed_false")
        forge_metadata_missing = _missing_context_metadata(forge_payload)
        if forge_metadata_missing:
            invalid.append("forge_starter_proof:missing_context_metadata")
            blockers.append(
                "invalid_execution_primitive: forge_starter_proof: "
                f"missing_context_metadata={','.join(sorted(forge_metadata_missing))}"
            )

    return {
        "status": "ok" if not blockers else "error",
        "run_id": run_id,
        "evidence_profile": resolved_profile,
        "required_evidence_requirements": list(required_evidence_requirements),
        "evidence_pack": str(evidence_path.relative_to(output_root)).replace("\\", "/"),
        "required": list(_REQUIRED_EXECUTION_PRIMITIVES),
        "missing": sorted(set(missing)),
        "invalid": sorted(set(invalid)),
        "evidence_paths": evidence_paths,
        "blockers": blockers,
    }


def _find_state_for_run(
    *,
    output_root: Path,
    module: str,
    run_id: str,
) -> tuple[Path | None, dict[str, Any] | None]:
    state_dir = output_root / ".omg" / "state" / module
    if not state_dir.exists():
        return None, None

    preferred = state_dir / f"{run_id}.json"
    if run_id and preferred.exists():
        try:
            payload = _load_json(preferred)
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            return preferred, payload

    for path in sorted(state_dir.glob("*.json")):
        try:
            payload = _load_json(path)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if run_id and str(payload.get("run_id", "")).strip() != run_id:
            continue
        return path, payload
    return None, None


def _find_test_intent_lock(
    *,
    output_root: Path,
    run_id: str,
    evidence_payload: dict[str, Any],
) -> tuple[Path | None, dict[str, Any] | None]:
    lock_dir = output_root / ".omg" / "state" / "test-intent-lock"
    if not lock_dir.exists():
        return None, None

    lock_id = ""
    test_delta = evidence_payload.get("test_delta")
    if isinstance(test_delta, dict):
        lock_id = str(test_delta.get("lock_id", "")).strip()

    for path in sorted(lock_dir.glob("*.json")):
        try:
            payload = _load_json(path)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        payload_lock_id = str(payload.get("lock_id", "")).strip()
        if lock_id and payload_lock_id == lock_id:
            return path, payload
        intent = payload.get("intent")
        if isinstance(intent, dict):
            intent_run = str(intent.get("run_id", "")).strip()
            if run_id and intent_run == run_id:
                return path, payload
        payload_run = str(payload.get("run_id", "")).strip()
        if run_id and payload_run == run_id:
            return path, payload
    return None, None


def _find_forge_starter_proof(*, output_root: Path, run_id: str) -> tuple[Path | None, dict[str, Any] | None]:
    evidence_dir = output_root / ".omg" / "evidence"
    if not evidence_dir.exists():
        return None, None
    for path in sorted(evidence_dir.glob("forge-specialists-*.json")):
        try:
            payload = _load_json(path)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        payload_run = str(payload.get("run_id", "")).strip()
        if run_id and payload_run and payload_run != run_id:
            continue
        return path, payload
    return None, None


def _check_test_intent_claims(payload: dict[str, Any]) -> list[str]:
    test_delta = payload.get("test_delta")
    claims = payload.get("claims", [])
    if not isinstance(claims, list):
        return []

    from runtime.test_intent_lock import evaluate_test_delta

    blockers: list[str] = []
    guarded_claims = {"tests passed", "tests_passed", "bug fixed", "bug_fixed"}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_type = str(claim.get("claim_type", "")).strip().lower()
        if claim_type not in guarded_claims:
            continue
        delta = claim.get("test_delta")
        if not isinstance(delta, dict):
            delta = test_delta if isinstance(test_delta, dict) else None
        if not isinstance(delta, dict):
            blockers.append(f"test_intent_lock_missing_delta: claim '{claim_type}' requires test_delta evidence")
            continue
        result = evaluate_test_delta(delta)
        if result.get("verdict") != "pass":
            reasons = result.get("reasons", [])
            reason_text = "; ".join(str(item) for item in reasons if str(item).strip())
            suffix = f": {reason_text}" if reason_text else ""
            blockers.append(f"test_intent_lock_blocked: claim '{claim_type}'{suffix}")
    return blockers


def _check_eval_gate(output_root: Path) -> dict[str, Any]:
    latest_path = output_root / ".omg" / "evals" / "latest.json"
    if not latest_path.exists():
        return {"status": "missing", "blockers": []}
    payload = _load_json(latest_path)
    blockers: list[str] = []
    if payload.get("status") != "ok" or bool(payload.get("summary", {}).get("regressed")):
        blockers.append("eval regression detected")
    return {
        "status": "ok" if not blockers else "error",
        "path": str(latest_path.relative_to(output_root)),
        "blockers": blockers,
    }


def _check_proof_chain(output_root: Path) -> dict[str, Any]:
    chain_module = importlib.import_module("runtime.proof_chain")
    gate_module = importlib.import_module("runtime.proof_gate")

    gate_input = chain_module.build_proof_gate_input(str(output_root))
    chain = gate_input.get("proof_chain", {}) if isinstance(gate_input, dict) else {}
    chain_status = str(chain.get("status", "error"))
    raw_blockers = chain.get("blockers", [])
    blockers = [f"proof_chain_linkage: {item}" for item in raw_blockers] if isinstance(raw_blockers, list) else ["proof_chain_linkage: invalid blockers"]
    if chain_status == "ok":
        blockers = []

    proof_gate = gate_module.evaluate_proof_gate(gate_input if isinstance(gate_input, dict) else {})
    if str(proof_gate.get("verdict", "fail")) != "pass":
        gate_blockers = proof_gate.get("blockers", [])
        if isinstance(gate_blockers, list) and gate_blockers:
            blockers.extend(f"proof_gate_blocked: {item}" for item in gate_blockers)
        else:
            blockers.append("proof_gate_blocked: verdict_fail")

    return {
        "status": "ok" if not blockers else "error",
        "proof_chain": chain,
        "proof_gate": proof_gate,
        "blockers": blockers,
    }


def _check_bundle_promotion_parity(root: Path, output_root: Path) -> dict[str, Any]:
    missing_settings_required_bundles: list[str] = []
    missing_dist_public: list[str] = []
    missing_dist_enterprise: list[str] = []
    missing_pyproject_data_files: list[str] = []

    settings_path = output_root / "settings.json"
    if settings_path.exists():
        settings = _load_json(settings_path)
        required_bundles = settings.get("_omg", {}).get("generated", {}).get("required_bundles", [])
        if not isinstance(required_bundles, list):
            required_bundles = []
        required_bundle_set = {str(item) for item in required_bundles}
        missing_settings_required_bundles = [
            bundle_id for bundle_id in TRUTH_COUNCIL_BUNDLES if bundle_id not in required_bundle_set
        ]
    else:
        missing_settings_required_bundles = list(TRUTH_COUNCIL_BUNDLES)

    for bundle_id in TRUTH_COUNCIL_BUNDLES:
        public_skill = output_root / "dist" / "public" / "bundle" / ".agents" / "skills" / "omg" / bundle_id / "SKILL.md"
        if not public_skill.exists():
            missing_dist_public.append(str(public_skill.relative_to(output_root)))

        enterprise_skill = output_root / "dist" / "enterprise" / "bundle" / ".agents" / "skills" / "omg" / bundle_id / "SKILL.md"
        if not enterprise_skill.exists():
            missing_dist_enterprise.append(str(enterprise_skill.relative_to(output_root)))

    pyproject_path = root / "pyproject.toml"
    if pyproject_path.exists():
        pyproject_content = pyproject_path.read_text(encoding="utf-8")
        for bundle_id in TRUTH_COUNCIL_BUNDLES:
            data_file_key = f'".agents/skills/omg/{bundle_id}" = '
            if data_file_key not in pyproject_content:
                missing_pyproject_data_files.append(bundle_id)
    else:
        missing_pyproject_data_files = list(TRUTH_COUNCIL_BUNDLES)

    failed = any(
        (
            missing_settings_required_bundles,
            missing_dist_public,
            missing_dist_enterprise,
            missing_pyproject_data_files,
        )
    )
    return {
        "status": "ok" if not failed else "error",
        "blockers": ["bundle_promotion_parity"] if failed else [],
        "missing_settings_required_bundles": missing_settings_required_bundles,
        "missing_dist_public": missing_dist_public,
        "missing_dist_enterprise": missing_dist_enterprise,
        "missing_pyproject_data_files": missing_pyproject_data_files,
    }


def _check_packaged_install_smoke(root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    with tempfile.TemporaryDirectory(prefix="omg-wheel-") as tmp_dir:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", tmp_dir],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if proc.returncode != 0:
            return {
                "status": "error",
                "blockers": ["package smoke failed to build wheel"],
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        wheels = sorted(Path(tmp_dir).glob("*.whl"))
        if not wheels:
            return {"status": "error", "blockers": ["package smoke did not produce a wheel"]}
        with zipfile.ZipFile(wheels[-1]) as archive:
            names = set(archive.namelist())
        required_suffixes = (
            "control_plane/service.py",
            "registry/verify_artifact.py",
            "plugins/dephealth/cve_scanner.py",
            "OMG_COMPAT_CONTRACT.md",
            ".agents/skills/omg/security-check/SKILL.md",
            ".agents/skills/omg/plan-council/SKILL.md",
            ".agents/skills/omg/claim-judge/SKILL.md",
            ".agents/skills/omg/test-intent-lock/SKILL.md",
            ".agents/skills/omg/proof-gate/SKILL.md",
        )
        for suffix in required_suffixes:
            if not any(name.endswith(suffix) for name in names):
                blockers.append(f"package parity missing {suffix}")
    return {"status": "ok" if not blockers else "error", "blockers": blockers}
