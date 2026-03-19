# Deprecated GitHub App Setup

This document is deprecated.

OMG no longer uses a GitHub App for PR review or automation posting. The supported
setup is a fine-grained GitHub account token for `oh-my-god-bot`, exposed as
`OMG_GITHUB_TOKEN`.

Use [GitHub Token Setup](github-token.md) instead.

## Migration

- Remove any `OMG_APP_*` and `GITHUB_APP_*` repository variables or secrets.
- Add `OMG_GITHUB_TOKEN` with the permissions described in [GitHub Token Setup](github-token.md).
- Re-run trusted review and release automation after the token is configured.

## What Changed

- PR review posting no longer mints installation tokens.
- Trusted workflows now pass `OMG_GITHUB_TOKEN` directly.
- The visible automation identity is `oh-my-god-bot`.
