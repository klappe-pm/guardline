# run-the-tests

This guide lists every check a change must pass and how to run it. The suite reads fixtures only, never the live home directory, a real network or a real git remote, and the default run passes on Linux. Run all of it before opening a pull request.

## the-suite

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests
```

The adversarial timing tests in `tests/test_security.py` feed large inputs and take several seconds. To skip them while iterating:

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests --deselect /path/to/guardline/tests/test_security.py
```

## coverage

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests --cov=guardline --cov-report=term-missing
```

The target is at least 90 percent line coverage of the package. Report the real number in the pull request.

## lint-and-format

```bash
/path/to/guardline/.venv/bin/ruff check /path/to/guardline
```

```bash
/path/to/guardline/.venv/bin/ruff format --check /path/to/guardline
```

## types

```bash
/path/to/guardline/.venv/bin/mypy --config-file /path/to/guardline/pyproject.toml /path/to/guardline/guardline
```

The configuration runs `mypy --strict` on the `guardline` package.

## what-each-test-file-covers

- `test_rules.py`: every rule has both examples, fires on one and not on the other, passes the nested quantifier check; the loader's validation errors; the family counts.
- `test_engine.py`: attribution, token and command behavior, the fenced code switch, limits, payloads.
- `test_shell.py`: the shell splitter.
- `test_hook.py`: the hook's decisions and its failure handling.
- `test_cli.py`: the command line, its exit statuses and its output formats.
- `test_config.py`: configuration discovery, validation and rule assembly.
- `test_diff.py`: scanning added lines, against a throwaway local git repository.
- `test_consistency.py`: the same input gets the same verdict from the API, the hook, the file scan, the diff scan and the pre-commit entries.
- `test_security.py`: no value in any output, bounded work on adversarial input, fail closed, and the pinned list of known bypasses.
- `test_docs.py`: the documentation rules in the [documentation guide](../../docs/documentation-guide/README.md).

## values-in-tests

Test values are synthetic and assembled from fragments in `tests/samples.py`, so no test file holds a complete credential or a complete attribution line. A test that checks a value does not leak uses `assert_absent` from `tests/helpers.py`, which fails without printing the value. A plain `assert secret not in output` would print both operands on failure.
