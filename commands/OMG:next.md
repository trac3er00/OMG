---
description: "Analyze project health and surface prioritized improvement suggestions using the ProjectAnalyzer runtime."
allowed-tools: Read, Bash(python3:*), Bash(python:*), Bash(cat:*), Bash(ls:*)
argument-hint: "[--focus <area>] [--quick] [--output <path>]"
---

# /OMG:next — Project Health & Next-Step Surface

## Purpose

Runs the `ProjectAnalyzer` against the current project to produce health scores
and prioritized improvement suggestions. Use this to decide what to work on next
based on data rather than intuition.

## Usage

```
npx omg next                          # full analysis, all dimensions
npx omg next --focus security         # focus on security dimension
npx omg next --focus testing          # focus on test coverage
npx omg next --quick                  # fast mode (skip deep analysis)
npx omg next --output report.json     # save JSON report to file
npx omg next --focus security --output /tmp/health.json
```

## How It Works

1. Delegates to `runtime/project_analyzer.py:ProjectAnalyzer.analyze()`.
2. Scans the project directory for structure, dependencies, test coverage,
   security posture, and documentation completeness.
3. Computes per-dimension health scores (0–100).
4. Generates prioritized improvement suggestions ranked by impact/effort ratio.
5. Returns a structured report with scores, suggestions, and metadata.

## Output Format

```
📊 Project Health Scores
  security             [████████░░] 80/100
  testing              [██████░░░░] 60/100
  documentation        [████░░░░░░] 40/100
  architecture         [███████░░░] 70/100

💡 Top 5 Improvement Suggestions
1. [testing] Add integration tests for auth module
   Impact: 85/100 | Effort: 30/100 | Risk: 10/100
2. [documentation] Add API reference for public endpoints
   Impact: 70/100 | Effort: 20/100 | Risk: 5/100
```

When `--output` is provided, the full JSON report is written to the specified
path for integration with CI pipelines or other tooling.

## Options

| Flag       | Default | Description                             |
| ---------- | ------- | --------------------------------------- |
| `--focus`  | —       | Narrow analysis to a specific dimension |
| `--quick`  | false   | Skip deep analysis for faster results   |
| `--output` | —       | Write full JSON report to this path     |

## Dimensions

| Dimension       | What It Measures                        |
| --------------- | --------------------------------------- |
| `security`      | Secrets, dependency CVEs, auth patterns |
| `testing`       | Coverage, test quality, CI integration  |
| `documentation` | README, API docs, inline comments       |
| `architecture`  | Modularity, coupling, dependency graphs |
| `performance`   | Bundle size, query patterns, caching    |
| `reliability`   | Error handling, logging, retry patterns |

## Notes

- Does **not** modify any source files. Read-only analysis.
- Falls back gracefully if the Python runtime is unavailable.
- Designed for pre-commit and CI integration via `--output`.
