# Big Picture — Map Before Code

**When:** Task touches 2+ subsystems, you're unfamiliar with the area, or change could cascade.

**Steps:**
1. Write .oal/state/_context.md with:
   - Subsystems involved (names + responsibilities)
   - Data flow between them
   - Public interfaces affected
2. Identify side effects: "If I change X, what breaks?"
3. Get user confirmation before proceeding

**Skip when:** Single-file fix within one well-understood module.

**Format:**
```
Subsystems: [A] → [B] → [C]
Change in A affects: B (interface), C (data format)
Risk: B's tests may break → run B's tests first
```
