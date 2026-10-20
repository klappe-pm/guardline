# Run the Tests

This guide lists every check a change must pass and how to run it. The suite reads fixtures only, never the live home directory, a real network or a real git remote, and the default run passes on Linux. Run all of it before opening a pull request.

## The Suite

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests
```

The adversarial timing tests in `tests/test_security.py` feed large inputs and take several seconds. To skip them while iterating:

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests --deselect /path/to/guardline/tests/test_security.py
```

## Coverage

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests --cov=guardline --cov-report=term-missing
```

The target is at least 90 percent line coverage of the package. Report the real number in the pull request.

## Lint and Format

```bash
/path/to/guardline/.venv/bin/ruff check /path/to/guardline
```

```bash
/path/to/guardline/.venv/bin/ruff format --check /path/to/guardline
```

## Types

```bash
/path/to/guardline/.venv/bin/mypy --config-file /path/to/guardline/pyproject.toml /path/to/guardline/guardline
```

The configuration runs `mypy --strict` on the `guardline` package.

## What Each Test File Covers

- `test_rules.py`: every rule has both examples, fires on one and not on the other, passes the nested quantifier check; the loader's validation errors; the family counts.
- `test_engine.py`: attribution, token and command behavior, the fenced code switch, limits, payloads.
- `test_shell.py`: the shell splitter.
- `test_hook.py`: the hook's decisions and its failure handling.
- `test_cli.py`: the command line, its exit statuses and its output formats.
- `test_config.py`: configuration discovery, validation and rule assembly.
- `test_init.py`: `guardline init` for every mode and family combination, the interactive questions, refusing to overwrite, the printed snippets, and `guardline config show`.
- `test_diff.py`: scanning added lines, against a throwaway local git repository.
- `test_consistency.py`: the same input gets the same verdict from the API, the hook, the file scan, the diff scan and the pre-commit entries.
- `test_security.py`: no value in any output, bounded work on adversarial input, fail closed, and the pinned list of known bypasses.
- `test_docs.py`: the documentation rules: Title Case headings, one line per paragraph, no dash punctuation, working links, a listing of every page, and the required repository files.

## Values in Tests

Test values are synthetic and assembled from fragments in `tests/samples.py`, so no test file holds a complete credential or a complete attribution line. A test that checks a value does not leak uses `assert_absent` from `tests/helpers.py`, which fails without printing the value. A plain `assert secret not in output` would print both operands on failure.
