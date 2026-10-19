# cli

This page lists every subcommand, option and exit status of the `guardline` command. For a walk through the common ones see [getting started](../tutorials/getting-started.md).

## synopsis

```text
guardline [--version] <command> [options]
```

Commands: `hook`, `scan`, `diff` and `rules`.

## exit-statuses

| status | meaning |
| --- | --- |
| 0 | clean, or report mode, or a hook that allowed the call or denied it with JSON |
| 1 | block mode found something (`scan`, `diff`), or `rules check` found a problem |
| 2 | a usage, configuration or rule file error; for `hook --deny-with exit-code`, a deny |

The `hook` command never blocks with exit 1, because a runtime treats exit 1 as a non-blocking error. See [hook protocol](hook-protocol.md).

## common-options

These options are accepted by `hook`, `scan`, `diff` and `rules`.

| option | meaning |
| --- | --- |
| `--config PATH` | read this `guardline.toml`, or the `[tool.guardline]` table when the file is named `pyproject.toml` |
| `--no-config` | ignore every configuration file |
| `--mode report` or `--mode block` | `report` prints findings and exits 0; `block` exits 1 on any finding. Default: the configured mode, else `block` |
| `--disable RULE_ID` | turn a rule off; repeatable; an unknown id is an error |
| `--rules FILE` | load an extra rule file; repeatable |
| `--family NAME` | run only rules of this family; repeatable; overrides the configured `families` |
| `--allow-fenced-attribution` | do not report attribution inside a closed fenced code block |

## guardline-hook

```text
guardline hook [common options] [--deny-with json|exit-code]
```

Reads one tool call payload on standard input and judges it. The hook never discovers configuration: it reads a configuration file only when `--config PATH` names one, so a file the agent writes into the project cannot change it. `--deny-with json` (the default) writes a JSON deny decision to standard output and exits 0. `--deny-with exit-code` writes the reason to standard error and exits 2. `--allow-config-edit` lets the agent write guardline configuration files; without it a Write, Edit or MultiEdit to `guardline.toml`, to a pyproject.toml with a `[tool.guardline]` table, or to the hook's own `--config` or `--rules` file is denied. Empty input, a payload that is not JSON, invalid bytes, a configuration error or a crash blocks the call in block mode and is only printed in report mode.

## guardline-scan

```text
guardline scan [common options] [--format text|json] [--shell] [--commit-msg] [PATH ...]
```

Scans files, directories and standard input. With no path, or with `-`, it reads standard input and calls the source `<stdin>`. A directory is walked recursively and `.git` is the only directory never entered; `node_modules`, virtual environments and the like are scanned unless the configured `exclude` globs skip them. Binary files are scanned too, with NUL characters removed. A symbolic link or special file found in a directory walk is not read; it is reported as a `guardline-file-skipped` finding, so in block mode it fails the run. A file named on the command line is always read, even if it is a link.

| option | meaning |
| --- | --- |
| `--format text` | one line per finding: `source:line:column: rule [family] description` (default) |
| `--format json` | one JSON document: `version`, `mode`, `blocked` and `findings` |
| `--shell` | treat the input as shell commands and run the command rules; without it only text rules run |
| `--commit-msg` | blank the diff git appends after the scissors line (`# ---- >8 ----`) of a commit message file, keeping line numbers; comment lines above it are scanned because git keeps them for `-m` and `-F` messages |

A file longer than `max_text_chars` is not read in full and yields a `guardline-input-too-large` finding. A file that cannot be read is an error (exit 2).

## guardline-diff

```text
guardline diff [common options] [--staged] [--base REV] [--repo DIR] [--format text|json] [PATH ...]
```

Runs `git diff --unified=0` and scans only the added lines. Findings are reported at the line numbers of the new file. `--staged` diffs the index, `--base REV` compares against a revision (a value starting with a dash is refused), `--repo DIR` names the repository (default: the current directory), and the paths limit the files. The command runs `git` with an argument list and never contacts a remote.

## guardline-rules-list

```text
guardline rules list [common options] [--format text|json]
```

Lists the active rules after configuration and disables. Text output is one tab separated line per rule: id, family, scope, description. JSON output is a list of objects with `id`, `family`, `scope`, `description` and `builtin`.

## guardline-rules-check

```text
guardline rules check [FILE ...]
```

With no file, validates the built-in rules and runs their examples. With files, loads them, validates every rule and runs each rule's examples against the built-in rules plus the file. Exits 0 and prints `ok: N rule(s) validated` when every rule fires on its fire example and stays quiet on its look-alike example. Otherwise it prints each problem on standard error and exits 1. A file that fails validation exits 2. Messages never quote an example.

## version

```text
guardline --version
```

Prints `guardline` and the package version.
