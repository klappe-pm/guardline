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

Install the `test` and `lint` extras first: `pip install -e '.[test,lint]'`. `pytest` and `pytest-cov` are the test extra, with `pytest` at 9.0.3 or newer because earlier releases carry CVE-2025-71176, and `ruff` and `mypy` are the lint extra.

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
- `test_docs.py`: the documentation and repository hygiene rules: Title Case headings, one H1, no provenance keys or agent credit, no home paths, a language on every fence, working relative links, absolute links in the README and its skeleton, one line per paragraph, no dash punctuation, the required community files, and a `.github` folder that holds only the templates, the banner and the release workflow.
- `test_docs_content.py`: what the pages say about Guardline stays true: the rules reference, the rule counts, the agent names, the TOML blocks, and the output shown in the tutorial.
- `test_self_scan.py`: Guardline finds no credential and no attribution in its own repository.
- `test_no_personal_terms.py`: no tracked file names the owner's email, a private tool, a tracker ticket code or an absolute home path. Set `GUARDLINE_FORBIDDEN_TERMS_FILE` to a text file of further terms, one per line, and any of them in a tracked file fails the test. Keep that file outside the repository.
- `test_release_workflow.py`: the release workflow pins its actions, keeps build, test and publish in separate jobs, installs only hashed requirements, and grants `id-token` to the publish job alone. It also checks the lock files and the packaging metadata.

## The Source Distribution

Tests marked `repo_only` read files that the source distribution leaves out: `.github/`, `docs/` and the community files. They skip themselves when those paths are missing, so the tests that ship in the sdist pass when run from an extracted copy. To check that, build the distributions, extract the sdist, install the wheel and run the tests there:

```bash
cd /path/to/guardline && python3 -m build --outdir /path/to/dist
```

```bash
tar -xzf /path/to/dist/guardline-<version>.tar.gz -C /path/to/sdist && python3 -m venv /path/to/venv && /path/to/venv/bin/pip install /path/to/dist/guardline-<version>-py3-none-any.whl pytest && cd /path/to/sdist/guardline-<version> && /path/to/venv/bin/python -m pytest
```

## Values in Tests

Test values are synthetic and assembled from fragments in `tests/samples.py`, so no test file holds a complete credential or a complete attribution line. A test that checks a value does not leak uses `assert_absent` from `tests/helpers.py`, which fails without printing the value. A plain `assert secret not in output` would print both operands on failure.
