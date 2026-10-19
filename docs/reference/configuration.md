# configuration

This page lists every configuration key and says how the file is found. Configuration is optional; with none, every built-in rule runs and the mode is `block`.

## where-it-lives

Either a `guardline.toml` with the keys at the top level, or a `[tool.guardline]` table in `pyproject.toml`. guardline starts in the current directory (for `diff`, the `--repo` directory) and walks up. In each directory `guardline.toml` is tried before `pyproject.toml`, and a `pyproject.toml` without a `[tool.guardline]` table is skipped. The walk stops after the first directory that holds a `.git` entry, or at the filesystem root. `--config PATH` names one file and skips the search, and `--no-config` ignores all files. `guardline hook` never searches: it reads a file only when `--config PATH` names one.

## keys

An unknown key is an error, so a misspelled key cannot silently do nothing.

| key | type | default | meaning |
| --- | --- | --- | --- |
| `mode` | `"report"` or `"block"` | `"block"` | `report` prints findings and exits 0, `block` exits 1 on a finding. The `--mode` option wins. |
| `disable` | list of strings | `[]` | rule ids to turn off. An id that names no loaded rule is an error. |
| `rule_files` | list of strings | `[]` | extra rule files; relative paths are resolved against the configuration file's directory and must stay inside it, so a configuration cannot pull in a rule file from elsewhere; a path that leaves the directory is an error. An id that a built-in rule or another file already uses is an error. |
| `families` | list of strings | all | run only rules of these families. The `--family` option wins. |
| `exclude` | list of strings | `[]` | glob patterns of paths the file scan skips, matched against the whole path and the file name. |
| `max_text_chars` | positive integer | `1048576` | longest text, in characters, that one scan accepts. |
| `max_command_chars` | positive integer | `65536` | longest shell command, in characters, that one scan accepts. |

Input over a limit is not scanned. It yields one `guardline-input-too-large` finding, so oversize input is reported and never passes silently.

## not-a-key

There is no key for `--allow-fenced-attribution`. The exception for quoting attribution inside a fenced code block is a per run switch on purpose. See [quote third party attribution](../how-to-guides/quote-third-party-attribution.md).

## example-guardline-toml

```toml
mode = "block"
disable = ["token-hex-run-near-keyword"]
rule_files = ["rules/team.toml"]
exclude = ["*.lock", "tests/fixtures/*"]
max_text_chars = 2097152
```

## example-pyproject-toml

```toml
[tool.guardline]
mode = "report"
disable = ["attribution-robot-byline"]
```
