# Configuration

This page lists every configuration key and says how the file is found. Configuration is optional; with none, every built-in rule runs and the mode is `block`. `guardline init` writes a file with the `mode` and `families` keys, and `guardline config show` prints what is active; see the [cli reference](cli.md).

## Where It Lives

Either a `guardline.toml` with the keys at the top level, or a `[tool.guardline]` table in `pyproject.toml`. Guardline starts in the current directory (for `diff`, the `--repo` directory) and walks up. In each directory `guardline.toml` is tried before `pyproject.toml`, and a `pyproject.toml` without a `[tool.guardline]` table is skipped. The walk stops after the first directory that holds a `.git` entry, or at the filesystem root. `--config PATH` names one file and skips the search, and `--no-config` ignores all files. `guardline hook` never searches: it reads a file only when `--config PATH` names one.

## Keys

An unknown key is an error, so a misspelled key cannot silently do nothing.

The file must be a regular file of at most 1 MiB, in UTF-8, and not nested absurdly deep. A FIFO, a device, an oversized file, bytes that are not UTF-8 and a document nested past the parser's recursion limit are all configuration errors, so none of them can hang the hook or surface as an unexpected exception. A symbolic link to a regular file is followed.

| key | type | default | meaning |
| --- | --- | --- | --- |
| `mode` | `"report"` or `"block"` | `"block"` | `report` prints findings and exits 0, `block` exits 1 on a finding. The `--mode` option wins. |
| `disable` | list of strings | `[]` | rule ids to turn off. An id that names no loaded rule is an error, and so is a list that turns off every rule. |
| `rule_files` | list of strings | `[]` | extra rule files; relative paths are resolved against the configuration file's directory and must stay inside it, so a configuration cannot pull in a rule file from elsewhere; a path that leaves the directory is an error. An id that a built-in rule or another file already uses is an error. |
| `families` | list of strings | all | run only rules of these families. The `--family` option wins. An empty list is an error, because it would leave no rule to run. |
| `exclude` | list of strings | `[]` | glob patterns of paths the file scan skips, matched against the whole path and the file name. |
| `max_text_chars` | positive integer | `1048576` | longest text, in characters, that one scan accepts. For the hook it also bounds all string values and all dictionary keys of one tool input together, and four times it bounds the whole payload in bytes. At most `16777216` (16 MiB); a larger value is a configuration error. |
| `max_command_chars` | positive integer | `65536` | longest shell command, in characters, that one scan accepts. For the hook it also bounds all command values of one tool input together. At most `1048576` (1 MiB); a larger value is a configuration error. |

A configuration that leaves no active rule is an error (`the configuration leaves no active rules`), whether it comes from an empty `families` list or from a `disable` list that names every rule. Block mode would otherwise allow everything. A configuration whose active rules include none with scope `text` is an error for `guardline scan` without `--shell` and for `guardline diff` (exit 2), because those commands judge text and would pass every file. This is what the pre-commit hooks run.

Input over a limit is not scanned. It yields one `guardline-input-too-large` finding, so oversize input is reported and never passes silently.

## Not a Key

There is no key for `--allow-fenced-attribution`. The exception for quoting attribution inside a fenced code block is a per run switch on purpose. See [quote third party attribution](../how-to-guides/quote-third-party-attribution.md).

## Example `guardline.toml`

```toml
mode = "block"
disable = ["token-hex-run-near-keyword"]
rule_files = ["rules/team.toml"]
exclude = ["*.lock", "tests/fixtures/*"]
max_text_chars = 2097152
```

## Example `pyproject.toml`

```toml
[tool.guardline]
mode = "report"
disable = ["attribution-robot-byline"]
```
