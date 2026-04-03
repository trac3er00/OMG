# Cross-Language Parity Contract

## Canonical Rule

**TypeScript (v3.0.0) is canonical for all NEW feature implementation.**
Python (v2.2.12) provides the production runtime and extends TS-defined behaviors.
TypeScript defines the interface contract; Python implements the full production executor.

This asymmetry is intentional: TS serves as the MCP/host integration layer and
compile-time interface authority. Python provides the runtime services with full
business logic, evidence persistence, and audit capabilities.

---

## Module Parity Registry

### Proof Gate

- **TS File**: `src/verification/proof-gate.ts` (71 LOC)
- **Python File**: `runtime/proof_gate.py` (713 LOC)
- **Classification**: `PYTHON_SUPERSET`
- **Canonical for new features**: TypeScript (interface) / Python (runtime)
- **Parity Notes**:
  - TS implements: basic evidence bundle validation (JUnit failures, coverage threshold 70%), 2 required primitives (junit, coverage)
  - Python implements: full production gate with claim_judge integration, proof_gate + test_intent_lock as required production primitives, artifact hash verification, SHA256 validation, SARIF parsing, evidence profile resolution, persistence to `.omg/evidence/`, tracebank event emission
  - **Gap**: TS version is an integration-test helper. Python is the production authority.
  - **New frontier code**: Add to TS interface first, then Python runtime

### Claim Judge

- **TS File**: `src/verification/claim-judge.ts` (77 LOC)
- **Python File**: `runtime/claim_judge.py` (709 LOC)
- **Classification**: `PYTHON_SUPERSET`
- **Canonical for new features**: TypeScript (interface) / Python (runtime)
- **Parity Notes**:
  - TS implements: simple evidence-reference counting, batch verdict aggregation, confidence scoring (min 0.9 + 0.02×count)
  - Python implements: full claim evaluation with run-scoped evidence packs, council evidence merging, per-claim artifact persistence, profile digest integration, causal chain metadata, aggregate verdicts with advisory context
  - **Gap**: TS provides a ~10x simpler interface for testing. Python is production authority.

### Test Intent Lock

- **TS File**: `src/verification/test-intent-lock.ts` (98 LOC)
- **Python File**: `runtime/test_intent_lock.py` (543 LOC)
- **Classification**: `PYTHON_SUPERSET`
- **Canonical for new features**: TypeScript (interface) / Python (runtime)
- **Parity Notes**:
  - TS implements: lock/verify/release state machine with atomic file operations
  - Python implements: full TDD enforcement with test file hash tracking, assertion metadata, weakened-assertion detection, covered-path enforcement, integration with proof gate
  - **Gap**: ~5.5x size difference. Core logic is equivalent; Python adds more validation layers.

### Decision Engine

- **TS File**: `src/orchestration/decision-engine.ts` (197 LOC)
- **Python File**: `runtime/decision_engine.py` (199 LOC)
- **Classification**: `EQUIVALENT`
- **Canonical for new features**: TypeScript
- **Parity Notes**:
  - Both implement task complexity classification (trivial/simple/moderate/complex/extreme)
  - Both use regex pattern matching against task descriptions
  - TS adds domain detection hints; Python adds dynamic model availability detection
  - **This is the closest to true parity in the codebase**

### Tool Fabric

- **TS File**: `src/governance/tool-fabric.ts` (169 LOC)
- **Python File**: `runtime/tool_fabric.py` (667 LOC)
- **Classification**: `PYTHON_SUPERSET`
- **Canonical for new features**: TypeScript (interface) / Python (runtime)
- **Parity Notes**:
  - TS implements: lane policy definitions, tool allowlist checking, basic governance result
  - Python implements: full lane policy enforcement with signed approval verification, attestation checking, evidence freshness validation, ledger persistence, budget envelope integration
  - **Gap**: ~4x size difference. Python has full production governance enforcement.

### Evidence Registry

- **TS File**: `src/evidence/registry.ts` (46 LOC)
- **Python File**: `runtime/evidence_registry.py` (16 LOC)
- **Classification**: `TS_SUPERSET`
- **Canonical for new features**: TypeScript
- **Parity Notes**:
  - TS implements: full evidence registry with append-only JSONL persistence, caching, type/runId/path queries
  - Python file is a minimal stub (16 LOC) — likely a placeholder
  - **Gap**: Python evidence registry is significantly underdeveloped vs TS
  - **Action**: Python evidence registry should be expanded to match TS in a future task

---

## Classification Summary

| Module            | TS LOC | Python LOC | Ratio | Classification  |
| ----------------- | ------ | ---------- | ----- | --------------- |
| Proof Gate        | 71     | 713        | 10x   | PYTHON_SUPERSET |
| Claim Judge       | 77     | 709        | 9.2x  | PYTHON_SUPERSET |
| Test Intent Lock  | 98     | 543        | 5.5x  | PYTHON_SUPERSET |
| Decision Engine   | 197    | 199        | 1.0x  | EQUIVALENT      |
| Tool Fabric       | 169    | 667        | 3.9x  | PYTHON_SUPERSET |
| Evidence Registry | 46     | 16         | 0.3x  | TS_SUPERSET     |

---

## Version Sync Strategy

- **TS v3.0.0** is the current canonical version
- **Python v2.2.12** is the current runtime version
- Version numbers reflect independent release cadences — this is expected
- When adding new frontier features: implement TypeScript interface first, Python runtime follows
- Breaking changes to shared data formats (evidence schemas) must update both implementations

---

## Parity Enforcement Rules

1. **New modules in both languages**: classify here before merging
2. **Evidence schema changes**: must be reflected in `src/evidence/schema-registry.ts` (versioned) and consumed by Python runtime
3. **Critical decision functions**: same input → same output (proof gate verdict, claim judge verdict, test intent lock status)
4. **TypeScript is canonical for**: interfaces, MCP integration, types, new frontier modules (T5-T37)
5. **Python is authoritative for**: production runtime execution, evidence persistence, hook implementations, provider integrations

---

## Future Parity Work (Identified Gaps)

| Priority | Gap                                                                       | Action                                                            |
| -------- | ------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| High     | Python evidence registry is 16 LOC stub vs 46 LOC TS                      | Expand Python registry to match TS in evidence frontier work      |
| Medium   | TS proof gate lacks production primitives (claim_judge, test_intent_lock) | Add to TS interface in T10 reliability work                       |
| Low      | TS claim judge lacks persistence                                          | Python persistence is production-grade; TS can remain lightweight |
