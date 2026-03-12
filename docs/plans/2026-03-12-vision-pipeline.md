# Vision Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a production-ready OMG vision pipeline that supports OCR extraction, deterministic image comparison, semantic visual comparison, and OMG-native evidence artifacts.

**Architecture:** Add a first-class `omg vision` command family backed by new runtime modules and a stronger `omg_natives.image` engine. Keep deterministic OCR and diff logic local and reproducible, then layer optional semantic provider analysis on top. Route all outputs into existing OMG lineage, eval, proof, and security surfaces.

**Tech Stack:** Python 3.10+, OMG CLI/runtime/control-plane, `omg_natives`, Rust native module boundary, pytest, JSON evidence artifacts, optional provider-routed multimodal analysis.

---

### Task 1: Lock the public contract

**Files:**
- Modify: `scripts/omg.py`
- Modify: `control_plane/openapi.yaml`
- Modify: `registry/bundles/vision.yaml`
- Modify: `runtime/domain_packs.py`
- Test: `tests/scripts/test_omg_cli.py`
- Test: `tests/control_plane/test_server_v2.py`
- Test: `tests/runtime/test_domain_packs.py`

**Step 1: Write the failing CLI tests**

```python
def test_vision_command_family_is_registered(cli_runner):
    result = cli_runner(["vision", "--help"])
    assert result.returncode == 0
    assert "ocr" in result.stdout
    assert "compare" in result.stdout
    assert "analyze" in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_omg_cli.py -k vision -v`
Expected: FAIL because `vision` is not a registered subcommand.

**Step 3: Register the command surface**

```python
vision = sub.add_parser("vision", help="OCR, visual diff, and semantic image analysis")
vision_sub = vision.add_subparsers(dest="vision_command", required=True)
for name in ("ocr", "compare", "analyze", "batch", "eval"):
    vision_sub.add_parser(name)
```

**Step 4: Extend the control-plane and vision bundle contracts**

```yaml
/v2/vision/jobs:
  post:
    summary: Submit a vision analysis job
```

```python
"vision": {
    "name": "vision",
    "required_evidence": ["dataset-provenance", "drift-check", "vision-artifacts"],
    "eval_hooks": ["vision-regression"],
}
```

**Step 5: Run the focused tests**

Run: `pytest tests/scripts/test_omg_cli.py tests/control_plane/test_server_v2.py tests/runtime/test_domain_packs.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add scripts/omg.py control_plane/openapi.yaml registry/bundles/vision.yaml runtime/domain_packs.py tests/scripts/test_omg_cli.py tests/control_plane/test_server_v2.py tests/runtime/test_domain_packs.py
git commit -m "feat: add vision command and contract surface"
```

### Task 2: Expand `omg_natives.image` into a deterministic engine boundary

**Files:**
- Modify: `omg_natives/image.py`
- Modify: `crates/omg-natives/src/image.rs`
- Test: `tests/performance/test_rust_modules.py`
- Test: `tests/runtime/test_runtime_profile.py`
- Create: `tests/runtime/test_vision_native_image.py`

**Step 1: Write the failing native tests**

```python
def test_image_compare_operation_returns_metrics(tmp_path):
    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    left.write_bytes(make_png_bytes("A"))
    right.write_bytes(make_png_bytes("B"))

    result = image(str(left), "compare", other_path=str(right))
    assert result["status"] == "ok"
    assert "pixel_delta_ratio" in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_vision_native_image.py -v`
Expected: FAIL because `compare` is unsupported.

**Step 3: Add Python fallback operations**

```python
def image(path: str, operation: str = "info", **kwargs: object) -> dict:
    if operation == "compare":
        return _compare_images(path, str(kwargs["other_path"]))
    if operation == "ocr":
        return _ocr_image(path)
```

**Step 4: Mirror the operation contract in Rust**

```rust
pub fn image_operation(operation: &str, path: &str, other_path: Option<&str>) -> String {
    match operation {
        "info" => info(path),
        "compare" => compare(path, other_path),
        "ocr" => ocr(path),
        _ => error("unsupported_operation"),
    }
}
```

**Step 5: Run native-focused tests**

Run: `pytest tests/runtime/test_vision_native_image.py tests/performance/test_rust_modules.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add omg_natives/image.py crates/omg-natives/src/image.rs tests/runtime/test_vision_native_image.py tests/performance/test_rust_modules.py
git commit -m "feat: add deterministic image compare and ocr operations"
```

### Task 3: Build runtime job orchestration

**Files:**
- Create: `runtime/vision_jobs.py`
- Create: `runtime/vision_artifacts.py`
- Create: `runtime/vision_cache.py`
- Modify: `runtime/__init__.py`
- Test: `tests/runtime/test_vision_jobs.py`
- Test: `tests/runtime/test_vision_artifacts.py`

**Step 1: Write failing runtime tests**

```python
def test_compare_job_expands_pairs_and_collects_artifacts(tmp_path):
    payload = {"mode": "compare", "inputs": ["a.png", "b.png"]}
    result = run_vision_job(str(tmp_path), payload)
    assert result["status"] == "ok"
    assert result["artifacts"]["compare_count"] == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_vision_jobs.py tests/runtime/test_vision_artifacts.py -v`
Expected: FAIL because the runtime modules do not exist.

**Step 3: Implement the job runner and artifact writer**

```python
def run_vision_job(project_dir: str, payload: dict[str, Any]) -> dict[str, Any]:
    job = normalize_vision_payload(payload)
    pairs = expand_pairs(job)
    deterministic = [run_compare(pair) for pair in pairs]
    artifacts = write_vision_artifacts(project_dir, job, deterministic)
    return {"status": "ok", "job": job, "artifacts": artifacts}
```

**Step 4: Add content-hash caching**

```python
cache_key = hash_inputs(normalized_input_paths, config=job["config"])
cached = load_cached_result(project_dir, cache_key)
if cached is not None:
    return cached
```

**Step 5: Run runtime tests**

Run: `pytest tests/runtime/test_vision_jobs.py tests/runtime/test_vision_artifacts.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add runtime/vision_jobs.py runtime/vision_artifacts.py runtime/vision_cache.py runtime/__init__.py tests/runtime/test_vision_jobs.py tests/runtime/test_vision_artifacts.py
git commit -m "feat: add runtime vision job orchestration"
```

### Task 4: Add OMG evidence and lineage integration

**Files:**
- Modify: `runtime/eval_gate.py`
- Modify: `runtime/proof_chain.py`
- Modify: `runtime/verification_controller.py`
- Modify: `hooks/shadow_manager.py`
- Test: `tests/runtime/test_eval_gate.py`
- Test: `tests/runtime/test_proof_chain.py`
- Test: `tests/runtime/test_verification_controller.py`
- Create: `tests/runtime/test_vision_evidence.py`

**Step 1: Write failing evidence tests**

```python
def test_vision_job_writes_eval_and_lineage_links(tmp_path):
    result = finalize_vision_run(str(tmp_path), sample_vision_result())
    assert result["eval_path"] == ".omg/evals/latest.json"
    assert result["lineage"]["trace_id"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_proof_chain.py tests/runtime/test_verification_controller.py tests/runtime/test_vision_evidence.py -v`
Expected: FAIL because vision artifacts are not linked into the evidence chain.

**Step 3: Wire vision artifacts into existing evidence producers**

```python
claims = [{"subject": "vision-job", "status": "supported"}]
evidence_links.extend(vision_artifact_paths)
lineage = build_vision_lineage(...)
evaluate_trace(project_dir, trace_id=trace_id, suites=["vision-regression"], metrics=metrics, lineage=lineage)
```

**Step 4: Preserve deterministic-only mode**

```python
if not semantic_result:
    claims.append({"subject": "semantic-analysis", "status": "skipped", "reason": "disabled"})
```

**Step 5: Run evidence tests**

Run: `pytest tests/runtime/test_proof_chain.py tests/runtime/test_verification_controller.py tests/runtime/test_vision_evidence.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add runtime/eval_gate.py runtime/proof_chain.py runtime/verification_controller.py hooks/shadow_manager.py tests/runtime/test_proof_chain.py tests/runtime/test_verification_controller.py tests/runtime/test_vision_evidence.py
git commit -m "feat: link vision runs into omg evidence flow"
```

### Task 5: Implement CLI execution paths

**Files:**
- Modify: `scripts/omg.py`
- Create: `runtime/vision_cli.py`
- Test: `tests/scripts/test_vision_cli.py`

**Step 1: Write failing CLI behavior tests**

```python
def test_vision_compare_writes_json_report(tmp_path, cli_runner):
    report = tmp_path / "report.json"
    result = cli_runner(["vision", "compare", "--left", "a.png", "--right", "b.png", "--out", str(report)])
    assert result.returncode == 0
    assert report.exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_vision_cli.py -v`
Expected: FAIL because the handler is missing.

**Step 3: Add CLI handlers**

```python
def cmd_vision_compare(args: argparse.Namespace) -> int:
    result = run_vision_cli(project_dir=".", mode="compare", args=args)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1
```

**Step 4: Reuse the runtime job layer instead of duplicating logic**

```python
def run_vision_cli(project_dir: str, mode: str, args: argparse.Namespace) -> dict[str, Any]:
    payload = payload_from_cli(mode, args)
    return run_vision_job(project_dir, payload)
```

**Step 5: Run CLI tests**

Run: `pytest tests/scripts/test_vision_cli.py tests/scripts/test_omg_cli.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add scripts/omg.py runtime/vision_cli.py tests/scripts/test_vision_cli.py
git commit -m "feat: add vision cli execution paths"
```

### Task 6: Expose control-plane APIs

**Files:**
- Modify: `control_plane/service.py`
- Modify: `control_plane/server.py`
- Modify: `control_plane/openapi.yaml`
- Test: `tests/control_plane/test_service.py`
- Test: `tests/control_plane/test_server_v2.py`
- Create: `tests/control_plane/test_vision_api.py`

**Step 1: Write failing API tests**

```python
def test_submit_vision_job_returns_accepted(client):
    response = client.post("/v2/vision/jobs", json={"mode": "ocr", "inputs": ["one.png"]})
    assert response.status_code == 202
    assert response.json()["job_id"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/control_plane/test_service.py tests/control_plane/test_server_v2.py tests/control_plane/test_vision_api.py -v`
Expected: FAIL because the route does not exist.

**Step 3: Add service handlers and routes**

```python
def vision_jobs(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    result = run_vision_job(self.project_dir, payload)
    return 202, result
```

```python
"/v2/vision/jobs": ("vision_jobs", False),
```

**Step 4: Validate input size and mode constraints**

```python
if len(inputs) > MAX_BATCH_INPUTS:
    return 400, {"status": "error", "error_code": "VISION_BATCH_TOO_LARGE"}
```

**Step 5: Run API tests**

Run: `pytest tests/control_plane/test_service.py tests/control_plane/test_server_v2.py tests/control_plane/test_vision_api.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add control_plane/service.py control_plane/server.py control_plane/openapi.yaml tests/control_plane/test_service.py tests/control_plane/test_server_v2.py tests/control_plane/test_vision_api.py
git commit -m "feat: add vision control plane apis"
```

### Task 7: Add semantic provider comparison

**Files:**
- Create: `runtime/vision_semantic.py`
- Modify: `runtime/team_router.py`
- Modify: `runtime/providers/gemini_provider.py`
- Modify: `runtime/providers/codex_provider.py`
- Test: `tests/runtime/test_vision_semantic.py`
- Test: `tests/runtime/test_gemini_provider.py`
- Test: `tests/runtime/test_team_router.py`

**Step 1: Write failing semantic tests**

```python
def test_semantic_compare_preserves_region_references():
    result = analyze_semantic_diff(sample_job(), deterministic_regions=[{"id": "r1"}])
    assert result["status"] == "ok"
    assert result["regions"][0]["id"] == "r1"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_vision_semantic.py tests/runtime/test_team_router.py -v`
Expected: FAIL because semantic analysis does not exist.

**Step 3: Implement provider-routed semantic analysis**

```python
def analyze_semantic_diff(job: dict[str, Any], deterministic_regions: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = build_semantic_prompt(job, deterministic_regions)
    route = resolve_vision_provider(job)
    return normalize_semantic_output(route.execute(prompt))
```

**Step 4: Make semantic analysis optional**

```python
if not job["config"].get("semantic_enabled", False):
    return {"status": "skipped", "reason": "semantic_disabled"}
```

**Step 5: Run semantic tests**

Run: `pytest tests/runtime/test_vision_semantic.py tests/runtime/test_gemini_provider.py tests/runtime/test_team_router.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add runtime/vision_semantic.py runtime/team_router.py runtime/providers/gemini_provider.py runtime/providers/codex_provider.py tests/runtime/test_vision_semantic.py tests/runtime/test_gemini_provider.py tests/runtime/test_team_router.py
git commit -m "feat: add semantic vision comparison routing"
```

### Task 8: Add security hardening and untrusted-content handling

**Files:**
- Modify: `runtime/security_check.py`
- Modify: `runtime/untrusted_content.py`
- Modify: `control_plane/service.py`
- Test: `tests/runtime/test_security_check.py`
- Test: `tests/runtime/test_untrusted_content.py`
- Create: `tests/runtime/test_vision_security.py`

**Step 1: Write failing security tests**

```python
def test_vision_html_report_escapes_ocr_text():
    report = render_vision_report({"ocr_text": "<script>alert(1)</script>"})
    assert "<script>" not in report
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_security_check.py tests/runtime/test_untrusted_content.py tests/runtime/test_vision_security.py -v`
Expected: FAIL because OCR/provider text is not classified for report rendering.

**Step 3: Treat OCR and semantic output as untrusted**

```python
classification = classify_untrusted_content(source="vision-ocr", content=text)
safe_text = sanitize_rendered_text(text)
```

**Step 4: Add security-check coverage for file parsing and provider calls**

```python
findings.append({"rule": "vision-external-input", "status": "checked"})
```

**Step 5: Run security tests**

Run: `pytest tests/runtime/test_security_check.py tests/runtime/test_untrusted_content.py tests/runtime/test_vision_security.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add runtime/security_check.py runtime/untrusted_content.py control_plane/service.py tests/runtime/test_security_check.py tests/runtime/test_untrusted_content.py tests/runtime/test_vision_security.py
git commit -m "feat: harden vision artifacts and inputs"
```

### Task 9: Add regression fixtures and eval gating

**Files:**
- Create: `tests/fixtures/vision/README.md`
- Create: `tests/fixtures/vision/*.json`
- Modify: `runtime/eval_gate.py`
- Modify: `tests/runtime/test_eval_gate.py`
- Create: `tests/runtime/test_vision_eval_gate.py`

**Step 1: Write failing eval tests**

```python
def test_vision_eval_gate_blocks_metric_regression(tmp_path):
    result = evaluate_trace(str(tmp_path), trace_id="trace-1", suites=["vision-regression"], metrics={"ocr_accuracy": 0.71})
    assert result["status"] == "blocked"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_eval_gate.py tests/runtime/test_vision_eval_gate.py -v`
Expected: FAIL because vision metrics are not interpreted specially.

**Step 3: Add vision regression metric handling**

```python
VISION_THRESHOLDS = {"ocr_accuracy": 0.95, "pixel_delta_stability": 0.99}
```

**Step 4: Add fixture-backed regression cases**

```json
{"suite": "vision-regression", "case": "ui-text-change", "expected_changed_regions": 2}
```

**Step 5: Run eval tests**

Run: `pytest tests/runtime/test_eval_gate.py tests/runtime/test_vision_eval_gate.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add tests/fixtures/vision runtime/eval_gate.py tests/runtime/test_eval_gate.py tests/runtime/test_vision_eval_gate.py
git commit -m "feat: add vision regression eval gate"
```

### Task 10: Verify release-readiness and derived surfaces

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/release-checklist.md`
- Modify: generated release/contract artifacts as required by repo workflows
- Test: `tests/scripts/test_release_surface_inventory.py`
- Test: `tests/test_public_surface.py`

**Step 1: Write or update release expectations**

```python
def test_release_surface_inventory_includes_vision_contracts():
    assert "registry/bundles/vision.yaml" in inventory_paths
```

**Step 2: Run release checks before regeneration**

Run: `pytest tests/scripts/test_release_surface_inventory.py tests/test_public_surface.py -v`
Expected: PASS after source and derived surfaces are synchronized.

**Step 3: Regenerate repo-derived surfaces**

```bash
python3 scripts/omg.py contract compile
python3 scripts/omg.py validate
```

**Step 4: Run the full targeted verification set**

Run: `pytest tests/runtime/test_vision_native_image.py tests/runtime/test_vision_jobs.py tests/runtime/test_vision_artifacts.py tests/runtime/test_vision_semantic.py tests/runtime/test_vision_evidence.py tests/runtime/test_vision_security.py tests/runtime/test_vision_eval_gate.py tests/control_plane/test_vision_api.py tests/scripts/test_vision_cli.py -v`
Expected: PASS

**Step 5: Run OMG production gates**

Run: `python3 scripts/omg.py security check --scope .`
Expected: exit 0 and a `.omg/evidence/security-check-*.json` artifact

Run: `python3 scripts/omg.py eval-gate --trace-id vision-release --suites vision-regression --metrics-json '{"ocr_accuracy": 0.99, "pixel_delta_stability": 1.0}'`
Expected: PASS and `.omg/evals/latest.json`

Run: `python3 scripts/omg.py release readiness`
Expected: PASS or an actionable blocker list

**Step 6: Commit**

```bash
git add CHANGELOG.md docs/release-checklist.md tests/scripts/test_release_surface_inventory.py tests/test_public_surface.py
git commit -m "chore: verify release readiness for vision pipeline"
```

### Task 11: Final manual review

**Files:**
- Review: `docs/plans/2026-03-12-vision-comparison-design.md`
- Review: `docs/plans/2026-03-12-vision-pipeline.md`
- Review: all touched source and test files

**Step 1: Run the final summary commands**

Run: `git status --short`
Expected: only intended files remain modified

Run: `git diff --stat`
Expected: source, tests, docs, and derived artifacts match the planned scope

**Step 2: Review residual risks**

```text
- OCR engine packaging and platform support
- semantic provider cost and timeout envelopes
- deterministic threshold tuning across diverse image classes
```

**Step 3: Decide whether to ship with semantic analysis default-off or profile-gated**

```text
Recommended: profile-gated, default-off in strict regression contexts.
```
