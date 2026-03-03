# Agent-Model Routing Update — Latest Model Versions

## TL;DR

> **Quick Summary**: Update OMG's 14-agent model routing to document and configure the correct latest model versions: GPT 5.3/5.2 for Codex agents, Gemini 3.1 Pro Preview for frontend, Claude Sonnet 4/Haiku 3.5 for native agents.
> 
> **Deliverables**:
> - `_agent_registry.py` with `model_version` field on all 9 domain agents + new `CORE_AGENT_MODELS` dict for 5 core agents
> - All 14 `agents/*.md` files with normalized frontmatter and model version annotations
> - `README.md` with updated Agent-Model Routing table (14 rows, model version column)
> - `team_router.py` exposing `model_version` in dispatch params
> - All tests passing with updated assertions
> 
> **Estimated Effort**: Short (2-3 hours)
> **Parallel Execution**: YES — 3 waves
> **Critical Path**: Task 1 → Tasks 3,4,5 → Task 6

---

## Context

### Original Request
Update OMG agent-model routing to use the correct latest model versions for each agent, ensuring Claude Sonnet/Haiku, GPT 5.3/5.2, and Gemini 3.1 Pro Preview are properly mapped.

### Interview Summary
**Key Discussions**:
- GPT 5.3 for code-level work + code review (backend, security, database, infra, critic)
- GPT 5.2 for plan review (architect agent)
- Gemini 3.1 Pro Preview for frontend/visual work
- Claude Sonnet 4 for accuracy-critical agents (executor, testing, architect-mode, qa-tester, implement-mode)
- Claude Haiku 3.5 for speed-critical agents (research-mode, escalation-router)
- Scope: Registry + docs + README — no CLI invocation changes

**Research Findings**:
- 5 core agents (architect, critic, executor, qa-tester, escalation-router) are NOT in keyword-matched registry — by design
- Frontmatter inconsistency: 5 core agents use `model:` field, 9 domain agents use `preferred_model:`
- CLI invocations don't pass `--model` flags — model_version is informational
- Test `test_registry_has_9_agents` will break if agents are blindly added to registry

### Metis Review
**Identified Gaps** (addressed):
- Core agents must NOT be added to keyword-matched `AGENT_REGISTRY` (would cause collision with domain routing) → **Solution**: New `CORE_AGENT_MODELS` dict
- Frontmatter field name inconsistency → **Solution**: Normalize all 14 agents to `model:` (shorter, already used by core agents) + add `model_version:` field
- `model_version` has no runtime consumer → **Solution**: Explicitly documentary. Comment in code.
- Test assertions hardcoded to 9 → **Solution**: Update test to match new count expectation (still 9 in AGENT_REGISTRY, CORE_AGENT_MODELS is separate)

---

## Work Objectives

### Core Objective
Accurately document and configure the latest model version for every OMG agent, ensuring the registry, agent definitions, documentation, and tests are consistent and correct.

### Concrete Deliverables
- `hooks/_agent_registry.py` — `model_version` on 9 entries + `CORE_AGENT_MODELS` dict with 5 entries
- `agents/*.md` (14 files) — normalized frontmatter with model version
- `README.md` — updated Agent-Model Routing table
- `runtime/team_router.py` — `model_version` in dispatch params
- `tests/test_agent_registry.py` — updated assertions + new model_version tests
- `tests/test_team_router.py` — updated to handle model_version

### Definition of Done
- [x] `python3 -m pytest tests/test_agent_registry.py tests/test_team_router.py -v` → ALL PASS
- [x] All 14 agents have documented model versions in both registry/dict and .md frontmatter
- [x] README table shows 14 agents with correct model version column
- [x] No existing `resolve_agent()` behavior changed for the 9 domain agents

### Must Have
- `model_version` field on every domain agent registry entry
- `CORE_AGENT_MODELS` dict for 5 core agents (separate from keyword routing)
- Normalized frontmatter across all 14 agent .md files
- Updated README table with model version column
- All existing tests still pass

### Must NOT Have (Guardrails)
- ❌ DO NOT add core agents to keyword-matched `AGENT_REGISTRY` (collision risk)
- ❌ DO NOT modify `invoke_codex()` or `invoke_gemini()` CLI invocations
- ❌ DO NOT add `--model` flags to subprocess calls
- ❌ DO NOT change `preferred_model` field meaning (provider, not version)
- ❌ DO NOT touch `vendor/` directory
- ❌ DO NOT add fallback chain logic (like OMC's model fallbacks)
- ❌ DO NOT modify `prompt-enhancer.py` behavior
- ❌ DO NOT add MCP tools or skills to core agents

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES (pytest)
- **Automated tests**: Tests-after (update existing tests + add new assertions)
- **Framework**: pytest
- **QA Policy**: Each task verified by running pytest + inline python assertions

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — registry + agent files):
├── Task 1: Update _agent_registry.py (model_version + CORE_AGENT_MODELS) [quick]
├── Task 2: Normalize all 14 agent .md frontmatter [quick]

Wave 2 (After Wave 1 — downstream consumers):
├── Task 3: Update team_router.py dispatch params [quick]
├── Task 4: Update README.md model routing table [quick]
├── Task 5: Update test files (assertions + new tests) [quick]

Wave 3 (After Wave 2 — verification):
├── Task 6: Run full verification suite (AC1-AC6) [quick]

Wave FINAL (After ALL tasks — independent review):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Scope fidelity check (deep)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | — | 3, 4, 5 |
| 2 | — | 4 |
| 3 | 1 | 6 |
| 4 | 1, 2 | 6 |
| 5 | 1 | 6 |
| 6 | 3, 4, 5 | F1-F3 |

### Agent Dispatch Summary

| Wave | Tasks | Categories |
|------|-------|------------|
| 1 | 2 | T1 → `quick`, T2 → `quick` |
| 2 | 3 | T3 → `quick`, T4 → `quick`, T5 → `quick` |
| 3 | 1 | T6 → `quick` |
| FINAL | 3 | F1 → `oracle`, F2 → `unspecified-high`, F3 → `deep` |

---

## Model Version Reference (Canonical Mapping)

| Agent | Provider | Model Version | Role |
|-------|----------|--------------|------|
| omg-frontend-designer | gemini-cli | `gemini-3.1-pro-preview` | Visual/UI |
| omg-backend-engineer | codex-cli | `gpt-5.3` | Code: API/logic |
| omg-security-auditor | codex-cli | `gpt-5.3` | Code: security |
| omg-database-engineer | codex-cli | `gpt-5.3` | Code: SQL/schema |
| omg-infra-engineer | codex-cli | `gpt-5.3` | Code: Docker/CI |
| omg-testing-engineer | claude | `claude-sonnet-4` | Test design |
| omg-research-mode | claude | `claude-haiku-3.5` | Info retrieval |
| omg-architect-mode | claude | `claude-sonnet-4` | System design |
| omg-implement-mode | claude | `claude-sonnet-4` | Code fallback |
| omg-architect | codex-cli | `gpt-5.2` | Plan review |
| omg-critic | codex-cli | `gpt-5.3` | Code review |
| omg-executor | claude | `claude-sonnet-4` | Implementation |
| omg-qa-tester | claude | `claude-sonnet-4` | QA test writing |
| omg-escalation-router | claude | `claude-haiku-3.5` | Routing |

---

## TODOs


- [x] 1. Add `model_version` field to AGENT_REGISTRY + create CORE_AGENT_MODELS dict

  **What to do**:
  - Add `'model_version': '<version>'` to each of the 9 existing entries in `AGENT_REGISTRY`
  - Use these exact values:
    - `frontend-designer`: `'gemini-3.1-pro-preview'`
    - `backend-engineer`: `'gpt-5.3'`
    - `security-auditor`: `'gpt-5.3'`
    - `database-engineer`: `'gpt-5.3'`
    - `testing-engineer`: `'claude-sonnet-4'`
    - `infra-engineer`: `'gpt-5.3'`
    - `research-mode`: `'claude-haiku-3.5'`
    - `architect-mode`: `'claude-sonnet-4'`
    - `implement-mode`: `'claude-sonnet-4'`
  - Create a new `CORE_AGENT_MODELS` dict (AFTER `AGENT_REGISTRY`, BEFORE `_MODEL_CACHE`) with 5 entries:
    ```python
    CORE_AGENT_MODELS = {
        'architect': {
            'preferred_model': 'codex-cli',
            'model_version': 'gpt-5.2',
            'task_category': None,
            'description': 'System design + planning + delegation routing.',
            'agent_file': 'agents/omg-architect.md',
        },
        'critic': {
            'preferred_model': 'codex-cli',
            'model_version': 'gpt-5.3',
            'task_category': None,
            'description': 'Code review — 3 perspectives, no LGTM allowed.',
            'agent_file': 'agents/omg-critic.md',
        },
        'executor': {
            'preferred_model': 'claude',
            'model_version': 'claude-sonnet-4',
            'task_category': 'deep',
            'description': 'Implements code with evidence, auto-escalates when stuck.',
            'agent_file': 'agents/omg-executor.md',
        },
        'qa-tester': {
            'preferred_model': 'claude',
            'model_version': 'claude-sonnet-4',
            'task_category': 'unspecified-high',
            'description': 'User-journey test writer — no boilerplate.',
            'agent_file': 'agents/omg-qa-tester.md',
        },
        'escalation-router': {
            'preferred_model': 'claude',
            'model_version': 'claude-haiku-3.5',
            'task_category': None,
            'description': 'Routes problems to Codex/Gemini/CCG based on domain.',
            'agent_file': 'agents/omg-escalation-router.md',
        },
    }
    ```
  - Add a docstring comment above `CORE_AGENT_MODELS`:
    `"""Core agent model preferences. NOT keyword-matched — used by orchestration pipeline only. model_version is informational (not passed to CLI)."""`
  - Export `CORE_AGENT_MODELS` from the module (add to imports if other files need it)

  **Must NOT do**:
  - Do NOT add core agents to `AGENT_REGISTRY` (keyword collision risk)
  - Do NOT add `trigger_keywords` or `skills` to core agents
  - Do NOT change `preferred_model` field meaning — it stays as provider string
  - Do NOT modify `resolve_agent()` — it only searches `AGENT_REGISTRY`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single file edit with clear exact content. No ambiguity.
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `backend-patterns`: Not a backend task — this is config editing

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 2)
  - **Blocks**: Tasks 3, 4, 5
  - **Blocked By**: None (can start immediately)

  **References** (CRITICAL):

  **Pattern References**:
  - `hooks/_agent_registry.py:11-96` — Full AGENT_REGISTRY dict structure. Each entry has: preferred_model, task_category, skills, trigger_keywords, mcp_tools, description, agent_file. Add `model_version` as the LAST field in each entry, before the closing `},`
  - `hooks/_agent_registry.py:98-99` — `_MODEL_CACHE` definition. Place `CORE_AGENT_MODELS` dict BETWEEN line 96 (end of AGENT_REGISTRY) and line 98 (_MODEL_CACHE)

  **Test References**:
  - `tests/test_agent_registry.py:53-54` — `test_registry_has_9_agents` asserts `len(AGENT_REGISTRY) == 9`. This MUST still pass (we're not adding to AGENT_REGISTRY)
  - `tests/test_agent_registry.py:57-61` — `test_all_agents_have_required_fields` checks for `{'preferred_model', 'task_category', 'skills', 'trigger_keywords', 'description'}`. The new `model_version` field is optional (not in required set) so this test still passes

  **WHY Each Reference Matters**:
  - Registry structure shows exact dict format to follow — prevents schema drift
  - _MODEL_CACHE location determines where CORE_AGENT_MODELS goes physically
  - Test assertions confirm our change won't break existing tests

  **Acceptance Criteria**:

  - [x] `python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import AGENT_REGISTRY; assert all('model_version' in v for v in AGENT_REGISTRY.values()); print('PASS: all 9 have model_version')"` → PASS
  - [x] `python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import CORE_AGENT_MODELS; assert len(CORE_AGENT_MODELS) == 5; print('PASS: 5 core agents')"` → PASS
  - [x] `python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import AGENT_REGISTRY; assert len(AGENT_REGISTRY) == 9; print('PASS: still 9 domain agents')"` → PASS

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Verify model_version values are specific (not generic)
    Tool: Bash (python3 inline)
    Preconditions: Task 1 changes applied to _agent_registry.py
    Steps:
      1. Run: python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import AGENT_REGISTRY, CORE_AGENT_MODELS; GENERIC={'opus','sonnet','haiku','claude','codex','gemini','codex-cli','gemini-cli'}; versions=[v.get('model_version','') for v in {**AGENT_REGISTRY,**CORE_AGENT_MODELS}.values()]; bad=[x for x in versions if x in GENERIC or not x]; assert not bad, f'Generic versions found: {bad}'; print('PASS')"
      2. Assert output contains 'PASS'
    Expected Result: All 14 model_version values are specific version strings
    Failure Indicators: AssertionError listing generic values
    Evidence: .sisyphus/evidence/task-1-model-versions-specific.txt

  Scenario: Verify resolve_agent() unchanged for domain agents
    Tool: Bash (python3 inline)
    Preconditions: Task 1 changes applied
    Steps:
      1. Run: python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import resolve_agent; r=resolve_agent({'auth','jwt','vulnerability'}); assert r['name']=='security-auditor'; assert r['preferred_model']=='codex-cli'; r2=resolve_agent({'css','layout','responsive'}); assert r2['name']=='frontend-designer'; assert r2['preferred_model']=='gemini-cli'; print('PASS: resolve_agent unchanged')"
      2. Assert output contains 'PASS'
    Expected Result: Domain agent keyword matching behavior identical to before
    Failure Indicators: AssertionError on agent name or preferred_model
    Evidence: .sisyphus/evidence/task-1-resolve-agent-unchanged.txt
  ```

  **Evidence to Capture:**
  - [x] task-1-model-versions-specific.txt
  - [x] task-1-resolve-agent-unchanged.txt

  **Commit**: YES
  - Message: `feat(agents): add model_version to registry + CORE_AGENT_MODELS dict`
  - Files: `hooks/_agent_registry.py`
  - Pre-commit: `python3 -m pytest tests/test_agent_registry.py -v`

- [x] 2. Normalize frontmatter across all 14 agent .md files

  **What to do**:
  - For EACH of the 14 files in `agents/`, update the YAML frontmatter (between `---` markers) to include:
    - `model:` field — the provider string (`codex-cli`, `gemini-cli`, `claude`)
    - `model_version:` field — the specific version string from the canonical mapping table
  - **5 core agents** (currently use `model: opus` or `model: sonnet`):
    - `omg-architect.md`: `model: codex-cli` / `model_version: gpt-5.2`
    - `omg-critic.md`: `model: codex-cli` / `model_version: gpt-5.3`
    - `omg-executor.md`: `model: claude` / `model_version: claude-sonnet-4`
    - `omg-qa-tester.md`: `model: claude` / `model_version: claude-sonnet-4`
    - `omg-escalation-router.md`: `model: claude` / `model_version: claude-haiku-3.5`
  - **9 domain agents** (currently use `preferred_model:` — keep that field name for backward compat, ADD `model_version:`):
    - `omg-frontend-designer.md`: keep `preferred_model: gemini-cli`, add `model_version: gemini-3.1-pro-preview`
    - `omg-backend-engineer.md`: keep `preferred_model: codex-cli`, add `model_version: gpt-5.3`
    - `omg-security-auditor.md`: keep `preferred_model: codex-cli`, add `model_version: gpt-5.3`
    - `omg-database-engineer.md`: keep `preferred_model: codex-cli`, add `model_version: gpt-5.3`
    - `omg-testing-engineer.md`: keep `preferred_model: claude`, add `model_version: claude-sonnet-4`
    - `omg-infra-engineer.md`: keep `preferred_model: codex-cli`, add `model_version: gpt-5.3`
    - `omg-research-mode.md`: keep `preferred_model: claude`, add `model_version: claude-haiku-3.5`
    - `omg-architect-mode.md`: keep `preferred_model: claude`, add `model_version: claude-sonnet-4`
    - `omg-implement-mode.md`: keep `preferred_model: domain-dependent`, add `model_version: claude-sonnet-4` (Claude fallback)
  - In each file, also update the "Preferred Tools" section first bullet to reference the actual model version:
    - E.g., `**Codex CLI (GPT 5.3)**: Complex algorithmic reasoning...`
    - E.g., `**Gemini CLI (Gemini 3.1 Pro Preview)**: Complex visual reasoning...`
    - E.g., `**Claude (Sonnet 4)**: Deep reasoning, edge case analysis...`

  **Must NOT do**:
  - Do NOT rename `preferred_model` to `model` in domain agent files (backward compat)
  - Do NOT change any constraint sections, MCP tool lists, or descriptions beyond model references
  - Do NOT add or remove frontmatter fields beyond `model_version`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Repetitive frontmatter edits across 14 files with exact values provided
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 1)
  - **Blocks**: Task 4
  - **Blocked By**: None (can start immediately)

  **References** (CRITICAL):

  **Pattern References**:
  - `agents/omg-frontend-designer.md:1-6` — Domain agent frontmatter format: `name`, `description`, `preferred_model`, `tools` between `---` markers. Add `model_version:` after `preferred_model:`
  - `agents/omg-architect.md:1-6` — Core agent frontmatter format: `name`, `description`, `tools`, `model` between `---` markers. Change `model: opus` to `model: codex-cli`, add `model_version: gpt-5.2`
  - `agents/omg-qa-tester.md:1-6` — Already uses `model: sonnet`. Change to `model: claude`, add `model_version: claude-sonnet-4`

  **WHY Each Reference Matters**:
  - Frontmatter format varies between core and domain agents — must handle both patterns
  - qa-tester shows the `model: sonnet` pattern that needs updating

  **Acceptance Criteria**:

  - [x] All 14 agent .md files have a `model_version:` field in frontmatter
  - [x] `grep -l 'model_version:' agents/*.md | wc -l` → 14
  - [x] No file still contains `model: opus` → `grep -rl 'model: opus' agents/` → empty
  - [x] No file still contains `model: sonnet` (old generic) → `grep -rn 'model: sonnet$' agents/` → empty

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All 14 files have model_version in frontmatter
    Tool: Bash (grep)
    Preconditions: All 14 agent .md files updated
    Steps:
      1. Run: grep -l 'model_version:' agents/*.md | wc -l
      2. Assert output is exactly `14`
      3. Run: grep -rn 'model: opus' agents/
      4. Assert output is empty (no matches)
    Expected Result: 14 files with model_version, 0 files with `model: opus`
    Failure Indicators: Count != 14, or opus found
    Evidence: .sisyphus/evidence/task-2-frontmatter-check.txt

  Scenario: Frontmatter model_version values match canonical mapping
    Tool: Bash (grep)
    Preconditions: All files updated
    Steps:
      1. Run: grep 'model_version:' agents/omg-frontend-designer.md
      2. Assert contains `gemini-3.1-pro-preview`
      3. Run: grep 'model_version:' agents/omg-backend-engineer.md
      4. Assert contains `gpt-5.3`
      5. Run: grep 'model_version:' agents/omg-architect.md
      6. Assert contains `gpt-5.2`
      7. Run: grep 'model_version:' agents/omg-executor.md
      8. Assert contains `claude-sonnet-4`
      9. Run: grep 'model_version:' agents/omg-research-mode.md
      10. Assert contains `claude-haiku-3.5`
    Expected Result: Each agent has the correct specific model version
    Failure Indicators: Wrong version string in any agent file
    Evidence: .sisyphus/evidence/task-2-version-values.txt
  ```

  **Evidence to Capture:**
  - [x] task-2-frontmatter-check.txt
  - [x] task-2-version-values.txt

  **Commit**: YES
  - Message: `docs(agents): normalize frontmatter with model version annotations`
  - Files: `agents/*.md` (14 files)
  - Pre-commit: `grep -c 'model_version:' agents/*.md`


- [x] 3. Update `team_router.py` to expose `model_version` in dispatch params

  **What to do**:
  - In `get_dispatch_params()` (line 120-146 of `_agent_registry.py`):
    - Add `'model_version': config.get('model_version', 'unknown')` to the returned `params` dict
  - In `team_router.py` `dispatch_to_model()` (line 237-272):
    - When returning the claude fallback dict (line 266-270), add `'model_version': agent.get('model_version', 'unknown')`
  - In `team_router.py` `package_prompt()` (line 167-190):
    - Include model_version in the packaged prompt string: add a line `f"Model: {agent.get('model_version', 'not specified')}\n"`
  - Add a new helper function `get_core_agent_model(agent_name: str) -> Optional[dict]`:
    ```python
    def get_core_agent_model(agent_name: str) -> Optional[dict]:
        """Get model preference for a core (non-keyword-matched) agent."""
        from _agent_registry import CORE_AGENT_MODELS
        return CORE_AGENT_MODELS.get(agent_name)
    ```

  **Must NOT do**:
  - Do NOT modify `invoke_codex()` or `invoke_gemini()` subprocess calls
  - Do NOT add `--model` flags to CLI invocations
  - Do NOT change the codex/gemini command arrays

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Small targeted edits to 2 files with clear locations
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 5)
  - **Blocks**: Task 6
  - **Blocked By**: Task 1

  **References** (CRITICAL):

  **Pattern References**:
  - `hooks/_agent_registry.py:120-146` — `get_dispatch_params()` function. The `params` dict on lines 138-143 is where `model_version` gets added
  - `runtime/team_router.py:237-272` — `dispatch_to_model()` function. Claude fallback dict on line 266-270 needs `model_version`
  - `runtime/team_router.py:167-190` — `package_prompt()` function. Prompt template on lines 183-188 needs model version line

  **WHY Each Reference Matters**:
  - `get_dispatch_params()` is the primary API other code uses to ask "what model should I use?"
  - `dispatch_to_model()` is the actual dispatch path — model_version should flow through
  - `package_prompt()` builds the prompt string — model info helps external CLIs context

  **Acceptance Criteria**:

  - [x] `python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import get_dispatch_params; p=get_dispatch_params('backend-engineer'); assert 'model_version' in p; assert p['model_version']=='gpt-5.3'; print('PASS')"` → PASS

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Dispatch params include model_version
    Tool: Bash (python3 inline)
    Preconditions: Tasks 1+3 changes applied
    Steps:
      1. Run: python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import get_dispatch_params; p=get_dispatch_params('frontend-designer'); assert p['model_version']=='gemini-3.1-pro-preview'; p2=get_dispatch_params('security-auditor'); assert p2['model_version']=='gpt-5.3'; print('PASS: model_version in dispatch')"
      2. Assert output contains 'PASS'
    Expected Result: model_version flows through dispatch params for all agents
    Failure Indicators: KeyError or wrong version string
    Evidence: .sisyphus/evidence/task-3-dispatch-model-version.txt

  Scenario: Core agent model lookup works
    Tool: Bash (python3 inline)
    Preconditions: Tasks 1+3 applied
    Steps:
      1. Run: python3 -c "import sys; sys.path.insert(0,'hooks'); sys.path.insert(0,'runtime'); from team_router import get_core_agent_model; m=get_core_agent_model('architect'); assert m is not None; assert m['model_version']=='gpt-5.2'; m2=get_core_agent_model('executor'); assert m2['model_version']=='claude-sonnet-4'; print('PASS: core agent lookup')"
      2. Assert output contains 'PASS'
    Expected Result: Core agent lookup returns correct model versions
    Failure Indicators: None return or wrong version
    Evidence: .sisyphus/evidence/task-3-core-agent-lookup.txt
  ```

  **Evidence to Capture:**
  - [x] task-3-dispatch-model-version.txt
  - [x] task-3-core-agent-lookup.txt

  **Commit**: NO (groups with Task 4+5)

- [x] 4. Update README.md Agent-Model Routing table

  **What to do**:
  - Find the "## Agent-Model Routing" section in `README.md`
  - Replace the existing 9-row table with a 14-row table that includes a "Model Version" column:
    ```markdown
    ## Agent-Model Routing

    OMG assigns specific models to domain agents for optimal results:

    | Agent | Provider | Model Version | Domain |
    |-------|----------|--------------|--------|
    | omg-frontend-designer | gemini-cli | Gemini 3.1 Pro Preview | UI/UX, CSS, responsive design |
    | omg-backend-engineer | codex-cli | GPT 5.3 | APIs, logic, algorithms |
    | omg-security-auditor | codex-cli | GPT 5.3 | Auth, encryption, vulnerabilities |
    | omg-database-engineer | codex-cli | GPT 5.3 | SQL, migrations, schema |
    | omg-testing-engineer | claude | Claude Sonnet 4 | Unit, integration, E2E tests |
    | omg-infra-engineer | codex-cli | GPT 5.3 | Docker, CI/CD, deployment |
    | omg-research-mode | claude | Claude Haiku 3.5 | Web search, docs lookup |
    | omg-architect-mode | claude | Claude Sonnet 4 | System design, trade-offs |
    | omg-implement-mode | domain-dependent | Claude Sonnet 4 (fallback) | Coding with TDD |
    | omg-architect | codex-cli | GPT 5.2 | Planning, delegation |
    | omg-critic | codex-cli | GPT 5.3 | Code review (3 perspectives) |
    | omg-executor | claude | Claude Sonnet 4 | Implementation with evidence |
    | omg-qa-tester | claude | Claude Sonnet 4 | User-journey test writing |
    | omg-escalation-router | claude | Claude Haiku 3.5 | Cross-model coordination |
    ```
  - Update the "How it works" section below the table to mention model versions:
    - Codex agents use GPT 5.3 (code) or GPT 5.2 (planning)
    - Gemini agents use Gemini 3.1 Pro Preview
    - Claude agents use Sonnet 4 (deep) or Haiku 3.5 (fast)
  - Update the introductory sentence: "OMG assigns specific models to **all 14** agents for optimal results:"

  **Must NOT do**:
  - Do NOT change any other README sections (installation, commands, file structure, etc.)
  - Do NOT rewrite the "How it works" explanatory bullets beyond model name updates

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Documentation-only change with exact table content provided
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 3, 5)
  - **Blocks**: Task 6
  - **Blocked By**: Tasks 1, 2 (need correct values from registry and frontmatter)

  **References** (CRITICAL):

  **Pattern References**:
  - `README.md` search for `## Agent-Model Routing` — The existing table section starts with this heading. Replace everything from the heading through the end of the `Fallback:` bullet (inclusive)

  **WHY Each Reference Matters**:
  - Must find exact section boundaries to replace cleanly without touching adjacent content

  **Acceptance Criteria**:

  - [x] `grep -c '^| omg-' README.md` → output is `14`
  - [x] `grep 'GPT 5.3' README.md | wc -l` → at least 5 (5 agents + explanatory text)
  - [x] `grep 'GPT 5.2' README.md | wc -l` → at least 1 (architect)
  - [x] `grep 'Gemini 3.1 Pro Preview' README.md | wc -l` → at least 1

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: README table has 14 agent rows with correct model versions
    Tool: Bash (grep)
    Preconditions: README.md updated
    Steps:
      1. Run: grep -c '^| omg-' README.md
      2. Assert output is `14`
      3. Run: grep 'Model Version' README.md
      4. Assert output contains `Model Version` (column header exists)
      5. Run: grep 'GPT 5.2' README.md | grep architect
      6. Assert output shows architect row with GPT 5.2
    Expected Result: 14-row table with Model Version column, correct values
    Failure Indicators: Count != 14, missing column header, wrong version on architect
    Evidence: .sisyphus/evidence/task-4-readme-table.txt
  ```

  **Evidence to Capture:**
  - [x] task-4-readme-table.txt

  **Commit**: NO (groups with Tasks 3+5)

- [x] 5. Update test files with new assertions + model_version validation

  **What to do**:
  - In `tests/test_agent_registry.py`:
    - Add import: `from _agent_registry import CORE_AGENT_MODELS` (alongside existing imports)
    - Add new test `test_all_agents_have_model_version()`:
      ```python
      def test_all_agents_have_model_version():
          for name, config in AGENT_REGISTRY.items():
              assert 'model_version' in config, f"Agent {name} missing model_version"
              assert config['model_version'], f"Agent {name} has empty model_version"
      ```
    - Add new test `test_core_agent_models_has_5_entries()`:
      ```python
      def test_core_agent_models_has_5_entries():
          assert len(CORE_AGENT_MODELS) == 5
      ```
    - Add new test `test_core_agents_have_model_version()`:
      ```python
      def test_core_agents_have_model_version():
          for name, config in CORE_AGENT_MODELS.items():
              assert 'model_version' in config, f"Core agent {name} missing model_version"
              assert 'preferred_model' in config, f"Core agent {name} missing preferred_model"
      ```
    - Add new test `test_model_versions_are_specific()`:
      ```python
      def test_model_versions_are_specific():
          GENERIC = {'opus', 'sonnet', 'haiku', 'claude', 'codex', 'gemini', 'codex-cli', 'gemini-cli'}
          all_agents = {**AGENT_REGISTRY, **CORE_AGENT_MODELS}
          for name, config in all_agents.items():
              v = config.get('model_version', '')
              assert v not in GENERIC, f"{name} has generic model_version: {v}"
              assert v, f"{name} has empty model_version"
      ```
    - **DO NOT change** `test_registry_has_9_agents` — it should still pass (AGENT_REGISTRY stays at 9)
    - **DO NOT change** `test_all_agents_have_required_fields` — `model_version` is NOT in the required set (it's new/optional in the required set sense, though every agent should have it)
  - In `tests/test_team_router.py`:
    - Add test `test_dispatch_params_include_model_version()`:
      ```python
      def test_dispatch_params_include_model_version() -> None:
          import sys; sys.path.insert(0, 'hooks')
          from _agent_registry import get_dispatch_params
          params = get_dispatch_params('backend-engineer')
          assert 'model_version' in params
          assert params['model_version'] == 'gpt-5.3'
      ```

  **Must NOT do**:
  - Do NOT delete or modify any existing test functions
  - Do NOT change assertion values in existing tests (they should all still pass)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Adding test functions with exact code provided
  - **Skills**: [`python-testing`]
    - `python-testing`: Pytest patterns, assertions, test structure

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 3, 4)
  - **Blocks**: Task 6
  - **Blocked By**: Task 1 (registry must exist for tests to reference)

  **References** (CRITICAL):

  **Pattern References**:
  - `tests/test_agent_registry.py:1-66` — Full test file. Import pattern on lines 6-12, test functions on lines 15-66. New tests go after line 66 (end of file)
  - `tests/test_team_router.py:1-91` — Full test file. New dispatch test goes after line 91 (end of file)

  **Test References**:
  - `tests/test_agent_registry.py:53-54` — `test_registry_has_9_agents` — MUST NOT change, must still pass
  - `tests/test_agent_registry.py:57-61` — `test_all_agents_have_required_fields` — MUST NOT change, must still pass

  **WHY Each Reference Matters**:
  - Existing test functions define the contract — we add to them, never modify
  - Import section shows what's already imported — add CORE_AGENT_MODELS to existing import

  **Acceptance Criteria**:

  - [x] `python3 -m pytest tests/test_agent_registry.py -v` → ALL PASS (old + new tests)
  - [x] `python3 -m pytest tests/test_team_router.py -v` → ALL PASS (old + new tests)
  - [x] New tests appear in output: `test_all_agents_have_model_version`, `test_core_agent_models_has_5_entries`, `test_core_agents_have_model_version`, `test_model_versions_are_specific`

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All tests pass including new model_version tests
    Tool: Bash (pytest)
    Preconditions: Tasks 1, 3, 5 all applied
    Steps:
      1. Run: python3 -m pytest tests/test_agent_registry.py tests/test_team_router.py -v 2>&1
      2. Assert output contains `passed` and does NOT contain `FAILED`
      3. Assert output contains `test_all_agents_have_model_version`
      4. Assert output contains `test_core_agent_models_has_5_entries`
      5. Assert output contains `test_model_versions_are_specific`
    Expected Result: All tests pass, including 4 new tests + all existing tests
    Failure Indicators: Any FAILED or ERROR in output
    Evidence: .sisyphus/evidence/task-5-test-results.txt

  Scenario: Existing tests unchanged and still passing
    Tool: Bash (pytest)
    Preconditions: All changes applied
    Steps:
      1. Run: python3 -m pytest tests/test_agent_registry.py::test_registry_has_9_agents -v
      2. Assert PASSED (registry still has 9)
      3. Run: python3 -m pytest tests/test_agent_registry.py::test_resolve_agent_security_keywords -v
      4. Assert PASSED (domain routing unchanged)
    Expected Result: Pre-existing tests unaffected by our changes
    Failure Indicators: Any FAILED test that existed before our changes
    Evidence: .sisyphus/evidence/task-5-existing-tests-intact.txt
  ```

  **Evidence to Capture:**
  - [x] task-5-test-results.txt
  - [x] task-5-existing-tests-intact.txt

  **Commit**: YES (groups Tasks 3+4+5)
  - Message: `feat(routing): expose model_version in dispatch + update docs and tests`
  - Files: `runtime/team_router.py`, `README.md`, `tests/test_agent_registry.py`, `tests/test_team_router.py`
  - Pre-commit: `python3 -m pytest tests/test_agent_registry.py tests/test_team_router.py -v`

- [x] 6. Run full verification suite (AC1-AC6)

  **What to do**:
  - Execute ALL acceptance criteria commands sequentially:
    - AC1: `python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import AGENT_REGISTRY; assert len(AGENT_REGISTRY)==9; print('AC1 PASS: 9 domain agents')"` 
    - AC2: `python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import CORE_AGENT_MODELS; assert len(CORE_AGENT_MODELS)==5; print('AC2 PASS: 5 core agents')"` 
    - AC3: `python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import AGENT_REGISTRY, CORE_AGENT_MODELS; GENERIC={'opus','sonnet','haiku','claude','codex','gemini','codex-cli','gemini-cli'}; all_a={**AGENT_REGISTRY,**CORE_AGENT_MODELS}; versions=[v.get('model_version','') for v in all_a.values()]; bad=[x for x in versions if x in GENERIC or not x]; assert not bad, f'Generic: {bad}'; print('AC3 PASS: all specific')"` 
    - AC4: `python3 -m pytest tests/test_agent_registry.py tests/test_team_router.py -v`
    - AC5: `python3 -c "import sys,re; sys.path.insert(0,'hooks'); from _agent_registry import AGENT_REGISTRY; [open(v['agent_file']).read() for v in AGENT_REGISTRY.values()]; print('AC5 PASS: all agent files exist and readable')"` 
    - AC6: `grep -c '^| omg-' README.md` (expect 14)
  - If ANY check fails, report the failure with exact error — do NOT mark task complete
  - Save all outputs to evidence files

  **Must NOT do**:
  - Do NOT modify any files in this task — verification only
  - Do NOT skip any AC check

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Running commands and capturing output only
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential after all Wave 2 tasks)
  - **Blocks**: Final verification wave
  - **Blocked By**: Tasks 3, 4, 5

  **References** (CRITICAL):

  **Pattern References**:
  - This plan's "Success Criteria" section — AC commands are defined there

  **Acceptance Criteria**:

  - [x] All 6 AC checks output PASS
  - [x] Evidence files saved for each check

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Full acceptance criteria suite passes
    Tool: Bash (python3 + grep)
    Preconditions: All Tasks 1-5 complete
    Steps:
      1. Run AC1 through AC6 sequentially
      2. Capture stdout of each to .sisyphus/evidence/task-6-ac{N}.txt
      3. Assert ALL contain 'PASS' or expected count
    Expected Result: 6/6 acceptance criteria pass
    Failure Indicators: Any AC returning error or unexpected value
    Evidence: .sisyphus/evidence/task-6-full-verification.txt
  ```

  **Evidence to Capture:**
  - [x] task-6-full-verification.txt (combined output of all AC checks)

  **Commit**: NO (verification only)

---
## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 3 review agents run in PARALLEL. ALL must APPROVE.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read registry, check frontmatter, verify README). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [6/6] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `python3 -m pytest tests/ -v`. Review all changed files for: unused imports, inconsistent naming, dead code, missing docstrings on new functions. Check model_version strings are consistent between registry and agent .md files.
  Output: `Tests [PASS/FAIL] | Files [N clean/N issues] | Consistency [PASS/FAIL] | VERDICT`

- [x] F3. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify nothing beyond spec was built (no creep). Check "Must NOT do" compliance: no CLI invocation changes, no vendor/ touches, no prompt-enhancer changes.
  Output: `Tasks [6/6 compliant] | Must NOT [N/N clean] | VERDICT`

---

## Commit Strategy

| After Task | Commit Message | Files |
|-----------|---------------|-------|
| 1 | `feat(agents): add model_version to registry + CORE_AGENT_MODELS dict` | `hooks/_agent_registry.py` |
| 2 | `docs(agents): normalize frontmatter with model version annotations` | `agents/*.md` (14 files) |
| 3+4+5 | `feat(routing): expose model_version in dispatch + update docs and tests` | `runtime/team_router.py`, `README.md`, `tests/*.py` |

---

## Success Criteria

### Verification Commands
```bash
python3 -m pytest tests/test_agent_registry.py tests/test_team_router.py -v  # Expected: ALL PASS
python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import AGENT_REGISTRY, CORE_AGENT_MODELS; assert len(AGENT_REGISTRY)==9; assert len(CORE_AGENT_MODELS)==5; print('PASS')"
grep -c "^| omg-" README.md  # Expected: 14
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] All tests pass
- [x] model_version values are specific (not generic like "codex" or "sonnet")
- [x] Frontmatter consistent across all 14 agent files
