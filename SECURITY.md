# Security Policy

## Reporting a Vulnerability

Please use GitHub's private vulnerability reporting for this repository if it is enabled.

If private reporting is not available, do not open a public issue with exploit details. Open a minimal issue asking for a private contact path through the maintainer's GitHub profile instead.

Include:

- affected version
- impact
- reproduction steps
- proof of concept if safe to share privately
- suggested mitigation if known

## Response Expectations

- We will triage reports before public discussion.
- We may ask for additional reproduction details.
- Coordinated disclosure is preferred over immediate public disclosure.

## Supported Versions

Security fixes are prioritized for the latest released version.

## Maintainer Notes

- The shipped `safe` preset is expected to enforce pre-tool security hooks before helper hooks run.
- `firewall.py` should screen `Bash` usage and `secret-guard.py` should screen `Read`, `Write`, `Edit`, and `MultiEdit`.
- Sensitive shell commands such as raw `env` dumps, interpreter entry points, and direct permission changes should require approval in the `safe` preset rather than being silently allowed.
