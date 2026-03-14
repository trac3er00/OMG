# GitHub App Setup for PR Reviewer Bot

The PR Reviewer Bot uses a GitHub App installation token, not `GITHUB_TOKEN`.

## 1) Create a GitHub App

- Go to GitHub Settings -> Developer settings -> GitHub Apps -> New GitHub App.
- Set callback URL to any valid HTTPS URL if your org policy requires it.
- Disable webhook delivery if you only use workflow-triggered execution.
- Grant repository permissions:
  - Pull requests: Read and write
  - Checks: Read and write
  - Contents: Read-only

## 2) Install the App

- Install the app on the target repository or organization.
- Copy the installation ID from the app installation URL.

## 3) Configure credentials

Set these environment variables in the trusted job that posts reviews/check-runs:

```bash
export GITHUB_APP_ID="<app-id>"
export GITHUB_APP_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
export GITHUB_INSTALLATION_ID="<installation-id>"
```

Notes:

- `GITHUB_APP_PRIVATE_KEY` may be a multiline PEM or a single-line string with `\n` escapes.
- Missing values fail closed with machine-readable errors (`GITHUB_CREDENTIALS_MISSING`).

## 4) Verify in CI

- Ensure the reviewer workflow runs in a trusted lane.
- Do not expose app credentials to untrusted PR checkout jobs.
- The bot posts SHA-scoped reviews and check-runs and marks prior approvals stale on new pushes.
