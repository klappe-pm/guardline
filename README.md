# guardline

guardline is one detector library for coding agent guardrails. The same rules run from an agent runtime hook, a pre-commit hook and a command line scan, so a given input gets the same verdict from all three. It catches agent attribution in authored text, shell commands that dump the environment, and token-shaped values, and it never prints a matched value. It ships as a Python package and needs only the Python 3.11 standard library at runtime.

Compatibility targets: the Claude Code `PreToolUse` hook payload, [pre-commit](https://pre-commit.com/), and any CI system that can run a command.

## status

The detectors were ported from private shell and Python hook scripts into one pure Python library. Nothing is released yet and there is no PyPI package, so you install from the repository. The first release will be `0.1.0`, and [changelog.md](changelog.md) records the work so far. 43 rules ship in three families: attribution (9), environment dumps (14) and token-shaped values (20).

guardline is a set of heuristics. It catches accidents and lazy bypasses; it is not a sandbox and it does not stop a determined person or program. Read the [security model](docs/explanation/security-model.md) for what it protects against and for the bypasses that are known and open.

## quickstart

Install the command. Until the package reaches PyPI, install from the repository.

```bash
pipx install git+https://github.com/klappe-pm/guardline
```

Scan a commit message file and a script:

```bash
guardline scan /path/to/COMMIT_EDITMSG
```

```bash
guardline scan --shell /path/to/deploy.sh
```

Judge a tool call the way an agent runtime hook does. The command reads the payload on standard input and answers with a JSON decision:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"printenv"}}' | guardline hook
```

Add it to Claude Code with the settings snippet in [use with claude code](docs/how-to-guides/use-with-claude-code.md), or to a repository with the hook ids in [use with pre-commit](docs/how-to-guides/use-with-pre-commit.md).

## documentation

Two trees, one per audience, each arranged by [Diátaxis](https://diataxis.fr/) quadrant: tutorials, how-to guides, reference and explanation.

- I use guardline, where do I start: [getting started](docs/tutorials/getting-started.md), then the rest of [docs](docs/README.md).
- I change guardline, where do I start: [first contribution](developer-docs/tutorials/first-contribution.md), then the rest of [developer-docs](developer-docs/README.md).

## support-and-contributing

[support.md](support.md) says where to ask for help and where to file an issue. [contributing.md](contributing.md) holds the contribution guidelines. Report vulnerabilities privately as described in [security.md](security.md).

## license

MIT. See [LICENSE](LICENSE).
