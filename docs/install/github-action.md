# OMG GitHub Action

The official `OMG PR Reviewer` composite action provides one-step integration for
evidence-backed PR governance checks. It wraps the full review pipeline into a
single `action.yml` consumable from any GitHub Actions workflow.

## Quick Setup

Add the action to your workflow:

```yaml
name: OMG PR Review
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # ... your build / test steps that produce artifacts/ ...

      - uses: trac3er00/OMG@v2
        with:
          repo-full-name: ${{ github.repository }}
          pr-number: ${{ github.event.pull_request.number }}
          head-sha: ${{ github.event.pull_request.head.sha }}
          github-app-id: ${{ vars.OMG_APP_ID }}
          github-app-installation-id: ${{ vars.OMG_APP_INSTALLATION_ID }}
          github-app-private-key: ${{ secrets.OMG_APP_PRIVATE_KEY }}
```

The action is defined in the root `action.yml` of this repository.

## Inputs

| Input | Required | Description |
| :--- | :---: | :--- |
| `repo-full-name` | ✅ | Repository full name (`owner/repo`) |
| `pr-number` | ✅ | Pull request number |
| `head-sha` | ✅ | PR head commit SHA |
| `github-app-id` | ✅ | GitHub App ID for posting the review |
| `github-app-installation-id` | ✅ | GitHub App installation ID |
| `github-app-private-key` | ✅ | GitHub App private key (PEM format) |

## GitHub App Setup

The action authenticates via a GitHub App. Follow [GitHub App Setup](github-app.md)
to create the app, generate a private key, and configure the required secrets.

## Stable Check Name

The required-check name for branch protection is **immutable**:

```
OMG PR Reviewer
```

This name is defined in `action.yml` and must not be changed. Set it as your
required status check in **Settings → Branches → Branch protection rules**.

> **Important**: When adding the required check in the GitHub UI, select the
> entry showing the OMG App icon (not the GitHub Actions icon) to ensure the
> check is pinned to your App's `app_id`. See [GitHub App Setup](github-app.md)
> for `app_id` pinning details.

## Reusable Workflow

For repositories that prefer a reusable workflow over a composite action, OMG
also ships `.github/workflows/evidence-gate.yml`. See [GitHub App Setup](github-app.md)
for the reusable workflow invocation pattern.

## Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| Check never appears | App not installed on repo | Install the GitHub App on the target repository |
| `GITHUB_CREDENTIALS_MISSING` | Missing env vars | Verify all three secrets/variables are set |
| Wrong check selected in branch protection | Selected Actions check instead of App check | Choose the entry with the OMG App icon |
