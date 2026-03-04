# DDD (Domain-Driven Drive) + SDD (Spec-Driven Development)

**When:** Building new features, creating new modules, or the user mentions domain/spec/pattern.

**Core DDD workflow (4 steps):**
1. **Write first domain by hand** — Define concepts + data handling manually. This becomes the REFERENCE.
2. **Establish criteria** — Understand the reference deeply. Know what's correct vs wrong.
3. **Replicate by pattern** — Use the reference to generate similar domains. AI output is MUCH more accurate with a concrete pattern.
4. **Maintain structure → increasing accuracy** — Initial setup is EVERYTHING. Without it, AI generates plausible-looking garbage.

**4 Principles:**
- Structure becomes pattern → code should be PREDICTABLE across domains
- Focus per domain → one bounded context at a time, NEVER mix concerns
- Code names = business language → `createOrder()` not `processData()`, `PaymentIntent` not `TransactionObj`
- Hooks trigger skills → user command → hook fires → skill activates → AI generates with pattern

**SDD workflow:**
1. Read the spec/requirement COMPLETELY before writing code
2. Extract: inputs, outputs, constraints, edge cases, error states
3. Write interface/type first, implementation second
4. Every function maps to a spec requirement (traceability)

**Before generating code for a new domain, ASK:**
- Does a reference domain exist? → Read it first, match the pattern
- Does a spec exist? → Read it, extract requirements
- If neither → ask the user to define one, or draft one together with /OMG:deep-plan

**Evidence:** When creating domain code, cite which reference pattern was followed.
