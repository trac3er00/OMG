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

### 1. Bump version surfaces

Edit the canonical version source and propagate to all surfaces:

```bash
# 1. Edit runtime/adoption.py — update CANONICAL_VERSION
# 2. Edit package.json — update "version"

# 3. Sync all authored surfaces
python3 scripts/sync-release-identity.py

# 4. Compile derived manifests
python3 scripts/omg.py contract compile --host claude --host codex --host gemini --host kimi --channel public
python3 scripts/omg.py contract compile --host claude --host codex --host gemini --host kimi --channel enterprise
python3 scripts/omg.py contract compile --host claude --host codex --host gemini --host kimi --channel public --output-root artifacts/release
python3 scripts/omg.py contract compile --host claude --host codex --host gemini --host kimi --channel enterprise --output-root artifacts/release

# 5. Rebuild Python package
python3 -m build --wheel

# 6. Manually update .gemini/settings.json and .kimi/mcp.json
#    Set _omg._version and _omg.generated.contract_version to the new version
```

> **WARNING:** Do NOT pass `--output-root dist` to the compile command — it creates `dist/dist/` double-nesting. Only use `--output-root artifacts/release` for release artifact outputs.

### 2. Validate

```bash
python3 scripts/validate-release-identity.py --scope all
pytest tests/test_version_gate.py -v
```

Both must exit 0 before proceeding.

### 3. Pre-release safety check

```bash
./scripts/pre-release-check.sh <version>
```

### 4. Commit and push

```bash
git add -A
git commit -m "chore(release): bump to v<version> and sync all surfaces"
git push origin main
```

### 5. Publish

Trigger the `Publish to npm` workflow via GitHub Actions workflow dispatch, or push a `v*.*.*` tag. The workflow includes an automatic pre-release tag safety check that will fail fast if the tag is locked.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `tag_name was used by an immutable release` | Bump the version number. The old tag is permanently locked. |
| `validate-release-identity.py` fails | Run the fix sequence shown in the error output. |
| `dist/dist/` double-nesting | You passed `--output-root dist`. Re-run without that flag. |
| `.gemini` or `.kimi` version mismatch | These are not tracked by `sync-release-identity.py` — update manually. |
