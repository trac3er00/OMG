#!/usr/bin/env python3
"""OMG v1 Policy Engine

Centralized policy decision layer for tool access, file access, and supply-chain
artifact verification.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from fnmatch import fnmatch
import os
import re
from typing import Any


Action = str
RiskLevel = str


@dataclass
class PolicyDecision:
    action: Action  # allow | ask | deny
    risk_level: RiskLevel  # low | med | high | critical
    reason: str = ""
    controls: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("controls") is None:
            data["controls"] = []
        return data


def allow(reason: str = "", controls: list[str] | None = None) -> PolicyDecision:
    return PolicyDecision("allow", "low", reason, controls or [])


def ask(reason: str, risk_level: RiskLevel = "med", controls: list[str] | None = None) -> PolicyDecision:
    return PolicyDecision("ask", risk_level, reason, controls or [])


def deny(reason: str, risk_level: RiskLevel = "high", controls: list[str] | None = None) -> PolicyDecision:
    return PolicyDecision("deny", risk_level, reason, controls or [])


# === BASH POLICY ============================================================

DESTRUCT_PATTERNS = [
    (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/(\s|$|\*)", "rm -rf /"),
    (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+~/?(\s|$|\*)", "rm -rf ~"),
    (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+\$HOME", "rm -rf $HOME"),
    (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+\$\{?HOME\}?", "rm -rf ${HOME}"),
    (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+\.\.\s", "rm -rf .."),
    (r":\(\)\s*\{\s*:\|:&\s*\}\s*;:", "fork bomb"),
    (r"function\s+\w+\(\)\s*\{\s*\w+\s*\|\s*\w+\s*&", "potential fork bomb"),
    (r">\s*/dev/sd[a-z]", "overwrite disk"),
    (r"dd\s+.*of=/dev/sd[a-z]", "dd to disk device"),
    (r"sudo\s+(dd|mkfs|fdisk|parted|wipefs)\b", "destructive disk op"),
    (r"sudo\s+rm\b", "sudo rm"),
    (r"echo\s+.*>\s*/proc/", "write to /proc"),
    (r"echo\s+.*>\s*/sys/", "write to /sys"),
]

PIPE_SHELL_PATTERNS = [
    r"(curl|wget)\s+.*\|\s*(sudo\s+)?(ba)?sh",
    r"(curl|wget)\s+.*\|\s*python[23]?",
    r"(curl|wget)\s+.*\|\s*perl",
    r"(curl|wget)\s+.*\|\s*ruby",
    r"base64\s+.*\|\s*(ba)?sh",
    r"echo\s+.*\|\s*base64\s+-d\s*\|\s*(ba)?sh",
]

EVAL_PATTERNS = [
    r"\beval\s+\"\$",
    r"\beval\s+\$\(",
    r"\beval\s+`",
]

SAFE_ENV_REFERENCE = re.compile(r"\.env\.(example|sample|template)\b", re.IGNORECASE)

SECRET_FILE_PATTERNS = [
    r"\.(env|pem|key|p12|pfx|jks|keystore|netrc|npmrc|pypirc)\b",
    r"/\.aws/(credentials|config)\b",
    r"/\.kube/config\b",
    r"/id_(rsa|ed25519|ecdsa)\b",
    r"/\.ssh/",
    r"\bsecrets?/",
    r"\bcredentials?\.",
    r"\bpasswords?\.",
    r"\btokens?\.",
]

READ_COMMANDS = [
    "cat", "less", "more", "head", "tail", "strings", "xxd", "od",
    "hexdump", "base64", "vim", "vi", "nano", "emacs", "view",
    "bat", "pygmentize", "highlight", "source", "\\.",
    "awk", "gawk", "mawk", "perl", "ruby", "python", "python3", "node",
]
READ_PATTERN = r"(?:^|\s|;|&&|\|\|)(?:" + "|".join(re.escape(c) for c in READ_COMMANDS) + r")\s+"

EXFIL_COMMANDS = [
    r"\b(cp|mv|ln\s+-s)\s+",
    r"\btar\s+.*-?c",
    r"\bzip\s+",
]

ASK_PATTERNS = [
    (r"(^|\s)(curl|wget)(\s|$)", "Network egress"),
    (r"(^|\s)(ssh|scp|rsync)(\s|$)", "Remote connection"),
    (r"git\s+push\s+.*(-f|--force)", "Force push"),
    (r"git\s+push\s+.*(main|master|production|release)", "Push to protected branch"),
    (r"chmod\s+(777|666|a\+[rwx])", "Overly permissive chmod"),
    (r"docker\s+run\s+.*--privileged", "Privileged container"),
    (r"python[23]?\s+-c\s+", "Inline Python execution"),
    (r"node\s+-e\s+", "Inline Node execution"),
]

UNTRUSTED_MUTATION_PATTERNS = [
    r"\bgit\s+(commit|push|tag)\b",
    r"\bnpm\s+(install|publish)\b",
    r"\bpython[23]?\s+.*\b(setup\.py|manage\.py)\b",
    r"\b(mv|cp|tee|sed\s+-i|touch|mkdir)\b",
]


def _is_untrusted_content_mode_active() -> bool:
    try:
        from runtime.untrusted_content import is_untrusted_content_mode_active

        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        return is_untrusted_content_mode_active(project_dir)
    except Exception:
        return False


def evaluate_bash_command(cmd: str) -> PolicyDecision:
    if not cmd:
        return allow("empty command")

    for pat, label in DESTRUCT_PATTERNS:
        if re.search(pat, cmd):
            return deny(f"Blocked: {label}", "critical", ["destructive-op"])

    for pat in PIPE_SHELL_PATTERNS:
        if re.search(pat, cmd):
            return deny("Blocked: pipe-to-shell", "critical", ["remote-code-exec"])

    for pat in EVAL_PATTERNS:
        if re.search(pat, cmd):
            return deny("Blocked: dynamic eval", "high", ["dynamic-eval"])

    for secret_pat in SECRET_FILE_PATTERNS:
        if not re.search(secret_pat, cmd, re.IGNORECASE):
            continue

        if SAFE_ENV_REFERENCE.search(cmd):
            cleaned = SAFE_ENV_REFERENCE.sub("__SAFE_REF__", cmd)
            if not re.search(secret_pat, cleaned, re.IGNORECASE):
                continue

        if re.search(READ_PATTERN, cmd, re.IGNORECASE):
            return deny("Blocked: reading secret file", "critical", ["secret-access"])

        if re.search(r"<\s*\S*(" + secret_pat + r")", cmd, re.IGNORECASE):
            return deny("Blocked: reading secret file via redirect", "critical", ["secret-access"])

        for exfil in EXFIL_COMMANDS:
            if re.search(exfil, cmd):
                return deny("Blocked: copying secret file", "critical", ["secret-exfiltration"])

        if re.search(r"\bgrep\b", cmd):
            return ask("Searching inside potential secret file — confirm this is safe", "high", ["secret-search"])

    for pat, label in ASK_PATTERNS:
        if re.search(pat, cmd):
            return ask(f"{label}: {cmd[:120]}", "med", ["human-approval"])

    if _is_untrusted_content_mode_active():
        for pat in UNTRUSTED_MUTATION_PATTERNS:
            if re.search(pat, cmd):
                return ask(
                    "Untrusted external content mode is active. Review before running state-changing commands.",
                    "high",
                    ["manual-approval", "review-provenance"],
                )

    return allow("command allowed")


# === FILE POLICY ============================================================

BLOCKED_FILES = {
    ".env", ".env.local", ".env.development", ".env.production",
    ".env.staging", ".env.test", ".npmrc", ".pypirc", ".netrc",
    "id_rsa", "id_ed25519", "id_ecdsa", "id_rsa.pub", "id_ed25519.pub", "id_ecdsa.pub",
}

EXAMPLE_FILES = {".env.example", ".env.sample", ".env.template"}

BLOCKED_PATH_PATTERNS = [
    r"/\.aws/(credentials|config)$",
    r"/\.kube/config$",
    r"/\.ssh/",
    r"/\.gnupg/",
    r"/secrets?/",
    r"\.(pem|key|p12|pfx|jks|keystore)$",
    r"(^|/)secret[s]?\.",
    r"(^|/)credential[s]?\.",
    r"(^|/)password[s]?\.",
    r"(^|/)token[s]?\.",
    r"(^|/)\.docker/config\.json$",
    r"(^|/)\.git-credentials$",
]


# OMG internal credential store paths (exempted from secret-file blocking)
# Only these exact filenames inside .omg/state/ are allowed.
_OMG_CREDENTIAL_STORE_ALLOWLIST = frozenset({
    "credentials.enc",
    "credentials.meta",
})


def _is_omg_credential_path(normalized_path: str) -> bool:
    """Return True if the path is an OMG credential store file.

    Only exempts files that are:
    1. Inside .omg/state/ directory
    2. Named exactly 'credentials.enc' or 'credentials.meta'
    3. Feature flag MULTI_CREDENTIAL is enabled

    This is deliberately narrow to prevent path traversal attacks.
    """
    # Import here to avoid circular dependency at module level
    from _common import get_feature_flag

    # Only exempt if feature is enabled
    if not get_feature_flag("MULTI_CREDENTIAL", default=False):
        return False

    basename = os.path.basename(normalized_path).lower()
    if basename not in _OMG_CREDENTIAL_STORE_ALLOWLIST:
        return False

    # Verify it's actually inside .omg/state/
    parent = os.path.dirname(normalized_path)
    return parent.endswith(os.sep + ".omg" + os.sep + "state") or \
           parent.endswith("/.omg/state")


# === ALLOWLIST SUPPORT =======================================================

# Globs that are too broad to be safe — reject these in allowlist entries.
OVERLY_BROAD_GLOBS = frozenset({
    "*", "**", "**/*", "**/**", "*/*", "*/**",
})


def validate_allowlist_entry(entry: dict[str, Any]) -> None:
    """Validate a single allowlist entry.

    Schema: {"path": "glob", "tools": ["Read", "Write"], "reason": "text"}

    Raises ValueError if the entry is invalid.
    """
    if not isinstance(entry, dict):
        raise ValueError("Allowlist entry must be a dict")

    for field in ("path", "tools", "reason"):
        if field not in entry:
            raise ValueError(f"Missing required field: {field}")

    path = entry["path"]
    if path in OVERLY_BROAD_GLOBS:
        raise ValueError(f"Overly broad glob rejected: {path}")

    tools = entry["tools"]
    if not isinstance(tools, list) or not tools:
        raise ValueError("tools must be a non-empty list")


def is_allowlisted(file_path: str, tool: str, allowlist: list[dict[str, Any]]) -> bool:
    """Check if a file_path + tool combination is allowlisted.

    Matches the file's basename and normalized path against allowlist globs.
    Invalid entries are silently skipped.

    Returns True if the path+tool matches any valid allowlist entry.
    """
    if not allowlist:
        return False

    normalized = os.path.normpath(file_path)
    basename = os.path.basename(normalized)

    for entry in allowlist:
        try:
            validate_allowlist_entry(entry)
        except (ValueError, TypeError):
            continue

        pattern = entry["path"]
        entry_tools = entry["tools"]

        # Match against basename or full normalized path
        if fnmatch(basename, pattern) or fnmatch(normalized, pattern):
            if tool in entry_tools:
                _log_allowlist_bypass(
                    file_path, tool, entry.get("reason", "")
                )
                return True

    return False


def load_allowlist(project_dir: str = ".") -> list[dict[str, Any]]:
    """Load allowlist entries from .omg/policy.yaml.

    Returns a list of valid allowlist entries. Invalid entries (overly broad
    globs, missing fields) are filtered out silently.

    Returns empty list if file doesn't exist or has no allowlist section.
    """
    policy_path = os.path.join(project_dir, ".omg", "policy.yaml")
    if not os.path.isfile(policy_path):
        return []

    try:
        import yaml
        with open(policy_path, "r") as f:
            data = yaml.safe_load(f)
    except ImportError:
        # Fallback: no yaml module — try simple line-by-line parse
        data = _parse_policy_yaml_fallback(policy_path)
    except Exception:
        return []

    if not isinstance(data, dict):
        return []

    raw_allowlist = data.get("allowlist")
    if not isinstance(raw_allowlist, list):
        return []

    # Filter out invalid entries
    valid = []
    for entry in raw_allowlist:
        try:
            validate_allowlist_entry(entry)
            valid.append(entry)
        except (ValueError, TypeError):
            continue

    return valid


def _parse_policy_yaml_fallback(path: str) -> dict[str, Any]:
    """Minimal YAML-like parser for allowlist section only.

    Used when PyYAML is not available. Handles simple allowlist entries.
    """
    try:
        with open(path, "r") as f:
            lines = f.readlines()
    except Exception:
        return {}

    result: dict[str, Any] = {}
    in_allowlist = False
    allowlist: list[dict[str, Any]] = []
    current_entry: dict[str, Any] | None = None

    for line in lines:
        stripped = line.rstrip()

        if stripped == "allowlist:":
            in_allowlist = True
            continue

        if in_allowlist:
            # Detect end of allowlist section (new top-level key)
            if stripped and not stripped.startswith(" ") and not stripped.startswith("\t"):
                in_allowlist = False
                continue

            # New list entry
            if stripped.lstrip().startswith("- path:"):
                if current_entry is not None:
                    allowlist.append(current_entry)
                val = stripped.split(":", 1)[1].strip().strip("'\"")
                current_entry = {"path": val, "tools": [], "reason": ""}
            elif current_entry is not None:
                clean = stripped.strip()
                if clean.startswith("reason:"):
                    current_entry["reason"] = clean.split(":", 1)[1].strip().strip("'\"")
                elif clean.startswith("- ") and "tools" not in clean:
                    current_entry["tools"].append(clean[2:].strip().strip("'\""))

    if current_entry is not None:
        allowlist.append(current_entry)

    if allowlist:
        result["allowlist"] = allowlist

    return result


def _log_allowlist_bypass(path: str, tool: str, reason: str) -> None:
    """Record that an allowlist entry overrode a deny decision.

    Writes an audit trail entry to .omg/state/ledger/secret-access.jsonl
    with allowlisted=True. Uses CLAUDE_PROJECT_DIR or cwd as project root.
    Silently fails — never raises exceptions (crash isolation invariant).
    """
    try:
        from secret_audit import log_secret_access

        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        log_secret_access(
            project_dir=project_dir,
            tool=tool,
            file_path=path,
            decision="allow",
            reason=f"allowlist bypass: {reason}",
            allowlisted=True,
        )
    except Exception:
        pass  # Crash isolation: audit logging must never break policy evaluation


def evaluate_file_access(
    tool: str,
    file_path: str,
    allowlist: list[dict[str, Any]] | None = None,
) -> PolicyDecision:
    """Evaluate file access policy.

    If an allowlist is provided, matching entries may override non-secret-file
    deny decisions for the given path and tool combination.
    """
    if not file_path:
        return allow("no file")

    normalized = os.path.normpath(file_path)
    # Resolve symlinks to prevent bypass via symlink to secret file
    try:
        normalized = os.path.realpath(normalized)
    except (OSError, ValueError):
        pass
    basename = os.path.basename(normalized).lower()
    lowpath = normalized.lower()

    if basename in EXAMPLE_FILES and tool in ("Write", "Edit", "MultiEdit"):
        return deny(
            f"Modifying example env file blocked (Read is allowed): {file_path}",
            "high",
            ["immutable-env-template"],
        )

    if basename in BLOCKED_FILES:
        return deny(f"Secret file blocked: {file_path}", "critical", ["secret-access"])

    if re.match(r"^\.env(\..+)?$", basename) and basename not in EXAMPLE_FILES:
        return deny(f"Environment file blocked: {file_path}", "critical", ["secret-access"])

    # EXEMPTION: OMG credential store files within .omg/state/
    # These are managed by hooks/credential_store.py and must be accessible
    if _is_omg_credential_path(normalized):
        return allow("OMG credential store (managed path)")

    for pat in BLOCKED_PATH_PATTERNS:
        if re.search(pat, lowpath):
            return deny(f"Sensitive path blocked: {file_path}", "critical", ["secret-access"])

    if tool in {"Write", "Edit", "MultiEdit"} and _is_untrusted_content_mode_active():
        return ask(
            "Untrusted external content mode is active. Review before mutating files.",
            "high",
            ["manual-approval", "review-provenance"],
        )

    if allowlist and is_allowlisted(file_path, tool, allowlist):
        return allow(f"Allowlisted: {file_path}")

    return allow("file allowed")


# === SUPPLY CHAIN POLICY ====================================================


def evaluate_supply_artifact(artifact: dict[str, Any], mode: str = "warn_and_run") -> PolicyDecision:
    """Verify artifact trust with Warn-And-Run semantics.

    mode=warn_and_run: missing trust metadata returns ASK
    critical findings always DENY
    """
    findings = artifact.get("static_scan") or []
    permissions = artifact.get("permissions") or []
    signer = artifact.get("signer")
    checksum = artifact.get("checksum")

    for finding in findings:
        sev = str((finding or {}).get("severity", "")).lower()
        if sev == "critical":
            return deny("Critical static-scan finding detected", "critical", ["supply-critical-block"])

    joined_perms = " ".join(str(p) for p in permissions)
    if any(token in joined_perms for token in ["sudo", "rm -rf", "--privileged", "curl |", "wget |"]):
        return deny("Critical permission profile detected in artifact", "critical", ["dangerous-permissions"])

    if not signer or not checksum:
        if mode == "warn_and_run":
            return ask(
                "Artifact missing signer/checksum metadata (untrusted). Continue with isolation.",
                "high",
                ["isolate-network", "read-only-fs", "manual-approval"],
            )
        return deny("Artifact missing signer/checksum metadata", "high", ["unsigned-artifact"])

    has_high = any(str((finding or {}).get("severity", "")).lower() == "high" for finding in findings)
    if has_high:
        return ask("High-risk findings present. Explicit approval required.", "high", ["manual-approval"])

    return allow("artifact trusted")


def to_pretool_hook_output(decision: PolicyDecision) -> dict[str, Any] | None:
    if decision.action == "allow":
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision.action,
            "permissionDecisionReason": decision.reason,
        }
    }
