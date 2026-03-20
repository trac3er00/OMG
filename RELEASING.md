# Releasing OMG

This document covers the release procedure and golden rules for publishing new versions of OMG.

## Golden Rules

1. **Never delete a published GitHub release.** GitHub marks deleted releases as immutable ghosts. The tag name becomes permanently locked — you cannot re-create a release or tag with the same name. If you delete a release by accident, you must bump the version number and release under the new version.

2. **Always run `pre-release-check.sh` before releasing.** This script verifies that the target tag name is not locked by an immutable release ghost and that no conflicting tag already exists on the remote.

   ```bash
   ./scripts/pre-release-check.sh <version> [repo]
   # Example:
   ./scripts/pre-release-check.sh <version> trac3er00/OMG
   ```

3. **If a tag is locked by an immutable release**, you have two options:
   - **Bump the version** — increment the patch (or minor/major) version and release under the new number. This is the recommended and fastest path.
   - **Contact GitHub Support** at https://support.github.com — they may be able to clear the immutable lock, but this can take days and is not guaranteed.

## Release Procedure

### 1. Prepare and merge release changes

Open a PR that updates release-facing surfaces (for example `runtime/adoption.py`, `package.json`, and generated artifacts), then merge to `main` after CI is green.

### 2. Verify cubic-agents/ files match the Cubic dashboard

Before releasing, confirm that all agent prompts in `cubic-agents/` are synced with the Cubic dashboard. If any in-repo file was updated since the last release, update the corresponding agent in the dashboard.

### 3. Push main to trigger the authoritative release workflow

```bash
git push origin main
```

`release.yml` is now the single authoritative publish path and runs semantic-release on merges to `main`. It uses full git history (`fetch-depth: 0`) and performs release-readiness checks before publishing.

### 3a. Ensure policy packs are signed

All policy packs must be signed before releasing. The CI release-readiness gate enforces this via `OMG_REQUIRE_TRUSTED_POLICY_PACKS=1`.

```bash
# Generate a new signing keypair (first time only)
python3 scripts/omg.py policy-pack keygen --output keys/dev-key.json --add-to-trust-root

# Sign a specific pack
OMG_SIGNING_KEY="<base64-private-key>" python3 scripts/omg.py policy-pack sign locked-prod

# Or use a key file
python3 scripts/omg.py policy-pack sign locked-prod --key-path keys/dev-key.json

# Verify all packs
python3 scripts/omg.py policy-pack verify --all
```

If any pack is unsigned or tampered, the release-readiness gate will fail.

### 4. What semantic-release automates

- determines next version from conventional commits
- updates changelog + versioned files
- runs `python3 scripts/sync-release-identity.py` in prepare phase
- publishes npm package
- publishes GitHub release and writes back `chore(release): <version> [skip ci]`

### 5. Legacy manual publish workflow

`publish-npm.yml` is retired for normal releases. Use the semantic-release path via `release.yml`.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `tag_name was used by an immutable release` | Bump the version number. The old tag is permanently locked. |
| `validate-release-identity.py` fails | Run the fix sequence shown in the error output. |
| `dist/dist/` double-nesting | You passed `--output-root dist`. Re-run without that flag. |
| `.gemini` or `.kimi` version mismatch | These are not tracked by `sync-release-identity.py` — update manually. |
