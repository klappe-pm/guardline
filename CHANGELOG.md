# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- Package scaffold: `pyproject.toml` with the hatchling build backend and the `guardline` console script.
- A rule engine where every rule is data: versioned TOML rule files shipped as package data and read through `importlib.resources`, each rule carrying an id, a family, a description, a pattern, a fire example and a look-alike example that must not fire.
- 43 built-in rules in three families: agent attribution (9), environment dumps (14) and token-shaped values (20).
- A shell command splitter that looks through pipes, substitutions, heredocs, here-strings and wrappers such as `bash -c`, `sudo`, `ssh`, `env VAR=val`, `xargs`, `find -exec`, `docker exec` and `kubectl exec`.
- `guardline hook`, which judges a Claude Code `PreToolUse` payload and answers with a JSON decision or an exit code, and fails closed.
- `guardline scan` for files, directories and standard input, with `--shell` and `--commit-msg`, and `guardline diff` for the lines a git diff adds.
- `guardline rules list` and `guardline rules check`, which validates a rule file and runs its examples.
- Configuration through `guardline.toml` or `[tool.guardline]`: disable rules by id, add rule files, restrict families, exclude paths and set size limits. Report and block modes.
- `.pre-commit-hooks.yaml` with a `guardline` hook and a `guardline-commit-msg` hook.
- An explicit `--allow-fenced-attribution` switch for quoting a third party's attribution inside a closed fenced code block. It has no configuration key.
- Findings that carry the rule id and a position and never the matched value, with tests proving it across the API, the hook and the command line.
- Input size limits, a token budget for the shell splitter, and linear patterns, with a rule loader check for nested quantifiers and tests that feed large adversarial input. Input over a limit and a command too complex to split are reported as findings, never skipped.
- A hook and a command line that do not fail open: invalid bytes on standard input, a crash and a bad configuration all block in block mode, and an unexpected error in a scan exits 2 without printing the input.
- Repository documents: `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md` and `CODE_OF_CONDUCT.md`, with issue and pull request templates under `.github/`.
- Documentation in one tree under `docs/`, arranged by Diátaxis quadrant, with a `README.md` per folder listing its pages. The pages for contributors sit beside the pages for users: `docs/tutorials/first-contribution.md`, `docs/how-to-guides/run-the-tests.md`, `docs/how-to-guides/cut-a-release.md`, `docs/reference/source-layout.md` and `docs/explanation/architecture.md`.
- A shell lexer that decodes quoting the way a shell does (`$'...'` with hex, octal and unicode escapes, `$"..."`, backslash-newline, comments), a table of wrappers with their long options, and function bodies and `source /dev/stdin` as commands to inspect.
- `guardline hook` reads configuration only from an explicit `--config`, refuses empty input in block mode, denies edits to Guardline configuration files unless `--allow-config-edit`, judges every string of a tool input at any depth, and never puts rule file keys in a deny reason.
- Attribution found in `--message=` and `--body=` values, in decoded `$'...'` text, and in text fed to a publishing command by an echo, a printf or a here-string.
- Rule loader checks for adjacent overlapping repeats, more than 3 unbounded repeats, alternation inside a wide repeat and backreferences; `rule_files` confined to the configuration directory.
- Token rules for Hugging Face, Slack app level and SendGrid keys, ABIA ids, PGP private key blocks, quoted assignment names and longer JWTs; token rules also run over the decoded shell words.
- Directory scans read binary files, enter every directory but `.git`, and report skipped links as findings; `git diff` is run with `--text`.
- `guardline init`, an interactive setup that asks for the mode (`block` by default, or `report`), the rule families, the file to write (`guardline.toml` or a `[tool.guardline]` table) and the setup snippets to print. Every answer has a flag (`--mode`, `--families`, `--target`, `--hook`), `--yes` accepts the defaults, it shows a diff and asks before writing, and it refuses to replace existing configuration without `--force`.
- The Claude Code snippet printed by `guardline init` names the written file with an absolute `--config`, because the hook ignores discovered configuration. The pre-commit snippet sets `args: [--mode, report, --]` for report mode, because the hook entries pass `--mode block` themselves.
- `guardline config show`, which prints the effective configuration: the source file, the mode and where it came from, the enabled families and the disabled rule ids. `--format json` prints the same facts as a document.
- A family in the configuration or in `--family` that matches no active rule is a configuration error, so a misspelled family can no longer leave block mode with zero rules.
- Documentation for both commands: a step in the getting started tutorial, a how-to guide on choosing block or report mode, and entries in the cli and python api references.
- A documented list of open gaps in `docs/explanation/security-model.md`, each pinned by a test.
- `guardline scan --no-stdin`, which treats `-` as a file name and never reads standard input.

### Security

- A staged file named like an option (`--mode=report`, `--help`, `--family=env-dump`) or named `-` can no longer change a pre-commit scan or turn it into a read of standard input: the hook entries end their options with `--` and pass `--no-stdin`, the `guardline init` report mode snippet is `args: [--mode, report, --]`, and every parser refuses abbreviated option names.
- `guardline init` no longer writes through a symbolic link: it refuses a link as its target, creates a new file exclusively and without following links, and replaces an existing file through a temporary file after checking that it has not changed since the diff was shown.
- `guardline diff` runs `git diff` with `--no-textconv`, so a `textconv` driver in the repository's attributes can no longer rewrite the added lines and hide a match, and it decodes git's output as UTF-8 with replacement, so one Latin-1 byte no longer crashes the command.
- Configuration and rule files are read only if they are regular files of at most 1 MiB, opened without blocking, so a FIFO can no longer hang the hook. Bytes that are not UTF-8 and deeply nested TOML are now a `ConfigError` or `RuleError` instead of an unexpected exception.
- A configuration that leaves no active rule is an error: an empty `families` list is refused when the file is read, and `build_scanner` refuses a rule set that is empty after `disable`. The hook denies in block mode instead of allowing every call.
- The hook denies edits to the rule files that its `--config` file names in `rule_files`, as it already did for the config file and `--rules` files, so an agent cannot rewrite a rule that guards it.
- The file hook uses `types: [file]` instead of `types: [text]`, so a file that pre-commit tags as binary, such as one with a NUL byte or a `.pdf` name, is still scanned.
