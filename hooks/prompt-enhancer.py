#!/usr/bin/env python3
"""
UserPromptSubmit Hook — OMG v1

Inspired by oh-my-opencode's Sisyphus agent system. Key upgrades:
  1. Intent classification BEFORE acting (IntentGate)
  2. Discipline enforcement — never stop halfway
  3. Agent-aware routing — Codex/Gemini/Claude orchestration
  4. Anti-hallucination protocol
  5. Error loop prevention (circuit-breaker awareness)
  6. Vision/screenshot auto-detection
  7. DDD/Security domain auto-triggers
  8. Context budget: MAX 800 chars output

No dependency on CLAUDE.md or AGENTS.md.
"""
import json, sys, os, re, time
import importlib

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

try:
    from hooks._common import setup_crash_handler, json_input, atomic_json_write, get_feature_flag, _resolve_project_dir
    from hooks.state_migration import resolve_state_dir
    from hooks._budget import BUDGET_PROMPT_TOTAL as budget_prompt_total
    from hooks.context_pressure import estimate_context_pressure
except ImportError:
    _common = importlib.import_module("_common")
    _state_migration = importlib.import_module("state_migration")
    _budget = importlib.import_module("_budget")
    _context_pressure = importlib.import_module("context_pressure")
    setup_crash_handler = _common.setup_crash_handler
    json_input = _common.json_input
    atomic_json_write = _common.atomic_json_write
    get_feature_flag = _common.get_feature_flag
    _resolve_project_dir = _common._resolve_project_dir
    resolve_state_dir = _state_migration.resolve_state_dir
    budget_prompt_total = _budget.BUDGET_PROMPT_TOTAL
    estimate_context_pressure = _context_pressure.estimate_context_pressure

BUDGET_PROMPT_TOTAL = budget_prompt_total

setup_crash_handler("prompt-enhancer", fail_closed=False)

data = json_input()

prompt = data.get("tool_input", {}).get("user_message", "") or data.get("user_message", "")
if not prompt:
    sys.exit(0)

prompt_lower = prompt.lower().strip()
project_dir = _resolve_project_dir()
omg_root = os.path.join(project_dir, ".omg")
state_dir = resolve_state_dir(project_dir, "state", "")
knowledge_dir = resolve_state_dir(project_dir, "knowledge", "knowledge")
injections = []

# ── Context budget ──
MAX_CHARS = BUDGET_PROMPT_TOTAL

def budget_ok():
    return sum(len(i) for i in injections) < MAX_CHARS

def add(text):
    remaining = MAX_CHARS - sum(len(i) for i in injections)
    if remaining <= 20:
        return
    if len(text) > remaining:
        text = text[:remaining - 3] + "..."
    injections.append(text)


def signal_matches_text(signal, text):
    if re.search(r'[\uac00-\ud7a3]', signal):
        return signal in text
    return re.search(r'\b' + re.escape(signal) + r'\b', text, re.IGNORECASE) is not None

# ── Zero-injection optimization ──
# Simple prompts (≤10 words, no coding/mode/routing signals) get zero overhead
_word_count_early = len(prompt_lower.split())
_has_any_signal = any([
    any(signal_matches_text(sig, prompt) for sig in ["fix","bug","implement","build","create","refactor",
                                                     "review","auth","css","layout","ui","ux","test",
                                                     "stuck","error","crash","ralph","ulw","crazy",
                                                     "plan","design","search","find","research","explain",
                                                     "codex","gemini","ccg","screenshot","screen",
                                                     "security","warning","hook error","resume","handoff",
                                                     "continue","domain","scaffold","debug","deploy",
                                                     "수정","구현","버그","에러","고쳐","스크린샷","보안"]),
    _word_count_early > 10,
])
if not _has_any_signal:
    sys.exit(0)
# ═══════════════════════════════════════════════════════════
# 1. INTENT CLASSIFICATION (IntentGate)
# ═══════════════════════════════════════════════════════════
INTENT_MAP = {
    "fix": {
        "signals": ["fix", "bug", "error", "broken", "crash", "not working", "fails",
                     "수정", "버그", "에러", "고쳐", "고치", "안돼", "안됨", "깨짐", "오류"],
        "directive": "FIX — Debug root cause, patch source code (NOT tests), verify with evidence"
    },
    "plan": {
        "signals": ["plan", "design", "architect", "strategy",
                     "계획", "설계", "아키텍처", "전략"],
        "directive": "PLAN — Ask clarifying questions. Map domain. Plan before code"
    },
    "refactor": {
        "signals": ["refactor", "clean", "optimize", "improve", "simplify",
                     "리팩토링", "리팩터", "최적화", "개선", "정리"],
        "directive": "REFACTOR — Preserve behavior. Before AND after tests must pass"
    },
    "review": {
        "signals": ["review", "check", "audit", "inspect", "look at",
                     "리뷰", "검토", "확인", "감사", "점검"],
        "directive": "REVIEW — Read ALL code first. Report findings. Don't change unless asked"
    },
    "research": {
        "signals": ["research", "find", "search", "how to", "what is", "explain",
                     "검색", "찾아", "어떻게", "설명", "문서"],
        "directive": "RESEARCH — Search, synthesize, report. Use web_search if needed"
    },
    "implement": {
        "signals": ["implement", "build", "create", "add", "make", "feature", "new",
                     "구현", "빌드", "생성", "만들", "추가", "기능", "개발"],
        "directive": "IMPLEMENT — Plan → code → test → verify. Follow existing patterns"
    },
}

detected_intent = None
for intent_key, intent_data in INTENT_MAP.items():
    if any(signal_matches_text(sig, prompt) for sig in intent_data["signals"]):
        detected_intent = intent_key
        break

# ═══════════════════════════════════════════════════════════
# 2. DISCIPLINE SYSTEM (Sisyphus-grade)
# ═══════════════════════════════════════════════════════════
parts = []

if detected_intent:
    parts.append(f"@intent: {INTENT_MAP[detected_intent]['directive']}")

parts.append(
    "@discipline: Senior-eng mode. Clean minimal code. "
    "VERIFY changes. NEVER claim done unverified. "
    "NEVER modify tests as fix. No noise comments, "
    "no generic names (data/result/temp/val). FULL file reads."
)

if detected_intent in ("fix", "implement", "refactor"):
    parts.append(
        "@verify: After EVERY change run build/lint/test. Show exit code."
    )

if parts and budget_ok():
    add("\n".join(parts))

# ═══════════════════════════════════════════════════════════
# 3. MODE DETECTION (ulw/ralph/crazy)
# ═══════════════════════════════════════════════════════════
ULW_SIGNALS = ["ulw", "ultrawork", "ralph", "끝까지", "멈추지마", "계속해",
               "다될때까지", "don't stop", "keep going", "until done",
               "finish everything", "complete all"]
is_ulw = any(signal_matches_text(sig, prompt) for sig in ULW_SIGNALS)

CRAZY_SIGNALS = ["crazy", "all agents", "maximum", "모든 에이전트", "최대", "미친"]
is_crazy = any(signal_matches_text(sig, prompt) for sig in CRAZY_SIGNALS)

if is_crazy and budget_ok():
    add(
        "@mode:CRAZY — All agents active. "
        "Brainstorming is merged in CRAZY (no separate brainstorm step). "
        "Claude=orchestrator, Codex=deep-code+security, Gemini=UI/UX. "
        "Parallel dispatch. Error-loop prevention ON. "
        "After planning, run a Codex validation pass before implementation."
    )
elif is_ulw and budget_ok():
    add(
        "@mode:PERSISTENT — Do NOT stop until complete. "
        "Work through ALL items. Skip if blocked, continue others. "
        "Escalate to Codex/Gemini as needed. Verify everything."
    )

# ── Ralph loop auto-activation on keyword ──
if is_ulw and get_feature_flag('ralph_loop'):
    ralph_path = os.path.join(project_dir, '.omg', 'state', 'ralph-loop.json')
    if not os.path.exists(ralph_path):
        # Extract the goal from the prompt (everything after the keyword)
        goal = prompt.strip()
        for kw in ('ralph', 'ulw', 'ultrawork'):
            if kw in prompt_lower:
                idx = prompt_lower.find(kw) + len(kw)
                extracted = prompt[idx:].strip()
                if extracted:
                    goal = extracted
                break
        from datetime import datetime as _dt, timezone
        state = {
            'active': True,
            'iteration': 0,
            'max_iterations': 50,
            'original_prompt': goal[:200],
            'started_at': _dt.now(timezone.utc).isoformat(),
            'checklist_path': '.omg/state/_checklist.md'
        }
        try:
            os.makedirs(os.path.dirname(ralph_path), exist_ok=True)
            atomic_json_write(ralph_path, state)
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════
# 3b. AUTO-COMPLEXITY DETECTION (auto-trigger modes for complex tasks)
# ═══════════════════════════════════════════════════════════
# If user didn't explicitly request crazy/ulw, detect complexity and auto-suggest
if not is_crazy and not is_ulw and budget_ok():
    complexity_score = 0

    # Multi-step connectors (+1 each)
    MULTI_STEP = ["and then", "after that", "followed by", "next", "also",
                  "그리고", "다음에", "이후에", "또한", "하고", "그다음"]
    complexity_score += sum(1 for s in MULTI_STEP if signal_matches_text(s, prompt))

    # Multiple action verbs in same prompt (+1 per verb beyond first, max +3)
    ACTION_VERBS = ["fix", "implement", "build", "create", "add", "update",
                    "refactor", "migrate", "deploy", "rewrite", "redesign",
                    "수정", "구현", "만들", "추가", "수정", "리팩토링", "배포"]
    verb_count = sum(1 for v in ACTION_VERBS if signal_matches_text(v, prompt))
    complexity_score += min(max(verb_count - 1, 0), 3)

    # Multi-file/component signals (+2 each)
    MULTI_COMPONENT = ["entire", "all files", "whole project", "full stack",
                       "frontend and backend", "client and server", "end to end",
                       "every", "all the", "across",
                       "전체", "모든 파일", "풀스택", "모두", "전부",
                       "처음부터 끝까지"]
    complexity_score += sum(2 for s in MULTI_COMPONENT if signal_matches_text(s, prompt))

    # Architecture signals (+2 each)
    ARCH_SIGNALS = ["architect", "redesign", "migration", "microservice",
                    "monorepo", "restructure", "overhaul", "rewrite from scratch",
                    "아키텍처", "마이그레이션", "재설계", "전면 수정", "처음부터 다시"]
    complexity_score += sum(2 for s in ARCH_SIGNALS if signal_matches_text(s, prompt))

    # Enumeration signals (numbered/bullet lists)
    numbered_items = len(re.findall(r'(?:^|\n)\s*[\d]+[.)]\s', prompt_lower))
    bullet_items = len(re.findall(r'(?:^|\n)\s*[-*]\s', prompt_lower))
    complexity_score += min(numbered_items + bullet_items, 5)

    # Word count signal
    word_count = len(prompt_lower.split())
    if word_count > 80:
        complexity_score += 2
    elif word_count > 40:
        complexity_score += 1

    # HIGH complexity (≥4): auto-trigger CRAZY
    if complexity_score >= 4:
        add(
            "@mode:CRAZY(auto) — Complex task detected (multi-step/multi-component). "
            "All agents active: Claude=orchestrator, Codex=deep-code, Gemini=UI/UX. "
            "Work through all items systematically. Verify each step."
        )
    # MEDIUM complexity (≥2): auto-trigger PERSISTENT
    elif complexity_score >= 2:
        add(
            "@mode:PERSISTENT(auto) — Multi-step task detected. "
            "Work through ALL items. Skip if blocked, continue others. "
            "Don't stop until checklist complete."
        )

# ═══════════════════════════════════════════════════════════
# 3c. COGNITIVE MODE (from .omg/state/mode.txt)
# ═══════════════════════════════════════════════════════════
_mode_path = os.path.join(state_dir, 'mode.txt')
if os.path.exists(_mode_path) and budget_ok():
    try:
        with open(_mode_path, 'r', encoding='utf-8') as _mf:
            _mode = _mf.read().strip().lower()
        if _mode in ('research', 'architect', 'implement'):
            _mode_hints = {
                'research': 'RESEARCH — Read/search/synthesize. No code changes unless asked.',
                'architect': 'ARCHITECT — Map system first. Specs and interfaces only, no implementation.',
                'implement': 'IMPLEMENT — TDD. Verify every change. Follow existing patterns.',
            }
            add(f'@mode:{_mode_hints[_mode]}')
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
# 4. SPECIALIST ROUTING (registry-based)
# ═══════════════════════════════════════════════════════════
CCG_SIGNALS = [
    "ccg", "full stack", "full-stack", "frontend and backend", "backend and frontend",
    "architecture review", "review everything", "cross-functional", "end-to-end", "e2e",
    "풀스택", "아키텍처 리뷰", "전체 리뷰",
]
DEEP_PLAN_SIGNALS = ["deep-plan", "deep plan", "/omg:deep-plan"]
EXPLICIT_GEMINI = ["gemini", "제미니"]
EXPLICIT_CODEX = ["codex", "코덱스"]

# Keyword-first model routing. If an explicit keyword exists, force OMG route first.
has_ccg_signal = any(signal_matches_text(sig, prompt) for sig in CCG_SIGNALS)
has_deep_plan_signal = any(signal_matches_text(sig, prompt) for sig in DEEP_PLAN_SIGNALS)
has_gemini_signal = any(signal_matches_text(sig, prompt) for sig in EXPLICIT_GEMINI)
has_codex_signal = any(signal_matches_text(sig, prompt) for sig in EXPLICIT_CODEX)

route_lock = ""
if has_deep_plan_signal:
    route_lock = "deep-plan"
elif has_ccg_signal or (has_gemini_signal and has_codex_signal):
    route_lock = "ccg"
elif has_gemini_signal:
    route_lock = "gemini"
elif has_codex_signal:
    route_lock = "codex"

if route_lock and budget_ok():
    if route_lock == "deep-plan":
        add(
            '@route-lock: Explicit keyword route=deep-plan. Execute /OMG:deep-plan "[goal]" FIRST. '
            "Do NOT call plugin/Skill routes (omc-teams/frontend-design/etc) before this OMG route."
        )
    elif route_lock == "ccg":
        add(
            '@route-lock: Explicit keyword route=ccg. Execute /OMG:ccg "[problem]" FIRST. '
            "Do NOT call plugin/Skill routes (omc-teams/frontend-design/etc) before this OMG route."
        )
    elif route_lock == "gemini":
        add(
            '@route-lock: Explicit keyword route=gemini. Execute /OMG:escalate gemini "[problem]" FIRST. '
            "Do NOT call plugin/Skill routes (omc-teams/frontend-design/etc) before this OMG route."
        )
    else:
        add(
            '@route-lock: Explicit keyword route=codex. Execute /OMG:escalate codex "[problem]" FIRST. '
            "Do NOT call plugin/Skill routes (omc-teams/frontend-design/etc) before this OMG route."
        )

if not route_lock and get_feature_flag('agent_registry') and budget_ok():
    try:
        try:
            from hooks._agent_registry import resolve_agent, detect_available_models
        except ImportError:
            _agent_registry = importlib.import_module("_agent_registry")
            resolve_agent = _agent_registry.resolve_agent
            detect_available_models = _agent_registry.detect_available_models
        _maybe_kws = locals().get("kws")
        _routing_kws = _maybe_kws if _maybe_kws else set(re.findall(r'\b[a-zA-Z]{3,}\b', prompt_lower))
        matched_agent = resolve_agent(_routing_kws)
        if isinstance(matched_agent, dict):
            _agent_name = matched_agent.get('name', '')
            _preferred = matched_agent.get('preferred_model', 'claude')
            if _preferred == 'gemini-cli':
                add(f'@agent: {_agent_name} → /OMG:escalate gemini "[task]" (visual/frontend domain)')
            elif _preferred == 'codex-cli':
                add(f'@agent: {_agent_name} → /OMG:escalate codex "[task]" (backend/security domain)')
            elif _preferred in ('claude', 'domain-dependent'):
                _desc = str(matched_agent.get('description', ''))[:80]
                if _desc:
                    add(f'@agent: {_agent_name} — {_desc}')
    except Exception:
        pass

SEQUENTIAL_THINKING_SIGNALS = [
    "sequential thinking",
    "sequential-thinking",
    "chain of thought",
    "step by step reasoning",
    "단계적 사고",
]
if any(signal_matches_text(sig, prompt) for sig in SEQUENTIAL_THINKING_SIGNALS) and budget_ok():
    add("@reasoning: Use /OMG:sequential-thinking for structured hypothesis and verification flow.")

# Security domain warning (keep this — it's additive, not routing)
SECURITY_SIGNALS = [
    "auth", "login", "signup", "session", "token", "password", "jwt", "oauth",
    "payment", "billing", "checkout", "stripe", "card",
    "database", "migration", "schema", "sql", "query",
    "encrypt", "decrypt", "cors",
    "인증", "로그인", "세션", "토큰", "비밀번호", "결제", "데이터베이스", "보안",
]
if not route_lock and any(signal_matches_text(sig, prompt) for sig in SECURITY_SIGNALS) and budget_ok():
    if detected_intent in ("fix", "implement", "refactor"):
        add("@security: CRITICAL DOMAIN — No hardcoded secrets. Run /OMG:security-review after.")

# ═══════════════════════════════════════════════════════════
# 5. VISION DETECTION
# ═══════════════════════════════════════════════════════════
VISION_SIGNALS = [
    "screenshot", "screen", "look at this", "see this", "attached image",
    "this image", "the picture", "visual bug", "looks wrong", "looks broken",
    "스크린샷", "화면 캡처", "이미지", "사진", "보여", "이렇게 보여",
]
if any(signal_matches_text(sig, prompt) for sig in VISION_SIGNALS) and budget_ok():
    add(
        "@vision: Visual context detected. Use screenshot tools if available. "
        "/OMG:escalate gemini for visual analysis."
    )

# ═══════════════════════════════════════════════════════════
# 6. RESUME / HANDOFF
# ═══════════════════════════════════════════════════════════
RESUME_SIGNALS = [
    "continue where", "pick up where", "left off", "resume", "handoff",
    "what was i working on", "previous session",
    "이어서", "계속해", "이전 세션", "하던 거", "핸드오프",
    "session handoff", "## what was done",
]
if any(signal_matches_text(sig, prompt) for sig in RESUME_SIGNALS) and budget_ok():
    for hp in [os.path.join(state_dir, "handoff.md"), os.path.join(state_dir, "handoff-portable.md")]:
        if os.path.exists(hp):
            try:
                with open(hp, "r", encoding="utf-8", errors="ignore") as f:
                    htext = f.read(1500)
                sections = []
                for s in re.split(r"\n## ", htext):
                    h = s.split("\n")[0].lower()
                    if any(k in h for k in ("next", "state", "fail")):
                        sections.append("## " + s.strip()[:200])
                if sections:
                    add("@handoff:" + "\n".join(sections)[:250])
                else:
                    add("@handoff: Read .omg/state/handoff.md for context")
            except Exception:
                pass
            break

# ═══════════════════════════════════════════════════════════
# 7. CODING CONTEXT (checklist + DDD + knowledge)
# ═══════════════════════════════════════════════════════════
CODE_SIGNALS = [
    "fix", "implement", "refactor", "build", "add", "create", "modify",
    "change", "update", "code", "test", "debug",
    "수정", "구현", "빌드", "추가", "생성", "코드", "테스트", "디버그",
    "고쳐", "개발",
]
is_coding = any(signal_matches_text(sig, prompt) for sig in CODE_SIGNALS)

if is_coding and budget_ok():
    cp = os.path.join(state_dir, "_checklist.md")
    if os.path.exists(cp):
        try:
            with open(cp, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            done = sum(1 for l in lines if "[x]" in l.lower())
            total = sum(1 for l in lines if l.strip().startswith(("[", "- [")))
            pending = [l.strip().replace("[ ] ", "").replace("- [ ] ", "")[:50]
                      for l in lines if "[ ]" in l][:2]
            if total > 0:
                add(f"@progress: {done}/{total} | next: {' → '.join(pending)}")
        except Exception:
            pass

# DDD
DDD_SIGNALS = ["new domain", "new module", "scaffold", "domain", "새 도메인", "새 모듈"]
if any(signal_matches_text(sig, prompt) for sig in DDD_SIGNALS) and budget_ok():
    pd = os.path.join(knowledge_dir, "domain-patterns")
    if os.path.isdir(pd):
        pats = [f.replace(".md", "") for f in os.listdir(pd) if f.endswith(".md")]
        if pats:
            add(f"@ddd: Patterns: {', '.join(pats[:3])}. Follow existing.")
    else:
        add("@ddd: No patterns. Use /OMG:domain-init for first reference.")

# Knowledge retrieval (top-2, with index cache for performance)
# §4.5: Instead of os.walk + read every file on every prompt,
# maintain a lightweight index (.omg/knowledge/.index.json) keyed by mtime.
kd = knowledge_dir
# Skip knowledge search for very short prompts with no coding signals (perf optimization)
_word_count = len(prompt_lower.split())
_has_code_signal = is_coding or detected_intent is not None
if os.path.isdir(kd) and budget_ok() and (_word_count >= 15 or _has_code_signal):
    words = set(re.findall(r'\b[a-zA-Z]{3,}\b', prompt_lower))
    words |= set(re.findall(r'[\uac00-\ud7a3]{2,}', prompt))
    stops = {"the","and","for","that","this","with","from","have","will",
             "but","not","are","was","can","could","should","about",
             "just","also","want","need","like","make","please","help","use","try"}
    kws = words - stops
    if kws:
        # Load or rebuild index
        index_path = os.path.join(kd, ".index.json")
        index = {}
        try:
            if os.path.exists(index_path):
                with open(index_path, "r") as f:
                    index = json.load(f)
                if not isinstance(index, dict):
                    print(f"[OMG] prompt-enhancer: index.json is not a dict ({type(index).__name__}), rebuilding", file=sys.stderr)
                    try:
                        os.remove(index_path)
                    except OSError:
                        pass
                    index = {}
        except (json.JSONDecodeError, ValueError):
            # Corrupted index — delete and rebuild
            try:
                os.remove(index_path)
            except OSError:
                pass
            index = {}
        except FileNotFoundError:
            index = {}
        except Exception:
            index = {}

        # Scan files, rebuild stale/missing entries (cap: 30 files)
        rebuild = False
        file_count = 0
        for root, dirs, files in os.walk(kd):
            for fn in files:
                if not fn.endswith(".md") or fn.startswith("."):
                    continue
                file_count += 1
                if file_count > 30:
                    break
                fp = os.path.join(root, fn)
                try:
                    mtime = str(os.path.getmtime(fp))
                    cached = index.get(fp, {})
                    if cached.get("mtime") == mtime:
                        continue  # still fresh
                    # Read and index (sanitize potential secrets before caching)
                    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(1500).lower()
                    # Strip lines that look like secret assignments before caching
                    sanitized_lines = []
                    for cline in content.split("\n"):
                        if re.search(r'(?:key|secret|token|password|credential)\s*[:=]', cline):
                            continue
                        sanitized_lines.append(cline)
                    content = "\n".join(sanitized_lines)
                    index[fp] = {"mtime": mtime, "content": content}
                    rebuild = True
                except Exception:
                    pass
            if file_count > 30:
                break

        # Cap index at 100 entries, remove oldest by mtime if needed
        if len(index) > 100:
            # Sort by mtime (oldest first) and remove excess
            sorted_entries = sorted(index.items(), key=lambda x: x[1].get("mtime", "0"))
            entries_to_remove = len(index) - 100
            for fp, _ in sorted_entries[:entries_to_remove]:
                del index[fp]
            rebuild = True
        
        # Save index if changed using atomic write
        if rebuild:
            atomic_json_write(index_path, index)

        # Match keywords against cached content
        matches = []
        for fp, data in index.items():
            if not isinstance(data, dict) or "content" not in data:
                continue
            c = data["content"]
            sc = sum(1 for kw in kws if kw in c)
            if sc >= 2:
                matches.append((sc, fp))
        matches.sort(key=lambda x: -x[0])
        for sc, fp in matches[:2]:
            if not budget_ok():
                break
            rel = os.path.relpath(fp, omg_root)
            add(f"@knowledge({rel})")

# ═══════════════════════════════════════════════════════════
# 7b. MEMORY RETRIEVAL (cross-session context)
# ═══════════════════════════════════════════════════════════
if get_feature_flag('memory') and budget_ok():
    try:
        try:
            from hooks._memory import search_memories
        except ImportError:
            _memory = importlib.import_module("_memory")
            search_memories = _memory.search_memories
        # Reuse keywords already extracted for knowledge search
        _kws_local = locals().get("kws")
        _mem_kws = list(_kws_local) if _kws_local else []
        if _mem_kws:
            mem_context = search_memories(project_dir, _mem_kws, max_results=3, max_chars=200)
            if mem_context:
                add(f'@memory: {mem_context}')
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════
# 8. ERROR LOOP PREVENTION
# ═══════════════════════════════════════════════════════════
STUCK_SIGNALS = ["stuck", "same error", "keep getting", "tried everything",
                 "doesn't work", "막혀", "안돼", "실패", "같은에러", "모르겠"]
if any(signal_matches_text(sig, prompt) for sig in STUCK_SIGNALS) and budget_ok():
    tp = os.path.join(state_dir, "ledger", "failure-tracker.json")
    ctx = ""
    active = {}
    if os.path.exists(tp):
        try:
            with open(tp, "r") as f:
                t = json.load(f)
            active = {k: v.get("count", 0) for k, v in t.items()
                     if isinstance(v, dict) and v.get("count", 0) >= 2}
            if active:
                top = sorted(active.items(), key=lambda x: -x[1])[:2]
                ctx = f" ({', '.join(f'{k[:25]}×{c}' for k,c in top)})"
        except Exception:
            pass
    # Only inject if there are ≥2 tracked failures (not just keyword match)
    if active:
        # Dedup: skip if @stuck was injected within last 60 seconds
        ts_path = os.path.join(state_dir, ".last-stuck-ts")
        now = time.time()
        should_inject = True
        try:
            if os.path.exists(ts_path):
                with open(ts_path, "r") as f:
                    last_ts = float(f.read().strip())
                if now - last_ts < 60:
                    should_inject = False
        except (ValueError, OSError):
            pass  # Corrupt file → allow injection
        if should_inject:
            try:
                os.makedirs(os.path.dirname(ts_path) or ".", exist_ok=True)
                with open(ts_path, "w") as f:
                    f.write(str(now))
            except OSError:
                pass
            add(f"@stuck{ctx}: STOP retrying. /OMG:escalate codex | different approach | ask user")

# ═══════════════════════════════════════════════════════════
# 9. WRITE/EDIT FAILURE AWARENESS (anti-hallucination)
# ═══════════════════════════════════════════════════════════
# When hook errors or write/edit failures occur, Claude often claims success.
# Detect error patterns and inject a verification requirement.
WRITE_ERROR_SIGNALS = [
    "hook error", "error editing file", "error writing file",
    "error: pretooluse", "error: posttooluse",
    "security warning", "security_reminder",
    "⚠️", "xss", "innerhtml", "xss vulnerabilit",
    "hook 에러", "파일 수정 에러", "파일 쓰기 에러",
]
if any(signal_matches_text(sig, prompt) for sig in WRITE_ERROR_SIGNALS) and budget_ok():
    add(
        "@write-verify: Hook/Write/Edit error detected in conversation. "
        "BEFORE claiming success: READ the target file to verify changes are present. "
        "If file unchanged → retry with different method (Edit, Bash heredoc, or cat >). "
        "NEVER say 'updated successfully' without reading the file first."
    )

# ═══════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════
try:
    tool_count, _threshold, is_high_pressure = estimate_context_pressure(project_dir)
    if is_high_pressure:
        add(f"@context-pressure: High context usage detected ({tool_count} tool calls). Auto-saving state...")
except Exception:
    pass

if injections:
    output = "\n".join(injections)
    if len(output) > MAX_CHARS:
        output = output[:MAX_CHARS - 3] + "..."
    json.dump({"contextInjection": output}, sys.stdout)

sys.exit(0)
