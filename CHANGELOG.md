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
- A banner, `.github/guardline-banner.svg`, made by `scripts/make-banner.py`, and a README that follows the Stratarc skeleton with absolute links.
- A release workflow with separate build, test and publish jobs. It publishes to PyPI through trusted publishing in an approval gated `pypi` environment, installs only hash pinned tools from `requirements/`, checks that the tag matches the version and that the tagged commit is on `main`, tests the wheel it built, and writes checksums to the job summary. [Cut a Release](docs/how-to-guides/cut-a-release.md) describes the one-time PyPI and GitHub setup.
- Package metadata for PyPI: keywords, classifiers, project URLs, `Typing :: Typed`, a bounded `hatchling` requirement, and an sdist whose include patterns are anchored.
- Tests for the documentation, the published tree, the release workflow and the lock files. Tests that need repository only files carry the `repo_only` marker and skip themselves in the source distribution.

### Changed

- The optional dependencies are `test` (`pytest>=9.0.3`, `pytest-cov>=7`) and `lint` (`ruff`, `mypy`). Install both with `pip install -e '.[test,lint]'`.
- Ruff checks the `S` and `RUF` rule sets as well.
- The configuration reference says that dictionary keys of a tool input count toward the `max_text_chars` bound of the hook, as the security model already did.

### Fixed

- `token-generic-assignment` detects typed literal assignments and retains findings for ambiguous type annotations. Quoted and unquoted dotted password and secret assignments remain findings. Vendor token rules are unchanged. Regression tests cover credential controls and ambiguous public metadata.

### Security

- An escaped or quoted `;`, `|`, `&`, `<`, `>` or parenthesis is now a word, not an operator, as in a shell. `find . -exec echo a \; -exec printenv \;` used to end the command at the `\;` and miss the second `-exec`; `echo a \; printenv` is now one `echo` command with a literal `;` argument. This closes the known gap listed for a second `find -exec`.
- A `<<` inside `${...}` or `$[...]` no longer opens a heredoc. `echo ${x:-a<<b}`, `echo ${x#<<}` and `echo $[1<<2]` blanked the lines that followed, so a `printenv` on the next line passed unjudged. A line that holds `${` or `$[` now opens no heredoc, as one that holds `((` already did, and a real heredoc on another line still stays data.
- A heredoc body is judged as commands when a shell reads it from another line. `bash \` followed by `<<EOF` on the next line, and `cat <<EOF |` followed by a body and then `bash`, passed a `printenv` in the body as data. A backslash-newline is joined before the heredoc line is read, and a heredoc line that ends in `|` or `|&` keeps its body as commands when the first command after the body is a shell. A heredoc that no shell reads stays data.
- Dictionary keys of a tool input have a limit of their own, 2000, and no longer count toward the 2000 string limit. Counting them there cut the largest `MultiEdit` that is not reported as too complex from 999 edits to 399. A `MultiEdit` of 999 edits is judged again, and 2001 keys are still reported as too complex.
- `guardline diff` passes `--src-prefix=a/ --dst-prefix=b/` to `git diff`, so a global `diff.mnemonicPrefix=true` can no longer change the reported path (`i/settings.py` instead of `settings.py`).
- The rule loader audit keeps the overlap across one character, or one fixed repeat, between two wide repeats. `a*aa*;`, `a*a{2}a*;`, `a*a{1,3}a*;` and `\w+_\w+;` were accepted, and `\w+_\w+;` took 104 s on 4000 characters; they are rejected now, and `a*;a*;` is still accepted. Five built-in rules had the same shape around the flag letter they look for (`declare -p`, `ps -E`, `ps e`, `security ... -w` and `security dump-keychain -d`) and took about ten seconds on a 30000 character run of that letter; they now assert the letter in a lookahead and run in about 30 ms. A run of two or more characters between the repeats (`a*aaa*;`) is listed under known gaps.
- The rule loader audit catches the shapes that used to pass: overlaps hidden by case folding (`a*A*`), by an optional item between repeats (`\w*-?\w*`) or by non ASCII characters (`.*é*`), nested repeats inside atomic groups, bounds over 1024 (now counted as unbounded), and a variable length repeat inside a repeat that can repeat (`(?:a{1,2}){0,16}`, `(?:a+){0,4}`). `unsafe_pattern_reason` takes the rule's flags. All built-in rules still load.
- `guardline rules check` warns, without failing, about a custom pattern or `unless` expression that holds an unbounded repeat. A single unbounded repeat is still accepted and is listed under known gaps.
- One text value made of repeated quoted co-author or assisted-by trailer openings at the 1 MiB limit no longer takes about two seconds to scan. The two trailer rules now stop their name part at a quote or backtick and allow one closing quote before the agent name, and the footer rule's leading punctuation is possessive. A trailer whose name part contains a quote, such as `Dana's` followed by an agent name, is no longer matched; this is listed as a known gap.
- A tool input is bounded as a whole. Six values just under the text limit each took their full scan time; now all string values of one tool input together are limited to `max_text_chars` and all command values together to `max_command_chars`, and the findings collected across values are capped at the usual 1000.
- The hook command reads at most four times `max_text_chars` bytes from standard input, and `run_hook` refuses a longer payload before parsing it, so 8 MiB of input is a quick deny instead of a long parse.
- The hook's deny reason now says which limit was hit (for example "longer than 65536 characters"), names a payload that nests too deeply for the JSON parser, and reads the payload in its own try block that catches any exception, so a parser failure still blocks the call.
- A command with thousands of `find -exec` words no longer takes quadratic time and memory in the shell splitter. A 64 KiB command took 23 s and 646 MB; each `-exec` body is now collected once.
- A command that starts with thousands of `{` or `!` words is split in linear time. The leading keyword strip copied the word list once per keyword.
- A staged file named like an option (`--mode=report`, `--help`, `--family=env-dump`) or named `-` can no longer change a pre-commit scan or turn it into a read of standard input: the hook entries end their options with `--` and pass `--no-stdin`, the `guardline init` report mode snippet is `args: [--mode, report, --]`, and every parser refuses abbreviated option names.
- `guardline init` no longer writes through a symbolic link: it refuses a link as its target, creates a new file exclusively and without following links, and replaces an existing file through a temporary file after checking that it has not changed since the diff was shown.
- `guardline diff` runs `git diff` with `--no-textconv`, so a `textconv` driver in the repository's attributes can no longer rewrite the added lines and hide a match, and it decodes git's output as UTF-8 with replacement, so one Latin-1 byte no longer crashes the command.
- Configuration and rule files are read only if they are regular files of at most 1 MiB, opened without blocking, so a FIFO can no longer hang the hook. Bytes that are not UTF-8 and deeply nested TOML are now a `ConfigError` or `RuleError` instead of an unexpected exception.
- A configuration that leaves no active rule is an error: an empty `families` list is refused when the file is read, and `build_scanner` refuses a rule set that is empty after `disable`. The hook denies in block mode instead of allowing every call.
- The hook denies edits to the rule files that its `--config` file names in `rule_files`, as it already did for the config file and `--rules` files, so an agent cannot rewrite a rule that guards it.
- The file hook uses `types: [file]` instead of `types: [text]`, so a file that pre-commit tags as binary, such as one with a NUL byte or a `.pdf` name, is still scanned.
- A quoted or escaped heredoc operator (`cat '<<' EOF`, `"<<"`, `$'<<'`) is a word, so the lines after it are read as commands, as bash runs them. It used to open a heredoc that blanked the next lines and hid `printenv` from the scan. Only an unquoted `<<` opens a heredoc. No built-in rule changed.
- The rule loader audit keeps the overlap between two wide repeats across a group or an alternation between them. `(a*)a*;`, `a*(a*);`, `(?i:a*)a*;`, `a*(?:x|a*);` and `\w+(-?)\w+;` were accepted and ran in super linear time; they are rejected now. A scoped case flag such as `(?i:...)` is read inside its group. All built-in rules still load and match as before.
- The rule loader audit rejects an alternation inside a small repeat when two branches can start with the same character or both can be empty. `(?:a|a){0,16};` and `(?:aa|a){0,16};` were accepted with no warning and allow exponentially many ways to match. All built-in rules still load and match as before.
- `guardline diff` passes `--no-relative` to `git diff`, so a global `diff.relative=true` no longer hides a staged file that sits outside the directory the command runs in.
- `guardline scan` without `--shell`, `--commit-msg` included, and `guardline diff` stop with exit 2 when no active rule judges text. `families = ["env-dump"]` used to leave the pre-commit file hooks with nothing to run, so they exited 0 on every file. `guardline init` warns when the chosen families have no text rule and the pre-commit snippet is chosen.
- The hook checks the payload length before it checks for an empty payload, so a payload of whitespace over the limit is denied as "longer than" the limit and not as empty.
- `max_text_chars` is capped at 16 MiB (16777216) and `max_command_chars` at 1 MiB (1048576). A larger value is a `ConfigError`; `max_text_chars = 100000000000` used to end a scan with an internal error or an attempt to allocate that much.
- The pre-commit snippet from `guardline init` and the two how-to guides pin `rev: v0.1.0`, the release tag, instead of the moving `main` branch. A test requires every `rev:` in the documents to be a release tag or a commit hash.
- A tool input with exactly 2001 strings is now reported as too complex, as the documents promise for more than 2000. The leaf check ran before a string was added, so one string too many was judged without the finding.
- `guardline init --force` over a `guardline.toml` that is not UTF-8 text stops with a configuration error and exit 2, and leaves the file alone. It used to end with an internal error.
- A token placed in a dictionary key of a tool input is now judged. Keys are scanned as text with the attribution family left out, are labelled `<key>` in sources so the key name is never echoed, and count toward a limit of 2000 keys and the `max_text_chars` bound.
- The known gaps in the security model list the repeat shapes the rule audit still does not compare: a repeat of a capture group or of more than one character, and a zero width assertion between two repeats. Each is pinned by a test.
