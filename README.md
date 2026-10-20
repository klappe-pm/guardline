<p align="center">
  <a href="https://github.com/klappe-pm/guardline"><img src="https://raw.githubusercontent.com/klappe-pm/guardline/main/.github/guardline-banner.svg" alt="A terminal window: guardline scan is typed, the guardline wordmark appears, and each rule family reports its result" width="760"></a>
</p>

<h1 align="center">Guardline</h1>

<p align="center">
  One detector library for coding agent guardrails.
</p>

<p align="center">
  <a href="https://pypi.org/project/guardline/"><img src="https://img.shields.io/pypi/v/guardline?style=flat-square&color=3ddc84&labelColor=162233&label=PyPI" alt="PyPI version"></a>
  <a href="https://pypi.org/project/guardline/"><img src="https://img.shields.io/pypi/pyversions/guardline?style=flat-square&color=5aa9ff&labelColor=162233&label=Python" alt="Python versions"></a>
  <a href="https://github.com/klappe-pm/guardline/releases"><img src="https://img.shields.io/github/v/release/klappe-pm/guardline?style=flat-square&color=3ddc84&labelColor=162233&label=release" alt="Latest release"></a>
  <a href="https://github.com/klappe-pm/guardline/blob/main/LICENSE"><img src="https://img.shields.io/github/license/klappe-pm/guardline?style=flat-square&color=5aa9ff&labelColor=162233&label=license" alt="MIT license"></a>
  <a href="https://github.com/klappe-pm/guardline/blob/main/pyproject.toml"><img src="https://img.shields.io/badge/dependencies-none-3ddc84?style=flat-square&labelColor=162233" alt="No runtime dependencies"></a>
  <a href="https://github.com/klappe-pm/guardline/blob/main/docs/reference/rules.md"><img src="https://img.shields.io/badge/rules-43-5aa9ff?style=flat-square&labelColor=162233" alt="43 built-in rules"></a>
</p>

<p align="center">
  <a href="#installation">Installation</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#how-it-works">How It Works</a> ·
  <a href="#commands">Commands</a> ·
  <a href="https://github.com/klappe-pm/guardline/blob/main/docs/README.md">Docs</a> ·
  <a href="#contributing">Contributing</a>
</p>

---

A coding agent writes commit messages, runs shell commands and edits files faster than anyone reads them. Three accidents keep recurring: authored text carries a co-author trailer or a generated with footer that a policy forbids, a shell command prints the whole environment into a transcript, and a token-shaped value is about to land in a file, a commit or a shell history. Each team ends up with its own pile of private hook scripts, and the scripts disagree with each other.

Guardline is one detector library behind three entry points. The same rules run from an agent runtime hook, a pre-commit hook and a command line scan, so a given input gets the same verdict from all three. It catches agent attribution in authored text, shell commands that dump the environment, and token-shaped values, and it never prints a matched value. It ships as a Python package and needs only the Python 3.11 standard library at runtime. It is a set of heuristics that catches accidents and lazy bypasses; it is not a sandbox, and the [Security Model](https://github.com/klappe-pm/guardline/blob/main/docs/explanation/security-model.md) lists the bypasses that are known and open.

## Why Guardline?

| Without Guardline | With Guardline |
| --- | --- |
| Each hook script reimplements the same checks and drifts from the others | One rule set serves the agent hook, pre-commit and CI, with one verdict |
| A detection rule is code that only its author can review | Every rule is data: an id, a pattern, and two examples the test suite runs |
| A scanner that prints what it found puts the secret in the log again | Findings carry the rule id and a position, never the matched text |
| A hook that crashes or times out lets the call through | The hook fails closed: bad input, bad configuration and crashes block the call |
| A dumped environment shows up in a transcript after the fact | `printenv`, `set`, `docker inspect` and the rest are caught before the command runs |

## Who This Is For

- Developers running a coding agent who want a hook that stops attribution lines, environment dumps and pasted credentials before they land.
- Teams that want the same checks in the agent hook, in pre-commit and in CI.
- Anyone who wants to add personal or team rules as a small data file instead of a script.

## Highlights

- **43 built-in rules in three families.** Agent attribution (9), environment dumps (14) and token-shaped values (20).
- **One verdict, three entry points.** `guardline hook` for an agent runtime, the pre-commit hooks, and `guardline scan` and `guardline diff` for the command line and CI.
- **Never prints a value.** Findings, deny reasons and logs carry rule ids and positions only, and tests prove it across the API, the hook and the command line.
- **Reads shell the way a shell does.** A lexer decodes quoting and looks through pipes, substitutions, heredocs and wrappers such as `sudo`, `ssh`, `env` and `bash -c`.
- **Fails closed.** In block mode the hook denies when it cannot judge, and it never searches for a configuration an agent could have written.
- **Bounded work.** Input size limits, a token budget for the shell lexer and linear patterns keep a hostile input from making the guard slow.
- **Nothing to install but Python.** Pure standard library at runtime, no dependencies.

## Installation

Guardline needs Python 3.11 or newer. [pipx](https://pipx.pypa.io/) is the easiest way to get a command-line tool onto your path:

```bash
pipx install guardline
```

Nothing is published to PyPI yet. Until the first release, install from GitHub:

```bash
pipx install git+https://github.com/klappe-pm/guardline
```

Then check that it runs:

```bash
guardline --version
```

## Quick Start

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

Choose block or report mode and the rule families, write the configuration and print the setup snippets in one step:

```bash
guardline init
```

Add it to Claude Code with the settings snippet in [Use with Claude Code](https://github.com/klappe-pm/guardline/blob/main/docs/how-to-guides/use-with-claude-code.md), or to a repository with the hook ids in [Use with Pre-Commit](https://github.com/klappe-pm/guardline/blob/main/docs/how-to-guides/use-with-pre-commit.md).

## How It Works

Every rule is an entry in a TOML rule file with an id, a family, a pattern and two examples: one the rule must fire on and one look-alike it must not. The built-in rules ship as package data, and a rule file of your own is loaded the same way. The engine judges text and shell commands against the active rules, and the three entry points are thin wrappers around it.

| Family | Rules | What it catches |
| --- | --- | --- |
| attribution | 9 | A co-author trailer, a generated with footer, a session link or a robot byline in authored text |
| env-dump | 14 | Shell commands that print the environment, a process environment or a keychain secret |
| token | 20 | Values shaped like API keys, tokens, private key blocks and other credentials |

| Entry point | Where it runs | What it reads |
| --- | --- | --- |
| `guardline hook` | An agent runtime, before a tool call | A tool call payload on standard input |
| pre-commit hooks | `git commit` | The staged files and the commit message |
| `guardline scan` and `guardline diff` | A terminal or a CI job | Files, directories, standard input, or the lines a git diff adds |

Configuration is optional. A `guardline.toml` or a `[tool.guardline]` table sets the mode (`block` or `report`), turns rules off by id, restricts families, adds rule files and sets size limits. The hook reads configuration only from an explicit `--config`, so an agent that can write files cannot switch its own guard off.

## Commands

| Command | What it does |
| --- | --- |
| `guardline hook` | Judges a tool call payload on standard input and answers with a JSON decision or an exit code. |
| `guardline scan` | Scans files, directories or standard input, optionally as shell commands (`--shell`) or as a commit message (`--commit-msg`). |
| `guardline diff` | Scans only the lines a git diff adds, in the work tree, the index (`--staged`) or against a revision (`--base`). |
| `guardline rules list` | Lists the active rules after configuration and disables. |
| `guardline rules check` | Validates rule files and runs each rule's two examples. |
| `guardline init` | Chooses a mode and rule families, writes the configuration and prints the setup snippets. |
| `guardline config show` | Prints the effective configuration and where each part came from. |

`guardline scan` and `guardline diff` exit 0 when clean or in report mode, 1 when block mode finds something, and 2 for a usage, configuration or rule file error. The [CLI reference](https://github.com/klappe-pm/guardline/blob/main/docs/reference/cli.md) covers the full surface, and the [Python API reference](https://github.com/klappe-pm/guardline/blob/main/docs/reference/python-api.md) covers the library.

## Documentation

The docs live in one tree under `docs/`, following the [Diátaxis](https://diataxis.fr/) layout: tutorials, how-to guides, reference and explanation.

- **Using it:** start with [Getting Started](https://github.com/klappe-pm/guardline/blob/main/docs/tutorials/getting-started.md), then browse the rest of [docs](https://github.com/klappe-pm/guardline/blob/main/docs/README.md).
- **Hacking on it:** start with [First Contribution](https://github.com/klappe-pm/guardline/blob/main/docs/tutorials/first-contribution.md), which sits in the same tree.
- **What ships:** the [changelog](https://github.com/klappe-pm/guardline/blob/main/CHANGELOG.md).

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](https://github.com/klappe-pm/guardline/blob/main/CONTRIBUTING.md) first; it will save you a round trip. If you are stuck or have found a bug, [SUPPORT.md](https://github.com/klappe-pm/guardline/blob/main/SUPPORT.md) says where to ask and where to file an issue.

## Security

Please report vulnerabilities privately as described in [SECURITY.md](https://github.com/klappe-pm/guardline/blob/main/SECURITY.md) rather than opening a public issue.

## License

Guardline is released under the [MIT License](https://github.com/klappe-pm/guardline/blob/main/LICENSE).
