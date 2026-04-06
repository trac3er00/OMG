# OMG Core/Pack Module Boundaries

## Classification Criteria

- **CORE**: Always loaded on startup. Required for basic operation. Target: <20 modules.
- **PACK**: Lazy-loaded on first use. Domain-specific functionality.
- **BRIDGE**: Loaded on first use, but provides compatibility/adapter services.

## CORE Modules (Always Loaded)

These modules are required for ALL OMG operations:

| Module | Purpose |
|--------|---------|
| mutation_gate.py | File mutation safety gate |
| proof_gate.py | Evidence verification |
| claim_judge.py | Claim adjudication |
| memory_store.py | Encrypted state storage |
| complexity_classifier.py | Task complexity analysis |
| model_registry.py | Model capability registry |
| router_selector.py | Multi-model routing |
| router_executor.py | Route execution |
| complexity_scorer.py | Complexity scoring |
| delta_classifier.py | Change classification |
| test_intent_lock.py | TDD gate |
| tool_plan_gate.py | Tool plan verification |
| session_health.py | Session state monitoring |
| context_compiler.py | Context assembly |
| release_run_coordinator.py | Release orchestration |
| compliance_governor.py | Governance enforcement |
| dispatch*.py | Task dispatch |
| context_compactor.py | Session handoff |
| decision_engine.py | Decision logic |

## PACK Modules (Lazy-Loaded)

| Module | Pack Name | Trigger |
|--------|-----------|---------|
| vision_*.py | vision | `from runtime.vision_*` |
| playwright_*.py | browser | `from runtime.playwright_*` |
| music_omr_testbed.py | music-omr | `from runtime.music_omr_testbed` |
| api_twin.py | api-twin | `from runtime.api_twin` |
| robotics/ | robotics | `from runtime.robotics` |
| data_lineage.py | data-lineage | `from runtime.data_lineage` |
| eval_*.py | eval | `from runtime.eval_*` |

## BRIDGE Modules (On-First-Use)

| Module | Purpose |
|--------|---------|
| plugin_interop.py | Third-party plugin compatibility |
| compat.py | Legacy compatibility |
| canonical_surface.py | Surface normalization |

## Import Contract Rules

1. **Core → Core**: Allowed
2. **Core → Pack**: FORBIDDEN (breaks lazy-loading)
3. **Pack → Core**: Allowed
4. **Pack → Pack**: Discouraged (prefer Core APIs)
5. **Bridge → Core**: Allowed
6. **Bridge → Pack**: Allowed (bridge loads on-demand anyway)

## Enforcement

Run `scripts/measure-import-time.py` to verify core-only import stays under 500ms.
