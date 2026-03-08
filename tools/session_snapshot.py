#!/usr/bin/env python3
"""
Session State Snapshot System for OMG

Captures `.omg/state/` directory, compresses it, versions snapshots,
and stores them in `.omg/state/snapshots/`.

Feature flag: OMG_SNAPSHOT_ENABLED (default: False)
"""

import json
import os
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Lazy import from hooks
def _get_feature_flag_enabled() -> bool:
    """Check if snapshot feature is enabled."""
    env_val = os.environ.get("OMG_SNAPSHOT_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True

    # Lazy import from hooks
    hooks_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks")
    )
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        from _common import get_feature_flag  # type: ignore[import-untyped]
        return get_feature_flag("SNAPSHOT", default=False)
    except ImportError:
        return False


def _get_atomic_json_write():
    """Lazy-import atomic_json_write from hooks/_common.py."""
    hooks_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks")
    )
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        from _common import atomic_json_write  # type: ignore[import-untyped]
        return atomic_json_write
    except ImportError:
        return None


def create_snapshot(name: Optional[str] = None, state_dir: str = ".omg/state") -> Dict[str, Any]:
    """
    Capture `.omg/state/` directory and create a compressed snapshot.

    Args:
        name: Optional name suffix for the snapshot
        state_dir: Path to the state directory (default: ".omg/state")

    Returns:
        Snapshot metadata dict with keys: id, name, created_at, files_count, compressed_size, state_dir
        or {"skipped": True} if feature flag is disabled
    """
    if not _get_feature_flag_enabled():
        return {"skipped": True}

    # Generate snapshot ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_id = f"{timestamp}_{name}" if name else timestamp

    # Ensure snapshots directory exists
    snapshots_dir = os.path.join(state_dir, "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)

    # Paths for snapshot files
    snapshot_tar_path = os.path.join(snapshots_dir, f"{snapshot_id}.tar.gz")
    snapshot_meta_path = os.path.join(snapshots_dir, f"{snapshot_id}.json")

    # Files to exclude
    exclude_patterns = {
        "snapshots",  # Don't snapshot the snapshots directory itself
        "credentials.enc",
        "credentials.meta",
    }

    # Create tar.gz archive
    files_count = 0
    try:
        with tarfile.open(snapshot_tar_path, "w:gz") as tar:
            for root, dirs, files in os.walk(state_dir):
                # Filter out excluded directories
                dirs[:] = [d for d in dirs if d not in exclude_patterns]

                for file in files:
                    file_path = os.path.join(root, file)
                    # Skip excluded files
                    if file in exclude_patterns:
                        continue

                    # Calculate arcname (relative path in archive)
                    arcname = os.path.relpath(file_path, state_dir)
                    tar.add(file_path, arcname=arcname)
                    files_count += 1

    except Exception as e:
        print(f"[OMG] Error creating snapshot: {e}", file=sys.stderr)
        return {"error": str(e)}

    # Get compressed size
    compressed_size = os.path.getsize(snapshot_tar_path) if os.path.exists(snapshot_tar_path) else 0

    # Create metadata
    metadata = {
        "id": snapshot_id,
        "name": name or "",
        "created_at": datetime.now().isoformat(),
        "files_count": files_count,
        "compressed_size": compressed_size,
        "state_dir": state_dir,
    }

    # Write metadata atomically
    atomic_json_write = _get_atomic_json_write()
    if atomic_json_write:
        atomic_json_write(snapshot_meta_path, metadata)
    else:
        # Fallback: write without atomic guarantee
        try:
            with open(snapshot_meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, separators=(",", ":"))
        except Exception as e:
            print(f"[OMG] Error writing metadata: {e}", file=sys.stderr)

    return metadata


def list_snapshots(state_dir: str = ".omg/state") -> List[Dict[str, Any]]:
    """
    List all available snapshots.

    Args:
        state_dir: Path to the state directory (default: ".omg/state")

    Returns:
        List of snapshot metadata dicts, sorted by created_at descending (newest first)
    """
    snapshots_dir = os.path.join(state_dir, "snapshots")
    if not os.path.isdir(snapshots_dir):
        return []

    snapshots = []
    try:
        for file in os.listdir(snapshots_dir):
            if file.endswith(".json"):
                meta_path = os.path.join(snapshots_dir, file)
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                        snapshots.append(metadata)
                except (json.JSONDecodeError, OSError):
                    pass  # Skip invalid metadata files
    except OSError:
        pass

    # Sort by created_at descending (newest first)
    snapshots.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return snapshots


def restore_snapshot(snapshot_id: str, state_dir: str = ".omg/state") -> bool:
    """
    Restore a snapshot to the state directory.

    Args:
        snapshot_id: ID of the snapshot to restore
        state_dir: Path to the state directory (default: ".omg/state")

    Returns:
        True if restored successfully, False if snapshot not found
    """
    snapshots_dir = os.path.join(state_dir, "snapshots")
    snapshot_tar_path = os.path.join(snapshots_dir, f"{snapshot_id}.tar.gz")

    if not os.path.exists(snapshot_tar_path):
        return False

    try:
        with tarfile.open(snapshot_tar_path, "r:gz") as tar:
            # Use filter='data' for Python 3.14+ compatibility
            try:
                tar.extractall(path=state_dir, filter='data')
            except TypeError:
                # Fallback for Python < 3.12
                tar.extractall(path=state_dir)
        return True
    except Exception as e:
        print(f"[OMG] Error restoring snapshot: {e}", file=sys.stderr)
        return False


def delete_snapshot(snapshot_id: str, state_dir: str = ".omg/state") -> bool:
    """
    Delete a snapshot.

    Args:
        snapshot_id: ID of the snapshot to delete
        state_dir: Path to the state directory (default: ".omg/state")

    Returns:
        True if deleted successfully, False if snapshot not found
    """
    snapshots_dir = os.path.join(state_dir, "snapshots")
    snapshot_tar_path = os.path.join(snapshots_dir, f"{snapshot_id}.tar.gz")
    snapshot_meta_path = os.path.join(snapshots_dir, f"{snapshot_id}.json")

    deleted = False
    try:
        if os.path.exists(snapshot_tar_path):
            os.remove(snapshot_tar_path)
            deleted = True
    except OSError as e:
        print(f"[OMG] Error deleting snapshot tar: {e}", file=sys.stderr)

    try:
        if os.path.exists(snapshot_meta_path):
            os.remove(snapshot_meta_path)
            deleted = True
    except OSError as e:
        print(f"[OMG] Error deleting snapshot metadata: {e}", file=sys.stderr)

    return deleted


# --- Branch / Fork API ---


def _get_branching_flag_enabled() -> bool:
    """Check if branching feature is enabled."""
    env_val = os.environ.get("OMG_BRANCHING_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True

    # Lazy import from hooks
    hooks_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks")
    )
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        from _common import get_feature_flag  # type: ignore[import-untyped]
        return get_feature_flag("BRANCHING", default=False)
    except ImportError:
        return False


def create_branch(
    name: str,
    from_snapshot_id: Optional[str] = None,
    state_dir: str = ".omg/state",
) -> Dict[str, Any]:
    """
    Create a named branch from a snapshot or the current state.

    Args:
        name: Branch name (must be non-empty, no slashes)
        from_snapshot_id: Optional snapshot ID to branch from.
            If provided, restores that snapshot first.
            Otherwise, creates a new snapshot automatically.
        state_dir: Path to the state directory (default: ".omg/state")

    Returns:
        Branch metadata dict with keys: name, snapshot_id, created_at,
        parent_branch, status.
        Or {"skipped": True} if feature flag is disabled.
    """
    if not _get_branching_flag_enabled():
        return {"skipped": True}

    if not name or "/" in name:
        return {"error": "Invalid branch name: must be non-empty with no slashes"}

    # Resolve source snapshot
    if from_snapshot_id:
        # Verify snapshot exists before restoring
        snapshots_dir = os.path.join(state_dir, "snapshots")
        tar_path = os.path.join(snapshots_dir, f"{from_snapshot_id}.tar.gz")
        if not os.path.exists(tar_path):
            return {"error": f"Snapshot not found: {from_snapshot_id}"}
        restore_snapshot(from_snapshot_id, state_dir=state_dir)
        snapshot_id = from_snapshot_id
    else:
        # Create a fresh snapshot for this branch
        snap = create_snapshot(name=name, state_dir=state_dir)
        if snap.get("error") or snap.get("skipped"):
            return snap
        snapshot_id = snap["id"]

    # Read current branch (parent)
    current_branch_path = os.path.join(state_dir, "current_branch.json")
    parent_branch: Optional[str] = None
    if os.path.exists(current_branch_path):
        try:
            with open(current_branch_path, "r", encoding="utf-8") as f:
                cb = json.load(f)
                parent_branch = cb.get("name")
        except (json.JSONDecodeError, OSError):
            pass

    # Build branch metadata
    metadata: Dict[str, Any] = {
        "name": name,
        "snapshot_id": snapshot_id,
        "created_at": datetime.now().isoformat(),
        "parent_branch": parent_branch,
        "status": "active",
    }

    # Write branch metadata
    branches_dir = os.path.join(state_dir, "branches")
    os.makedirs(branches_dir, exist_ok=True)
    branch_path = os.path.join(branches_dir, f"{name}.json")

    atomic_json_write = _get_atomic_json_write()
    if atomic_json_write:
        atomic_json_write(branch_path, metadata)
    else:
        try:
            with open(branch_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, separators=(",", ":"))
        except Exception as e:
            print(f"[OMG] Error writing branch metadata: {e}", file=sys.stderr)
            return {"error": str(e)}

    # Update current branch tracker
    _update_current_branch(name, state_dir=state_dir)

    return metadata


def list_branches(state_dir: str = ".omg/state") -> List[Dict[str, Any]]:
    """
    List all branches with metadata.

    Args:
        state_dir: Path to the state directory (default: ".omg/state")

    Returns:
        List of branch metadata dicts, sorted by created_at descending (newest first)
    """
    branches_dir = os.path.join(state_dir, "branches")
    if not os.path.isdir(branches_dir):
        return []

    branches: List[Dict[str, Any]] = []
    try:
        for file in os.listdir(branches_dir):
            if file.endswith(".json"):
                branch_path = os.path.join(branches_dir, file)
                try:
                    with open(branch_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                        branches.append(metadata)
                except (json.JSONDecodeError, OSError):
                    pass  # Skip invalid metadata files
    except OSError:
        pass

    # Sort by created_at descending (newest first)
    branches.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return branches


def switch_branch(name: str, state_dir: str = ".omg/state") -> bool:
    """
    Switch to a named branch by restoring its snapshot.

    Args:
        name: Branch name to switch to
        state_dir: Path to the state directory (default: ".omg/state")

    Returns:
        True if switched successfully, False otherwise
    """
    branches_dir = os.path.join(state_dir, "branches")
    branch_path = os.path.join(branches_dir, f"{name}.json")

    if not os.path.exists(branch_path):
        return False

    try:
        with open(branch_path, "r", encoding="utf-8") as f:
            branch_meta = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False

    snapshot_id = branch_meta.get("snapshot_id")
    if not snapshot_id:
        return False

    if not restore_snapshot(snapshot_id, state_dir=state_dir):
        return False

    _update_current_branch(name, state_dir=state_dir)
    return True


def _update_current_branch(name: str, state_dir: str = ".omg/state") -> None:
    """Update the current branch tracker file."""
    current_branch_path = os.path.join(state_dir, "current_branch.json")
    data = {"name": name, "switched_at": datetime.now().isoformat()}
    atomic_json_write = _get_atomic_json_write()
    if atomic_json_write:
        atomic_json_write(current_branch_path, data)
    else:
        try:
            with open(current_branch_path, "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"))
        except Exception as e:
            print(f"[OMG] Error updating current branch: {e}", file=sys.stderr)


# --- Merge API ---


def _get_merge_flag_enabled() -> bool:
    """Check if merge feature is enabled."""
    env_val = os.environ.get("OMG_MERGE_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True

    # Lazy import from hooks
    hooks_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks")
    )
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        from _common import get_feature_flag  # type: ignore[import-untyped]
        return get_feature_flag("MERGE", default=False)
    except ImportError:
        return False


def _load_branch_state(branch_name: str, state_dir: str = ".omg/state") -> Optional[Dict[str, Any]]:
    """Load a branch's metadata as a flat state dict.

    Args:
        branch_name: Name of the branch to load
        state_dir: Path to the state directory

    Returns:
        Branch metadata dict, or None if branch does not exist or is invalid.
    """
    branch_path = os.path.join(state_dir, "branches", f"{branch_name}.json")
    if not os.path.exists(branch_path):
        return None
    try:
        with open(branch_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def detect_merge_conflicts(
    source_state: Dict[str, Any], target_state: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Compare two state dicts and find keys where both sides have different values.

    Args:
        source_state: State dict from the source branch
        target_state: State dict from the target branch

    Returns:
        List of conflict dicts with keys: key, source_value, target_value, conflict_type.
        conflict_type is "value_conflict" when both sides changed the same key
        to different values.
    """
    conflicts: List[Dict[str, Any]] = []
    # Find keys present in both dicts with different values
    common_keys = set(source_state.keys()) & set(target_state.keys())
    for key in sorted(common_keys):
        source_val = source_state[key]
        target_val = target_state[key]
        if source_val != target_val:
            conflicts.append({
                "key": key,
                "source_value": source_val,
                "target_value": target_val,
                "conflict_type": "value_conflict",
            })
    return conflicts


_BRANCH_META_KEYS = frozenset({
    "name", "created_at", "snapshot_id", "parent_branch",
    "status", "switched_at", "merged_at", "merged_into",
})


def _strip_branch_meta(state: Dict[str, Any]) -> Dict[str, Any]:
    """Return *state* without branch-level metadata keys."""
    return {k: v for k, v in state.items() if k not in _BRANCH_META_KEYS}


def preview_merge(
    source_branch: str,
    target_branch: str = "main",
    state_dir: str = ".omg/state",
) -> Dict[str, Any]:
    """Preview a merge without applying changes.

    Loads both branch snapshot states (as flat JSON dicts from snapshot
    metadata), strips branch-level metadata keys that always differ,
    and detects conflicts on the remaining user-state keys.

    Args:
        source_branch: Branch to merge from
        target_branch: Branch to merge into (default: "main")
        state_dir: Path to the state directory

    Returns:
        Preview dict with keys: source, target, conflicts, changes, preview.
        Or {"skipped": True} if feature flag is disabled.
        Or {"error": ...} if a branch cannot be found.
    """
    if not _get_merge_flag_enabled():
        return {"skipped": True}

    source_state = _load_branch_state(source_branch, state_dir=state_dir)
    if source_state is None:
        return {"error": f"Source branch not found: {source_branch}"}

    target_state = _load_branch_state(target_branch, state_dir=state_dir)
    if target_state is None:
        return {"error": f"Target branch not found: {target_branch}"}

    source_user = _strip_branch_meta(source_state)
    target_user = _strip_branch_meta(target_state)
    conflicts = detect_merge_conflicts(source_user, target_user)

    source_only_keys = set(source_user.keys()) - set(target_user.keys())
    changes = len(source_only_keys) + len(conflicts)

    return {
        "source": source_branch,
        "target": target_branch,
        "conflicts": conflicts,
        "changes": changes,
        "preview": True,
    }


def merge_branch(
    source_branch: str,
    target_branch: str = "main",
    state_dir: str = ".omg/state",
) -> Dict[str, Any]:
    """Merge source branch state into target branch.

    Uses last-write-wins strategy when there are no conflicts.
    If conflicts exist, the merge is aborted and conflicts are returned.

    Args:
        source_branch: Branch to merge from
        target_branch: Branch to merge into (default: "main")
        state_dir: Path to the state directory

    Returns:
        Result dict with keys: merged, conflicts, changes_applied.
        Or {"skipped": True} if feature flag is disabled.
        Or {"error": ...} on failure.
    """
    if not _get_merge_flag_enabled():
        return {"skipped": True}

    source_state = _load_branch_state(source_branch, state_dir=state_dir)
    if source_state is None:
        return {"error": f"Source branch not found: {source_branch}"}

    target_state = _load_branch_state(target_branch, state_dir=state_dir)
    if target_state is None:
        return {"error": f"Target branch not found: {target_branch}"}

    source_user = _strip_branch_meta(source_state)
    target_user = _strip_branch_meta(target_state)
    conflicts = detect_merge_conflicts(source_user, target_user)

    if conflicts:
        return {
            "merged": False,
            "conflicts": conflicts,
            "changes_applied": 0,
        }

    merged_state = {**target_state, **source_state}
    merged_state["name"] = target_branch
    merged_state["status"] = "active"

    source_only_keys = set(source_user.keys()) - set(target_user.keys())
    changes_applied = len(source_only_keys)

    # Write merged state to target branch file
    target_branch_path = os.path.join(state_dir, "branches", f"{target_branch}.json")
    atomic_json_write = _get_atomic_json_write()
    if atomic_json_write:
        atomic_json_write(target_branch_path, merged_state)
    else:
        try:
            os.makedirs(os.path.dirname(target_branch_path), exist_ok=True)
            with open(target_branch_path, "w", encoding="utf-8") as f:
                json.dump(merged_state, f, separators=(",", ":"))
        except Exception as e:
            return {"error": f"Failed to write merged state: {e}"}

    # Mark source branch as merged
    source_branch_path = os.path.join(state_dir, "branches", f"{source_branch}.json")
    if source_state:
        source_state["status"] = "merged"
        source_state["merged_into"] = target_branch
        source_state["merged_at"] = datetime.now().isoformat()
        if atomic_json_write:
            atomic_json_write(source_branch_path, source_state)
        else:
            try:
                with open(source_branch_path, "w", encoding="utf-8") as f:
                    json.dump(source_state, f, separators=(",", ":"))
            except Exception as e:
                print(f"[OMG] Error updating source branch status: {e}", file=sys.stderr)

    # Update current_branch.json to reflect merged state
    _update_current_branch(target_branch, state_dir=state_dir)

    return {
        "merged": True,
        "conflicts": [],
        "changes_applied": changes_applied,
    }

def fork_branch(
    from_snapshot_id: str,
    name: str,
    state_dir: str = ".omg/state",
) -> Dict[str, Any]:
    """Fork a new branch from a specific snapshot checkpoint.

    This is a convenience wrapper around ``create_branch`` that always
    requires a source snapshot ID.

    Args:
        from_snapshot_id: Snapshot ID to fork from (required, non-empty).
        name: Name for the new branch (required, non-empty, no slashes).
        state_dir: Path to the state directory (default: ".omg/state").

    Returns:
        Branch metadata dict on success, ``{"skipped": True}`` if feature
        flag is disabled, or ``{"error": ...}`` on failure.
    """
    if not _get_branching_flag_enabled():
        return {"skipped": True}

    if not from_snapshot_id:
        return {"error": "fork_branch requires a non-empty snapshot ID"}
    if not name or "/" in name:
        return {"error": "Invalid branch name: must be non-empty with no slashes"}

    return create_branch(name, from_snapshot_id=from_snapshot_id, state_dir=state_dir)


# Public alias expected by callers (canonical name is preview_merge)
merge_preview = preview_merge


def get_status(state_dir: str = ".omg/state") -> Dict[str, Any]:
    """
    Get the current branch name and total snapshot count.

    Args:
        state_dir: Path to the state directory (default: ".omg/state")

    Returns:
        Dict with keys: current_branch, snapshot_count
    """
    # Get current branch
    current_branch = None
    current_branch_path = os.path.join(state_dir, "current_branch.json")
    if os.path.exists(current_branch_path):
        try:
            with open(current_branch_path, "r", encoding="utf-8") as f:
                cb = json.load(f)
                current_branch = cb.get("name")
        except (json.JSONDecodeError, OSError):
            pass

    # Get snapshot count
    snapshots = list_snapshots(state_dir=state_dir)
    snapshot_count = len(snapshots)

    return {
        "current_branch": current_branch,
        "snapshot_count": snapshot_count,
    }


def main():
    """CLI entry point."""
    state_dir = os.environ.get("OMG_STATE_DIR", ".omg/state")

    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        _dest = sys.stdout if (len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h")) else sys.stderr
        _code = 0 if _dest is sys.stdout else 1
        print(
            "Usage: python3 session_snapshot.py <command> [options]",
            file=_dest,
        )
        print("Commands:", file=_dest)
        print("  status                Show current branch and snapshot count", file=_dest)
        print("  create [--name NAME]  Create a snapshot", file=_dest)
        print("  list                  List all snapshots", file=_dest)
        print("  restore <snapshot_id> Restore a snapshot", file=_dest)
        print("  delete <snapshot_id>  Delete a snapshot", file=_dest)
        print("  branch <name>        Create a branch", file=_dest)
        print("  branches             List all branches", file=_dest)
        print("  switch <name>        Switch to a branch", file=_dest)
        print("  fork --from <snapshot_id> --name <name>  Fork from snapshot", file=_dest)
        print("  merge <source> [--into <target>]  Merge branches", file=_dest)
        print("  merge-preview <source> [--into <target>]  Preview merge", file=_dest)
        sys.exit(_code)

    command = sys.argv[1]

    if command == "status":
        result = get_status(state_dir=state_dir)
        print(json.dumps(result, indent=2))

    elif command == "create":
        name = None
        if len(sys.argv) > 3 and sys.argv[2] == "--name":
            name = sys.argv[3]
        result = create_snapshot(name=name, state_dir=state_dir)
        print(json.dumps(result, indent=2))

    elif command == "list":
        snapshots = list_snapshots(state_dir=state_dir)
        print(json.dumps(snapshots, indent=2))

    elif command == "restore":
        if len(sys.argv) < 3:
            print("Usage: python3 session_snapshot.py restore <snapshot_id>", file=sys.stderr)
            sys.exit(1)
        snapshot_id = sys.argv[2]
        success = restore_snapshot(snapshot_id, state_dir=state_dir)
        result = {"success": success, "snapshot_id": snapshot_id}
        print(json.dumps(result, indent=2))

    elif command == "delete":
        if len(sys.argv) < 3:
            print("Usage: python3 session_snapshot.py delete <snapshot_id>", file=sys.stderr)
            sys.exit(1)
        snapshot_id = sys.argv[2]
        success = delete_snapshot(snapshot_id, state_dir=state_dir)
        result = {"success": success, "snapshot_id": snapshot_id}
        print(json.dumps(result, indent=2))

    elif command == "branch":
        if len(sys.argv) < 3:
            print("Usage: python3 session_snapshot.py branch <name> [--from <snapshot_id>]", file=sys.stderr)
            sys.exit(1)
        branch_name = sys.argv[2]
        from_id = None
        if len(sys.argv) > 4 and sys.argv[3] == "--from":
            from_id = sys.argv[4]
        result = create_branch(branch_name, from_snapshot_id=from_id, state_dir=state_dir)
        print(json.dumps(result, indent=2))

    elif command == "branches":
        branches = list_branches(state_dir=state_dir)
        print(json.dumps(branches, indent=2))

    elif command == "switch":
        if len(sys.argv) < 3:
            print("Usage: python3 session_snapshot.py switch <name>", file=sys.stderr)
            sys.exit(1)
        branch_name = sys.argv[2]
        success = switch_branch(branch_name, state_dir=state_dir)
        result = {"success": success, "branch": branch_name}
        print(json.dumps(result, indent=2))

    elif command == "merge":
        if len(sys.argv) < 3:
            print("Usage: python3 session_snapshot.py merge <source> [--into <target>]", file=sys.stderr)
            sys.exit(1)
        source = sys.argv[2]
        target = "main"
        if len(sys.argv) > 4 and sys.argv[3] == "--into":
            target = sys.argv[4]
        result = merge_branch(source, target_branch=target, state_dir=state_dir)
        print(json.dumps(result, indent=2))

    elif command == "fork":
        from_id = None
        fork_name = None
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--from" and i + 1 < len(sys.argv):
                from_id = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--name" and i + 1 < len(sys.argv):
                fork_name = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        if not from_id or not fork_name:
            print("Usage: python3 session_snapshot.py fork --from <snapshot_id> --name <name>", file=sys.stderr)
            sys.exit(1)
        result = fork_branch(from_snapshot_id=from_id, name=fork_name, state_dir=state_dir)
        print(json.dumps(result, indent=2))

    elif command == "merge-preview":
        if len(sys.argv) < 3:
            print("Usage: python3 session_snapshot.py merge-preview <source> [--into <target>]", file=sys.stderr)
            sys.exit(1)
        source = sys.argv[2]
        target = "main"
        if len(sys.argv) > 4 and sys.argv[3] == "--into":
            target = sys.argv[4]
        result = preview_merge(source, target_branch=target, state_dir=state_dir)
        print(json.dumps(result, indent=2))

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
