# disable-a-rule

This guide turns rules off, in one run or for a whole project. A rule is disabled by its id, which `guardline rules list` prints. An id that names no rule is an error, so a typo can never leave a rule silently on.

## for-one-run

```bash
guardline scan --disable token-hex-run-near-keyword /path/to/file.txt
```

The option is repeatable.

## for-a-project-with-guardline-toml

Create `guardline.toml` at the repository root:

```toml
disable = ["token-hex-run-near-keyword", "attribution-robot-byline"]
```

## for-a-project-with-pyproject-toml

```toml
[tool.guardline]
disable = ["token-hex-run-near-keyword"]
```

The nearest `guardline.toml` or `pyproject.toml` with a `[tool.guardline]` table, walking up from the current directory, wins. `guardline.toml` wins over `pyproject.toml` in the same directory. The walk stops at the first directory that holds a `.git` entry.

## a-whole-family

List the families that should run and the rest are off:

```toml
families = ["token"]
```

## a-path

The file scan skips paths that match a glob. A pattern is matched against the whole path and against the file name:

```toml
exclude = ["*.lock", "tests/fixtures/*"]
```

## why-there-is-no-way-to-allow-quoting-in-the-config

Quoting a third party's attribution inside a fenced code block is a per run switch, `--allow-fenced-attribution`, and has no configuration key, so a committed file cannot quietly turn the exception on for everyone. See [quote third party attribution](quote-third-party-attribution.md).
