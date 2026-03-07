# Public Release Checklist

Use this checklist before making OMG public or cutting a release tag.

## Identity

- README, `package.json`, plugin manifests, and CLI version output agree on the version
- repo URL is `https://github.com/trac3er00/OMG`
- plugin and marketplace id are `omg`

## Public Safety

- `python3 scripts/check-omg-public-ready.py` passes
- no internal planning docs ship in `docs/plans/`
- no absolute local paths or stale internal path references remain

## Verification

- `python3 scripts/omg.py contract validate` passes
- `python3 scripts/omg.py contract compile --host claude --host codex --channel public --output-root <tmp>` passes
- `python3 scripts/omg.py contract compile --host claude --host codex --channel enterprise --output-root <tmp>` passes
- `python3 scripts/omg.py release readiness --channel dual --output-root <tmp>` passes
- `python3 scripts/check-omg-standalone-clean.py` passes
- `./scripts/verify-standalone.sh` passes
- `python3 -m pytest tests -q` passes

## Docs

- README matches the current product surface
- install guides for Claude Code and Codex are current
- proof page includes current verification evidence
- changelog includes the release entry

## Release Ops

- `package.json` version matches the tag you will create
- npm publishing credentials are configured for `publish-npm.yml`
- GitHub Actions required checks are green
