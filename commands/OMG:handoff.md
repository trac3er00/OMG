---
description: "Produce a structured handoff document from the current session context — decisions, constraints, open loops, risks, artifacts, and next actions."
allowed-tools: Read, Bash(python3:*), Bash(python:*), Bash(cat:*), Bash(ls:*)
argument-hint: "[--save] [--format md|json] [--verbosity brief|standard|detailed]"
---

# /OMG:handoff — Session Handoff Document

## Purpose

Generates a structured summary of the current session suitable for continuing
work in a new session or handing off to another agent. The output captures
decisions made, constraints discovered, open loops, risks, changed artifacts,
and recommended next actions.

## Usage

```
npx omg handoff                          # print markdown to stdout
npx omg handoff --save                   # save to .sisyphus/handoffs/
npx omg handoff --format json            # output JSON envelope
npx omg handoff --verbosity detailed     # include more items per section
```

## How It Works

1. Reads the interaction journal from `.omg/state/interaction-journal.jsonl`
   (or the `interaction_journal/` directory).
2. Calls `runtime/context_compactor.py:compact_context()` to classify entries
   into decisions, constraints, open loops, risks, and next actions.
3. Extracts recent artifact changes via `git status` / `git diff`.
4. Renders the compacted context as Markdown or JSON.

## Output Format

```markdown
# Session Handoff Context

## Decisions

- Selected X over Y because ...

## Constraints

- Must not modify file Z

## Open Loops

- Pending review of PR #42

## Risks

- Risk: circular dependency in module A

## Artifacts

- Changed: src/cli/commands/handoff.ts

## Next Actions

- Complete integration tests
```

## Options

| Flag          | Default    | Description                                                      |
| ------------- | ---------- | ---------------------------------------------------------------- |
| `--save`      | `false`    | Write output to `.sisyphus/handoffs/`                            |
| `--format`    | `md`       | Output format: `md` or `json`                                    |
| `--verbosity` | `standard` | Items per section: `brief` (3), `standard` (10), `detailed` (50) |

## Notes

- Does **not** automatically transfer to a new session. The user decides how to
  use the output (paste into new session, save for later, etc.).
- When `--save` is used, files are written to `.sisyphus/handoffs/` with a
  timestamped filename.
- Falls back gracefully if Python runtime is unavailable.
