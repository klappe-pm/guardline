# Disable a Rule

This guide turns rules off, in one run or for a whole project. A rule is disabled by its id, which `guardline rules list` prints. An id that names no rule is an error, so a typo can never leave a rule silently on.

## For One Run

```bash
guardline scan --disable token-hex-run-near-keyword /path/to/file.txt
```

The option is repeatable.

## For a Project with `guardline.toml`

Create `guardline.toml` at the repository root:

```toml
disable = ["token-hex-run-near-keyword", "attribution-robot-byline"]
```

## For a Project with `pyproject.toml`

```toml
[tool.guardline]
disable = ["token-hex-run-near-keyword"]
```

The nearest `guardline.toml` or `pyproject.toml` with a `[tool.guardline]` table, walking up from the current directory, wins. `guardline.toml` wins over `pyproject.toml` in the same directory. The walk stops at the first directory that holds a `.git` entry.

## A Whole Family

List the families that should run and the rest are off:

```toml
families = ["token"]
```

## A Path

The file scan skips paths that match a glob. A pattern is matched against the whole path and against the file name:

```toml
exclude = ["*.lock", "tests/fixtures/*"]
```

## Why There Is No Way to Allow Quoting in the Config

Quoting a third party's attribution inside a fenced code block is a per run switch, `--allow-fenced-attribution`, and has no configuration key, so a committed file cannot quietly turn the exception on for everyone. See [quote third party attribution](quote-third-party-attribution.md).
