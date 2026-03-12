# Vision Comparison Design

**Status:** Approved for planning

**Problem**

OMG currently detects vision-oriented prompts and exposes a `vision` domain pack, but it does not implement production OCR extraction, deterministic image comparison, or semantic image-to-image analysis. The existing native image surface only reports file metadata, and the Rust image module is a placeholder.

**Goal**

Add a production-ready OMG vision pipeline that can:
- extract OCR text from one or many images
- compare images deterministically across pairs or batches
- generate semantic explanations of differences using routed vision providers
- emit OMG-native lineage, evaluation, proof, and security artifacts

**Non-Goals**

- replacing existing Gemini/Codex routing behavior outside vision jobs
- building a general-purpose media processing framework for video/audio
- making semantic provider output a required gate for release readiness

**Current Repo Fit**

- `omg_natives/image.py` and `crates/omg-natives/src/image.rs` provide the right boundary for deterministic native image work
- `scripts/omg.py` already hosts user-facing CLI subcommands and batch-oriented runtime entrypoints
- `control_plane/service.py`, `control_plane/server.py`, and `control_plane/openapi.yaml` provide a stable control-plane surface for structured jobs
- `runtime/domain_packs.py`, `registry/bundles/vision.yaml`, `runtime/eval_gate.py`, `runtime/proof_chain.py`, and `runtime/security_check.py` already define the governance/evidence model

**Recommended Architecture**

Use a hybrid pipeline with three stages:

1. Deterministic local stage
- decode and normalize images
- correct orientation
- compute exact/perceptual hashes
- run OCR and region extraction
- run visual diff metrics and changed-region detection

2. Semantic provider stage
- feed normalized crops plus deterministic summaries to routed multimodal providers
- return natural-language explanations of visual and textual differences
- keep semantic output optional and trace-linked, never the only source of truth

3. OMG evidence stage
- persist run state and artifacts under `.omg/`
- connect each run to lineage, eval, proof, and security evidence
- allow release gates to depend on deterministic metrics even when semantic analysis is disabled

**User-Facing Surfaces**

Add a first-class `vision` command family under `scripts/omg.py`:

- `omg vision ocr`
- `omg vision compare`
- `omg vision analyze`
- `omg vision batch`
- `omg vision eval`

Expected inputs:
- explicit file lists
- directories
- manifest JSON
- baseline/candidate sets

Expected outputs:
- machine-readable JSON
- optional markdown/html report
- `.omg/lineage/*.json`
- `.omg/evals/latest.json`
- `.omg/evidence/*.json`

**Runtime Model**

Introduce a job-oriented runtime API:

- `runtime/vision_jobs.py`
  - input validation
  - batching and pair expansion
  - run id propagation
  - stage orchestration
- `runtime/vision_artifacts.py`
  - normalized result schema
  - evidence serialization
  - report building
- `runtime/vision_semantic.py`
  - provider prompts
  - semantic result normalization
  - drift-aware provider metadata

The deterministic engine remains separable from the semantic engine so CI and offline workflows can run without provider access.

**Deterministic Engine**

The deterministic engine should support:

- image info
- normalization metadata
- OCR blocks with bounding boxes and confidence
- exact hash and perceptual hash
- pixel delta ratio
- structural similarity score
- changed region masks or bounding boxes
- OCR text delta between images

This engine should be content-hash cacheable so repeated runs across identical inputs do not redo OCR or normalization.

**Semantic Comparison**

Semantic analysis should use the OMG routing layer instead of hardcoding a single provider:

- `codex`: not primary for image semantics, but may consume OCR/diff summaries
- `gemini`: preferred for multimodal visual reasoning
- `ccg`: useful when comparison findings must translate into code changes

Semantic output must include:
- provider name
- prompt profile
- confidence
- referenced regions
- linked deterministic evidence ids

**Control Plane**

Extend the control plane with typed endpoints for:

- submit vision job
- fetch vision job status
- ingest or fetch structured vision evidence

The control-plane layer should validate payload sizes, supported modes, and path safety before runtime execution.

**Governance and Skills**

The implementation should explicitly use OMG’s existing production skills:

- `omg-vision` for the domain pack contract
- `omg-data-lineage` for provenance and privacy tracking
- `omg-eval-gate` for reproducible regression thresholds
- `omg-proof-gate` for release claims bound to evidence
- `omg-security-check` for file parsing and external input hardening

**Error Handling**

Fail deterministically and per-image where possible:

- invalid image: mark item failed, continue batch
- OCR unavailable: surface structured stage error
- provider timeout: preserve deterministic output and report semantic stage failure
- oversized batch: reject early with structured validation error
- unsupported format: classify as input error, not runtime crash

**Testing Strategy**

Coverage should include:

- unit tests for normalization, hashing, OCR schema, diff metrics, and evidence output
- CLI tests for new `omg vision` subcommands
- control-plane tests for new endpoints
- eval fixtures for known OCR/diff baselines
- performance tests for native image operations

Release gating should require:

- stable deterministic metrics on fixture sets
- lineage artifact generation
- eval gate pass for vision regression suites
- proof gate evidence linkage
- security check covering parser and provider boundaries

**Rollout**

Phase 1
- deterministic OCR and compare
- local artifacts
- CLI support

Phase 2
- control-plane API
- semantic provider integration
- richer reports

Phase 3
- batch datasets
- regression/eval suites
- release-readiness automation

**Decision Summary**

Build a first-class user-facing `omg vision` surface backed by a hybrid deterministic plus semantic pipeline. Deterministic outputs are mandatory and gateable. Semantic outputs are optional, traceable, and operator-facing.
