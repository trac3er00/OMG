# Rule 04 — User-Journey Testing

## The Standard: Test What USERS Need

Don't write boilerplate. Ask:
1. What does the user expect to happen?
2. What could go wrong for the user?
3. What edge cases would a real user hit?

Then write tests for THOSE scenarios.

## Test Categories (consider all, run what applies)
- **Happy path:** The main user flow works
- **Error handling:** Bad input, unauthorized, network failure, timeout
- **Edge cases:** Empty, null, max length, concurrent, boundary values
- **Regression:** Existing behavior unchanged after this change
- **Integration:** Components work together correctly

## Forbidden Patterns
- assert True / expect(true).toBe(true)
- Only testing that functions exist (typeof checks)
- Mocking the thing you're testing
- 5+ tests but no error/edge cases

## Quality Gate
Every change runs: format → lint → typecheck (if typed) → test
If quality-gate.json exists, quality-runner.ts enforces this.

> Enforced: test-generator-hook.ts catches missing coverage follow-up for generated tests.
> quality-runner.ts runs QA commands.
