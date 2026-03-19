# GitHub Token Setup

OMG authenticates GitHub review and automation flows with a fine-grained token
owned by the `oh-my-god-bot` account.

## Required Secret Name

- GitHub Actions: `secrets.OMG_GITHUB_TOKEN`
- Local hooks/commands: `OMG_GITHUB_TOKEN`

## Required Repository Permissions

Grant the token these repository permissions:

- `Contents: write`
- `Pull requests: write`
- `Issues: write`
- `Checks: write`
- `Metadata: read`

## GitHub Actions

Add `OMG_GITHUB_TOKEN` as an encrypted repository or organization secret.

### Reusable workflow example

```yaml
jobs:
  evidence-gate:
    uses: trac3er00/OMG/.github/workflows/evidence-gate.yml@main
    with:
      repo-full-name: ${{ github.repository }}
      pr-number: ${{ github.event.pull_request.number }}
      head-sha: ${{ github.event.pull_request.head.sha }}
    secrets:
      OMG_GITHUB_TOKEN: ${{ secrets.OMG_GITHUB_TOKEN }}
```

### Composite action example

```yaml
- uses: trac3er00/OMG@v2
  with:
    repo-full-name: ${{ github.repository }}
    pr-number: ${{ github.event.pull_request.number }}
    head-sha: ${{ github.event.pull_request.head.sha }}
  env:
    OMG_GITHUB_TOKEN: ${{ secrets.OMG_GITHUB_TOKEN }}
```

## Local Hooks And Commands

Export the same token before running OMG flows that need to post reviews, comments,
checks, tags, or releases:

```bash
export OMG_GITHUB_TOKEN="ghp_your_token_here"
```

## Branch Protection

- Require the `OMG PR Reviewer` check by name.
- Keep trusted review posting on the base checkout.
- Restrict access to `OMG_GITHUB_TOKEN` to trusted workflows only.

## Troubleshooting

| Error | Meaning | Fix |
| :--- | :--- | :--- |
| `GITHUB_TOKEN_MISSING` | `OMG_GITHUB_TOKEN` is absent or blank | Set `OMG_GITHUB_TOKEN` in the current environment |
| Review posts fail with 403 | Token is under-scoped | Add the missing repo permission |
| Release/tag push uses the wrong actor | Workflow still uses a different token or git identity | Ensure the workflow uses `OMG_GITHUB_TOKEN` and `oh-my-god-bot` git config |
