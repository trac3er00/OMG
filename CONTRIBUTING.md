# Contributing to OMG

Thanks for contributing to OMG.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest tests -q
```

If you are validating the public launch surface, also run:

```bash
python3 scripts/check-omg-public-ready.py
python3 scripts/check-omg-standalone-clean.py
./scripts/verify-standalone.sh
```

## Workflow

1. Create a branch from `main`.
2. Keep changes surgical and evidence-backed.
3. Add or update tests before changing behavior.
4. Run the relevant targeted tests while iterating.
5. Run `python3 -m pytest tests -q` before opening a PR.

## Pull Requests

PRs should explain:

- what changed
- why it changed
- how it was verified
- any follow-up risk or known limitation

Public-surface changes should also mention whether README, proof docs, install docs, and community docs stayed consistent.

## Versioning and Releases

- OMG uses semantic version tags such as `v2.0.1`.
- `package.json`, plugin metadata, and release tags must agree before a release is cut.
- npm publishing is driven by the `publish-npm.yml` workflow on version tags.

Before cutting a release, run the checklist in [docs/release-checklist.md](docs/release-checklist.md).

## CI/CD & Code Review

### GitHub Actions (automated CI)

Only four workflows run in GitHub Actions:

| Workflow | Trigger | Purpose |
|---|---|---|
| `cla.yml` | PR opened / comment | CLA signature verification |
| `gitguardian.yml` | push / PR | Secret scanning via GitGuardian |
| `release.yml` | push to main | Automated semantic-release + npm publish |
| `publish-npm.yml` | manual dispatch | Manual versioned npm publish |

### Cubic AI (PR review)

All code review and quality gates are handled by **Cubic AI** with 5 custom agents:

| Agent | What it checks |
|---|---|
| **Contract Integrity** | Snapshot drift, version parity, contract schema completeness |
| **Release Safety** | Workflow integrity, secret handling, release gate preservation |
| **Compat & Host Parity** | Breaking changes, host config sync, vendor name leaks |
| **Public Surface & Docs** | Manifest consistency, doc drift, internal exposure |
| **Security Hygiene** | Secret exposure, unpinned actions, dangerous patterns |

### When to update Cubic agents

If your PR touches any of these areas, **you must also update the corresponding Cubic agent instruction** in the Cubic dashboard:

| Change | Cubic agent to update |
|---|---|
| New contract fields or schema changes | Contract Integrity |
| New host added (e.g. `.windsurf/`) | Compat & Host Parity |
| New workflow or release step added | Release Safety |
| New public directory or doc convention | Public Surface & Docs |
| New dependency type or secret pattern | Security Hygiene |
| File path restructure (e.g. `runtime/` renamed) | **All agents** (update file patterns) |

**How to update:** Agent prompts are versioned in `cubic-agents/`. Update the in-repo file FIRST, then sync to the Cubic dashboard (Settings → Custom Agents → edit the relevant agent's instruction and/or file patterns).

### Legacy CI gates (removed)

The following workflows were migrated to Cubic and deleted:

- `evidence-gate.yml` → Cubic built-in PR review
- `omg-artifact-self-audit.yml` → Public Surface & Docs agent
- `omg-compat-gate.yml` → Contract Integrity + Compat & Host Parity agents
- `omg-release-readiness.yml` → Release Safety agent
- `action.yml` + review bot → Cubic built-in inline comments

## Scope Guidance

- Keep OMC, OMX, and Superpowers mentions limited to compatibility and adoption guidance.
- Avoid adding public commands that mirror another project's branding or command names.
- Prefer OMG-native setup and orchestration language in docs and UX.
