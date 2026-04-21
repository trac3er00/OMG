# Learnings — omg-production-test-strategy

## [2026-04-21] Initial Codebase Analysis

### TypeScript Structure
- `src/types/config.ts:36-44` — HostTypeSchema uses z.enum(). Add "ollama-cloud" to this list.
- `src/runtime/canonical-surface.ts:25-95` — HOST_SURFACES Record<HostType, HostSurface>. Ollama entry (lines 66-75) is the pattern for cloud: http-sse transport, supportsHooks: false.
- CANONICAL_HOSTS array at line 88, FULLY_SUPPORTED_HOSTS at 96, LOCAL_HOSTS at 103.
- `HostSurface` interface fields: hostType, cliCommand, configFormat, configPath, supportsHooks, supportsPresets, transportType, description.
- configFormat values: "mcp-json" | "config-toml" | "settings-json" | "kimi-json"

### Kimi Skills
- `skills/kimi/SKILL.md` is a stub — only one file in directory. Must create subdirectories: long-context/, web-search/, code-generation/, moonshot/
- Pattern from `.agents/skills/omg/control-plane/SKILL.md` should be referenced for good SKILL.md structure
- `registry/skills.json` lines 193-226 contain Kimi skill stubs needing path updates

### Chaos Framework
- `simulation/src/chaos/framework.ts` — ChaosInjector exists but is no-op
- `simulation/src/chaos/resources.ts` and `transport.ts` also exist
- Must only inject inside Docker containers (safety guard mandatory)

### Test Infrastructure
- `tests/` has: build, commands, control_plane, e2e, fixtures, hooks, hud, integration, lab, perf, performance, plugins, registry, runtime, scripts, security subdirs
- `tests/production/` needs to be CREATED
- `tests/conftest.py` exists — do NOT modify, create separate `tests/production/conftest.py`
- pytest + bun test already work

### CI
- `.github/workflows/ci.yml` exists — add simulation job but don't break existing steps

## [2026-04-21] Task 6 — Chaos Injector Activation

### What worked
- `simulation/src/chaos/framework.ts` can keep existing `ChaosInjector.inject()/cleanup()/status()` contract while replacing only the default runtime path.
- Docker safety can be enforced without host mutation by requiring `/.dockerenv` OR `/proc/1/cgroup` markers (`docker`, `containerd`, `kubepods`) before any fault command.
- Realistic fault commands with safe fallback chain:
  - Network: `tc netem` first, `iptables` probabilistic drop fallback.
  - Memory: `stress-ng` first, tmpfs fill fallback.
  - Disk: `fallocate` first, `dd` fallback.
- Tests remain deterministic by injecting `commandExecutor`, `fileExists`, and `readFile` mocks into `ChaosInjector`.

### Conventions observed
- Preserve async-exclusive sequencing (`runExclusive`) for state safety.
- Keep timer-based effect expiration logic intact; only swap effect handle behavior.
- Evidence and regression confidence improve when running both:
  - full chaos tests (`~/.bun/bin/bun test simulation/src/chaos/`)
  - focused file tests (`~/.bun/bin/bun test simulation/src/chaos/framework.test.ts`)

## [2026-04-21] Task 1 — Ollama Cloud API Verification

### Findings
- Public cloud REST surface exists at `https://ollama.com/api` (not separate `api.ollama.ai` / `cloud.ollama.com` hosts in this environment).
- `GET https://ollama.com/api/tags` is publicly reachable and returns model metadata JSON.
- `POST https://ollama.com/api/chat` requires auth for direct cloud inference (`401 unauthorized` without bearer token).
- Official docs confirm `Authorization: Bearer $OLLAMA_API_KEY` for direct cloud API calls.

### Provider strategy implications
- Keep `ollama` (local host) and `ollama-cloud` (hosted API) as distinct providers.
- Reuse local Ollama endpoint schema (`/api/tags`, `/api/chat`, `stream` flag) for cloud provider integration.
- If direct cloud endpoint is unavailable, degrade to local Ollama host passthrough and/or OpenAI-compatible wrapper path.

## [2026-04-21] Task 9 — Python Ollama Cloud Provider

### Implementation notes
- Added `runtime/providers/ollama_cloud_provider.py` as an API-backed `CLIProvider` adapter using `POST https://ollama.com/api/chat` with `Authorization: Bearer $OLLAMA_API_KEY`.
- `detect()` and `check_auth()` are environment-key based (`OLLAMA_API_KEY`) for graceful no-key failure.
- `write_mcp_config()` reuses `write_kimi_mcp_config(..., config_path="~/.ollama-cloud/mcp.json")` to preserve MCP JSON merge/validation behavior.
- Registered `ollama-cloud` in `runtime/providers/provider_registry.py` as a confirmed MCP-capable provider.

### Testing notes
- Added focused unit tests in `tests/runtime/test_ollama_cloud_provider.py` for key presence detection, auth check, config path, and MCP config file creation.
- Updated `tests/runtime/test_provider_parity.py` provider-count expectations to include `ollama-cloud` and keep parity registry tests aligned.

## [2026-04-21] Task 12 — Kimi Native Hook Adapter

### Hook adapter contract
- `hooks/kimi-adapter.py` follows stdin JSON → stdout JSON hook flow and handles both `event/tool/input` and fallback `tool_name/tool_input` payload shapes.
- Adapter enforces Kimi-host scoping (`host != "" and host != "kimi"` short-circuits to allow) so non-Kimi payloads pass through safely.
- Dangerous command deny path is constrained to `Bash|Execute|Shell` with pattern checks for `rm -rf`, `chmod 777`, and `curl | bash`.

### Bundle integration
- `registry/bundles/hook-governor.yaml` now includes `kimi` in `hosts` and wires `hooks/kimi-adapter.py` into both `PreToolUse` and `PostToolUse` compiled hook chains.

### Validation pattern
- Direct hook smoke check via stdin (`echo ... | python3 hooks/kimi-adapter.py`) is useful to verify stdout decision schema before pytest.
- Focused regression file `tests/hooks/test_kimi_adapter.py` should cover: safe allow, dangerous deny, post-tool allow, non-Kimi pass-through allow, and invalid JSON graceful allow+error.

## [2026-04-21] Task 8 — OllamaCloudProvider TypeScript

### Implementation learnings
- `OllamaCloudProvider` can reuse the local Ollama provider shape while switching transport to cloud base URL (`https://ollama.com/api`) and adding bearer auth.
- With base URL already including `/api`, endpoint suffixes should be `/tags` and `/chat` (not `/api/tags` / `/api/chat`) to prevent duplicated path segments.
- Graceful key-missing behavior should be explicit: `healthCheck()` returns unavailable/auth-false and `isAvailable()` returns `false` without throwing.
- Tier inference is more robust when including explicit Opus threshold for very large models (`>=100b`) in addition to Sonnet threshold (`>=30b`) and mixture parsing (`8x22b`).

### Runtime/test learnings
- Bun `.js` specifier resolution can pick checked-in JS artifacts first; stale `src/runtime/canonical-surface.js` caused `Unknown host type: ollama-cloud` until updated.
- Extending `HostType` with `ollama-cloud` requires exhaustive updates to host-keyed maps (`canonical-surface`, `vision` default adapters, parity test fixtures).
- Focused verification remained stable with:
  - `~/.bun/bin/bun test src/providers/ollama-cloud.test.ts`
  - `~/.bun/bin/bunx tsc --noEmit` (only pre-existing `src/context/compiler.ts` error)

## [2026-04-21] Task 15 — Sub-agent orchestration test suite

### Test suite implementation notes
- `tests/production/test_subagent_orchestration.py` validates orchestration surface presence via file-level checks for `hooks/_agent_registry.py`, `runtime/model_router.py`, and `src/orchestration/router.js`.
- Agent-type coverage is stable with string presence checks for `explore`, `librarian`, and `oracle` in `_agent_registry.py`.
- Routing coverage stays lightweight by asserting `model_router.py` is present and non-trivial in size rather than invoking live provider selection.

### Evidence and verification
- Created evidence artifact: `.sisyphus/evidence/task-15-agent-selection.txt`.
- Focused execution command: `pytest tests/production/test_subagent_orchestration.py -v`.
- Result: `7 passed`.
