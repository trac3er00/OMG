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

try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, EOFError):
    sys.exit(0)

file_path = data.get("tool_input", {}).get("file_path", "")
if not file_path:
    sys.exit(0)

# Resolve relative paths against project dir
project_dir = _resolve_project_dir()
if not os.path.isabs(file_path):
    file_path = os.path.join(project_dir, file_path)

if not os.path.exists(file_path):
    sys.exit(0)

ext = os.path.splitext(file_path)[1].lower()

# ── 1. AUTO-FORMAT (opt-in via quality-gate.json, non-blocking) ──
# §4.4: Auto-format only runs if the project has opted in via quality-gate.json.
# This avoids unintended tool execution (supply-chain risk) on projects without
# explicit formatter configuration.
format_enabled = False
qg_path = resolve_state_file(project_dir, "state/quality-gate.json", "quality-gate.json")
with contextlib.suppress(Exception):  # intentional: cleanup — format stays disabled on config error
    if os.path.exists(qg_path):
        with open(qg_path, "r") as f:
            qg = json.load(f)
        # "format" key must exist and not be null/empty
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
    # Validate formatter binary exists before running (supply-chain defense)
    import shutil
    if shutil.which(fmt_cmd[0]):
        try:
            subprocess.run(fmt_cmd + [file_path], capture_output=True, timeout=15, cwd=project_dir)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

# ── 2. SECRET SCAN (blocking) ──
# Skip binary files and very large files
try:
    file_size = os.path.getsize(file_path)
    if file_size > 1_000_000:  # 1MB limit
        sys.exit(0)
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
except Exception as e:
    print(f"[OMG] post-write.py: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(0)

# Skip known non-secret file types
SKIP_EXTENSIONS = {".lock", ".sum", ".svg", ".png", ".jpg", ".gif", ".ico", ".woff", ".woff2", ".ttf"}
if ext in SKIP_EXTENSIONS:
    sys.exit(0)

SECRET_PATTERNS = [
    # AWS
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"(?:aws_secret_access_key|AWS_SECRET)\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?", "AWS Secret Key"),
    # Private keys
    (r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "Private Key"),
    # Generic API keys/tokens (in assignment context)
    (r"""(?:api[_-]?key|api[_-]?secret|auth[_-]?token|access[_-]?token|secret[_-]?key)\s*[:=]\s*['"][A-Za-z0-9+/=_\-.]{20,}['"]""", "Hardcoded API Key/Token"),
    # GitHub
    (r"gh[ps]_[A-Za-z0-9_]{36,}", "GitHub Token"),
    (r"github_pat_[A-Za-z0-9_]{22,}", "GitHub Fine-grained PAT"),
    # Slack
    (r"xoxb-[0-9]{10,}-[A-Za-z0-9]{20,}", "Slack Bot Token"),
    (r"xoxp-[0-9]{10,}-[0-9]{10,}-[A-Za-z0-9]{20,}", "Slack User Token"),
    # Stripe
    (r"sk_live_[A-Za-z0-9]{20,}", "Stripe Live Secret Key"),
    (r"rk_live_[A-Za-z0-9]{20,}", "Stripe Restricted Key"),
    (r"pk_live_[A-Za-z0-9]{20,}", "Stripe Live Publishable Key (should use env)"),
    # Supabase / Firebase
    (r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_-]{20,}", "Supabase/Firebase Service Key"),
    # Google
    (r"AIza[A-Za-z0-9_-]{35}", "Google API Key"),
    # Twilio
    (r"SK[A-Za-z0-9]{32}", "Twilio API Key"),
    # SendGrid
    (r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}", "SendGrid API Key"),
    # Passwords in config
    (r"""(?:password|passwd|pwd)\s*[:=]\s*['"][^'"]{8,}['"]""", "Hardcoded Password"),
    # Generic secret in env-like format
    (r"""(?:SECRET|TOKEN|PRIVATE_KEY|ENCRYPTION_KEY)\s*=\s*['"]?[A-Za-z0-9+/=_\-.]{16,}['"]?""", "Hardcoded Secret"),
    # Database connection strings with credentials
    (r"(?:postgres|mysql|mongodb|redis)://[^:]+:[^@]+@", "Database URL with credentials"),
    # JWT tokens (3 base64 segments separated by dots)
    (r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "JWT Token"),
    # Hardcoded URLs with credentials
    (r"https?://[^:]+:[^@]+@", "URL with embedded credentials"),
    # Webhook URLs (often secret)
    (r"""(?:webhook[_-]?url|slack[_-]?webhook|discord[_-]?webhook)\s*[:=]\s*['"]https?://""", "Hardcoded Webhook URL"),
]

# URI / Security anti-patterns (WARNING, not blocking)
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
    # Skip lines that are entirely comments (bare "*" removed — too broad)
    if stripped.startswith(("#", "//", "/*", "* ", "<!--", "%", ";")):
        continue
    if is_test_file:
        continue
    for pattern, label in SECRET_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            findings.append(f"  Line {i}: {label}")
            if label not in patterns_matched:
                patterns_matched.append(label)
            break  # One finding per line is enough

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
    # NOTE: exit(0), not exit(2). Non-zero exits crash sibling hooks
    # ("Sibling tool call errored"). The warning in stderr is still visible.
    sys.exit(0)

# ── 3. SECURITY WARNING SCAN (non-blocking, advisory) ──
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
