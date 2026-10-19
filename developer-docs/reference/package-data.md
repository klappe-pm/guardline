# package-data

This page describes the data files that ship inside the package and how the code reads them. The rule files are the package's only data. They are read through `importlib.resources`, never through a path built from `__file__`, so they load from a wheel, a zip import or an editable install alike.

## files

| file | family | rules |
| --- | --- | --- |
| `guardline/data/rules/attribution.toml` | attribution | 9 |
| `guardline/data/rules/env-dump.toml` | env-dump | 14 |
| `guardline/data/rules/token.toml` | token | 20 |

The format is described in the [rule file format](../../docs/reference/rule-file-format.md).

## how-they-are-read

`builtin_rules()` in `guardline/rules.py` lists `guardline/data/rules` with `importlib.resources.files("guardline").joinpath("data", "rules")`, sorts the entries by file name, parses each `.toml` file and returns the rules as a tuple. The result is cached for the life of the process. A file that fails validation raises `RuleError` at first use, which is why `tests/test_rules.py` loads every file.

## how-they-are-built-into-the-wheel

`pyproject.toml` lists `artifacts = ["guardline/data/**"]` for both the wheel and the sdist, so hatchling includes the non-Python files. A new data directory needs the same pattern to be covered. After changing it, build a wheel and list its contents to confirm the files are present.

## no-network-no-home

The package reads nothing else: no file under the home directory, no network, no environment variable. Configuration and extra rule files are read only from paths the caller names or from the directory walk described in [configuration](../../docs/reference/configuration.md).
