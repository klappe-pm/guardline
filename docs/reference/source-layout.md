# Source Layout

This page maps the repository: each module of the `guardline` package and each test file, with the one job it has. Use it to find where a change belongs. For how the modules work together see [architecture](../explanation/architecture.md).

## Package

| path | job |
| --- | --- |
| `guardline/__init__.py` | public names and `__version__` |
| `guardline/__main__.py` | `python -m guardline` |
| `guardline/model.py` | `Rule` and `Finding`, the scopes and family names |
| `guardline/errors.py` | `GuardlineError`, `RuleError`, `ConfigError` |
| `guardline/rules.py` | parse, validate and verify rule files; the nested quantifier check; the built-in rule loader |
| `guardline/shell.py` | the shell command splitter and its wrapper handling |
| `guardline/engine.py` | `Scanner`: text, command and payload scanning, fenced code, limits |
| `guardline/fileio.py` | read a small configuration or rule file: regular files only, opened without blocking, capped at 1 MiB |
| `guardline/config.py` | find and validate configuration, assemble the rule set and the scanner |
| `guardline/hook.py` | the agent runtime hook: payload in, decision out, fail closed |
| `guardline/diffscan.py` | run `git diff` and scan the added lines |
| `guardline/initcmd.py` | `guardline init`: the questions, the config text, the diff and the setup snippets |
| `guardline/cli.py` | the `guardline` command, including `config show` |
| `guardline/py.typed` | marks the package as typed |
| `guardline/data/rules/` | the built-in rule files, see [package data](package-data.md) |

## Repository Files

| path | job |
| --- | --- |
| `.pre-commit-hooks.yaml` | the hook ids other repositories consume |
| `pyproject.toml` | build, dependencies, console script, pytest, ruff and mypy configuration |
| `docs/` | the documentation, in one tree arranged by Diátaxis quadrant |
| `tests/` | the test suite |

## Tests

| path | job |
| --- | --- |
| `tests/samples.py` | synthetic values assembled from fragments |
| `tests/helpers.py` | `assert_absent` and small helpers |
| `tests/test_rules.py` | the rule contract and the loader |
| `tests/test_engine.py` | scanner behavior |
| `tests/test_shell.py` | the shell splitter |
| `tests/test_hook.py` | the hook |
| `tests/test_cli.py` | the command line |
| `tests/test_config.py` | configuration |
| `tests/test_init.py` | `guardline init` and `guardline config show` |
| `tests/test_diff.py` | the diff scan |
| `tests/test_consistency.py` | one verdict from every entry point |
| `tests/test_security.py` | leaks, timing, fail closed, known bypasses |
| `tests/test_docs.py` | documentation conventions |
