# GitHub App Required Checks

## Required Check Context Name

The OMG PR Reviewer creates a check-run with a deterministic name:

```
OMG PR Reviewer
```

This name is the **context** string used for required status checks in branch protection rules.

## Pinning Required Checks to `app_id`

GitHub allows any integration or workflow to create a check-run with any name. To prevent spoofing of the `OMG PR Reviewer` check, pin the required check to the OMG GitHub App's `app_id` in your branch protection settings.

### REST API (branch protection)

```json
PUT /repos/{owner}/{repo}/branches/{branch}/protection
{
  "required_status_checks": {
    "strict": true,
    "contexts": [],
    "checks": [
      {
        "context": "OMG PR Reviewer",
        "app_id": YOUR_OMG_APP_ID
      }
    ]
  }
}
```

When `app_id` is set, only check-runs created by that specific GitHub App are considered authoritative. A workflow or third-party App posting a check-run with the same name but a different `app_id` will not satisfy the requirement.

> **Important**: The `app_id` field **must** be specified in the branch protection API call. Omitting it leaves the check unpinned.

> **Warning**: Never leave required checks unpinned — any actor can spoof an unpinned check name. Always specify `app_id` to bind the check to the OMG GitHub App.

### Repository Settings UI

1. Go to **Settings > Branches > Branch protection rules**.
2. Edit the rule for your default branch.
3. Under **Require status checks to pass before merging**, search for `OMG PR Reviewer`.
4. Select the entry that shows the OMG App icon (not the GitHub Actions icon).

## Merge-Readiness Evaluation via `isRequired` GraphQL Field

Do **not** rely on the raw `mergeable` field from the REST API to determine merge readiness. The `mergeable` field conflates merge conflict status with required-check status and can produce false positives.

Instead, use the GraphQL `statusCheckRollup` with the `isRequired` field to query whether each required check has passed:

```graphql
query MergeReadiness($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      commits(last: 1) {
        nodes {
          commit {
            statusCheckRollup {
              contexts(first: 50) {
                nodes {
                  ... on CheckRun {
                    name
                    conclusion
                    isRequired(pullRequestNumber: $pr)
                  }
                  ... on StatusContext {
                    context
                    state
                    isRequired(pullRequestNumber: $pr)
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

The `isRequired` field returns `true` only for checks that are configured as required for the target branch. A PR is merge-ready when every context where `isRequired: true` also has `conclusion: "SUCCESS"` (for check-runs) or `state: "SUCCESS"` (for status contexts).

## Split-Lane Security Model

The OMG CI pipeline uses a split-lane model to isolate untrusted analysis from trusted posting:

| Job | Permissions | Checkout | Purpose |
|---|---|---|---|
| `pr-analyze` | `contents: read` | PR head (default) | Runs analysis on PR code, produces review artifacts |
| `post-review` | `contents: read`, `pull-requests: write`, `checks: write` | **Base SHA** (`github.event.pull_request.base.sha`) | Posts review and check-run using App credentials |

The `post-review` job checks out the **base branch SHA**, not the PR head. This ensures the posting code is from the trusted base branch and cannot be tampered with by the PR author. App credentials (`OMG_APP_ID`, `OMG_APP_PRIVATE_KEY`, `OMG_APP_INSTALLATION_ID`) are only available in the trusted posting job.

## Check-Run Conclusions

The OMG PR Reviewer maps verdict statuses to GitHub check-run conclusions:

| Verdict Status | GitHub Conclusion | PR UI Effect |
|---|---|---|
| `pass` | `success` | Green checkmark |
| `fail` | `failure` | Red X |
| `action_required` | `action_required` | "Take action" button |
| `pending` | `neutral` | Grey dash |
