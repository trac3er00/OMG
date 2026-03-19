# oh-my-god-bot GitHub Identity Migration Design

## Goal

Replace the current GitHub App and `oh-my-god[bot]`-style review path with a single GitHub account identity, `oh-my-god-bot`, using one fine-grained token contract shared by GitHub Actions and local OMG hooks/commands.

## Current State

- PR review posting uses App-backed auth in `runtime/github_integration.py`.
- Trusted review workflows pass App credentials into `scripts/github_review_helpers.py post-review`.
- Release and publish flows still expose other automation identities such as `github-actions[bot]`.
- Install docs are centered on GitHub App setup, App installation IDs, and App-pinned required checks.

## Approved Decisions

### Auth model

- Use a single fine-grained token named `OMG_GITHUB_TOKEN`.
- Use the same name in both environments:
  - GitHub Actions: `secrets.OMG_GITHUB_TOKEN`
  - Local hooks/commands: `OMG_GITHUB_TOKEN`
- Remove the current App path entirely. No fallback layer.
- Use `oh-my-god-bot` as the visible GitHub automation identity.
- Use the account's GitHub noreply email for workflow-authored commits where git identity is visible.

### Permission model

The token should be documented and validated against the permissions needed for full automation:

- `Contents: write`
- `Pull requests: write`
- `Issues: write`
- `Checks: write`
- `Metadata: read`

## Recommended Approach

Keep the current review/check-run behavior intact and swap only the credential model underneath it.

This means:

- `runtime/github_review_bot.py` continues posting reviews, inline comments, dismissals, and check runs through the same code paths.
- `runtime/github_integration.py` stops minting installation tokens and becomes a strict PAT loader/validator.
- Workflow jobs keep their trusted-lane structure, but switch from App secrets to `OMG_GITHUB_TOKEN`.

This is the lowest-risk path because it preserves behavior while simplifying setup.

## Migration Surface

### Runtime and scripts

- `runtime/github_integration.py`
  - Replace GitHub App JWT/install-token logic with token loading and validation.
  - Replace App-specific error codes/messages with PAT-specific configuration and permission errors.
- `runtime/github_review_bot.py`
  - Preserve review/check behavior.
  - Remove App-specific assumptions from comments or supporting logic.
- `scripts/github_review_helpers.py`
  - Update command help text and messaging so it no longer references GitHub App auth.

### Workflows

- `omg-compat-gate.yml`
  - Replace trusted posting job secret usage with `OMG_GITHUB_TOKEN`.
- `evidence-gate.yml`
  - Replace workflow-call secret contract from App secrets to `OMG_GITHUB_TOKEN`.
- `release.yml`
  - Replace App-token creation path with `OMG_GITHUB_TOKEN`.
- `publish-npm.yml`
  - Change visible git author from `github-actions[bot]` to `oh-my-god-bot` plus GitHub noreply email.

### Docs and config

- Deprecate and remove GitHub App setup/config docs.
- Replace them with token-based setup docs for `oh-my-god-bot`.
- Remove App-ID-pinned required-check guidance and replace it with branch protection guidance compatible with PAT-backed check runs.

### Hooks and commands

- Document `OMG_GITHUB_TOKEN` as the local contract for hooks/commands that invoke GitHub review automation.
- Do not invent new hook plumbing if the current path already flows through runtime helpers; update the existing contract instead.

## Deprecation Policy

- `OMG_APP_*`, `GITHUB_APP_*`, and installation-ID wiring are deprecated immediately and removed in the same change.
- Existing users must migrate configuration to `OMG_GITHUB_TOKEN`.
- Tests should fail if App references remain in the runtime, workflows, or install docs.

## Error Handling

- Missing `OMG_GITHUB_TOKEN` should yield a direct configuration error.
- Permission failures should explicitly name the missing capability surface where practical (`Checks`, `Pull requests`, `Issues`, `Contents`).
- Since there is no compatibility bridge, leftover App-only configuration should be treated as stale configuration, not a supported path.

## Verification Strategy

- Update unit tests for token loading/auth errors.
- Keep PR review bot tests and convert them to the new token contract.
- Update workflow tests to require `OMG_GITHUB_TOKEN` and reject App secret usage.
- Verify release/publish automation identity changes.
- Verify docs no longer instruct users to create or install a GitHub App.

## Rollout

1. Add `OMG_GITHUB_TOKEN` to the repository/org secret store.
2. Remove the old App variables/secrets.
3. Merge the migration.
4. Re-run PR review and release/publish flows using the new account identity.

## Non-Goals

- No compatibility layer that keeps both App auth and token auth alive.
- No change to the `@omg` trigger model introduced in the current PR.
