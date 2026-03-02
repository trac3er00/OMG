# Dependency Safety

**When:** Adding, upgrading, or removing any dependency.

**Before adding:**
1. Can stdlib or existing deps solve this? (Check lockfile for overlap)
2. Evaluate: maintenance status, last publish date, weekly downloads, license, bundle size
3. Check for known vulnerabilities: `npm audit` / `pip audit` / `cargo audit`

**After adding:**
- Lockfile updated and committed
- dev vs prod classification correct
- Version pinned (not floating/latest)
- Run full test suite to catch conflicts

**Red flags:** Last publish >1 year, <1K weekly downloads, copyleft license in proprietary project, >500KB for a utility function.
