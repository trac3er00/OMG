#!/usr/bin/env python3
"""OAL v1 Policy Engine

Centralized policy decision layer for tool access, file access, and supply-chain
artifact verification.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
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


def evaluate_file_access(tool: str, file_path: str) -> PolicyDecision:
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

    for pat in BLOCKED_PATH_PATTERNS:
        if re.search(pat, lowpath):
            return deny(f"Sensitive path blocked: {file_path}", "critical", ["secret-access"])

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
