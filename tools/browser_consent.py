#!/usr/bin/env python3
"""
Browser Consent Manager for OMG

Manages explicit user consent for browser stealth mode. Provides a ToS warning
display, consent recording with timestamps, and persistent consent state.

Consent file: .omg/state/browser_consent.json
Format: {"consented": true/false, "acknowledged_at": "ISO timestamp", "version": "1.0"}

IMPORTANT:
  - show_warning() returns text; caller decides how to display
  - record_consent() is the ONLY function that writes consent state
  - No consent is stored without explicit user action
  - import alone does NOT trigger any side effects
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# --- Consent version ---
CONSENT_VERSION = "1.0"

# --- Consent file relative path ---
CONSENT_REL_PATH = os.path.join(".omg", "state", "browser_consent.json")

# --- Warning text ---
_WARNING_TEXT = """\
╔══════════════════════════════════════════════════════════════════╗
║                        ⚠  WARNING  ⚠                          ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  You are about to enable Browser Stealth Mode.                   ║
║                                                                  ║
║  This feature modifies browser fingerprints and injects           ║
║  JavaScript to evade bot-detection systems. Using stealth         ║
║  plugins may violate the Terms of Service of websites you         ║
║  visit.                                                           ║
║                                                                  ║
║  By granting explicit consent, you acknowledge that:              ║
║                                                                  ║
║    1. You understand the stealth plugins alter browser behavior   ║
║    2. You accept responsibility for compliance with applicable    ║
║       Terms of Service and laws                                   ║
║    3. OMG provides these tools as-is, without warranty            ║
║    4. You may revoke consent at any time                          ║
║                                                                  ║
║  Consent is required before any stealth plugin can be applied.    ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝"""

# --- Lazy imports for hooks/_common.py ---

_atomic_json_write = None


def _ensure_imports():
    """Lazy import atomic_json_write from hooks/_common.py."""
    global _atomic_json_write
    if _atomic_json_write is not None:
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hooks_dir = os.path.join(repo_root, "hooks")
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        from _common import atomic_json_write as _ajw
        _atomic_json_write = _ajw
    except ImportError:
        pass


def _write_consent_file(path: str, data: Dict[str, Any]) -> bool:
    """Write consent data using atomic_json_write or fallback.

    Returns True on success, False on failure.
    """
    _ensure_imports()
    if _atomic_json_write is not None:
        try:
            _atomic_json_write(path, data)
            return True
        except Exception:
            return False
    # Fallback: direct write with makedirs
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        return True
    except Exception:
        return False


def _read_consent_file(path: str) -> Optional[Dict[str, Any]]:
    """Read and parse consent file. Returns None on any failure."""
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return None
    except (json.JSONDecodeError, OSError, TypeError):
        return None


# =============================================================================
# ConsentManager — manages browser stealth consent lifecycle
# =============================================================================


class ConsentManager:
    """Manages user consent for browser stealth mode.

    All consent state is persisted to .omg/state/browser_consent.json.
    No consent is recorded without explicit calls to record_consent().

    Attributes:
        project_dir: Root directory containing the .omg/ state folder.
    """

    def __init__(self, project_dir: Optional[str] = None):
        self.project_dir = project_dir or os.environ.get(
            "CLAUDE_PROJECT_DIR", os.getcwd()
        )

    @property
    def consent_path(self) -> str:
        """Full path to the consent file."""
        return os.path.join(self.project_dir, CONSENT_REL_PATH)

    def show_warning(self) -> str:
        """Return the ToS warning text for browser stealth mode.

        Returns the multi-line warning string. Does NOT print it —
        the caller decides how to display the warning.

        Returns:
            Multi-line warning string containing Terms of Service notice.
        """
        return _WARNING_TEXT

    def record_consent(self, acknowledged: bool = True) -> bool:
        """Record the user's consent decision.

        Saves consent state to .omg/state/browser_consent.json with
        a timestamp and version identifier.

        Args:
            acknowledged: True if user explicitly consented, False otherwise.

        Returns:
            True if consent was successfully written, False on failure.
        """
        data = {
            "consented": acknowledged,
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            "version": CONSENT_VERSION,
        }
        return _write_consent_file(self.consent_path, data)

    def is_consented(self) -> bool:
        """Check if user has given explicit consent for stealth plugins.

        Reads .omg/state/browser_consent.json and checks for
        ``{"consented": true}``.

        Returns:
            True if consent file exists and consented is True, False otherwise.
        """
        data = _read_consent_file(self.consent_path)
        if data is None:
            return False
        return data.get("consented", False) is True

    def revoke_consent(self) -> bool:
        """Revoke previously granted consent.

        Sets consented to False in the consent file while preserving
        the timestamp of revocation.

        Returns:
            True if revocation was successfully written, False on failure.
        """
        data = {
            "consented": False,
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            "version": CONSENT_VERSION,
        }
        return _write_consent_file(self.consent_path, data)

    def get_consent_status(self) -> Dict[str, Any]:
        """Return the full consent record.

        Returns:
            Full consent dict if file exists and is valid,
            otherwise {"consented": False}.
        """
        data = _read_consent_file(self.consent_path)
        if data is None:
            return {"consented": False}
        return data


# =============================================================================
# Module-level convenience function
# =============================================================================


def is_consented(project_dir: Optional[str] = None) -> bool:
    """Module-level convenience: check if consent has been granted.

    Args:
        project_dir: Root directory (auto-detected if None).

    Returns:
        True if consented, False otherwise.
    """
    return ConsentManager(project_dir=project_dir).is_consented()


# =============================================================================
# CLI Interface
# =============================================================================


def _cli_main():
    """CLI entry point for browser_consent.py."""
    import argparse

    parser = argparse.ArgumentParser(
        description="OMG Browser Consent — manage consent for browser stealth mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show current consent status",
    )
    parser.add_argument(
        "--show-warning", action="store_true",
        help="Display the ToS warning text",
    )
    parser.add_argument(
        "--grant", action="store_true",
        help="Grant consent for stealth mode",
    )
    parser.add_argument(
        "--revoke", action="store_true",
        help="Revoke consent for stealth mode",
    )
    parser.add_argument(
        "--project-dir", default=None,
        help="Project directory (default: auto-detect)",
    )

    args = parser.parse_args()
    manager = ConsentManager(project_dir=args.project_dir)

    if args.show_warning:
        print(manager.show_warning())
        return

    if args.grant:
        success = manager.record_consent(acknowledged=True)
        print(json.dumps({"granted": success}, indent=2))
        return

    if args.revoke:
        success = manager.revoke_consent()
        print(json.dumps({"revoked": success}, indent=2))
        return

    if args.status:
        status = manager.get_consent_status()
        print(json.dumps(status, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    _cli_main()
