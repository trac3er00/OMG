# OMG Control Plane — API Reference

The control plane exposes a lightweight HTTP server for development and local HUD use.
For production, the stdio-first `omg-control` MCP is the canonical interface.

- **Base URL**: `http://127.0.0.1:8787`
- **Default port**: `8787` (override with `--port`)
- **Auth**: None — loopback-only by default; `--unsafe` / `--dev` required for non-loopback binding
- **Content-Type**: `application/json` for all request and response bodies
- **Versioning**: `/v2/*` is current; `/v1/*` aliases are deprecated (responses include `"deprecated": true`)

All responses include an `"api_version": "v2"` field.

---

## Policy

### Evaluate Tool Call

Evaluate a tool call against the current security policy.

```
POST /v2/policy/evaluate
```

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tool` | string | Yes | Tool name: `Bash`, `Read`, `Write`, `Edit`, `MultiEdit`, or `SupplyArtifact` |
| `input` | object | Conditional | Tool input data. For `Bash`: `{ "command": "..." }`. For file tools: `{ "file_path": "..." }` |
| `artifact` | object | Conditional | Artifact metadata (required when `tool` is `SupplyArtifact`) |
| `mode` | string | No | Enforcement mode for `SupplyArtifact`. Default: `"warn_and_run"` |

**Response `200 OK`**

Policy decision object from the policy engine. Shape varies by tool:

```json
{
  "action": "allow",
  "reason": "Command is safe",
  "api_version": "v2"
}
```

**Response `400 Bad Request`**

```json
{
  "status": "error",
  "error_code": "INVALID_POLICY_INPUT",
  "message": "Unsupported tool for policy evaluation",
  "api_version": "v2"
}
```

**Supported tools**

| Tool | Evaluated via |
|------|---------------|
| `Bash` | `evaluate_bash_command(command)` |
| `Read`, `Write`, `Edit`, `MultiEdit` | `evaluate_file_access(tool, file_path)` |
| `SupplyArtifact` | `evaluate_supply_artifact(artifact, mode)` |

---

## Trust / Verification

### Review Config Change

Review configuration changes for trust and safety.

```
POST /v2/trust/review
```

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_path` | string | No | Path to the config file being changed. Default: `"settings.json"` |
| `old_config` | object | Yes | Previous configuration state |
| `new_config` | object | Yes | Proposed new configuration state |

**Response `200 OK`**

```json
{
  "verdict": "safe",
  "changes": [...],
  "api_version": "v2"
}
```

**Response `400 Bad Request`**

```json
{
  "status": "error",
  "error_code": "INVALID_TRUST_INPUT",
  "message": "old_config and new_config must be objects",
  "api_version": "v2"
}
```

---

### Judge Claims

Judge a list of claims against available evidence.

```
POST /v2/trust/claim-judge
```

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `claims` | array | Yes | List of claim objects to evaluate |

**Response `200 OK`**

```json
{
  "verdict": "pass",
  "results": [...],
  "api_version": "v2"
}
```

**Response `400 Bad Request`**

```json
{
  "status": "error",
  "error_code": "INVALID_CLAIM_INPUT",
  "message": "claims must be a list",
  "api_version": "v2"
}
```

---

### Test Intent Lock

Manage test intent locks. Supports two actions: `lock` and `verify`.

```
POST /v2/trust/test-intent-lock
```

**Request — lock action**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string | Yes | Must be `"lock"` |
| `intent` | object | Yes | Intent descriptor to lock |

**Request — verify action**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string | Yes | Must be `"verify"` |
| `lock_id` | string | Yes | ID of the previously created lock |
| `results` | object | Yes | Actual test results to verify against the lock |

**Response `200 OK`**

```json
{
  "status": "locked",
  "lock_id": "lock_abc123",
  "api_version": "v2"
}
```

**Response `400 Bad Request`**

```json
{
  "status": "error",
  "error_code": "INVALID_INTENT_ACTION",
  "message": "Unknown action: 'foo'; expected 'lock' or 'verify'",
  "api_version": "v2"
}
```

---

### Mutation Gate Check

Check whether a file mutation is permitted by the mutation gate.

```
POST /v2/trust/mutation-gate
```

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tool` | string | Yes | Tool requesting the mutation (e.g., `Write`, `Edit`, `Bash`) |
| `file_path` | string | Yes | Target file path (optional for `Bash`) |
| `lock_id` | string | No | Active test intent lock ID |
| `exemption` | string | No | Exemption reason string |
| `command` | string | No | Bash command string (for `Bash` tool) |
| `run_id` | string | No | Current run identifier |
| `metadata` | object | No | Additional context metadata |

**Response `200 OK`**

```json
{
  "allowed": true,
  "reason": "No active lock",
  "api_version": "v2"
}
```

**Response `400 Bad Request`** — raised as `ValueError` when required fields are missing or invalid.

```json
{
  "status": "error",
  "message": "tool is required",
  "api_version": "v2"
}
```

---

## Security

### Security Check

Run a security audit on the project or a specified scope.

```
POST /v2/security/check
```

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `scope` | string | No | Path or glob to audit. Default: `"."` (entire project) |
| `include_live_enrichment` | boolean | No | Fetch live CVE/advisory data. Default: `false` |
| `external_inputs` | array of objects | No | External data sources to include in the audit |
| `waivers` | array of strings or objects | No | Finding identifiers or waiver objects to suppress |

**Response `200 OK`**

```json
{
  "status": "pass",
  "findings": [],
  "summary": "No issues found",
  "api_version": "v2"
}
```

**Response `400 Bad Request`**

```json
{
  "status": "error",
  "error_code": "INVALID_EXTERNAL_INPUTS",
  "message": "external_inputs must be a list of objects or null",
  "api_version": "v2"
}
```

---

### Evidence Ingest

Ingest evidence artifacts for a specific run.

```
POST /v2/evidence/ingest
```

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `run_id` | string | Yes | Opaque run identifier (validated format) |
| `tests` | any | Yes | Test results or summary |
| `security_scans` | any | Yes | Security scan results |
| `diff_summary` | any | Yes | Diff or change summary |
| `reproducibility` | any | Yes | Reproducibility evidence |
| `unresolved_risks` | any | Yes | List of unresolved risks |
| `provenance` | any | No | Provenance metadata |
| `trust_scores` | any | No | Trust scoring data |
| `api_twin` | any | No | API twin cassette data |
| `route_metadata` | any | No | Route metadata |
| `trace_ids` | any | No | Trace identifiers |
| `lineage` | any | No | Data lineage information |
| `claims` | any | No | Claims to attach to the evidence pack |
| `test_delta` | any | No | Test delta information |
| `browser_evidence_path` | string | No | Path to browser evidence artifacts |
| `repro_pack_path` | string | No | Path to reproduction pack |

**Response `202 Accepted`**

```json
{
  "status": "accepted",
  "run_id": "run_abc123",
  "evidence_path": ".omg/evidence/run_abc123",
  "api_version": "v2"
}
```

**Response `400 Bad Request`**

```json
{
  "status": "error",
  "error_code": "INVALID_EVIDENCE_INPUT",
  "message": "run_id is required",
  "api_version": "v2"
}
```

---

### Registry Verify

Verify an artifact against the registry.

```
POST /v2/registry/verify
```

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `artifact` | object | Yes | Artifact metadata to verify |
| `mode` | string | No | Enforcement mode. Default: `"warn_and_run"` |

**Response `200 OK`** — artifact allowed

```json
{
  "action": "allow",
  "reason": "Artifact verified",
  "api_version": "v2"
}
```

**Response `403 Forbidden`** — artifact denied

```json
{
  "action": "deny",
  "reason": "Artifact not in registry",
  "api_version": "v2"
}
```

**Response `400 Bad Request`**

```json
{
  "status": "error",
  "error_code": "INVALID_REGISTRY_INPUT",
  "message": "artifact must be an object",
  "api_version": "v2"
}
```

---

## Runtime

### Runtime Dispatch

Dispatch a task to a specific runtime environment.

```
POST /v2/runtime/dispatch
```

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `runtime` | string | Yes | Runtime identifier (e.g., `"forge"`, `"codex"`) |
| `idea` | object | Yes | Task descriptor to dispatch |

**Response `200 OK`**

```json
{
  "status": "dispatched",
  "runtime": "forge",
  "api_version": "v2"
}
```

**Response `400 Bad Request`**

```json
{
  "status": "error",
  "error_code": "INVALID_RUNTIME_INPUT",
  "message": "runtime is required",
  "api_version": "v2"
}
```

---

### Guide Assert

Assert that a candidate string satisfies specified guidance rules.

```
POST /v2/guide/assert
```

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `candidate` | string | Yes | The string to evaluate |
| `rules` | object | Yes | Rules object describing the constraints to check |

**Response `200 OK`**

```json
{
  "passed": true,
  "violations": [],
  "api_version": "v2"
}
```

**Response `400 Bad Request`**

```json
{
  "status": "error",
  "error_code": "INVALID_GUIDE_INPUT",
  "message": "rules must be an object",
  "api_version": "v2"
}
```

---

### Tool Fabric Request

Request a tool from the governed tool fabric.

```
POST /v2/trust/tool-fabric
```

> **Note**: This endpoint is served via `ControlPlaneService.tool_fabric_request` and is accessible through the MCP stdio interface. HTTP routing may vary by deployment.

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `lane_name` | string | Yes | Fabric lane name: `lsp-pack`, `hash-edit`, `ast-pack`, or `terminal-lane` |
| `tool_name` | string | Yes | Name of the tool to request within the lane |
| `run_id` | string | Yes | Current run identifier |
| `context` | object | No | Additional context for the tool request |

**Response `200 OK`** — tool allowed

```json
{
  "status": "allowed",
  "reason": "Tool approved by lane policy",
  "evidence_path": ".omg/evidence/run_abc123/tool-fabric.json",
  "ledger_entry": { ... },
  "api_version": "v2"
}
```

**Response `403 Forbidden`** — tool blocked

```json
{
  "status": "blocked",
  "reason": "Tool not permitted in this lane",
  "evidence_path": null,
  "ledger_entry": null,
  "api_version": "v2"
}
```

**Response `400 Bad Request`**

```json
{
  "status": "error",
  "error_code": "INVALID_TOOL_FABRIC_INPUT",
  "message": "lane_name is required",
  "api_version": "v2"
}
```

**Available lanes**

| Lane | Bundle |
|------|--------|
| `lsp-pack` | `registry/bundles/lsp-pack.yaml` |
| `hash-edit` | `registry/bundles/hash-edit.yaml` |
| `ast-pack` | `registry/bundles/ast-pack.yaml` |
| `terminal-lane` | `registry/bundles/terminal-lane.yaml` |

---

### Session Health

Retrieve health status for a session or the latest run.

```
POST /v2/session/health
```

> **Note**: This endpoint is served via `ControlPlaneService.session_health`. HTTP routing may vary by deployment.

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `run_id` | string | No | Run ID to query. If omitted, returns the most recent run's health state |

**Response `200 OK`**

```json
{
  "run_id": "run_abc123",
  "status": "healthy",
  "checked_at": "2026-03-28T00:00:00Z",
  "api_version": "v2"
}
```

**Response `404 Not Found`**

```json
{
  "status": "error",
  "message": "No session health state found",
  "api_version": "v2"
}
```

---

## Lab

### Submit Lab Job

Submit a lab pipeline job.

```
POST /v2/lab/jobs
```

**Request**

Pipeline configuration object. Shape is pipeline-specific.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| *(pipeline fields)* | any | Yes | Pipeline configuration and inputs (object required) |

**Response `201 Created`** — pipeline ready or evaluation failed

```json
{
  "status": "ready",
  "pipeline_id": "pipe_abc123",
  "api_version": "v2"
}
```

**Response `400 Bad Request`**

```json
{
  "status": "error",
  "error_code": "INVALID_LAB_INPUT",
  "message": "job payload must be an object",
  "api_version": "v2"
}
```

---

### Submit Vision Job

Submit a vision job for processing.

```
POST /v2/vision/jobs
```

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mode` | string | Yes | Processing mode: `ocr`, `compare`, `analyze`, `batch`, or `eval` |
| `inputs` | array of strings | Yes | Non-empty list of file paths (relative to project root) |

**Response `202 Accepted`**

```json
{
  "status": "accepted",
  "job_type": "vision",
  "mode": "ocr",
  "input_count": 3,
  "api_version": "v2"
}
```

**Response `400 Bad Request`**

```json
{
  "status": "error",
  "error_code": "INVALID_VISION_INPUT",
  "message": "mode must be one of: analyze, batch, compare, eval, ocr",
  "api_version": "v2"
}
```

---

## Scoreboard

### Get Baseline Metrics

Retrieve the baseline scoreboard metrics.

```
GET /v2/scoreboard/baseline
```

**Request**: No body required.

**Response `200 OK`**

```json
{
  "generated_at": "2026-03-28T00:00:00+00:00",
  "baseline": {
    "safe_autonomy_rate": 0.0,
    "pr_throughput": 0.0,
    "adoption_velocity": 0.0
  },
  "target_policy": "non-regression-or-better",
  "api_version": "v2"
}
```

---

## Error Codes

| Code | Description |
|------|-------------|
| `INVALID_POLICY_INPUT` | Unsupported tool or malformed policy request |
| `INVALID_TRUST_INPUT` | Malformed trust review request |
| `INVALID_EVIDENCE_INPUT` | Missing or invalid evidence ingest fields |
| `INVALID_EXTERNAL_INPUTS` | `external_inputs` is not a list of objects |
| `INVALID_WAIVERS` | `waivers` is not a list of strings or objects |
| `INVALID_GUIDE_INPUT` | `rules` is not an object |
| `INVALID_RUNTIME_INPUT` | Missing `runtime` or malformed `idea` |
| `INVALID_REGISTRY_INPUT` | `artifact` is not an object |
| `INVALID_LAB_INPUT` | Lab job payload is not an object |
| `INVALID_CLAIM_INPUT` | `claims` is not a list |
| `INVALID_INTENT_INPUT` | Missing or invalid intent lock fields |
| `INVALID_INTENT_ACTION` | Unknown `action` value (expected `lock` or `verify`) |
| `INVALID_VISION_INPUT` | Invalid `mode` or `inputs` for vision job |
| `INVALID_TOOL_FABRIC_INPUT` | Missing required tool fabric fields |

---

## Deprecated v1 Aliases

All `/v1/*` paths are deprecated aliases for their `/v2/*` counterparts. Responses from `/v1/*` endpoints include:

```json
{
  "deprecated": true,
  "deprecated_alias": "v1",
  "api_version": "v2"
}
```

| Deprecated | Current |
|------------|---------|
| `POST /v1/policy/evaluate` | `POST /v2/policy/evaluate` |
| `POST /v1/vision/jobs` | `POST /v2/vision/jobs` |
| `POST /v1/trust/review` | `POST /v2/trust/review` |
| `POST /v1/evidence/ingest` | `POST /v2/evidence/ingest` |
| `POST /v1/security/check` | `POST /v2/security/check` |
| `POST /v1/guide/assert` | `POST /v2/guide/assert` |
| `POST /v1/runtime/dispatch` | `POST /v2/runtime/dispatch` |
| `POST /v1/registry/verify` | `POST /v2/registry/verify` |
| `POST /v1/lab/jobs` | `POST /v2/lab/jobs` |
| `POST /v1/trust/claim-judge` | `POST /v2/trust/claim-judge` |
| `POST /v1/trust/test-intent-lock` | `POST /v2/trust/test-intent-lock` |
| `POST /v1/trust/mutation-gate` | `POST /v2/trust/mutation-gate` |
| `GET /v1/scoreboard/baseline` | `GET /v2/scoreboard/baseline` |

---

## Running the Server

```bash
# Default: loopback only, port 8787
python -m control_plane.server

# Custom port
python -m control_plane.server --port 9000

# Development mode (allows non-loopback binding)
python -m control_plane.server --host 0.0.0.0 --dev
```

For production use, prefer the stdio-first MCP interface (`omg-control`) over the HTTP server.
