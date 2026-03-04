# Context Management

**When:** Long sessions (100+ tool calls), feeling lost, or about to compact.

**Prefer /OMG:handoff over automatic compaction.** /OMG:handoff preserves intent + decisions + failure history. Automatic compaction loses nuance.

**Minimize context waste:**
- Read file line ranges, not entire files: `Read(file.ts:10-50)` not `Read(file.ts)`
- Keep working-memory.md concise (under 30 lines)
- Don't re-read files you already read this session
- Use Grep/Glob to find specific content instead of reading everything

**Signs of thin context (you need /OMG:handoff soon):**
- Repeating questions you already asked
- Contradicting earlier decisions
- Forgetting file locations
- Re-reading the same files

**Rule:** When in doubt, /OMG:handoff now. It's cheaper than losing context.
