#!/usr/bin/env python3
"""OMG Migration Script — Migrate OMC settings to OMG.

Handles:
  1. Back up current ~/.claude/settings.json
  2. Deploy OMG hooks to ~/.claude/hooks/
  3. Deduplicate hooks in settings.json (remove double-registered entries)
  4. Fix common format bugs (ConfigChange wrapper, etc.)
  5. Switch statusLine from OMC HUD to OMG HUD
  6. Remove dead/erroring plugins
  7. Deploy OMG HUD to ~/.claude/hud/

Idempotent — safe to run multiple times. Always creates a backup first.

Usage:
  python3 scripts/migrate-legacy.py                  # full migration
  python3 scripts/migrate-legacy.py --dry-run        # preview changes only
  python3 scripts/migrate-legacy.py --hooks-only      # only deploy hooks
  python3 scripts/migrate-legacy.py --hud-only        # only switch HUD
  python3 scripts/migrate-legacy.py --restore BACKUP  # restore a backup
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths ────────────────────────────────────────────────────────────────────
OMG_ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"
HOOKS_DIR = CLAUDE_DIR / "hooks"
HUD_DIR = CLAUDE_DIR / "hud"
BACKUP_DIR = CLAUDE_DIR / ".omg-backups"

OMG_HOOKS_DIR = OMG_ROOT / "hooks"
OMG_HUD_SRC = OMG_ROOT / "hud" / "omg-hud.mjs"
OMG_VERSION_TAG = "omg-v1"

# ── Hook canonical definitions ───────────────────────────────────────────────
# Single source of truth for which hooks run on which events.
# This eliminates duplication regardless of how many times migration runs.
CANONICAL_HOOKS: dict[str, list[dict[str, Any]]] = {
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/firewall.py"', "timeout": 5}],
        },
        {
            "matcher": "Read|Write|Edit|MultiEdit",
            "hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/secret-guard.py"', "timeout": 5}],
        },
    ],
    "PostToolUse": [
        {
            "matcher": "Bash|Write|Edit|MultiEdit",
            "hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/tool-ledger.py"', "timeout": 10}],
        },
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/circuit-breaker.py"', "timeout": 10}],
        },
        {
            "matcher": "Write|Edit|MultiEdit",
            "hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/post-write.py"', "timeout": 30}],
        },
        {
            "matcher": "Write|Edit|MultiEdit",
            "hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/shadow_manager.py"', "timeout": 15}],
        },
    ],
    "Stop": [
        {
            "hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/quality-gate.py"', "timeout": 10}],
        },
        {
            "hooks": [
                {"type": "command", "command": 'python3 "$HOME/.claude/hooks/stop-gate.py"', "timeout": 15},
                {"type": "command", "command": 'python3 "$HOME/.claude/hooks/test-validator.py"', "timeout": 30},
                {"type": "command", "command": 'python3 "$HOME/.claude/hooks/quality-runner.py"', "timeout": 180},
            ],
        },
    ],
    "PreCompact": [
        {
            "hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/pre-compact.py"', "timeout": 15}],
        },
    ],
    "SessionStart": [
        {
            "hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/session-start.py"', "timeout": 10}],
        },
    ],
    "UserPromptSubmit": [
        {
            "hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/prompt-enhancer.py"', "timeout": 10}],
        },
    ],
    "ConfigChange": [
        {
            "hooks": [{"type": "command", "command": 'python3 "$HOME/.claude/hooks/config-guard.py"', "timeout": 10}],
        },
    ],
}

# Plugins to remove (known dead/erroring)
DEAD_PLUGINS = [
    "claude-delegator@jarrodwatts-claude-delegator",
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def backup_settings() -> Path | None:
    """Create a timestamped backup of settings.json. Returns backup path."""
    if not SETTINGS_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"settings-{timestamp()}.json"
    shutil.copy2(SETTINGS_PATH, dest)
    return dest


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {"$schema": "https://json.schemastore.org/claude-code-settings.json"}
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_settings(settings: dict[str, Any]) -> None:
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ── Migration steps ──────────────────────────────────────────────────────────

def step_deploy_hooks(dry_run: bool) -> list[str]:
    """Copy OMG hook files to ~/.claude/hooks/."""
    changes: list[str] = []
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)

    hook_files = [f for f in OMG_HOOKS_DIR.iterdir() if f.suffix == ".py" and not f.name.startswith("__")]
    for src in sorted(hook_files):
        dest = HOOKS_DIR / src.name
        # Check if update needed
        if dest.exists():
            src_content = src.read_bytes()
            dest_content = dest.read_bytes()
            if src_content == dest_content:
                continue
        changes.append(f"  hooks/{src.name} -> ~/.claude/hooks/{src.name}")
        if not dry_run:
            shutil.copy2(src, dest)
            dest.chmod(0o755)

    # Write version marker
    version_file = HOOKS_DIR / ".omg-version"
    tag = f"{OMG_VERSION_TAG}-{timestamp()[:8]}"
    if not dry_run:
        version_file.write_text(tag + "\n", encoding="utf-8")
    changes.append(f"  .omg-version = {tag}")

    # Write coexist marker
    coexist_file = HOOKS_DIR / ".omg-coexist"
    if not dry_run:
        coexist_file.write_text("omc-coexist\n", encoding="utf-8")

    return changes


def step_deduplicate_hooks(settings: dict[str, Any], dry_run: bool) -> list[str]:
    """Replace all hook entries with the canonical set."""
    changes: list[str] = []
    old_hooks = settings.get("hooks", {})

    # Count old entries for reporting
    old_count = sum(
        len(v) if isinstance(v, list) else 1
        for v in old_hooks.values()
    )
    new_count = sum(len(v) for v in CANONICAL_HOOKS.values())

    if old_hooks != CANONICAL_HOOKS:
        changes.append(f"  hooks: {old_count} entries -> {new_count} canonical entries")
        if not dry_run:
            settings["hooks"] = CANONICAL_HOOKS

    return changes


def step_switch_hud(settings: dict[str, Any], dry_run: bool) -> list[str]:
    """Switch statusLine to OMG HUD."""
    changes: list[str] = []

    # Deploy OMG HUD file
    HUD_DIR.mkdir(parents=True, exist_ok=True)
    hud_dest = HUD_DIR / "omg-hud.mjs"
    if OMG_HUD_SRC.exists():
        if hud_dest.exists():
            if OMG_HUD_SRC.read_bytes() != hud_dest.read_bytes():
                changes.append(f"  hud/omg-hud.mjs updated")
                if not dry_run:
                    shutil.copy2(OMG_HUD_SRC, hud_dest)
        else:
            changes.append(f"  hud/omg-hud.mjs deployed")
            if not dry_run:
                shutil.copy2(OMG_HUD_SRC, hud_dest)

    # Update statusLine in settings
    old_sl = settings.get("statusLine", {})
    new_sl = {"type": "command", "command": "node ~/.claude/hud/omg-hud.mjs"}
    if old_sl != new_sl:
        old_cmd = old_sl.get("command", "(none)")
        changes.append(f"  statusLine: {old_cmd} -> node ~/.claude/hud/omg-hud.mjs")
        if not dry_run:
            settings["statusLine"] = new_sl

    return changes


def step_clean_plugins(settings: dict[str, Any], dry_run: bool) -> list[str]:
    """Remove dead/erroring plugins."""
    changes: list[str] = []
    plugins = settings.get("enabledPlugins", {})

    for plugin_id in DEAD_PLUGINS:
        if plugin_id in plugins:
            changes.append(f"  removed plugin: {plugin_id}")
            if not dry_run:
                del plugins[plugin_id]

    return changes


def step_fix_plugin_manifests(dry_run: bool) -> list[str]:
    """Fix known plugin manifest issues (unrecognized keys)."""
    changes: list[str] = []

    # Fix legacy plugin manifest
    manifest_path = CLAUDE_DIR / "plugins" / "cache" / "claude-plugins-official" / "omg-superpowers"
    if manifest_path.exists():
        for version_dir in manifest_path.iterdir():
            plugin_json = version_dir / ".claude-plugin" / "plugin.json"
            if plugin_json.exists():
                try:
                    data = json.loads(plugin_json.read_text(encoding="utf-8"))
                    bad_keys = [k for k in ("category", "source") if k in data]
                    if bad_keys:
                        changes.append(f"  fixed {plugin_json.relative_to(CLAUDE_DIR)}: removed {bad_keys}")
                        if not dry_run:
                            for k in bad_keys:
                                del data[k]
                            plugin_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                except (json.JSONDecodeError, OSError):
                    pass

    return changes


def step_add_comment(settings: dict[str, Any], dry_run: bool) -> list[str]:
    """Add OMG migration marker comment."""
    changes: list[str] = []
    marker = f"OMG v1 migrated {timestamp()[:8]}. Hooks canonical. HUD standalone."
    old_comment = settings.get("_comment", "")
    if "OMG" not in old_comment:
        changes.append(f"  _comment updated")
        if not dry_run:
            settings["_comment"] = marker
    return changes


# ── Remove hooks from project settings.json ──────────────────────────────────

def step_clean_project_settings(dry_run: bool) -> list[str]:
    """Remove hooks from OMG project settings.json to prevent double-execution."""
    changes: list[str] = []
    project_settings = OMG_ROOT / "settings.json"
    if not project_settings.exists():
        return changes

    try:
        data = json.loads(project_settings.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return changes

    if "hooks" in data:
        hook_count = sum(len(v) if isinstance(v, list) else 1 for v in data["hooks"].values())
        changes.append(f"  project settings.json: removed {hook_count} hook entries (already in user-level)")
        if not dry_run:
            del data["hooks"]
            project_settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return changes


# ── Restore ──────────────────────────────────────────────────────────────────

def restore_backup(backup_path: str) -> None:
    p = Path(backup_path)
    if not p.exists():
        print(f"ERROR: backup not found: {p}", file=sys.stderr)
        sys.exit(1)
    # Validate JSON
    try:
        json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in backup: {e}", file=sys.stderr)
        sys.exit(1)
    shutil.copy2(p, SETTINGS_PATH)
    print(f"Restored {SETTINGS_PATH} from {p}")


# ── Main ─────────────────────────────────────────────────────────────────────

def run_migration(
    dry_run: bool = False,
    hooks_only: bool = False,
    hud_only: bool = False,
) -> int:
    print(f"{'[DRY RUN] ' if dry_run else ''}OMG Migration v1")
    print(f"  OMG root:  {OMG_ROOT}")
    print(f"  Claude:    {CLAUDE_DIR}")
    print()

    # Backup
    if not dry_run:
        backup = backup_settings()
        if backup:
            print(f"Backup: {backup}")
        print()

    settings = load_settings()
    all_changes: list[str] = []

    # Step 1: Deploy hooks
    if not hud_only:
        print("Step 1: Deploy hooks")
        changes = step_deploy_hooks(dry_run)
        all_changes.extend(changes)
        for c in changes:
            print(c)
        if not changes:
            print("  (no changes)")
        print()

    # Step 2: Deduplicate hooks in settings
    if not hud_only:
        print("Step 2: Deduplicate hooks in settings.json")
        changes = step_deduplicate_hooks(settings, dry_run)
        all_changes.extend(changes)
        for c in changes:
            print(c)
        if not changes:
            print("  (already canonical)")
        print()

    # Step 3: Switch HUD
    if not hooks_only:
        print("Step 3: Switch to OMG HUD")
        changes = step_switch_hud(settings, dry_run)
        all_changes.extend(changes)
        for c in changes:
            print(c)
        if not changes:
            print("  (already using OMG HUD)")
        print()

    # Step 4: Clean plugins
    if not hooks_only and not hud_only:
        print("Step 4: Clean dead plugins")
        changes = step_clean_plugins(settings, dry_run)
        all_changes.extend(changes)
        for c in changes:
            print(c)
        if not changes:
            print("  (none to remove)")
        print()

    # Step 5: Fix plugin manifests
    if not hooks_only and not hud_only:
        print("Step 5: Fix plugin manifests")
        changes = step_fix_plugin_manifests(dry_run)
        all_changes.extend(changes)
        for c in changes:
            print(c)
        if not changes:
            print("  (none to fix)")
        print()

    # Step 6: Clean project settings
    if not hud_only:
        print("Step 6: Clean project settings.json")
        changes = step_clean_project_settings(dry_run)
        all_changes.extend(changes)
        for c in changes:
            print(c)
        if not changes:
            print("  (already clean)")
        print()

    # Step 7: Add migration marker
    if not hooks_only and not hud_only:
        print("Step 7: Add migration marker")
        changes = step_add_comment(settings, dry_run)
        all_changes.extend(changes)
        for c in changes:
            print(c)
        if not changes:
            print("  (already marked)")
        print()

    # Save
    if not dry_run and all_changes:
        save_settings(settings)
        print(f"Saved {SETTINGS_PATH}")

    # Summary
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Migration complete: {len(all_changes)} changes")
    if dry_run and all_changes:
        print("  Run without --dry-run to apply changes.")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate-legacy",
        description="Migrate OMC settings to OMG. Idempotent — safe to run multiple times.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--hooks-only", action="store_true", help="Only deploy hooks")
    parser.add_argument("--hud-only", action="store_true", help="Only switch HUD")
    parser.add_argument("--restore", metavar="BACKUP", help="Restore a backup file")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.restore:
        restore_backup(args.restore)
        return 0

    return run_migration(
        dry_run=args.dry_run,
        hooks_only=args.hooks_only,
        hud_only=args.hud_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
