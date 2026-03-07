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

## CI Gates

The public release path is expected to pass:

- compat gate
- public-readiness hygiene check
- standalone verification
- full pytest suite

## Scope Guidance

- Keep OMC, OMX, and Superpowers mentions limited to compatibility and adoption guidance.
- Avoid adding public commands that mirror another project's branding or command names.
- Prefer OMG-native setup and orchestration language in docs and UX.
