---
name: omg-claim-judge
description: "Claim adjudication lane that judges per-claim evidence first, then aggregates release verdicts and preserves strict unsupported reason codes."
---

# OMG Claim Judge

Judge individual claims via `runtime/claim_judge.py:judge_claim`, then aggregate release verdicts with `judge_claims`. If strict causal-chain checks fail or excluded-failure waiver is missing, return unsupported verdict and preserve reason codes in artifact output.

- Channel: `enterprise`
- Execution modes: `embedded, local_supervisor`
- MCP servers: `omg-control`
- Evidence outputs: `.omg/evidence/claim-judge-*.json`
