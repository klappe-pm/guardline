# cli

This page lists every subcommand, option and exit status of the `guardline` command. For a walk through the common ones see [getting started](../tutorials/getting-started.md).

## synopsis

```text
guardline [--version] <command> [options]
```

Commands: `hook`, `scan`, `diff`, `rules`, `init` and `config`.

## exit-statuses

| status | meaning |
| --- | --- |
| 0 | clean, or report mode, or a hook that allowed the call or denied it with JSON |
| 1 | block mode found something (`scan`, `diff`), `rules check` found a problem, or you declined the confirmation of `init` |
| 2 | a usage, configuration or rule file error; for `hook --deny-with exit-code`, a deny |

The `hook` command never blocks with exit 1, because a runtime treats exit 1 as a non-blocking error. See [hook protocol](hook-protocol.md).

## common-options

These options are accepted by `hook`, `scan`, `diff`, `rules` and `config`. They go before the action of `rules` and `config`, as in `guardline config --no-config show`.

| option | meaning |
| --- | --- |
| `--config PATH` | read this `guardline.toml`, or the `[tool.guardline]` table when the file is named `pyproject.toml` |
| `--no-config` | ignore every configuration file |
| `--mode report` or `--mode block` | `report` prints findings and exits 0; `block` exits 1 on any finding. Default: the configured mode, else `block` |
| `--disable RULE_ID` | turn a rule off; repeatable; an unknown id is an error |
| `--rules FILE` | load an extra rule file; repeatable |
| `--family NAME` | run only rules of this family; repeatable; overrides the configured `families` |
| `--allow-fenced-attribution` | do not report attribution inside a closed fenced code block |

Option names must be written in full: every parser is created with abbreviations off, so `--mod` is a usage error rather than `--mode`. A file name that looks like an option cannot change a scan when it follows `--`, which the pre-commit hooks pass.

## guardline-hook

```text
guardline hook [common options] [--deny-with json|exit-code]
```

Reads one tool call payload on standard input and judges it. The hook never discovers configuration: it reads a configuration file only when `--config PATH` names one, so a file the agent writes into the project cannot change it. `--deny-with json` (the default) writes a JSON deny decision to standard output and exits 0. `--deny-with exit-code` writes the reason to standard error and exits 2. `--allow-config-edit` lets the agent write guardline configuration files; without it a Write, Edit or MultiEdit to `guardline.toml`, to a pyproject.toml with a `[tool.guardline]` table, or to the hook's own `--config` file, `--rules` file or a rule file named by that config's `rule_files` is denied. Empty input, a payload that is not JSON, invalid bytes, a configuration error or a crash blocks the call in block mode and is only printed in report mode.

## guardline-scan

```text
guardline scan [common options] [--format text|json] [--shell] [--no-stdin] [--commit-msg] [--] [PATH ...]
```

Scans files, directories and standard input. With no path, or with `-`, it reads standard input and calls the source `<stdin>`; `--no-stdin` turns that off, so `-` is a file name and no path scans nothing. A directory is walked recursively and `.git` is the only directory never entered; `node_modules`, virtual environments and the like are scanned unless the configured `exclude` globs skip them. Binary files are scanned too, with NUL characters removed. A symbolic link or special file found in a directory walk is not read; it is reported as a `guardline-file-skipped` finding, so in block mode it fails the run. A file named on the command line is always read, even if it is a link.

| option | meaning |
| --- | --- |
| `--format text` | one line per finding: `source:line:column: rule [family] description` (default) |
| `--format json` | one JSON document: `version`, `mode`, `blocked` and `findings` |
| `--no-stdin` | treat `-` as a file name and never read standard input; the pre-commit hooks use it |
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

## guardline-init

```text
guardline init [--mode block|report] [--families NAMES] [--target guardline.toml|pyproject.toml] [--hook claude-code|pre-commit|none] [--yes] [--force]
```

Chooses the settings and writes the configuration file in the current directory. Without flags it asks four questions in this order, and an answer given by a flag is not asked again. Standard input must be available for the questions: when it runs out, the command stops with exit 2 and writes nothing.

1. Target file. Asked only when a `pyproject.toml` exists in the current directory. The default is `pyproject.toml`, which gets a `[tool.guardline]` table appended; without one the file is `guardline.toml`.
2. Mode. `block` (the default) or `report`, each explained in one line.
3. Families. A comma separated list of `attribution`, `env-dump` and `token`, or `all` (the default). When every family is chosen the `families` key is left out, so a family added in a later release is not excluded by accident.
4. Setup snippets. `claude-code`, `pre-commit`, `both` or `none` (the default).

Then it prints a unified diff of the change and asks `Write this? [y/N]`. Answering anything but `y` or `yes` writes nothing and exits 1.

| option | meaning |
| --- | --- |
| `--mode MODE` | `block` or `report`; skips the mode question |
| `--families NAMES` | comma separated families, or `all`; an unknown family is an error |
| `--target FILE` | `guardline.toml` or `pyproject.toml`; a `pyproject.toml` target must already exist and must be valid TOML |
| `--hook NAME` | print a setup snippet after writing: `claude-code` or `pre-commit`; repeatable; `none` prints nothing and cannot be combined with another value |
| `--yes` | accept the default for every question not given by a flag, and skip the confirmation |
| `--force` | replace an existing `guardline.toml`, or an existing `[tool.guardline]` table |

Without `--force`, an existing `guardline.toml` or an existing `[tool.guardline]` table is an error (exit 2) and nothing is written. Two cases are errors even with `--force`: a `pyproject.toml` target while a `guardline.toml` sits in the same directory, because that file takes precedence and would hide the new table, and a `pyproject.toml` whose `guardline` table is defined in a way that cannot be rewritten safely, such as dotted keys under `[tool]`. The new file text is parsed again before it is written, so the file always loads.

The write itself is careful. A target that is a symbolic link, even a dangling one, is an error (exit 2) and nothing is written, with or without `--force`. A new file is created exclusively and without following a link, so a file or link that appears while the confirmation is open makes the write fail instead of replacing it. An existing file is read again just before the write and compared with the text the diff was built from; if it changed, nothing is written. The replacement goes through a temporary file in the same directory and keeps the original file's permissions.

The `claude-code` snippet is the `PreToolUse` settings entry for `guardline hook --config ABSOLUTE_PATH`. The hook never searches for configuration, so the snippet names the file you just wrote. The path of the `guardline` command is the one that is running, or the one found on `PATH`; when neither is found the snippet uses the bare name and says so. The `pre-commit` snippet adds `args: [--mode, report, --]` to both hooks when the mode is `report`, because the hook entries pass `--mode block` themselves and the last `--mode` wins. The trailing `--` is kept because `args` replaces the hook's own `args`, which is `--`.

## guardline-config-show

```text
guardline config [common options] show [--format text|json]
```

Prints the effective configuration, after the common options are applied: the file the settings came from (or `none (built-in defaults)`, or `none (--no-config)`), the mode and where it came from (`config file`, `--mode` or `default`), the families that have at least one active rule, the disabled rule ids, extra rule files, exclude globs and the number of active rules. A family named in the configuration or by `--family` that matches no active rule is an error (exit 2) here and in every other command, because a misspelled family would otherwise turn every rule off. `--format json` prints the same facts as one document with the keys `source`, `mode`, `mode_source`, `families`, `disabled_rules`, `rule_files`, `exclude` and `active_rules`.

`config show` describes what `scan` and `diff` use. The agent hook reads only the file named by its own `--config` option, so check it with `guardline config --config PATH show`.

## version

```text
guardline --version
```

Prints `guardline` and the package version.
