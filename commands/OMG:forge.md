---
description: "FORGE — Labs-only domain-model prototyping and evaluation orchestration. Routes into the lab pipeline with policy enforcement."
allowed-tools: Read, Bash
argument-hint: "[job file path]"
---

# /OMG:forge — Labs-Only Domain Prototyping

> **Availability**: `labs` preset only. Blocked on `safe`, `balanced`, and `interop` presets.

## What It Does

Forge orchestrates domain-model prototyping and evaluation through the existing lab pipeline (`lab/pipeline.py`). It validates jobs against lab policies (`lab/policies.py`), runs the staged pipeline (data → refine → train/distill → evaluate → regression), and emits structured evidence.

Forge does **not**:
- Train frontier models or perform research-scale model training
- Bypass lab policy gates (license checks, source validation)
- Operate outside the `labs` preset boundary

## Policy Enforcement

Every forge job is validated through `lab.policies.validate_job_request()` before pipeline execution:

1. **Dataset license** must be in `ALLOWED_LICENSES`: `apache-2.0`, `mit`, `bsd-3-clause`, `cc-by-4.0`
2. **Dataset source** must not contain blocked tokens: `unknown`, `leaked`, `stolen`, `unauthorized`, `pirated`
3. **Model source** must not contain blocked tokens
4. **Model distillation** must be explicitly allowed (`allow_distill: true`)

Jobs that fail policy checks are blocked with a structured reason before any pipeline stage runs.

## CLI Usage

```bash
# Run a forge job from a JSON file (domain required)
python3 scripts/omg.py forge run --job path/to/job.json

# Run with explicit preset (default: labs)
python3 scripts/omg.py forge run --job path/to/job.json --preset labs

# Run inline with domain-aware job JSON
python3 scripts/omg.py forge run --preset labs --job-json '{"domain":"vision","dataset":{"name":"vision-agent","license":"apache-2.0","source":"internal-curated"},"base_model":{"name":"distill-base-v1","source":"approved-registry","allow_distill":true},"target_metric":0.8,"simulated_metric":0.9,"specialists":["data-curator","training-architect","simulator-engineer"]}'
```

## Job File Format

Every forge job **must** include an explicit `domain` field. Valid canonical domains: `vision`, `robotics`, `algorithms`, `health`, `cybersecurity`. The alias `vision-agent` is accepted and canonicalized to `vision`.

```json
{
  "domain": "vision",
  "dataset": {
    "name": "vision-agent",
    "license": "apache-2.0",
    "source": "internal-curated"
  },
  "base_model": {
    "name": "distill-base-v1",
    "source": "approved-registry",
    "allow_distill": true
  },
  "target_metric": 0.85,
  "simulated_metric": 0.90,
  "specialists": ["data-curator", "training-architect", "simulator-engineer"],
  "evaluation_notes": "Domain adaptation for vision agent"
}
```

## Output

Forge returns structured JSON with pipeline results. Domain-aware jobs with specialists also include a `specialist_dispatch` block:

```json
{
  "status": "ready",
  "stage": "complete",
  "stages": [
    {"name": "data_prepare", "status": "ok"},
    {"name": "synthetic_refine", "status": "ok"},
    {"name": "train_distill", "status": "ok"},
    {"name": "evaluate", "status": "ok"},
    {"name": "regression_test", "status": "ok"}
  ],
  "published": false,
  "evaluation_report": {
    "metric": 0.90,
    "target_metric": 0.85,
    "passed": true
  },
  "specialist_dispatch": {
    "status": "ok",
    "specialists_dispatched": ["data-curator", "training-architect", "simulator-engineer"]
  }
}
```

## Scope Boundary

Forge is a **domain-prototyping** surface, not a model-training research tool. It stays within:

- The lab pipeline's staged execution model
- Lab policy validation for all dataset and model sources
- The `labs` preset boundary — no forge operations run without labs enabled
- Domain-pack contracts (`runtime/domain_packs.py`) for domain-specific prototyping

## Limitations

1. **Validation and Routing, Not Training**: Forge is a job validation and routing layer. It orchestrates the lab pipeline but does not perform actual model training or simulation itself.

2. **Adapter Dependencies**: Actual training and simulation require optional adapters (e.g., `axolotl` for training, `pybullet` for robotics simulation). Forge validates and routes jobs to these adapters if available.

3. **Registry-Based Dispatch**: Specialist dispatch is registry-based routing to domain-specific components, not autonomous agent invocation. Specialists are predefined workflow stages, not independent agents.
