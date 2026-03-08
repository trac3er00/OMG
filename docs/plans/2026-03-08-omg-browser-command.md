# OMG Browser Command Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a canonical `/OMG:browser` command with `/OMG:playwright` alias, powered by upstream `playwright-cli`, with optional OMG setup support and proof-ready browser artifacts across all OMG-supported hosts.

**Architecture:** Keep `omg-control` as the only canonical OMG MCP surface and implement browser automation as an OMG-owned command plus adapter. The adapter wraps upstream `playwright-cli`, normalizes install checks and execution output, and emits artifacts into the existing `.omg/evidence/` proof chain without inventing a second browser runtime.

**Tech Stack:** Markdown command specs, plugin manifests, shell install flow, Python runtime adapter, pytest, existing browser proof modules.

---

### Task 1: Lock the public command surface

**Files:**
- Create: `/Users/cminseo/Documents/scripts/Shell/OMG/commands/OMG:browser.md`
- Create: `/Users/cminseo/Documents/scripts/Shell/OMG/commands/OMG:playwright.md`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/plugins/core/plugin.json`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/plugins/README.md`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/test_public_surface.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/commands/test_alias_compat.py`

**Step 1: Write the failing tests**

```python
def test_core_plugin_manifest_includes_browser_command():
    manifest = json.loads((ROOT / "plugins" / "core" / "plugin.json").read_text())
    assert "browser" in manifest["commands"]


def test_browser_alias_points_to_playwright_compat_surface():
    browser_doc = _read("commands/OMG:browser.md")
    playwright_doc = _read("commands/OMG:playwright.md")
    assert "/OMG:browser" in browser_doc
    assert "alias" in playwright_doc.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_public_surface.py tests/commands/test_alias_compat.py -k "browser or playwright" -v`

Expected: FAIL because the command files and manifest entries do not exist yet.

**Step 3: Write minimal implementation**

- Add `/OMG:browser` as the canonical command doc.
- Add `/OMG:playwright` as an alias doc that clearly forwards to `/OMG:browser`.
- Register `browser` in `plugins/core/plugin.json`.
- Update `plugins/README.md` so the command appears in the public command table.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_public_surface.py tests/commands/test_alias_compat.py -k "browser or playwright" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add commands/OMG:browser.md commands/OMG:playwright.md plugins/core/plugin.json plugins/README.md tests/test_public_surface.py tests/commands/test_alias_compat.py
git commit -m "Add OMG browser command surface"
```

### Task 2: Add a runtime adapter for upstream playwright-cli

**Files:**
- Create: `/Users/cminseo/Documents/scripts/Shell/OMG/runtime/omg_browser_cli.py`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/runtime/playwright_pack.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/runtime/test_omg_browser_cli.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/runtime/test_playwright_pack.py`

**Step 1: Write the failing tests**

```python
def test_browser_cli_detects_missing_playwright_binary(tmp_path):
    result = ensure_playwright_cli(project_dir=tmp_path, which=stub_missing)
    assert result["status"] == "missing"
    assert "install" in result["remediation"]


def test_browser_cli_normalizes_trace_and_screenshot_paths(tmp_path):
    result = run_browser_cli(goal="smoke", project_dir=tmp_path, runner=stub_runner)
    assert result["status"] == "success"
    assert result["artifacts"]["trace"].startswith(str(tmp_path / ".omg" / "evidence"))
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_omg_browser_cli.py tests/runtime/test_playwright_pack.py -k "browser_cli or playwright_cli" -v`

Expected: FAIL because `runtime/omg_browser_cli.py` does not exist and the current pack does not consume normalized upstream output.

**Step 3: Write minimal implementation**

- Add a thin adapter that:
  - checks for upstream `playwright-cli`
  - checks whether browser binaries are installed
  - runs upstream commands through a controlled wrapper
  - returns normalized result payloads for OMG
- Keep browser evidence writing in `playwright_pack.py` or a nearby helper rather than duplicating proof logic.

**Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_omg_browser_cli.py tests/runtime/test_playwright_pack.py -k "browser_cli or playwright_cli" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add runtime/omg_browser_cli.py runtime/playwright_pack.py tests/runtime/test_omg_browser_cli.py tests/runtime/test_playwright_pack.py
git commit -m "Add playwright-cli adapter for OMG browser flows"
```

### Task 3: Wire proof and trust integration

**Files:**
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/runtime/proof_gate.py`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/runtime/proof_chain.py`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/runtime/playwright_adapter.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/runtime/test_proof_gate.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/runtime/test_proof_chain.py`

**Step 1: Write the failing tests**

```python
def test_browser_command_output_is_accepted_by_proof_chain(tmp_path):
    payload = build_browser_cli_payload(tmp_path)
    gate_input = resolve_proof_chain(output_root=tmp_path, evidence_payload=payload)
    assert gate_input["browser_evidence"]["schema"] in {"BrowserEvidence", "PlaywrightAdapterEvidence"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_proof_gate.py tests/runtime/test_proof_chain.py -k "browser_command or playwright_cli" -v`

Expected: FAIL because the new adapter output shape is not wired into the proof path yet.

**Step 3: Write minimal implementation**

- Ensure adapter output is accepted by `proof_chain` and `proof_gate`.
- Preserve current trace-linkage and browser evidence expectations.
- Do not loosen existing proof requirements to make tests pass.

**Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_proof_gate.py tests/runtime/test_proof_chain.py -k "browser_command or playwright_cli" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add runtime/proof_gate.py runtime/proof_chain.py runtime/playwright_adapter.py tests/runtime/test_proof_gate.py tests/runtime/test_proof_chain.py
git commit -m "Integrate OMG browser adapter with proof chain"
```

### Task 4: Add optional setup support for browser capability

**Files:**
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/OMG-setup.sh`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/hooks/setup_wizard.py`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/docs/install/claude-code.md`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/docs/install/codex.md`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/docs/install/gemini.md`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/docs/install/kimi.md`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/e2e/test_setup_script.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/hooks/test_setup_wizard.py`

**Step 1: Write the failing tests**

```python
def test_setup_browser_addon_installs_playwright_cli_when_enabled(tmp_path):
    result = run_setup("--enable-browser", home=tmp_path)
    assert result.exit_code == 0
    assert "browser capability enabled" in result.stdout.lower()


def test_setup_browser_addon_is_opt_in(tmp_path):
    result = run_setup(home=tmp_path)
    assert "browser capability enabled" not in result.stdout.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/e2e/test_setup_script.py tests/hooks/test_setup_wizard.py -k "browser addon or playwright" -v`

Expected: FAIL because setup does not expose a browser addon yet.

**Step 3: Write minimal implementation**

- Add an opt-in setup path for browser capability.
- Keep it disabled by default.
- Make remediation and verify steps explicit in install docs.
- Do not add a browser MCP server in this task.

**Step 4: Run test to verify it passes**

Run: `pytest tests/e2e/test_setup_script.py tests/hooks/test_setup_wizard.py -k "browser addon or playwright" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add OMG-setup.sh hooks/setup_wizard.py docs/install/claude-code.md docs/install/codex.md docs/install/gemini.md docs/install/kimi.md tests/e2e/test_setup_script.py tests/hooks/test_setup_wizard.py
git commit -m "Add optional browser capability to OMG setup"
```

### Task 5: Update public docs and command guidance

**Files:**
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/README.md`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/docs/proof.md`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/plugins/README.md`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/test_public_surface.py`

**Step 1: Write the failing tests**

```python
def test_readme_promotes_browser_command():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "/OMG:browser" in readme
    assert "/OMG:playwright" in readme
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_public_surface.py -k "browser or playwright" -v`

Expected: FAIL because the docs do not advertise the new command yet.

**Step 3: Write minimal implementation**

- Document `/OMG:browser` as canonical.
- Mention `/OMG:playwright` only as a compatibility alias.
- Explain that browser capability is powered by upstream `playwright-cli`, not a new OMG MCP.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_public_surface.py -k "browser or playwright" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add README.md docs/proof.md plugins/README.md tests/test_public_surface.py
git commit -m "Document OMG browser command"
```

### Task 6: End-to-end verification and release-readiness

**Files:**
- Modify only if verification reveals real gaps.
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/e2e/test_setup_script.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/runtime/test_omg_browser_cli.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/runtime/test_playwright_pack.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/test_public_surface.py`

**Step 1: Run the focused verification set**

Run:

```bash
pytest -q tests/commands/test_alias_compat.py tests/test_public_surface.py tests/hooks/test_setup_wizard.py tests/e2e/test_setup_script.py tests/runtime/test_omg_browser_cli.py tests/runtime/test_playwright_pack.py tests/runtime/test_proof_gate.py tests/runtime/test_proof_chain.py
```

Expected: PASS

**Step 2: Run syntax and contract checks**

Run:

```bash
python3 -m py_compile runtime/omg_browser_cli.py
python3 scripts/omg.py contract validate
```

Expected: exit code `0`

**Step 3: Perform manual smoke verification**

Run:

```bash
./OMG-setup.sh install --non-interactive --merge-policy=apply
```

Then verify:

- Claude path documents `/OMG:browser`
- browser addon is optional
- `.omg/evidence/` receives normalized browser artifacts
- no new browser MCP entry is required for host operation

**Step 4: Commit final adjustments if needed**

```bash
git add <only files changed during verification>
git commit -m "Finalize OMG browser command verification"
```

**Step 5: Prepare handoff**

- Update the active PR summary with:
  - canonical `/OMG:browser`
  - `/OMG:playwright` alias
  - upstream `playwright-cli` dependency
  - optional setup/browser capability
  - focused verification commands and results
