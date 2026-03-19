# OMG GitHub Action

The official `OMG PR Reviewer` composite action provides one-step integration for
evidence-backed PR governance checks. It now authenticates with a GitHub account
token owned by `oh-my-god-bot`.

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
        env:
          OMG_GITHUB_TOKEN: ${{ secrets.OMG_GITHUB_TOKEN }}
```

The action is defined in the root `action.yml` of this repository.

## Inputs

| Input | Required | Description |
| :--- | :---: | :--- |
| `repo-full-name` | ✅ | Repository full name (`owner/repo`) |
| `pr-number` | ✅ | Pull request number |
| `head-sha` | ✅ | PR head commit SHA |

## Token Setup

Follow [GitHub Token Setup](github-token.md) to create the fine-grained token and
store it as `OMG_GITHUB_TOKEN`.

## Stable Check Name

The required-check name for branch protection is **immutable**:

```
OMG PR Reviewer
```

This name is defined in `action.yml` and must not be changed. Set it as your
required status check in **Settings → Branches → Branch protection rules**.

## Reusable Workflow

For repositories that prefer a reusable workflow over a composite action, OMG
also ships `.github/workflows/evidence-gate.yml`. See [GitHub Token Setup](github-token.md)
for the reusable workflow invocation pattern.

## Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| Check never appears | `OMG_GITHUB_TOKEN` missing or under-scoped | Verify the token exists and has the documented permissions |
| `GITHUB_TOKEN_MISSING` | Missing env var | Set `OMG_GITHUB_TOKEN` in the runner environment |
| Wrong check selected in branch protection | Selected a different check name | Require `OMG PR Reviewer` exactly |
