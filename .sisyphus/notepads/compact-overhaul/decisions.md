# Decisions — compact-overhaul

## [2026-03-01] Atlas: Plan approved by Momus

- Plan reviewed by Momus → [OKAY] with 2 non-blocking notes
- `_build_context()` is in `stop_dispatcher.py` not `_common.py` — corrected in plan
- Hyphenated filenames can't be imported as Python modules — solution: `context_pressure.py`

## [2026-03-01] Atlas: Wave execution order

- Wave 1: Tasks 1, 2, 3, 7, 8, 9, 10 — all independent, run in parallel
- Wave 2: Tasks 4, 5, 6 — after Wave 1 (4 depends on 3, 5 depends on 2, 6 depends on 1+5)
- Wave 3: Tasks 11, 12, 13 — after Wave 2 (11 depends on 3, 12+13 depend on 4)
- Final: F1-F4 — after all tasks complete

## [2026-03-01] Atlas: Constraints (verbatim from plan)

- DO NOT remove any check function from stop_dispatcher.py
- DO NOT change blocking behavior for normal (non-context-limit) stops
- DO NOT weaken quality gates when "maybe" near limit — only demote on confirmed context pressure
- DO NOT remove quality-gate.py without absorbing its logic first
- DO NOT make Guard 5 skip quality gates after legitimate (non-loop) blocks
- DO NOT touch Ralph loop iteration counter when `should_skip` fires
- DO NOT add dependencies on Claude Code internals we can't control
- Do NOT delete test-validator.py or quality-runner.py source files
- Do NOT remove user-custom Stop hooks that aren't OMG hooks
- Do NOT change the Stop hook timeout below 90s


## F4 Verdict Basis (2026-03-01 00:41:43)
- Classified compliance strictly as spec-accurate only when task behavior matched 'What to do' + 'Must NOT do'.
- Marked cross-task contamination for coordinated gaps (3↔4, 5↔6, 11↔12↔13).
- Treated file-scope contamination as clean only where feature-signature scans stayed within expected files (no git baseline available).
