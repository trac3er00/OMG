#!/usr/bin/env python3
"""
settings-merge.py
Merges v2 hooks + permissions INTO existing ~/.claude/settings.json
without destroying existing non-OMG configuration.

Strategy:
- hooks{}: APPEND our matchers to each event (never replace existing)
- permissions.allow[]: UNION (add ours, keep theirs)
- permissions.deny[]: UNION
- permissions.ask[]: UNION
- Everything else: PRESERVE as-is
"""
import json
import sys
import os
import re
import shutil
from datetime import datetime

def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: {path} contains invalid JSON (line {e.lineno}, col {e.colno}):", file=sys.stderr)
        print(f"  {e.msg}", file=sys.stderr)
        print(f"  Fix the file manually or delete it to start fresh.", file=sys.stderr)
        sys.exit(1)
    except PermissionError:
        print(f"ERROR: Cannot read {path} — permission denied.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to read {path}: {e}", file=sys.stderr)
        sys.exit(1)

def merge_hooks(existing_hooks, new_hooks):
    """Append new hook matchers to existing, avoiding duplicates."""
    merged = dict(existing_hooks)  # shallow copy

    def _normalize_command_name(name):
        return re.sub(r"[^a-z0-9]+", "", name.lower())

    def _matcher_identity(entry):
        if not isinstance(entry, dict):
            return None
        matcher = entry.get("matcher")
        return None if matcher in ("", None) else matcher

    def _command_identity(command):
        if not command:
            return ""
        tokens = re.findall(r'"[^"]*"|\'[^\']*\'|\S+', command)
        if not tokens:
            return ""
        candidate = tokens[-1].strip("\"'")
        base = os.path.basename(candidate)
        stem, _ = os.path.splitext(base)
        normalized = _normalize_command_name(stem or base)
        return normalized or stem or base

    def extract_commands(entry):
        commands = set()
        if not isinstance(entry, dict):
            return commands
        hooks = entry.get("hooks")
        if isinstance(hooks, list):
            for hook in hooks:
                if not isinstance(hook, dict):
                    continue
                cmd = hook.get("command", "") or hook.get("prompt", "")
                if cmd:
                    commands.add(_command_identity(cmd))
            return commands
        cmd = entry.get("command", "") or entry.get("prompt", "")
        if cmd:
            commands.add(_command_identity(cmd))
        return commands

    for event, matchers in new_hooks.items():
        if event not in merged:
            merged[event] = matchers
            continue

        existing_matchers = merged[event]

        for new_matcher in matchers:
            new_cmds = extract_commands(new_matcher)

            overlap_indices = []
            already_exists = False
            for idx, em in enumerate(existing_matchers):
                existing_cmds = extract_commands(em)
                same_matcher = _matcher_identity(em) == _matcher_identity(new_matcher)
                if new_cmds and same_matcher and (new_cmds & existing_cmds):
                    overlap_indices.append(idx)
                    continue
                if not new_cmds and em == new_matcher:
                    already_exists = True
                    break

            if overlap_indices:
                first = overlap_indices[0]
                existing_matchers[first] = new_matcher
                for idx in reversed(overlap_indices[1:]):
                    existing_matchers.pop(idx)
                continue

            if not already_exists:
                existing_matchers.append(new_matcher)

    return merged

def merge_permission_list(existing, new):
    """Union two permission lists, preserving order (existing first)."""
    seen = set(existing)
    merged = list(existing)
    for item in new:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


def merge_mcp_servers(existing, new):
    merged = dict(existing or {})
    for name, config in (new or {}).items():
        if name not in merged:
            merged[name] = config
            continue
        existing_cfg = merged.get(name)
        if isinstance(existing_cfg, dict) and isinstance(config, dict):
            merged_cfg = dict(existing_cfg)
            if "args" in config:
                existing_args = merged_cfg.get("args", []) if isinstance(merged_cfg.get("args", []), list) else []
                new_args = config.get("args", []) if isinstance(config.get("args", []), list) else []
                merged_args = list(existing_args)
                for arg in new_args:
                    if arg not in merged_args:
                        merged_args.append(arg)
                merged_cfg["args"] = merged_args
            if "env" in config and isinstance(config.get("env"), dict):
                env = dict(merged_cfg.get("env", {})) if isinstance(merged_cfg.get("env"), dict) else {}
                for key, value in config["env"].items():
                    env.setdefault(key, value)
                merged_cfg["env"] = env
            for key, value in config.items():
                merged_cfg.setdefault(key, value)
            merged[name] = merged_cfg
    return merged

def merge_settings(existing, new):
    """
    Merge strategy:
    - hooks: append per-event
    - permissions: union per-category
    - everything else in existing: preserve
    - $schema: use new if not present
    """
    merged = dict(existing)

    # Schema
    if "$schema" not in merged and "$schema" in new:
        merged["$schema"] = new["$schema"]

    # Hooks
    if "hooks" in new:
        existing_hooks = merged.get("hooks", {})
        merged["hooks"] = merge_hooks(existing_hooks, new["hooks"])

    # Permissions
    if "permissions" in new:
        existing_perms = merged.get("permissions", {})
        new_perms = new["permissions"]
        merged_perms = dict(existing_perms)
        managed_rules = set()
        for category in ("allow", "deny", "ask"):
            managed_rules.update(new_perms.get(category, []))

        for category in ("allow", "deny", "ask"):
            existing_list = existing_perms.get(category, [])
            filtered_existing = [item for item in existing_list if item not in managed_rules]
            new_list = new_perms.get(category, [])
            merged_perms[category] = merge_permission_list(filtered_existing, new_list)

        merged["permissions"] = merged_perms

    if "mcpServers" in new:
        merged["mcpServers"] = merge_mcp_servers(merged.get("mcpServers", {}), new.get("mcpServers", {}))

    return merged

def main():
    if len(sys.argv) < 3:
        print("Usage: settings-merge.py <existing.json> <new.json> [--dry-run]")
        sys.exit(1)

    existing_path = sys.argv[1]
    new_path = sys.argv[2]
    dry_run = "--dry-run" in sys.argv

    existing = load_json(existing_path)
    new = load_json(new_path)

    merged = merge_settings(existing, new)

    if dry_run:
        print(json.dumps(merged, indent=2))
        print(f"\n--- DRY RUN ---", file=sys.stderr)
        # Show what was added
        new_hooks = set()
        for event, matchers in new.get("hooks", {}).items():
            for m in matchers:
                for h in m.get("hooks", []):
                    cmd = h.get("command", "")
                    if cmd:
                        new_hooks.add(f"  {event}: {os.path.basename(cmd.split()[-1])}")
        if new_hooks:
            print(f"Hooks to add:", file=sys.stderr)
            for h in sorted(new_hooks):
                print(h, file=sys.stderr)

        for cat in ("allow", "deny", "ask"):
            existing_set = set(existing.get("permissions", {}).get(cat, []))
            new_set = set(new.get("permissions", {}).get(cat, []))
            added = new_set - existing_set
            if added:
                print(f"permissions.{cat} to add: {len(added)} rules", file=sys.stderr)
        return

    # Backup existing
    if os.path.exists(existing_path):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{existing_path}.bak.{ts}"
        shutil.copy2(existing_path, backup)
        print(f"📦 Backed up: {backup}")

    with open(existing_path, "w") as f:
        json.dump(merged, f, indent=2)
        f.write("\n")

    print(f"✅ Merged into: {existing_path}")

    # Summary
    hook_events = list(merged.get("hooks", {}).keys())
    allow_count = len(merged.get("permissions", {}).get("allow", []))
    deny_count = len(merged.get("permissions", {}).get("deny", []))
    ask_count = len(merged.get("permissions", {}).get("ask", []))
    print(f"   Hooks: {', '.join(hook_events)}")
    print(f"   Permissions: {allow_count} allow, {deny_count} deny, {ask_count} ask")

if __name__ == "__main__":
    main()
