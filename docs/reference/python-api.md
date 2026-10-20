# Python API

This page lists every public name of the `guardline` package. The same rules and the same engine sit behind the command line, so a program that calls these functions gets the same verdicts. All functions are synchronous and have no side effects beyond reading the files they are told to read.

## Package

The package exports `Scanner`, `scan_text`, `scan_command`, `scan_payload`, `Finding`, `Rule`, `builtin_rules`, `load_rule_file`, `verify_rule_examples`, `GuardlineError`, `RuleError`, `ConfigError` and `__version__`.

### Scan Text

`scan_text(text, **options) -> list[Finding]` scans authored text with the built-in rules. Options are the keyword arguments of `Scanner`.

### Scan Command

`scan_command(command, **options) -> list[Finding]` scans a shell command string with the built-in rules.

### Scan Payload

`scan_payload(payload, **options) -> list[Finding]` scans a `PreToolUse` style payload (a mapping with `tool_input`).

### Scanner

`Scanner(rules=None, *, allow_fenced_attribution=False, max_text_chars=1048576, max_command_chars=65536, families=None, allow_config_edit=False, protected_paths=())` applies a set of rules.

- `rules`: a sequence of `Rule`. Default: the built-in rules.
- `allow_fenced_attribution`: drop attribution findings inside a closed fenced code block.
- `max_text_chars`, `max_command_chars`: size limits. Over the limit, a scan returns one `guardline-input-too-large` finding.
- `families`: run only rules of these families.
- `allow_config_edit`: when False, `scan_payload` reports a Write, Edit or MultiEdit to a Guardline configuration file.
- `protected_paths`: extra files `scan_payload` protects the same way, such as the hook's own `--config` and rule files.

Attributes: `rules` (the active rules), `max_text_chars`, `max_command_chars` and `allow_fenced_attribution`.

Methods:

- `scan_text(text, source="<text>", *, include_attribution=True) -> list[Finding]`: text rules only; NUL characters are removed first.
- `scan_command(command, source="<command>") -> list[Finding]`: command rules per simple command, non-attribution text rules over the whole command, attribution rules over the text a publishing command carries.
- `scan_payload(payload) -> list[Finding]`: see [hook protocol](hook-protocol.md).
- `oversize_finding(source) -> Finding`: the finding that stands for an input too large to scan.
- `skipped_finding(source) -> Finding`: the finding that stands for a file a directory scan did not read.

Findings are ordered by source and position, deduplicated by rule and position, and capped at 1000; past the cap a final `guardline-findings-truncated` finding is added.

### Finding

A frozen dataclass: `rule_id`, `family`, `description`, `source`, `offset`, `line`, `column`. `line` and `column` are one based. It has no field for the matched text. `to_dict()` returns a JSON ready mapping and `format_text()` returns `source:line:column: rule [family] description`.

### Rule

A frozen dataclass with the fields described in [rule file format](rule-file-format.md): `id`, `family`, `description`, `pattern`, `scope`, `programs`, `value_options`, `unless`, `ignore_case`, `example_fires`, `example_clean`, `origin`, and the compiled `regex` and `unless_regex`.

### Builtin Rules

`builtin_rules() -> tuple[Rule, ...]` returns every rule shipped in the package, read through `importlib.resources` and cached.

### Load Rule File

`load_rule_file(path) -> tuple[Rule, ...]` loads and validates a rule file. Raises `RuleError`.

### Verify Rule Examples

`verify_rule_examples(rule, ruleset=None) -> list[str]` returns a list of problems, empty when the rule fires on its fire example and not on its look-alike. Problems never quote an example.

### Errors

`GuardlineError` is the base class. `RuleError` is raised for an invalid rule file and `ConfigError` for an invalid configuration. Messages never contain matched text.

## Engine Module

- `fenced_ranges(text) -> list[tuple[int, int]]`: character ranges inside closed fenced code blocks.
- `strip_value_options(args, value_options) -> list[str]`: drops the word after each value taking option.
- `is_authoring_command(command) -> bool`: True for a command that publishes a message.
- `DEFAULT_MAX_TEXT_CHARS`, `DEFAULT_MAX_COMMAND_CHARS`, `MAX_FINDINGS`, `TOO_LARGE_RULE`, `TRUNCATED_RULE`, `TOO_COMPLEX_RULE`, `CONFIG_EDIT_RULE`, `FILE_SKIPPED_RULE`: the limits and engine rule ids.

## Shell Module

- `parse_shell(command) -> ShellParse`: splits a command into `SimpleCommand` items (`program`, `args`, `words`, `offset`, `depth`, `stdin`), data heredoc bodies as `(offset, text)`, and a `fallback` flag set when quotes were unbalanced and a lenient split was used, and an `exhausted` flag set when the token budget, the nesting depth or the command count ran out.

## Rules Module

- `parse_rules(text, origin) -> tuple[Rule, ...]`: parse rule file text.
- `merge_rules(base, extra) -> tuple[Rule, ...]`: combine rule sets; raises `RuleError` on a reused id.
- `unsafe_pattern_reason(pattern) -> str | None` and `has_nested_quantifier(pattern) -> bool`: the loader's regular expression denial of service audit.

## Config Module

- `Config`: a frozen dataclass of the resolved keys.
- `load_config_file(path)`, `discover_config(start)`, `config_from_table(table, origin)`: read configuration; raise `ConfigError`.
- `build_ruleset(config, extra_rule_files=(), extra_disable=())` and `build_scanner(config, *, extra_rule_files=(), extra_disable=(), families=None, allow_fenced_attribution=False, allow_config_edit=False, protected_paths=())`: assemble the active rules and a `Scanner`.

## Initcmd Module

The code behind `guardline init`. It reads and writes the files you name and prints to the stream it is given.

- `known_families() -> tuple[str, ...]`: the family names of the built-in rules, sorted.
- `parse_families(text) -> tuple[str, ...]`: parse a comma separated list or `all` into canonical order; raises `ConfigError` for an empty list or an unknown family.
- `parse_hooks(values) -> tuple[str, ...]`: normalise snippet choices, dropping `none`; raises `ConfigError` when `none` is mixed with another choice.
- `render_body(mode, families) -> str` and `expected_table(mode, families) -> dict`: the TOML text written for a choice, and the table the loader reads back from it.
- `inspect_target(directory, target, *, force) -> (Path, str | None)`: check a target can be written and return its current text; raises `ConfigError`.
- `compose(path, old, mode, families, target) -> Plan`: build the new file text, and check it parses to the expected table; raises `ConfigError`. `Plan` has `path`, `old`, `new` and `diff()`.
- `guardline_executable() -> (str, bool)` and `hook_command(config_path) -> (str, bool)`: the command path and the hook command line; the boolean says whether an absolute path was found.
- `claude_code_snippet(command) -> str` and `pre_commit_snippet(mode) -> str`: the snippets.
- `run_init(args, out, cwd=None) -> int`: run the command.

## Hook Module

- `run_hook(stdin_text, scanner, *, mode="block", deny_with="json") -> HookResult`: judge one payload. `HookResult` has `exit_code`, `stdout` and `stderr`.
- `deny_reason(findings)` and `startup_failure(message, mode, deny_with="json")`: build the reason text and the result for a hook that could not start.

## Diffscan Module

- `git_diff(repo, *, staged=False, base=None, paths=())`, `parse_added_lines(diff_text)` and `scan_added(scanner, added)`: scan the lines a diff adds.
