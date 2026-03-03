#!/usr/bin/env python3
"""OAL Multi-Credential Encrypted Store

Fernet-based encrypted credential storage with PBKDF2HMAC key derivation.
Stores encrypted credentials at .oal/state/credentials.enc with metadata
at .oal/state/credentials.meta.

CLI: python hooks/credential_store.py {add,list,remove,rotate} [options]

Feature flag: OAL_MULTI_CREDENTIAL_ENABLED (default off)
Design ref: .sisyphus/credential-store-design.md
"""
from __future__ import annotations

import argparse
import base64
import gc
import getpass
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

# --- Ensure hooks dir is on sys.path for _common imports ---
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import (
    atomic_json_write,
    get_feature_flag,
    get_project_dir,
    setup_crash_handler,
)

# Fail-closed: security-critical module
setup_crash_handler("credential_store", fail_closed=True)

# --- Lazy-loaded cryptography imports ---
_Fernet = None
_PBKDF2HMAC = None
_hashes = None


def _ensure_crypto():
    """Lazily import cryptography; fail with clear message if missing."""
    global _Fernet, _PBKDF2HMAC, _hashes
    if _Fernet is not None:
        return
    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        _Fernet = Fernet
        _PBKDF2HMAC = PBKDF2HMAC
        _hashes = hashes
    except ImportError:
        print(
            "Error: 'cryptography' library required. Install with: pip install cryptography",
            file=sys.stderr,
        )
        sys.exit(1)


# --- Constants ---
CREDENTIALS_ENC = "credentials.enc"
CREDENTIALS_META = "credentials.meta"
STATE_DIR = os.path.join(".oal", "state")
KDF_ITERATIONS = 600_000
SALT_BYTES = 16
MIN_PASSPHRASE_LEN = 8

# Default empty store schema
_EMPTY_STORE = {"version": 1, "providers": {}}


# =============================================================================
# Core Crypto Functions
# =============================================================================


def derive_key(passphrase: bytes, salt: bytes, kdf_config: dict | None = None) -> bytes:
    """Derive a Fernet key from passphrase using PBKDF2HMAC.

    Args:
        passphrase: Raw passphrase bytes
        salt: 16-byte random salt
        kdf_config: Optional dict with 'iterations' override

    Returns:
        URL-safe base64-encoded 32-byte key suitable for Fernet
    """
    _ensure_crypto()
    iterations = KDF_ITERATIONS
    if kdf_config and "iterations" in kdf_config:
        iterations = int(kdf_config["iterations"])

    kdf = _PBKDF2HMAC(
        algorithm=_hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase))


def encrypt_store(data: dict, key: bytes) -> bytes:
    """Encrypt credential store payload with Fernet.

    Args:
        data: Credential store dict to encrypt
        key: Fernet key (from derive_key)

    Returns:
        Fernet token bytes
    """
    _ensure_crypto()
    f = _Fernet(key)
    payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return f.encrypt(payload)


def decrypt_store(token: bytes, key: bytes) -> dict:
    """Decrypt credential store payload.

    Args:
        token: Fernet token bytes
        key: Fernet key (from derive_key)

    Returns:
        Decrypted credential store dict

    Raises:
        ValueError: If passphrase is wrong (Fernet InvalidToken)
    """
    _ensure_crypto()
    from cryptography.fernet import InvalidToken

    f = _Fernet(key)
    try:
        plaintext = f.decrypt(token)
    except InvalidToken:
        raise ValueError("Decryption failed: wrong passphrase or corrupted store")
    return json.loads(plaintext.decode("utf-8"))


# =============================================================================
# Store I/O
# =============================================================================


def _get_store_paths(project_dir: str | None = None) -> tuple[str, str]:
    """Return (enc_path, meta_path) for the credential store."""
    pdir = project_dir or get_project_dir()
    state_dir = os.path.join(pdir, STATE_DIR)
    return (
        os.path.join(state_dir, CREDENTIALS_ENC),
        os.path.join(state_dir, CREDENTIALS_META),
    )


def _load_meta(meta_path: str) -> dict:
    """Load metadata file or return default."""
    if not os.path.exists(meta_path):
        return {}
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_meta(meta_path: str, meta: dict) -> None:
    """Save metadata via atomic write."""
    atomic_json_write(meta_path, meta)


def _create_new_meta(salt: bytes) -> dict:
    """Create initial metadata structure."""
    return {
        "version": 1,
        "kdf": "pbkdf2-sha256",
        "kdf_params": {
            "iterations": KDF_ITERATIONS,
            "salt_b64": base64.b64encode(salt).decode("ascii"),
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "providers": [],
    }


def load_store(passphrase: str, project_dir: str | None = None) -> dict:
    """Load and decrypt the credential store. Creates new if missing.

    Args:
        passphrase: User passphrase string
        project_dir: Optional project directory override

    Returns:
        Decrypted store dict
    """
    enc_path, meta_path = _get_store_paths(project_dir)
    passphrase_bytes = passphrase.encode("utf-8")

    if not os.path.exists(enc_path):
        # New store — return empty
        return dict(_EMPTY_STORE)

    meta = _load_meta(meta_path)
    if not meta:
        raise ValueError("Metadata file missing or corrupted; cannot derive key")

    salt = base64.b64decode(meta["kdf_params"]["salt_b64"])
    kdf_config = meta.get("kdf_params", {})
    key = derive_key(passphrase_bytes, salt, kdf_config)

    with open(enc_path, "rb") as f:
        token = f.read()

    store = decrypt_store(token, key)

    # Best-effort memory cleanup
    del passphrase_bytes
    del key
    gc.collect()

    return store


def save_store(data: dict, passphrase: str, project_dir: str | None = None) -> None:
    """Encrypt and atomically write the credential store.

    Args:
        data: Credential store dict to save
        passphrase: User passphrase string
        project_dir: Optional project directory override
    """
    enc_path, meta_path = _get_store_paths(project_dir)
    passphrase_bytes = passphrase.encode("utf-8")

    # Ensure state directory exists
    state_dir = os.path.dirname(enc_path)
    os.makedirs(state_dir, exist_ok=True)

    meta = _load_meta(meta_path)

    if not meta:
        # First save — create new salt and metadata
        salt = os.urandom(SALT_BYTES)
        meta = _create_new_meta(salt)
    else:
        salt = base64.b64decode(meta["kdf_params"]["salt_b64"])

    kdf_config = meta.get("kdf_params", {})
    key = derive_key(passphrase_bytes, salt, kdf_config)
    token = encrypt_store(data, key)

    # Atomic write for encrypted store (temp + rename)
    tmp_path = enc_path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(token)
    os.rename(tmp_path, enc_path)

    # Update metadata (provider list only — no keys)
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    meta["providers"] = sorted(data.get("providers", {}).keys())
    _save_meta(meta_path, meta)

    # Best-effort memory cleanup
    del passphrase_bytes
    del key
    del token
    gc.collect()


# =============================================================================
# Credential Operations
# =============================================================================


def add_credential(
    provider: str,
    key: str,
    passphrase: str,
    label: str | None = None,
    project_dir: str | None = None,
) -> None:
    """Add an API key for a provider.

    Args:
        provider: Provider name (lowercase, alphanumeric + hyphens)
        key: API key value (NEVER logged)
        passphrase: User passphrase
        label: Optional human-readable label
        project_dir: Optional project directory
    """
    store = load_store(passphrase, project_dir)

    if "providers" not in store:
        store["providers"] = {}

    if provider not in store["providers"]:
        store["providers"][provider] = {
            "keys": [],
            "active_index": 0,
            "rotation_policy": "round-robin",
        }

    provider_data = store["providers"][provider]
    existing_keys = provider_data["keys"]

    # Duplicate detection: compare last 8 chars only (avoid logging full key)
    key_suffix = key[-8:] if len(key) >= 8 else key
    for i, existing in enumerate(existing_keys):
        existing_suffix = existing["key"][-8:] if len(existing["key"]) >= 8 else existing["key"]
        if existing_suffix == key_suffix:
            print(
                f"Warning: Key ending in ...{key_suffix[-4:]} may already exist at index {i} for {provider}",
                file=sys.stderr,
            )
            break

    index = len(existing_keys)
    if label is None:
        label = f"key-{index}"

    existing_keys.append(
        {
            "key": key,
            "label": label,
            "added": datetime.now(timezone.utc).isoformat(),
            "last_used": None,
            "usage_count": 0,
        }
    )

    # First key sets active_index
    if index == 0:
        provider_data["active_index"] = 0

    save_store(store, passphrase, project_dir)
    print(f"Added key '{label}' for provider '{provider}' at index {index}")


def list_credentials(
    passphrase: str | None = None,
    provider_filter: str | None = None,
    project_dir: str | None = None,
) -> dict[str, int]:
    """List providers and key metadata.

    Without passphrase: reads metadata only (provider names).
    With passphrase: shows labels and usage stats (never keys).

    Args:
        passphrase: Optional passphrase for detailed view
        provider_filter: Optional provider name to filter
        project_dir: Optional project directory

    Returns:
        Dict of provider name → key count
    """
    _, meta_path = _get_store_paths(project_dir)
    meta = _load_meta(meta_path)

    if not meta or not meta.get("providers"):
        print("No credentials configured.")
        return {}

    if passphrase and provider_filter:
        # Detailed view for specific provider
        store = load_store(passphrase, project_dir)
        providers = store.get("providers", {})

        if provider_filter not in providers:
            print(f"Provider '{provider_filter}' not found.")
            return {}

        pdata = providers[provider_filter]
        active_idx = pdata.get("active_index", 0)
        policy = pdata.get("rotation_policy", "round-robin")
        keys = pdata.get("keys", [])

        print(f"Provider: {provider_filter} (rotation: {policy})")
        for i, k in enumerate(keys):
            active_marker = " [ACTIVE]" if i == active_idx else ""
            last_used = k.get("last_used") or "never"
            if last_used != "never":
                last_used = last_used[:10]  # Date only
            added = (k.get("added") or "")[:10]
            usage = k.get("usage_count", 0)
            lbl = k.get("label", f"key-{i}")
            print(f"  [{i}] {lbl:<12} added={added}  last_used={last_used}  usage={usage}{active_marker}")

        return {provider_filter: len(keys)}

    # Summary view from metadata only
    result = {}
    if passphrase:
        # Can decrypt to get key counts
        store = load_store(passphrase, project_dir)
        providers = store.get("providers", {})
        for name in sorted(providers.keys()):
            pdata = providers[name]
            count = len(pdata.get("keys", []))
            active = pdata.get("active_index", 0)
            print(f"Provider: {name} ({count} keys, active: #{active})")
            result[name] = count
    else:
        # Metadata only (no decryption)
        for name in sorted(meta.get("providers", [])):
            print(f"Provider: {name}")
            result[name] = -1  # Count unknown without decryption

    return result


def remove_credential(
    provider: str,
    index: int | None = None,
    passphrase: str | None = None,
    project_dir: str | None = None,
    confirm: bool = True,
) -> None:
    """Remove a key or entire provider.

    Args:
        provider: Provider name
        index: Key index to remove (None = remove entire provider)
        passphrase: User passphrase
        project_dir: Optional project directory
        confirm: Whether to prompt for confirmation
    """
    if passphrase is None:
        passphrase = _get_passphrase()

    store = load_store(passphrase, project_dir)
    providers = store.get("providers", {})

    if provider not in providers:
        print(f"Error: Provider '{provider}' not found.", file=sys.stderr)
        sys.exit(1)

    if index is not None:
        # Remove specific key
        keys = providers[provider].get("keys", [])
        if index < 0 or index >= len(keys):
            print(f"Error: Index {index} out of range (0-{len(keys) - 1}).", file=sys.stderr)
            sys.exit(1)

        lbl = keys[index].get("label", f"key-{index}")
        if confirm:
            answer = input(f"Remove key #{index} ('{lbl}') from {provider}? [y/N] ")
            if answer.lower() not in ("y", "yes"):
                print("Cancelled.")
                return

        keys.pop(index)

        # Reset active_index if needed
        active_idx = providers[provider].get("active_index", 0)
        if active_idx >= len(keys):
            providers[provider]["active_index"] = 0

        if not keys:
            # No keys left — remove entire provider
            del providers[provider]
            print(f"Removed last key from '{provider}'; provider removed.")
        else:
            print(f"Removed key #{index} ('{lbl}') from '{provider}'.")
    else:
        # Remove entire provider
        key_count = len(providers[provider].get("keys", []))
        if confirm:
            answer = input(f"Remove provider '{provider}' ({key_count} keys)? [y/N] ")
            if answer.lower() not in ("y", "yes"):
                print("Cancelled.")
                return

        del providers[provider]
        print(f"Removed provider '{provider}' ({key_count} keys).")

    save_store(store, passphrase, project_dir)


def rotate_credential(
    provider: str,
    index: int | None = None,
    strategy: str | None = None,
    passphrase: str | None = None,
    project_dir: str | None = None,
) -> None:
    """Rotate the active key for a provider.

    Args:
        provider: Provider name
        index: Specific key index to set as active (None = advance to next)
        strategy: New rotation strategy (round-robin|failover|manual)
        passphrase: User passphrase
        project_dir: Optional project directory
    """
    if passphrase is None:
        passphrase = _get_passphrase()

    store = load_store(passphrase, project_dir)
    providers = store.get("providers", {})

    if provider not in providers:
        print(f"Error: Provider '{provider}' not found.", file=sys.stderr)
        sys.exit(1)

    pdata = providers[provider]
    keys = pdata.get("keys", [])
    if not keys:
        print(f"Error: No keys configured for '{provider}'.", file=sys.stderr)
        sys.exit(1)

    if strategy is not None:
        valid_strategies = ("round-robin", "failover", "manual")
        if strategy not in valid_strategies:
            print(f"Error: Invalid strategy '{strategy}'. Choose from: {', '.join(valid_strategies)}", file=sys.stderr)
            sys.exit(1)
        pdata["rotation_policy"] = strategy
        print(f"Set rotation strategy for '{provider}' to '{strategy}'.")

    if index is not None:
        if index < 0 or index >= len(keys):
            print(f"Error: Index {index} out of range (0-{len(keys) - 1}).", file=sys.stderr)
            sys.exit(1)
        pdata["active_index"] = index
        lbl = keys[index].get("label", f"key-{index}")
        print(f"Set active key for '{provider}' to #{index} ('{lbl}').")
    elif strategy is None:
        # Advance to next (round-robin style)
        current = pdata.get("active_index", 0)
        new_idx = (current + 1) % len(keys)
        pdata["active_index"] = new_idx
        lbl = keys[new_idx].get("label", f"key-{new_idx}")
        print(f"Rotated '{provider}' active key to #{new_idx} ('{lbl}').")

    save_store(store, passphrase, project_dir)


# =============================================================================
# Runtime API (called by team_router.py in Task 1.9)
# =============================================================================


def get_active_key(provider: str, project_dir: str | None = None) -> str | None:
    """Get the currently active API key for a provider.

    Called by runtime/team_router.py (Task 1.9).
    Returns None if feature disabled, provider not found, or no passphrase.
    """
    if not get_feature_flag("MULTI_CREDENTIAL", default=False):
        return None

    passphrase = os.environ.get("OAL_CREDENTIAL_PASSPHRASE")
    if not passphrase:
        return None

    try:
        store = load_store(passphrase, project_dir)
    except (ValueError, OSError):
        return None

    providers = store.get("providers", {})
    if provider not in providers:
        return None

    pdata = providers[provider]
    keys = pdata.get("keys", [])
    if not keys:
        return None

    active_idx = pdata.get("active_index", 0)
    # Safety: clamp index
    if active_idx < 0 or active_idx >= len(keys):
        active_idx = 0

    return keys[active_idx].get("key")


def advance_key(provider: str, project_dir: str | None = None) -> None:
    """Advance to next key for round-robin rotation.

    Called after successful API call by team_router.py.
    Updates usage_count and last_used on the current key before advancing.
    """
    if not get_feature_flag("MULTI_CREDENTIAL", default=False):
        return

    passphrase = os.environ.get("OAL_CREDENTIAL_PASSPHRASE")
    if not passphrase:
        return

    try:
        store = load_store(passphrase, project_dir)
    except (ValueError, OSError):
        return

    providers = store.get("providers", {})
    if provider not in providers:
        return

    pdata = providers[provider]
    keys = pdata.get("keys", [])
    if len(keys) <= 1:
        return  # Nothing to rotate

    policy = pdata.get("rotation_policy", "round-robin")
    if policy == "manual":
        return  # Don't auto-advance for manual policy

    active_idx = pdata.get("active_index", 0)
    if 0 <= active_idx < len(keys):
        keys[active_idx]["usage_count"] = keys[active_idx].get("usage_count", 0) + 1
        keys[active_idx]["last_used"] = datetime.now(timezone.utc).isoformat()

    if policy == "round-robin":
        pdata["active_index"] = (active_idx + 1) % len(keys)

    # Failover only advances on error, not after success
    try:
        save_store(store, passphrase, project_dir)
    except (ValueError, OSError):
        pass  # Best-effort; don't crash the API call


# =============================================================================
# Passphrase Handling
# =============================================================================


def _get_passphrase() -> str:
    """Get passphrase from env var or interactive prompt.

    Resolution order:
    1. OAL_CREDENTIAL_PASSPHRASE env var
    2. getpass.getpass() interactive prompt (if TTY)
    """
    env_passphrase = os.environ.get("OAL_CREDENTIAL_PASSPHRASE")
    if env_passphrase:
        return env_passphrase

    if not sys.stdin.isatty():
        print(
            "Error: No passphrase available. Set OAL_CREDENTIAL_PASSPHRASE env var "
            "for non-interactive use.",
            file=sys.stderr,
        )
        sys.exit(1)

    passphrase = getpass.getpass("Credential store passphrase: ")
    if len(passphrase) < MIN_PASSPHRASE_LEN:
        print(
            f"Warning: Passphrase is short ({len(passphrase)} chars). "
            f"Recommended minimum: {MIN_PASSPHRASE_LEN} chars.",
            file=sys.stderr,
        )
    return passphrase


# =============================================================================
# Feature Flag Gate
# =============================================================================


def _check_feature_flag() -> None:
    """Verify the multi-credential feature flag is enabled."""
    if not get_feature_flag("MULTI_CREDENTIAL", default=False):
        print(
            "Error: Multi-credential store is disabled.\n"
            "Set OAL_MULTI_CREDENTIAL_ENABLED=1 to enable.",
            file=sys.stderr,
        )
        sys.exit(1)


# =============================================================================
# CLI Interface
# =============================================================================


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="oal-creds",
        description="Multi-credential encrypted store for OAL.",
        epilog=(
            "environment:\n"
            "  OAL_MULTI_CREDENTIAL_ENABLED=1  Required to enable credential store\n"
            "  OAL_CREDENTIAL_PASSPHRASE        Passphrase for non-interactive use\n"
            "\n"
            "examples:\n"
            "  %(prog)s add --provider anthropic --key sk-ant-xxx\n"
            "  %(prog)s add --provider openai --key sk-proj-xxx --label backup\n"
            "  %(prog)s list\n"
            "  %(prog)s list --provider anthropic\n"
            "  %(prog)s remove --provider anthropic --index 1\n"
            "  %(prog)s rotate --provider anthropic\n"
            "  %(prog)s rotate --provider openai --strategy failover"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # add
    add_p = subparsers.add_parser("add", help="Add an API key for a provider")
    add_p.add_argument("--provider", required=True, help="Provider name (e.g., anthropic, openai)")
    add_p.add_argument("--key", required=True, help="API key value")
    add_p.add_argument("--label", default=None, help="Human-readable label (default: key-N)")

    # list
    list_p = subparsers.add_parser("list", help="List providers and key metadata")
    list_p.add_argument("--provider", default=None, help="Filter to specific provider (requires passphrase)")

    # remove
    rm_p = subparsers.add_parser("remove", help="Remove a key or provider")
    rm_p.add_argument("--provider", required=True, help="Provider name")
    rm_p.add_argument("--index", type=int, default=None, help="Key index to remove (omit to remove entire provider)")
    rm_p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    # rotate
    rot_p = subparsers.add_parser("rotate", help="Rotate active key or set rotation strategy")
    rot_p.add_argument("--provider", required=True, help="Provider name")
    rot_p.add_argument("--index", type=int, default=None, help="Set specific key index as active")
    rot_p.add_argument("--strategy", default=None, choices=["round-robin", "failover", "manual"], help="Set rotation strategy")

    return parser


def main() -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Feature flag gate
    _check_feature_flag()

    if args.command == "add":
        passphrase = _get_passphrase()
        add_credential(
            provider=args.provider.lower().strip(),
            key=args.key,
            passphrase=passphrase,
            label=args.label,
        )
        # Best-effort cleanup
        del passphrase
        gc.collect()

    elif args.command == "list":
        if args.provider:
            passphrase = _get_passphrase()
            list_credentials(
                passphrase=passphrase,
                provider_filter=args.provider.lower().strip(),
            )
            del passphrase
            gc.collect()
        else:
            # Try without passphrase first (metadata only)
            list_credentials(passphrase=None)

    elif args.command == "remove":
        passphrase = _get_passphrase()
        remove_credential(
            provider=args.provider.lower().strip(),
            index=args.index,
            passphrase=passphrase,
            confirm=not args.yes,
        )
        del passphrase
        gc.collect()

    elif args.command == "rotate":
        passphrase = _get_passphrase()
        rotate_credential(
            provider=args.provider.lower().strip(),
            index=args.index,
            strategy=args.strategy,
            passphrase=passphrase,
        )
        del passphrase
        gc.collect()

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
