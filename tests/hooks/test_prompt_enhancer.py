"""Tests for prompt-enhancer.py — OMG v1."""
import json, subprocess, os, tempfile, shutil

def run_enhancer(message, project_dir="."):
    """Run prompt-enhancer with a message and return parsed output."""
    payload = json.dumps({"tool_input": {"user_message": message}})
    proc = subprocess.run(
        ["python3", "hooks/prompt-enhancer.py"],
        input=payload, capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": project_dir},
    )
    assert proc.returncode == 0, f"Non-zero exit: {proc.stderr}"
    if not proc.stdout.strip():
        return ""
    data = json.loads(proc.stdout)
    return data.get("contextInjection", "")

# === Intent classification ===
def test_intent_fix():
    ctx = run_enhancer("fix the login bug")
    assert "@intent: FIX" in ctx

def test_intent_implement():
    ctx = run_enhancer("implement user registration")
    assert "@intent: IMPLEMENT" in ctx

def test_intent_refactor():
    ctx = run_enhancer("refactor the payment module")
    assert "@intent: REFACTOR" in ctx

def test_intent_review():
    ctx = run_enhancer("review the auth code")
    assert "@intent: REVIEW" in ctx

def test_intent_research():
    ctx = run_enhancer("search for Next.js docs")
    assert "@intent: RESEARCH" in ctx

def test_intent_plan():
    ctx = run_enhancer("plan the new architecture")
    assert "@intent: PLAN" in ctx

# === Discipline injection ===
def test_discipline_always_present():
    ctx = run_enhancer("fix the bug")
    assert "@discipline:" in ctx

def test_verify_on_fix():
    ctx = run_enhancer("fix the auth bug")
    assert "@verify:" in ctx

def test_verify_on_implement():
    ctx = run_enhancer("implement new feature")
    assert "@verify:" in ctx

def test_no_verify_on_review():
    ctx = run_enhancer("review this code")
    assert "@verify:" not in ctx

# === Mode detection ===
def test_ulw_mode():
    ctx = run_enhancer("ulw fix everything")
    assert "PERSISTENT" in ctx

def test_ralph_mode():
    ctx = run_enhancer("ralph 모든 버그 수정")
    assert "PERSISTENT" in ctx

def test_crazy_mode():
    ctx = run_enhancer("crazy build the entire app")
    assert "CRAZY" in ctx

# === Specialist routing ===
def test_ui_routing():
    ctx = run_enhancer("design the dashboard layout")
    assert "gemini" in ctx.lower() or "@route" in ctx

def test_explicit_gemini_route_keyword():
    ctx = run_enhancer("use gemini to review this component")
    assert "@route-lock" in ctx
    assert "gemini" in ctx.lower()
    assert "do not call plugin/skill routes" in ctx.lower()

def test_explicit_codex_route_keyword():
    ctx = run_enhancer("use codex to debug auth middleware")
    assert "@route-lock" in ctx
    assert "codex" in ctx.lower()
    assert "do not call plugin/skill routes" in ctx.lower()

def test_explicit_opencode_route_keyword():
    ctx = run_enhancer("use opencode to implement this patch")
    assert "@route-lock" in ctx
    assert "opencode" in ctx.lower()
    assert "claude_dispatch" in ctx.lower()

def test_explicit_kimi_route_keyword_marks_manual_review():
    ctx = run_enhancer("use kimi to inspect the local runtime")
    assert "@route-lock" in ctx
    assert "kimi" in ctx.lower()
    assert "manual_review_required" in ctx.lower()

def test_explicit_kimi_route_keyword_beats_ccg_signals():
    ctx = run_enhancer("use kimi for this full stack runtime analysis")
    assert "@route-lock" in ctx
    assert "route=kimi" in ctx.lower()

def test_explicit_ccg_route_keyword():
    ctx = run_enhancer("do a ccg review for this full stack task")
    assert "@route-lock" in ctx
    assert "ccg" in ctx.lower()
    assert "do not call plugin/skill routes" in ctx.lower()

def test_explicit_deep_plan_route_keyword():
    ctx = run_enhancer("use deep-plan for this migration strategy")
    assert "@route-lock" in ctx
    assert "deep-plan" in ctx.lower()
    assert "execute /omg:deep-plan" in ctx.lower()

def test_deep_plan_keyword_takes_priority_over_model_keywords():
    ctx = run_enhancer("deep-plan then use codex and gemini for implementation")
    assert "route=deep-plan" in ctx.lower()

def test_both_codex_and_gemini_keywords_force_ccg_route_lock():
    ctx = run_enhancer("use codex and gemini together for this change")
    assert "@route-lock" in ctx
    assert "route=ccg" in ctx.lower()

def test_security_domain():
    ctx = run_enhancer("fix the authentication login bug")
    assert "@security" in ctx

# === Vision detection ===
def test_vision_screenshot():
    ctx = run_enhancer("look at this screenshot")
    assert "@vision" in ctx

def test_vision_korean():
    ctx = run_enhancer("스크린샷 봐")
    assert "@vision" in ctx

# === Context budget ===
def test_budget_enforced():
    ctx = run_enhancer(
        "crazy ulw fix the auth login bug, im stuck, screenshot shows error, "
        "create new domain, search for docs"
    )
    assert len(ctx) <= 1000, f"Budget exceeded: {len(ctx)} chars"

def test_budget_with_auto_complexity():
    """Auto-complexity mode + other injections should still fit budget."""
    ctx = run_enhancer(
        "1. create registration\n2. add OAuth2\n3. implement reset\n"
        "4. add JWT\n5. create dashboard\n6. fix auth bug with screenshots"
    )
    assert len(ctx) <= 1000, f"Budget exceeded: {len(ctx)} chars"

# === Auto-complexity detection ===
def test_auto_no_trigger_simple():
    """Simple single-task prompts should NOT auto-trigger modes."""
    ctx = run_enhancer("fix the login bug")
    assert "CRAZY(auto)" not in ctx
    assert "PERSISTENT(auto)" not in ctx

def test_auto_persistent_medium():
    """Medium complexity (2+ actions) should auto-trigger PERSISTENT or CRAZY."""
    ctx = run_enhancer("fix the bug and then update the config, also check the logs")
    assert "PERSISTENT(auto)" in ctx or "CRAZY(auto)" in ctx

def test_auto_crazy_numbered_list():
    """5-item numbered list should auto-trigger CRAZY."""
    ctx = run_enhancer(
        "1. create user registration\n2. add OAuth2\n"
        "3. implement password reset\n4. add JWT\n5. create admin dashboard"
    )
    assert "CRAZY(auto)" in ctx

def test_auto_crazy_architecture():
    """Architecture overhaul should auto-trigger CRAZY."""
    ctx = run_enhancer(
        "redesign the entire frontend architecture from REST to GraphQL, "
        "migrate all API endpoints, and rewrite the client and server"
    )
    assert "CRAZY(auto)" in ctx

def test_auto_crazy_korean():
    """Korean complex tasks should auto-trigger."""
    ctx = run_enhancer("전체 프로젝트 리팩토링하고 프론트엔드 백엔드 모두 수정해")
    assert "CRAZY(auto)" in ctx or "PERSISTENT(auto)" in ctx

def test_auto_no_override_explicit():
    """Explicit crazy/ulw should use explicit mode, not auto."""
    ctx = run_enhancer("crazy build the entire app")
    assert "CRAZY(auto)" not in ctx
    assert "@mode:CRAZY" in ctx
def test_empty_message():
    payload = json.dumps({"tool_input": {"user_message": ""}})
    proc = subprocess.run(
        ["python3", "hooks/prompt-enhancer.py"],
        input=payload, capture_output=True, text=True,
    )
    assert proc.returncode == 0

def test_invalid_json():
    proc = subprocess.run(
        ["python3", "hooks/prompt-enhancer.py"],
        input="not json", capture_output=True, text=True,
    )
    assert proc.returncode == 0  # graceful degradation

# === Write/Edit failure awareness ===
def test_write_verify_hook_error():
    """Hook error signals should trigger write-verify injection."""
    ctx = run_enhancer("I got a hook error when trying to edit the file")
    assert "@write-verify" in ctx

def test_write_verify_error_editing():
    """'Error editing file' should trigger write-verify."""
    ctx = run_enhancer("Error editing file src/main.ts")
    assert "@write-verify" in ctx

def test_write_verify_security_warning():
    """Security warning with XSS should trigger write-verify."""
    ctx = run_enhancer("security warning: innerHTML setting XSS vulnerabilities")
    assert "@write-verify" in ctx

def test_write_verify_not_triggered_normal():
    """Normal prompts should NOT trigger write-verify."""
    ctx = run_enhancer("fix the login bug")
    assert "@write-verify" not in ctx


# === Stuck detection dedup ===
def test_stuck_dedup():
    """Two rapid stuck signals should produce only ONE @stuck injection (dedup)."""
    tmp = tempfile.mkdtemp(prefix="omg_test_stuck_")
    try:
        # Setup: create .omg/state/ledger/failure-tracker.json with ≥2 failures
        ledger_dir = os.path.join(tmp, ".omg", "state", "ledger")
        os.makedirs(ledger_dir, exist_ok=True)
        tracker = {"npm test": {"count": 3, "last": "2026-01-01T00:00:00Z"}}
        with open(os.path.join(ledger_dir, "failure-tracker.json"), "w") as f:
            json.dump(tracker, f)

        # First call: should inject @stuck
        ctx1 = run_enhancer("I'm stuck, same error keeps happening", project_dir=tmp)
        assert "@stuck" in ctx1, f"First call should inject @stuck, got: {ctx1}"

        # Second call: within 60s, should NOT inject @stuck (dedup)
        ctx2 = run_enhancer("I'm stuck, same error keeps happening", project_dir=tmp)
        assert "@stuck" not in ctx2, f"Second call should be deduped, got: {ctx2}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_stuck_no_inject_without_failures():
    """Stuck signal without ≥2 tracked failures should NOT inject @stuck."""
    tmp = tempfile.mkdtemp(prefix="omg_test_stuck_")
    try:
        # Setup: empty state (no failure tracker)
        state_dir = os.path.join(tmp, ".omg", "state")
        os.makedirs(state_dir, exist_ok=True)

        ctx = run_enhancer("I'm stuck, same error keeps happening", project_dir=tmp)
        assert "@stuck" not in ctx, f"Should not inject @stuck without failures: {ctx}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
