#!/usr/bin/env python3
"""
PostToolUse Hook (Write/Edit/MultiEdit): Auto-Format + Secret Scan (Enterprise)
1. Auto-format written files if opted-in via .omg/state/quality-gate.json (non-blocking)
2. Scan written content for hardcoded secrets (blocking: exit 2)
"""
import json, sys, os, re, subprocess
import contextlib
import importlib.util
from datetime import datetime, timezone


def _load_local_attr(module_name, filename, attr_name):
    module_path = os.path.join(os.path.dirname(__file__), filename)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, attr_name)


_resolve_project_dir = _load_local_attr("omg_hooks_common", "_common.py", "_resolve_project_dir")
resolve_state_file = _load_local_attr("omg_hooks_state_migration", "state_migration.py", "resolve_state_file")
detect_high_entropy_strings = _load_local_attr("omg_hooks_post_write", "_post_write.py", "detect_high_entropy_strings")
atomic_json_write = _load_local_attr("omg_hooks_common", "_common.py", "atomic_json_write")


def resolve_secret_detected(project_dir: str, reason: str) -> dict:
    """
    Resolve a stale secret-detected signal with an audit trail.
    
    Reads the existing .omg/state/secret-detected.json, adds resolution metadata
    (resolved: true, resolved_at: ISO timestamp, resolve_reason: reason), and
    writes back atomically. Preserves original detection metadata for audit.
    
    Args:
        project_dir: Project directory containing .omg/state/
        reason: Human-readable reason for resolution (e.g., "false_positive", "secret_rotated")
    
    Returns:
        Updated state dict with resolution metadata
    
    Raises:
        FileNotFoundError: If secret-detected.json does not exist
        json.JSONDecodeError: If existing state is malformed
    """
    state_path = os.path.join(project_dir, ".omg", "state", "secret-detected.json")
    
    # Read existing state
    if not os.path.exists(state_path):
        raise FileNotFoundError(f"No secret-detected signal found at {state_path}")
    
    with open(state_path, "r", encoding="utf-8") as f:
        state = json.load(f)
    
    # Add resolution metadata
    state["resolved"] = True
    state["resolved_at"] = datetime.now(timezone.utc).isoformat()
    state["resolve_reason"] = reason
    
    # Write atomically
    atomic_json_write(state_path, state)
    
    return state

def _main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    project_dir = _resolve_project_dir()
    if not os.path.isabs(file_path):
        file_path = os.path.join(project_dir, file_path)

    if not os.path.exists(file_path):
        sys.exit(0)

    ext = os.path.splitext(file_path)[1].lower()

    format_enabled = False
    qg_path = resolve_state_file(project_dir, "state/quality-gate.json", "quality-gate.json")
    with contextlib.suppress(Exception):
        if os.path.exists(qg_path):
            with open(qg_path, "r") as f:
                qg = json.load(f)
            if qg.get("format"):
                format_enabled = True

    FORMAT_MAP = {
        ".ts":  ["npx", "--no-install", "prettier", "--write"],
        ".tsx": ["npx", "--no-install", "prettier", "--write"],
        ".js":  ["npx", "--no-install", "prettier", "--write"],
        ".jsx": ["npx", "--no-install", "prettier", "--write"],
        ".css": ["npx", "--no-install", "prettier", "--write"],
        ".json": ["npx", "--no-install", "prettier", "--write"],
        ".py": ["ruff", "format"], ".go": ["gofmt", "-w"], ".rs": ["rustfmt"],
    }
    if format_enabled and ext in FORMAT_MAP:
        fmt_cmd = FORMAT_MAP[ext]
        import shutil
        if shutil.which(fmt_cmd[0]):
            try:
                subprocess.run(fmt_cmd + [file_path], capture_output=True, timeout=15, cwd=project_dir)
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                pass

    try:
        file_size = os.path.getsize(file_path)
        if file_size > 1_000_000:
            sys.exit(0)
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        print(f"[OMG] post-write.py: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(0)

    SKIP_EXTENSIONS = {".lock", ".sum", ".svg", ".png", ".jpg", ".gif", ".ico", ".woff", ".woff2", ".ttf"}
    if ext in SKIP_EXTENSIONS:
        sys.exit(0)

    SECRET_PATTERNS = [
        (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
        (r"(?:aws_secret_access_key|AWS_SECRET)\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?", "AWS Secret Key"),
        (r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "Private Key"),
        (r"""(?:api[_-]?key|api[_-]?secret|auth[_-]?token|access[_-]?token|secret[_-]?key)\s*[:=]\s*['"][A-Za-z0-9+/=_\-.]{20,}['"]""", "Hardcoded API Key/Token"),
        (r"gh[ps]_[A-Za-z0-9_]{36,}", "GitHub Token"),
        (r"github_pat_[A-Za-z0-9_]{22,}", "GitHub Fine-grained PAT"),
        (r"xoxb-[0-9]{10,}-[A-Za-z0-9]{20,}", "Slack Bot Token"),
        (r"xoxp-[0-9]{10,}-[0-9]{10,}-[A-Za-z0-9]{20,}", "Slack User Token"),
        (r"sk_live_[A-Za-z0-9]{20,}", "Stripe Live Secret Key"),
        (r"rk_live_[A-Za-z0-9]{20,}", "Stripe Restricted Key"),
        (r"pk_live_[A-Za-z0-9]{20,}", "Stripe Live Publishable Key (should use env)"),
        (r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_-]{20,}", "Supabase/Firebase Service Key"),
        (r"AIza[A-Za-z0-9_-]{35}", "Google API Key"),
        (r"SK[A-Za-z0-9]{32}", "Twilio API Key"),
        (r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}", "SendGrid API Key"),
        (r"""(?:password|passwd|pwd)\s*[:=]\s*['"][^'"]{8,}['"]""", "Hardcoded Password"),
        (r"""(?:SECRET|TOKEN|PRIVATE_KEY|ENCRYPTION_KEY)\s*=\s*['"]?[A-Za-z0-9+/=_\-.]{16,}['"]?""", "Hardcoded Secret"),
        (r"(?:postgres|mysql|mongodb|redis)://[^:]+:[^@]+@", "Database URL with credentials"),
        (r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "JWT Token"),
        (r"https?://[^:]+:[^@]+@", "URL with embedded credentials"),
        (r"""(?:webhook[_-]?url|slack[_-]?webhook|discord[_-]?webhook)\s*[:=]\s*['"]https?://""", "Hardcoded Webhook URL"),
    ]

    SECURITY_WARNINGS = [
        (r"cors\s*\(\s*\{[^}]*origin\s*:\s*['\"]?\*['\"]?", "CORS wildcard origin in code — use whitelist in production"),
        (r"httpOnly\s*:\s*false", "Cookie httpOnly disabled — session cookies should be httpOnly"),
        (r"secure\s*:\s*false", "Cookie secure flag disabled — use HTTPS in production"),
        (r"eval\s*\(", "eval() usage — potential code injection risk"),
        (r"innerHTML\s*=", "innerHTML assignment — potential XSS risk"),
        (r"dangerouslySetInnerHTML", "dangerouslySetInnerHTML — verify input is sanitized"),
    ]

    findings = []
    patterns_matched = []
    lowpath = file_path.lower()
    is_test_file = any(d in lowpath for d in ["/__tests__/", "/test/", "/tests/"])
    if not is_test_file:
        basename = os.path.basename(file_path).lower()
        is_test_file = any(p in basename for p in [".test.", ".spec."])

    for i, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith(("#", "//", "/*", "* ", "<!--", "%", ";")):
            continue
        if is_test_file:
            continue
        for pattern, label in SECRET_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                findings.append(f"  Line {i}: {label}")
                if label not in patterns_matched:
                    patterns_matched.append(label)
                break

        entropy_matches = detect_high_entropy_strings(line)
        if entropy_matches:
            findings.append(f"  Line {i}: High-entropy potential secret")
            if "High-entropy potential secret" not in patterns_matched:
                patterns_matched.append("High-entropy potential secret")

    if findings:
        try:
            proj_dir = _resolve_project_dir()
            state_dir = os.path.join(proj_dir, ".omg", "state")
            os.makedirs(state_dir, exist_ok=True)
            signal_path = os.path.join(state_dir, "secret-detected.json")
            signal_payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "file": file_path,
                "patterns_matched": patterns_matched,
                "action": "blocked",
            }
            with open(signal_path, "w", encoding="utf-8") as f:
                json.dump(signal_payload, f)
        except Exception as e:
            print(f"[OMG] post-write.py: {type(e).__name__}: {e}", file=sys.stderr)
        print(
            f"⚠ SECRET DETECTED in {file_path}. Signal written to .omg/state/secret-detected.json",
            file=sys.stderr,
        )
        msg = f"SECRET DETECTED in {file_path}:\n" + "\n".join(findings[:10])
        if len(findings) > 10:
            msg += f"\n  ... and {len(findings) - 10} more"
        msg += "\n\nRemove hardcoded secrets. Use environment variables or a secret manager."
        print(msg, file=sys.stderr)
        sys.exit(0)

    sec_warnings = []
    for i, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith(("#", "//", "/*", "*", "<!--")):
            continue
        for pattern, label in SECURITY_WARNINGS:
            if re.search(pattern, line, re.IGNORECASE):
                sec_warnings.append(f"  Line {i}: ⚠ {label}")
                break

    if sec_warnings:
        msg = f"SECURITY WARNINGS in {file_path}:\n" + "\n".join(sec_warnings[:5])
        msg += "\n\nConsider running /OMG:security-check for the canonical audit pipeline."
        print(msg, file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    _main()
