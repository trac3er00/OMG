# oh-my-god-bot GitHub Identity Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate OMG GitHub review and automation identity from the current GitHub App path to a single `oh-my-god-bot` fine-grained token contract using `OMG_GITHUB_TOKEN`.

**Architecture:** Keep the current review/check-run behavior and trusted workflow structure, but replace App credential acquisition with a direct token contract. Remove App-specific configuration, workflow wiring, and docs in the same change so the repo has one clear GitHub automation model.

**Tech Stack:** Python runtime helpers, GitHub Actions workflows, pytest, markdown install docs

---

### Task 1: Replace GitHub App auth with `OMG_GITHUB_TOKEN`

**Files:**
- Modify: `runtime/github_integration.py`
- Modify: `tests/runtime/test_github_integration.py`

**Step 1: Write the failing test**

Add or update tests to assert:

- `get_github_token()` returns `status=ok` when `OMG_GITHUB_TOKEN` is present.
- `get_github_token()` returns a direct missing-token error when `OMG_GITHUB_TOKEN` is absent.
- App env vars are no longer required or mentioned in expected errors.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/runtime/test_github_integration.py -q --no-cov`

Expected: FAIL because the runtime still expects `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, and `GITHUB_INSTALLATION_ID`.

**Step 3: Write minimal implementation**

- Remove the JWT, RSA key parsing, installation token exchange, and token cache path from `runtime/github_integration.py`.
- Replace it with a small loader that reads `OMG_GITHUB_TOKEN`, trims it, and returns either:
  - `{"status": "ok", "token": ...}`
  - or a direct config error for missing/empty token.
- Keep the public function name `get_github_token()` if that avoids wider churn.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/runtime/test_github_integration.py -q --no-cov`

Expected: PASS

**Step 5: Commit**

```bash
git add runtime/github_integration.py tests/runtime/test_github_integration.py
git commit -m "Replace GitHub App auth with OMG_GITHUB_TOKEN"
```

### Task 2: Keep PR review behavior while removing App assumptions

**Files:**
- Modify: `runtime/github_review_bot.py`
- Modify: `scripts/github_review_helpers.py`
- Modify: `tests/runtime/test_github_review_bot.py`
- Modify: `tests/e2e/test_pr_review_flow.py`

**Step 1: Write the failing test**

Add or update tests to assert:

- Review bot flows still call `get_github_token()` and work with a direct token string.
- No App-specific wording remains in helper CLI text or test expectations.
- E2E/workflow assertions no longer require App secret references in trusted review lanes.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/runtime/test_github_review_bot.py tests/e2e/test_pr_review_flow.py -q --no-cov`

Expected: FAIL because tests still expect App-flavored workflow/runtime behavior.

**Step 3: Write minimal implementation**

- Update comments/messages in `runtime/github_review_bot.py` only where they still describe App-only auth.
- Update `scripts/github_review_helpers.py` help text so `post-review` is token/auth neutral.
- Keep review posting, dismissal, and check-run logic unchanged.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/runtime/test_github_review_bot.py tests/e2e/test_pr_review_flow.py -q --no-cov`

Expected: PASS

**Step 5: Commit**

```bash
git add runtime/github_review_bot.py scripts/github_review_helpers.py tests/runtime/test_github_review_bot.py tests/e2e/test_pr_review_flow.py
git commit -m "Remove App assumptions from review bot flow"
```

### Task 3: Migrate trusted review workflows to `OMG_GITHUB_TOKEN`

**Files:**
- Modify: `.github/workflows/omg-compat-gate.yml`
- Modify: `.github/workflows/evidence-gate.yml`
- Modify: `tests/scripts/test_github_workflows.py`

**Step 1: Write the failing test**

Add or update workflow tests to assert:

- Trusted review/posting jobs use `OMG_GITHUB_TOKEN`.
- Workflow-call secret contracts in `evidence-gate.yml` no longer mention App credentials.
- `omg-compat-gate.yml` no longer exports `GITHUB_APP_*` or `OMG_APP_*` into the posting step.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/scripts/test_github_workflows.py -q --no-cov`

Expected: FAIL because workflow tests still expect App secret references.

**Step 3: Write minimal implementation**

- Replace App secret blocks in `omg-compat-gate.yml` and `evidence-gate.yml` with `OMG_GITHUB_TOKEN`.
- Ensure trusted posting jobs still run from the trusted base surface.
- Keep `pr-analyze` untrusted lanes free of GitHub write secrets.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/scripts/test_github_workflows.py -q --no-cov`

Expected: PASS

**Step 5: Commit**

```bash
git add .github/workflows/omg-compat-gate.yml .github/workflows/evidence-gate.yml tests/scripts/test_github_workflows.py
git commit -m "Migrate review workflows to OMG_GITHUB_TOKEN"
```

### Task 4: Migrate release and publish automation identity

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `.github/workflows/publish-npm.yml`
- Modify: `tests/scripts/test_github_workflows.py`

**Step 1: Write the failing test**

Add or update workflow tests to assert:

- `release.yml` no longer creates a GitHub App token.
- `publish-npm.yml` no longer configures `github-actions[bot]`.
- Visible git author for workflow-authored commits is `oh-my-god-bot` with the GitHub noreply email.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/scripts/test_github_workflows.py -q --no-cov`

Expected: FAIL because the current release/publish workflows still use App auth and `github-actions[bot]`.

**Step 3: Write minimal implementation**

- Replace release workflow auth with `OMG_GITHUB_TOKEN`.
- Update any push/release steps to authenticate using that token.
- Change git user name/email in publish/release flows to `oh-my-god-bot` and its noreply email.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/scripts/test_github_workflows.py -q --no-cov`

Expected: PASS

**Step 5: Commit**

```bash
git add .github/workflows/release.yml .github/workflows/publish-npm.yml tests/scripts/test_github_workflows.py
git commit -m "Move release automation to oh-my-god-bot"
```

### Task 5: Remove GitHub App docs and replace with token setup docs

**Files:**
- Modify: `docs/install/github-action.md`
- Modify: `docs/install/github-app.md`
- Modify: `docs/install/github-app-required-checks.md`
- Create or Modify: `docs/install/github-token.md`
- Modify: `README.md` if it links to App setup

**Step 1: Write the failing test**

Add or update doc-oriented tests or assertions to fail if install docs still direct users to:

- create a GitHub App
- configure `OMG_APP_*` / `GITHUB_APP_*`
- pin required checks to an App ID

If no existing automated doc check exists, add a focused pytest assertion in `tests/scripts/test_github_workflows.py` or a new doc test file that scans these docs for stale App guidance.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/scripts/test_github_workflows.py -q --no-cov`

Expected: FAIL because the docs still describe GitHub App setup.

**Step 3: Write minimal implementation**

- Rewrite install docs around `OMG_GITHUB_TOKEN` and `oh-my-god-bot`.
- Mark the old App path as removed, not supported.
- Replace App-ID-based required-check guidance with token-compatible branch protection guidance.
- Update any README/install links that point at GitHub App setup.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/scripts/test_github_workflows.py -q --no-cov`

Expected: PASS

**Step 5: Commit**

```bash
git add docs/install/github-action.md docs/install/github-app.md docs/install/github-app-required-checks.md docs/install/github-token.md README.md tests/scripts/test_github_workflows.py
git commit -m "Replace GitHub App docs with token setup"
```

### Task 6: Final verification and cleanup

**Files:**
- Verify: `runtime/github_integration.py`
- Verify: `runtime/github_review_bot.py`
- Verify: `.github/workflows/omg-compat-gate.yml`
- Verify: `.github/workflows/evidence-gate.yml`
- Verify: `.github/workflows/release.yml`
- Verify: `.github/workflows/publish-npm.yml`
- Verify: `docs/install/github-action.md`
- Verify: `docs/install/github-app.md`
- Verify: `docs/install/github-app-required-checks.md`
- Verify: `docs/install/github-token.md`

**Step 1: Run focused test suites**

Run:

```bash
python3 -m pytest tests/runtime/test_github_integration.py tests/runtime/test_github_review_bot.py tests/e2e/test_pr_review_flow.py tests/scripts/test_github_workflows.py -q --no-cov
```

Expected: PASS

**Step 2: Run diff hygiene**

Run:

```bash
git diff --check
```

Expected: no output

**Step 3: Grep for stale App config**

Run:

```bash
rg -n "OMG_APP_|GITHUB_APP_|installation token|GitHub App" runtime .github docs scripts tests
```

Expected: no live configuration references remain except clearly marked historical/deprecation text if intentionally kept.

**Step 4: Commit**

```bash
git add runtime .github docs scripts tests README.md
git commit -m "Finalize oh-my-god-bot GitHub automation migration"
```
