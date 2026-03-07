"""Canonical OMG contract registry, compiler, and release-readiness checks."""
from __future__ import annotations

import hashlib
import asyncio
import json
import os
from pathlib import Path
import shutil
from typing import Any, Iterable

import yaml

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
SUPPORTED_HOSTS = ("claude", "codex")
SUPPORTED_CHANNELS = ("public", "enterprise")
DEFAULT_REQUIRED_BUNDLES = (
    "control-plane",
    "hook-governor",
    "mcp-fabric",
    "lsp-pack",
    "secure-worktree-pipeline",
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
    root = _resolve_root(root_dir)
    return (root / CONTRACT_DOC_PATH).read_text(encoding="utf-8")


def load_contract_schema(root_dir: str | Path | None = None) -> dict[str, Any]:
    root = _resolve_root(root_dir)
    return _load_json(root / SCHEMA_PATH)


def load_contract_bundles(root_dir: str | Path | None = None) -> list[dict[str, Any]]:
    root = _resolve_root(root_dir)
    bundles: list[dict[str, Any]] = []
    for path in sorted((root / BUNDLES_DIR).glob("*.yaml")):
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected mapping bundle manifest in {path}")
        bundle = dict(parsed)
        bundle["_path"] = str(path.relative_to(root))
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

    doc_path = root / CONTRACT_DOC_PATH
    schema_path = root / SCHEMA_PATH
    bundles_path = root / BUNDLES_DIR

    if not doc_path.exists():
        errors.append(f"missing contract doc: {CONTRACT_DOC_PATH}")
        doc_text = ""
    else:
        doc_text = doc_path.read_text(encoding="utf-8")
        for token in REQUIRED_DOC_TOKENS:
            if token not in doc_text:
                errors.append(f"contract doc missing token: {token}")
        if CANONICAL_VERSION not in doc_text:
            errors.append(f"contract doc missing version: {CANONICAL_VERSION}")

    if not schema_path.exists():
        errors.append(f"missing contract schema: {SCHEMA_PATH}")
        schema_payload: dict[str, Any] = {}
    else:
        schema_payload = _load_json(schema_path)
        if str(schema_payload.get("version", "")) != CANONICAL_VERSION:
            errors.append(f"contract schema version drift: {schema_payload.get('version')!r}")

    if not bundles_path.exists():
        errors.append(f"missing bundles directory: {BUNDLES_DIR}")
        bundles: list[dict[str, Any]] = []
    else:
        bundles = load_contract_bundles(root)

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
        src = root / rel_path
        dst = output_root / rel_path
        _write_text(dst, src.read_text(encoding="utf-8"))
        copied.append(dst)
    for path in sorted((root / BUNDLES_DIR).glob("*.yaml")):
        rel_path = path.relative_to(root)
        dst = output_root / rel_path
        _write_text(dst, path.read_text(encoding="utf-8"))
        copied.append(dst)
    return copied


def _base_mcp_servers() -> dict[str, Any]:
    return {
        "context7": {
            "command": "npx",
            "args": ["@upstash/context7-mcp@2.1.3"],
        },
        "filesystem": {
            "command": "npx",
            "args": ["@modelcontextprotocol/server-filesystem@2026.1.14", "."],
        },
        "websearch": {
            "command": "npx",
            "args": ["@zhafron/mcp-web-search@1.2.2"],
        },
        "chrome-devtools": {
            "command": "npx",
            "args": ["chrome-devtools-mcp@0.19.0"],
        },
        "omg-memory": {
            "type": "http",
            "url": "http://127.0.0.1:8765/mcp",
        },
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
        "mcpServers": "./.mcp.json",
    }


def _build_claude_marketplace() -> dict[str, Any]:
    return {
        "name": CANONICAL_MARKETPLACE_ID,
        "description": "Marketplace metadata for the OMG Claude plugin",
        "owner": {"name": "trac3er00"},
        "metadata": {
            "description": "OMG - Oh-My-God for Claude Code",
            "version": CANONICAL_VERSION,
            "homepage": CANONICAL_REPO_URL,
            "repository": CANONICAL_REPO_URL,
        },
        "plugins": [
            {
                "name": CANONICAL_PLUGIN_ID,
                "description": "OMG plugin layer for Claude Code with native setup, orchestration, and interop.",
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


def _compile_claude_outputs(
    *,
    root: Path,
    output_root: Path,
    bundles: list[dict[str, Any]],
    channel: str,
) -> list[Path]:
    artifacts: list[Path] = []

    _write_json(output_root / ".claude-plugin" / "plugin.json", _build_claude_plugin())
    artifacts.append(output_root / ".claude-plugin" / "plugin.json")

    _write_json(output_root / ".claude-plugin" / "marketplace.json", _build_claude_marketplace())
    artifacts.append(output_root / ".claude-plugin" / "marketplace.json")

    mcp_payload = {"mcpServers": _base_mcp_servers()}
    _write_json(output_root / ".mcp.json", mcp_payload)
    artifacts.append(output_root / ".mcp.json")

    settings_path = root / "settings.json"
    settings = _load_json(settings_path)
    hook_bundle = _bundle_map(bundles)["hook-governor"]
    settings["hooks"] = _compile_hook_settings(hook_bundle)
    omg_settings = dict(settings.get("_omg", {}))
    omg_settings["_version"] = CANONICAL_VERSION
    omg_settings["generated"] = {
        "contract_version": CANONICAL_VERSION,
        "channel": channel,
        "required_bundles": list(DEFAULT_REQUIRED_BUNDLES),
        "protected_paths": _protected_paths_for_channel(channel),
        "emulated_events": list(hook_bundle.get("lifecycle_hooks", {}).get("emulated", [])),
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


def _compile_codex_outputs(
    *,
    output_root: Path,
    bundles: list[dict[str, Any]],
    channel: str,
) -> list[Path]:
    artifacts: list[Path] = []
    shared_dir = output_root / ".agents" / "skills" / "omg"
    shared_dir.mkdir(parents=True, exist_ok=True)

    rules_fragment = (
        "# OMG Codex Protection Rules\n\n"
        f"- Channel: `{channel}`\n"
        "- Protect `.omg/`, `.agents/`, `.codex/`, and `.claude/` from unreviewed mutation.\n"
        "- Require explicit invocation for production-control-plane skills.\n"
    )
    _write_text(shared_dir / "AGENTS.fragment.md", rules_fragment)
    artifacts.append(shared_dir / "AGENTS.fragment.md")

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


def _build_dist_manifest(output_root: Path, *, channel: str, artifacts: list[Path]) -> Path:
    dist_root = output_root / "dist" / channel
    payload = {
        "schema": "OmgCompiledArtifactManifest",
        "channel": channel,
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
    artifacts = _copy_contract_inputs(root, output)

    if "claude" in selected_hosts:
        artifacts.extend(_compile_claude_outputs(root=root, output_root=output, bundles=bundles, channel=channel))
    if "codex" in selected_hosts:
        artifacts.extend(_compile_codex_outputs(output_root=output, bundles=bundles, channel=channel))

    bundled_artifacts = _copy_release_bundle(output_root=output, channel=channel, artifacts=artifacts)
    manifest_path = _build_dist_manifest(output, channel=channel, artifacts=bundled_artifacts)
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

    for provider_name in ("claude", "codex"):
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

        import runtime.providers.codex_provider  # noqa: F401
        from runtime.cli_provider import get_provider

        provider = get_provider("codex")
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

    providers = _provider_statuses()
    checks["providers"] = providers
    for provider_name, status in providers.items():
        if not status.get("ready"):
            blockers.append(f"provider not ready: {provider_name}")

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
