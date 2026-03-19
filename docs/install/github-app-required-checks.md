# Deprecated GitHub App Required Checks

This document is deprecated.

OMG no longer binds required checks to a GitHub App installation. The supported
setup is a fine-grained token contract using `OMG_GITHUB_TOKEN`.

Use [GitHub Token Setup](github-token.md) for the current branch-protection and
token guidance.

## Current Guidance

- Require the `OMG PR Reviewer` check by name in branch protection.
- Ensure only trusted workflows can access `OMG_GITHUB_TOKEN`.
- Keep trusted posting on the base checkout so PR authors cannot change the posting code path.
