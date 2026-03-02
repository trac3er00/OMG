# Doc Check — Read Before Edit

**When:** Modifying core logic, adding new patterns, or changing public interfaces.

**Steps:**
1. Check if docs/ARCHITECTURE_TOC.md or docs/ARCHITECTURE.md exists
2. Read the relevant chapter for the subsystem you're touching
3. Note invariants — things that must NOT break
4. After changes: verify invariants still hold

**Skip when:** Fixing typos, updating comments, or trivial changes that don't alter behavior.

**Evidence:** "Read [doc], invariants: [list], all preserved: [yes/no]"
