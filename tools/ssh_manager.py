#!/usr/bin/env python3
"""
SSH Connection Manager for OMG

Manages SSH connection specs without requiring actual SSH libraries.
Functions are SPEC GENERATORS — they don't make real SSH connections.
Connection pool tracks connection metadata for orchestration use.

Feature flag: OMG_SSH_ENABLED (default: False)
"""

import hashlib
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# --- Lazy imports for hooks/_common.py ---

_get_feature_flag = None
_atomic_json_write = None


def _ensure_imports():
    """Lazy import feature flag and atomic write from hooks/_common.py."""
    global _get_feature_flag, _atomic_json_write
    if _get_feature_flag is not None:
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from hooks._common import get_feature_flag as _gff
        from hooks._common import atomic_json_write as _ajw
        _get_feature_flag = _gff
        _atomic_json_write = _ajw
    except ImportError:
        # Optional: hooks._common not available
        _get_feature_flag = None
        _atomic_json_write = None


# --- Feature flag ---

def _is_enabled() -> bool:
    """Check if SSH feature is enabled."""
    # Fast path: check env var directly
    env_val = os.environ.get("OMG_SSH_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True
    # Fallback to hooks/_common.get_feature_flag
    _ensure_imports()
    if _get_feature_flag is not None:
        return _get_feature_flag("SSH", default=False)
    return False


# --- Response helpers ---

def _success_response(result: Any) -> Dict[str, Any]:
    """Create a success response dict."""
    return {"success": True, "result": result, "error": None}


def _error_response(error: str) -> Dict[str, Any]:
    """Create an error response dict."""
    return {"success": False, "result": None, "error": error}


def _disabled_response() -> Dict[str, Any]:
    """Create a response for when the feature flag is disabled."""
    return _error_response("SSH feature is disabled (OMG_SSH_ENABLED=false)")


# =============================================================================
# Data Types
# =============================================================================


@dataclass
class SSHConnection:
    """SSH connection specification.

    Represents an SSH connection target with authentication details.
    This is a data container — no actual SSH connection is made.

    Attributes:
        host: Hostname or IP address.
        port: SSH port number (default: 22).
        user: Username for SSH authentication.
        key_path: Path to SSH private key file (optional).
        password: Password indicator — never stores actual password.
        shell: Default shell on the remote host.
        os_type: Operating system type of the remote host.
    """
    host: str
    port: int = 22
    user: str = ""
    key_path: Optional[str] = None
    password: Optional[str] = None
    shell: str = "bash"
    os_type: str = "linux"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a plain dictionary.

        Passwords are never included — only a ``password_set`` indicator.
        """
        data = asdict(self)
        # Never expose password in plain text
        has_password = data.pop("password", None) is not None
        data["password_set"] = has_password
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SSHConnection":
        """Create an SSHConnection from a dictionary.

        Accepts dicts with at least a 'host' key.
        Missing keys use defaults.
        """
        # Handle password_set indicator from serialized form
        password = None
        if data.get("password"):
            password = data["password"]
        elif data.get("password_set"):
            # Marker only — actual password is not stored
            password = "__SET__"

        return cls(
            host=data.get("host", ""),
            port=int(data.get("port", 22)),
            user=data.get("user", ""),
            key_path=data.get("key_path"),
            password=password,
            shell=data.get("shell", "bash"),
            os_type=data.get("os_type", "linux"),
        )


# =============================================================================
# Connection Pool — module-level state
# =============================================================================

# Active connections keyed by "host:port"
_connections: Dict[str, Dict[str, Any]] = {}

# Active SSHFS mounts keyed by local_path
_mounts: Dict[str, Dict[str, Any]] = {}


def _pool_key(host: str, port: int = 22) -> str:
    """Generate a connection pool key."""
    return f"{host}:{port}"


# =============================================================================
# Host Discovery
# =============================================================================


def discover_hosts(project_dir: str = ".") -> List[SSHConnection]:
    """Discover SSH hosts from project configuration files.

    Reads ``ssh.json`` or ``.ssh.json`` from the project directory.
    Returns an empty list if the feature flag is disabled, or if no
    configuration file is found.

    Expected JSON format::

        {
            "hosts": [
                {
                    "host": "server.example.com",
                    "port": 22,
                    "user": "ubuntu",
                    "key_path": "~/.ssh/id_rsa"
                }
            ]
        }

    Args:
        project_dir: Directory to search for ssh.json files.

    Returns:
        A list of SSHConnection objects discovered from configuration.
    """
    if not _is_enabled():
        return []

    abs_dir = os.path.abspath(project_dir)

    # Try ssh.json first, then .ssh.json
    for filename in ("ssh.json", ".ssh.json"):
        config_path = os.path.join(abs_dir, filename)
        if os.path.isfile(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                return []

            hosts_data = data.get("hosts", [])
            if not isinstance(hosts_data, list):
                return []

            connections = []
            for entry in hosts_data:
                if isinstance(entry, dict) and entry.get("host"):
                    # Expand ~ in key_path
                    if entry.get("key_path"):
                        entry["key_path"] = os.path.expanduser(entry["key_path"])
                    connections.append(SSHConnection.from_dict(entry))
            return connections

    return []


# =============================================================================
# Connection Management
# =============================================================================


def connect(
    host: str,
    port: int = 22,
    user: Optional[str] = None,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a connection spec and add it to the connection pool.

    This does NOT make an actual SSH connection — it generates a
    connection specification dict and registers it in the pool.

    Args:
        host: Hostname or IP address.
        port: SSH port (default: 22).
        user: Username for authentication.
        key_path: Path to SSH private key.
        password: Password for authentication (never stored in plaintext).

    Returns:
        A dict with connection spec on success, or error response if disabled.
    """
    if not _is_enabled():
        return _disabled_response()

    if not host or not isinstance(host, str):
        return _error_response("Host must be a non-empty string")

    # SSH policy check — block unapproved hosts
    policy = _check_ssh_policy(host, port)
    if not policy["allowed"]:
        return {
            "success": False,
            "result": None,
            "error": "Host not approved. Call approve_host() first.",
            "requires_approval": True,
        }

    session_id = uuid.uuid4().hex[:12]
    key = _pool_key(host, port)

    spec = {
        "host": host,
        "port": port,
        "user": user or os.environ.get("USER", ""),
        "connected": True,
        "session_id": session_id,
    }

    # Key path expansion
    if key_path:
        spec["key_path"] = os.path.expanduser(key_path)

    # Password indicator — NEVER store actual password
    spec["password_set"] = password is not None

    # Add to connection pool
    _connections[key] = spec

    return _success_response(spec)


def disconnect(host: str, port: int = 22) -> bool:
    """Remove a connection from the pool.

    Args:
        host: Hostname or IP of the connection to remove.
        port: Port of the connection (default: 22).

    Returns:
        True if the connection was found and removed, False otherwise.
    """
    if not _is_enabled():
        return False

    key = _pool_key(host, port)
    if key in _connections:
        del _connections[key]
        return True
    return False


def get_connections() -> List[Dict[str, Any]]:
    """List all active connections in the pool.

    Returns:
        A list of connection spec dicts. Empty list if disabled.
    """
    if not _is_enabled():
        return []

    return list(_connections.values())


# =============================================================================
# OS and Shell Detection
# =============================================================================


def detect_os(connection: Optional[Dict[str, Any]] = None) -> str:
    """Detect the operating system of a connection target.

    Since this is a spec generator (no actual SSH), returns sensible
    defaults based on connection metadata or "linux" as fallback.

    Args:
        connection: A connection spec dict (optional).

    Returns:
        One of "linux", "macos", "windows".
    """
    if not _is_enabled():
        return "unknown"

    if connection and isinstance(connection, dict):
        # Check if os_type was provided in connection metadata
        os_type = connection.get("os_type", "").lower()
        if os_type in ("linux", "macos", "windows"):
            return os_type

        # Heuristic: check host name patterns
        host = connection.get("host", "").lower()
        if "win" in host or "windows" in host:
            return "windows"
        if "mac" in host or "darwin" in host:
            return "macos"

    return "linux"


def detect_shell(connection: Optional[Dict[str, Any]] = None) -> str:
    """Detect the default shell of a connection target.

    Since this is a spec generator (no actual SSH), returns sensible
    defaults based on connection metadata or OS type.

    Args:
        connection: A connection spec dict (optional).

    Returns:
        One of "bash", "zsh", "sh", "powershell".
    """
    if not _is_enabled():
        return "unknown"

    if connection and isinstance(connection, dict):
        # Check if shell was provided in connection metadata
        shell = connection.get("shell", "").lower()
        if shell in ("bash", "zsh", "sh", "powershell", "fish"):
            return shell

        # Infer from OS
        os_type = detect_os(connection)
        if os_type == "windows":
            return "powershell"
        if os_type == "macos":
            return "zsh"

    return "bash"


# =============================================================================
# SSHFS Mount Management
# =============================================================================


def mount_sshfs(
    host: str,
    remote_path: str,
    local_path: str,
    user: Optional[str] = None,
    key_path: Optional[str] = None,
    port: int = 22,
) -> Dict[str, Any]:
    """Create an SSHFS mount spec and register it.

    This is a SPEC GENERATOR — no actual ``sshfs`` subprocess call is made.
    The mount spec is stored in the module-level ``_mounts`` registry.

    Args:
        host: Remote hostname or IP.
        remote_path: Path on the remote host to mount.
        local_path: Local mount point path.
        user: Username for SSH authentication.
        key_path: Path to SSH private key.
        port: SSH port (default: 22).

    Returns:
        Mount spec dict with success status and mount details.
    """
    if not _is_enabled():
        return _disabled_response()

    if not host or not isinstance(host, str):
        return _error_response("Host must be a non-empty string")

    if not remote_path or not isinstance(remote_path, str):
        return _error_response("Remote path must be a non-empty string")

    if not local_path or not isinstance(local_path, str):
        return _error_response("Local path must be a non-empty string")

    mount_id = f"{host}:{remote_path}"
    abs_local = os.path.abspath(local_path)

    spec = {
        "success": True,
        "host": host,
        "remote_path": remote_path,
        "local_path": abs_local,
        "mounted": True,
        "mount_id": mount_id,
        "port": port,
        "user": user or os.environ.get("USER", ""),
    }

    if key_path:
        spec["key_path"] = os.path.expanduser(key_path)

    _mounts[abs_local] = spec
    return spec


def unmount_sshfs(local_path: str) -> Dict[str, Any]:
    """Remove an SSHFS mount from the registry.

    Args:
        local_path: Local mount point to unmount.

    Returns:
        Dict with success status and unmount details.
    """
    if not _is_enabled():
        return _disabled_response()

    abs_local = os.path.abspath(local_path)

    if abs_local not in _mounts:
        return _error_response(f"No mount found at {abs_local}")

    removed = _mounts.pop(abs_local)
    return {
        "success": True,
        "host": removed["host"],
        "remote_path": removed["remote_path"],
        "local_path": abs_local,
        "mounted": False,
        "mount_id": removed["mount_id"],
    }


def get_mounts() -> List[Dict[str, Any]]:
    """List all active SSHFS mounts.

    Returns:
        List of mount spec dicts. Empty list if disabled.
    """
    if not _is_enabled():
        return []

    return list(_mounts.values())


def cleanup_mounts() -> int:
    """Unmount all SSHFS mounts and clear the registry.

    Returns:
        Number of mounts that were cleaned up.
    """
    if not _is_enabled():
        return 0

    count = len(_mounts)
    _mounts.clear()
    return count


def auto_mount_from_config(project_dir: str = ".") -> List[Dict[str, Any]]:
    """Read sshfs_mounts from ssh.json config and mount them.

    Reads ``ssh.json`` or ``.ssh.json`` from the project directory
    and processes the ``sshfs_mounts`` key.

    Expected JSON format::

        {
            "sshfs_mounts": [
                {
                    "host": "server.example.com",
                    "remote_path": "/home/user",
                    "local_path": "/mnt/remote",
                    "user": "ubuntu",
                    "port": 22
                }
            ]
        }

    Args:
        project_dir: Directory to search for ssh.json files.

    Returns:
        List of mount spec dicts for successfully registered mounts.
    """
    if not _is_enabled():
        return []

    abs_dir = os.path.abspath(project_dir)

    for filename in ("ssh.json", ".ssh.json"):
        config_path = os.path.join(abs_dir, filename)
        if os.path.isfile(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                return []

            mounts_data = data.get("sshfs_mounts", [])
            if not isinstance(mounts_data, list):
                return []

            results = []
            for entry in mounts_data:
                if not isinstance(entry, dict):
                    continue
                host = entry.get("host", "")
                remote_path = entry.get("remote_path", "")
                local_path = entry.get("local_path", "")
                if not host or not remote_path or not local_path:
                    continue

                spec = mount_sshfs(
                    host=host,
                    remote_path=remote_path,
                    local_path=local_path,
                    user=entry.get("user"),
                    key_path=entry.get("key_path"),
                    port=int(entry.get("port", 22)),
                )
                if isinstance(spec, dict) and spec.get("success"):
                    results.append(spec)

            return results

    return []


# =============================================================================
# SSH Policy Manager
# =============================================================================


# Default path for approved hosts state file
_SSH_APPROVED_HOSTS_PATH = os.path.join(".omg", "state", "ssh_approved_hosts.json")


class SSHPolicyManager:
    """Manages SSH host approval policy and fingerprint verification.

    Reads/writes approved hosts from `.omg/state/ssh_approved_hosts.json`.
    Integrates with the policy_engine pattern for SSH-specific checks.
    """

    def __init__(self, state_path: Optional[str] = None):
        """Initialize with optional custom state path."""
        self._state_path = state_path or _SSH_APPROVED_HOSTS_PATH

    def _load_approved_hosts(self) -> List[Dict[str, Any]]:
        """Load approved hosts from state file."""
        if not os.path.isfile(self._state_path):
            return []
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                hosts = data.get("hosts", [])
                return hosts if isinstance(hosts, list) else []
            return []
        except (json.JSONDecodeError, OSError):
            return []

    def _save_approved_hosts(self, hosts: List[Dict[str, Any]]) -> None:
        """Save approved hosts to state file using atomic write."""
        _ensure_imports()
        payload = {"hosts": hosts}
        if _atomic_json_write is not None:
            _atomic_json_write(self._state_path, payload)
        else:
            # Fallback: direct write with parent dir creation
            parent = os.path.dirname(self._state_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, separators=(",", ":"))

    def is_host_approved(self, host: str, port: int = 22) -> bool:
        """Check if a host:port is in the approved hosts list.

        Args:
            host: Hostname or IP address.
            port: SSH port (default: 22).

        Returns:
            True if the host:port is approved, False otherwise.
        """
        if not host:
            return False
        hosts = self._load_approved_hosts()
        for entry in hosts:
            if isinstance(entry, dict):
                if entry.get("host") == host and int(entry.get("port", 22)) == port:
                    return True
        return False

    def approve_host(self, host: str, port: int = 22, fingerprint: Optional[str] = None) -> bool:
        """Add a host to the approved hosts list.

        Args:
            host: Hostname or IP address.
            port: SSH port (default: 22).
            fingerprint: Optional SSH host fingerprint.

        Returns:
            True if the host was added (or already existed), False on error.
        """
        if not host or not isinstance(host, str):
            return False

        hosts = self._load_approved_hosts()

        # Check if already approved
        for entry in hosts:
            if isinstance(entry, dict):
                if entry.get("host") == host and int(entry.get("port", 22)) == port:
                    # Update fingerprint if provided
                    if fingerprint:
                        entry["fingerprint"] = fingerprint
                        self._save_approved_hosts(hosts)
                    return True

        # Add new entry
        entry = {
            "host": host,
            "port": port,
            "fingerprint": fingerprint,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }
        hosts.append(entry)
        self._save_approved_hosts(hosts)
        return True

    def revoke_host(self, host: str, port: int = 22) -> bool:
        """Remove a host from the approved hosts list.

        Args:
            host: Hostname or IP address.
            port: SSH port (default: 22).

        Returns:
            True if the host was found and removed, False otherwise.
        """
        if not host:
            return False
        hosts = self._load_approved_hosts()
        original_len = len(hosts)
        hosts = [
            e for e in hosts
            if not (isinstance(e, dict) and e.get("host") == host and int(e.get("port", 22)) == port)
        ]
        if len(hosts) < original_len:
            self._save_approved_hosts(hosts)
            return True
        return False

    def verify_fingerprint(self, host: str, expected_fingerprint: str, actual_fingerprint: str) -> bool:
        """Compare an expected fingerprint against an actual fingerprint.

        Args:
            host: Hostname (for context/logging).
            expected_fingerprint: The trusted fingerprint on file.
            actual_fingerprint: The fingerprint received from the host.

        Returns:
            True if fingerprints match, False otherwise.
        """
        if not expected_fingerprint or not actual_fingerprint:
            return False
        return expected_fingerprint.strip() == actual_fingerprint.strip()

    def get_approved_hosts(self) -> List[Dict[str, Any]]:
        """Return all approved hosts.

        Returns:
            List of approved host dicts.
        """
        return self._load_approved_hosts()

    def requires_approval(self, host: str, port: int = 22) -> Dict[str, Any]:
        """Check if a host requires approval before connecting.

        Args:
            host: Hostname or IP address.
            port: SSH port (default: 22).

        Returns:
            Dict with requires_approval bool and reason string.
        """
        if not host:
            return {"requires_approval": True, "reason": "Empty host"}
        if self.is_host_approved(host, port):
            return {"requires_approval": False, "reason": "Host is approved"}
        return {
            "requires_approval": True,
            "reason": f"Host {host}:{port} is not in the approved hosts list",
        }


def _check_ssh_policy(host: str, port: int = 22) -> Dict[str, Any]:
    """Check SSH policy for a host connection attempt.

    Returns:
        Dict with allowed bool, reason string, and fingerprint_required bool.
    """
    if not host:
        return {"allowed": False, "reason": "Empty host", "fingerprint_required": False}

    approval = _ssh_policy.requires_approval(host, port)
    if approval["requires_approval"]:
        # Check if the host has a stored fingerprint requirement
        hosts = _ssh_policy.get_approved_hosts()
        fingerprint_required = False
        for entry in hosts:
            if isinstance(entry, dict) and entry.get("host") == host:
                if entry.get("fingerprint"):
                    fingerprint_required = True
                    break
        return {
            "allowed": False,
            "reason": approval["reason"],
            "fingerprint_required": fingerprint_required,
        }

    return {"allowed": True, "reason": "Host approved", "fingerprint_required": False}


# Module-level singleton
_ssh_policy = SSHPolicyManager()


# =============================================================================
# CLI Interface
# =============================================================================


def _cli_main():
    """CLI entry point for ssh_manager.py."""
    import argparse

    parser = argparse.ArgumentParser(
        description="OMG SSH Connection Manager — SSH connection spec management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--discover", action="store_true",
        help="Discover SSH hosts from ssh.json or .ssh.json",
    )
    parser.add_argument(
        "--project-dir", default=".",
        help="Project directory to search for config (default: .)",
    )
    parser.add_argument(
        "--connect", dest="connect_host",
        help="Create a connection spec for HOST",
    )
    parser.add_argument("--port", type=int, default=22, help="SSH port (default: 22)")
    parser.add_argument("--user", help="SSH username")
    parser.add_argument("--key-path", dest="key_path", help="Path to SSH private key")
    parser.add_argument(
        "--list-connections", action="store_true",
        help="List active connections in the pool",
    )
    parser.add_argument(
        "--disconnect", dest="disconnect_host",
        help="Remove a connection from the pool",
    )
    parser.add_argument(
        "--detect-os", action="store_true",
        help="Detect OS type (use with --connect)",
    )
    parser.add_argument(
        "--detect-shell", action="store_true",
        help="Detect shell type (use with --connect)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would happen without making changes",
    )

    args = parser.parse_args()

    enabled = _is_enabled()

    # Discover hosts
    if args.discover:
        if args.dry_run:
            print(json.dumps({
                "dry_run": True,
                "operation": "discover",
                "project_dir": os.path.abspath(args.project_dir),
                "enabled": enabled,
            }, indent=2))
            return

        if not enabled:
            print(json.dumps({
                "error": "SSH feature is disabled (OMG_SSH_ENABLED=false)",
            }))
            sys.exit(1)

        hosts = discover_hosts(args.project_dir)
        output = [h.to_dict() for h in hosts]
        print(json.dumps({
            "hosts": output,
            "count": len(output),
            "project_dir": os.path.abspath(args.project_dir),
        }, indent=2))
        return

    # Connect
    if args.connect_host:
        if not enabled:
            print(json.dumps({
                "error": "SSH feature is disabled (OMG_SSH_ENABLED=false)",
            }))
            sys.exit(1)

        result = connect(
            host=args.connect_host,
            port=args.port,
            user=args.user,
            key_path=args.key_path,
        )
        print(json.dumps(result, indent=2))

        if args.detect_os or args.detect_shell:
            conn = result.get("result", {})
            info = {}
            if args.detect_os:
                info["os_type"] = detect_os(conn)
            if args.detect_shell:
                info["shell"] = detect_shell(conn)
            print(json.dumps(info, indent=2))
        return

    # List connections
    if args.list_connections:
        conns = get_connections()
        print(json.dumps({
            "connections": conns,
            "count": len(conns),
            "enabled": enabled,
        }, indent=2))
        return

    # Disconnect
    if args.disconnect_host:
        if not enabled:
            print(json.dumps({
                "error": "SSH feature is disabled (OMG_SSH_ENABLED=false)",
            }))
            sys.exit(1)

        removed = disconnect(args.disconnect_host, args.port)
        print(json.dumps({
            "disconnected": removed,
            "host": args.disconnect_host,
            "port": args.port,
        }, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    _cli_main()
