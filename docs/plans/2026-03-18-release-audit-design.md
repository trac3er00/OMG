# Release Audit Design

Date: 2026-03-18

Approved scope:
- repo-enforced prevention
- live GitHub release/tag remediation
- default dry-run with explicit `--apply`
- full diff, confirmation gate, rollback log

Design:
- Add `omg release audit --artifact` under the existing release command tree in `scripts/omg.py`.
- Implement a shared engine in `runtime/release_artifact_audit.py` so the CLI path, the standalone artifact audit script, and CI all evaluate the same checks.
- Keep `scripts/audit-published-artifact.py` as a thin compatibility wrapper over the shared engine instead of maintaining separate logic.
- Validate the full matrix: local canonical version surfaces, packed npm tarball metadata, git archive metadata, launcher `--version`, shipped docs, scoped residue/docstring drift, proof-lane references, GitHub default README, GitHub releases list, and the release-by-tag surface.
- Produce both a text PASS/FAIL table and a structured JSON report with an actionable diff and a mutation plan.
- In `--apply` mode, require an explicit confirmation token matching the target version plus working GitHub credentials before any mutation occurs.
- Remediation creates or updates the GitHub release for the audited tag, syncs the release body from generated release artifacts, uploads assets, and sets the release as Latest.
- Persist a rollback journal under `.omg/release-audit/<timestamp>/` containing before/after payloads, uploaded asset inventory, and a replayable restore plan.
- Block `omg ship` when release audit drift exists.
- Ship help/docs for the new command inside the npm artifact and cover it with focused tests and workflow gates.
