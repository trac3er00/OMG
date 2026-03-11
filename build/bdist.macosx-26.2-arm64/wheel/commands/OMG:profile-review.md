---
description: Review governed profile state — preferences, confirmations, decay, and provenance
allowed-tools: Bash(python3:*), Read, Grep, Glob
---

# /OMG:profile-review

Read-only inspection of the governed user profile. Reports active style and
safety preferences, pending destructive confirmations, stale/decay candidates,
and provenance summaries.

**This command never mutates `profile.yaml`.**

## Usage

```
python3 scripts/omg.py profile-review [--format json|text]
```

- `--format json` — machine-readable JSON (default)
- `--format text` — human-readable summary

## JSON output shape

```json
{
  "schema": "ProfileReview",
  "style": [ { "field": "...", "value": "...", "confirmation_state": "...", ... } ],
  "safety": [ { "field": "...", "value": "...", "confirmation_state": "...", ... } ],
  "pending_confirmations": [ { "field": "...", "value": "...", "section": "..." } ],
  "decay_candidates": [ { "field": "...", "decay_score": 0.3, ... } ],
  "provenance_summary": [ { "run_id": "...", "source": "...", "field": "...", "updated_at": "..." } ],
  "profile_version": "sha256..."
}
```

## Report sections

1. **Style preferences** — governed style entries with source, learned_at, decay metadata
2. **Safety preferences** — governed safety entries (decay-immune)
3. **Pending confirmations** — entries marked `pending_confirmation` (destructive signals awaiting user approval)
4. **Decay candidates** — style entries with `decay_score > 0` that may be stale
5. **Provenance summary** — recent profile update events from `profile_provenance.recent_updates`
