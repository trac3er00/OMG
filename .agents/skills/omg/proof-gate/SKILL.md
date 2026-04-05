---
name: omg-proof-gate
description: "Release proof gate that enforces blocker semantics for missing artifacts, missing lock evidence, and trace-link mismatches without advisory downgrade."
---

# OMG Proof Gate

Evaluate release readiness with `runtime/proof_gate.py:production_gate` and `evaluate_proof_gate`. If blockers include missing hashes, absent lock evidence, or trace mismatch, mark release blocked and emit blocker codes; do not downgrade to advisory.

- Channel: `enterprise`
- Execution modes: `embedded, local_supervisor`
- MCP servers: `omg-control`
- Evidence outputs: `.omg/evidence/proof-gate-*.json`
