# security

## reporting-a-vulnerability

Report vulnerabilities privately through GitHub security advisories: open the repository's Security tab and choose "Report a vulnerability", or go to <https://github.com/klappe-pm/guardline/security/advisories/new>. Do not open a public issue, pull request or discussion for a suspected vulnerability.

Include the affected version or commit, the steps to reproduce, and the impact you observed. You will receive an acknowledgement, and the fix and disclosure are coordinated with you through the advisory.

## scope

- The `guardline` command and the Python package.
- Any way to make guardline print, log or return a matched secret.
- Any input that makes a scan take unbounded time or memory (regular expression denial of service).
- Any way a hook can fail open: an input that makes the hook allow a call it should block or crash into an allow.
- The rule loader, including a rule file that escapes validation.

A bypass of a detector is a different thing. guardline is a set of heuristics and has known, documented bypasses (see the [security model](docs/explanation/security-model.md)). A new bypass is a welcome issue or pull request with a rule or a test, and is not treated as a vulnerability unless it also crosses one of the lines above.

Vulnerabilities in the agent runtimes themselves are out of scope; report those to their maintainers.

## supported-versions

Until the first release, only the `main` branch receives security fixes.
