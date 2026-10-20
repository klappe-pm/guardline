# Run the Tests

This guide lists every check a change must pass and how to run it. It assumes the development install from [First Contribution](../tutorials/first-contribution.md), and its commands use `/path/to/guardline` for your clone, which is also where the virtual environment lives. There is no CI service for changes, so these commands are the gate: a change that passes them all is ready for review. The release workflow runs the suite once more, against the built wheel, before it publishes.

## Test Suite

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests
```

Install the `test` and `lint` extras first: `pip install -e '/path/to/guardline[test,lint]'`. `pytest` and `pytest-cov` are the `test` extra, with `pytest` at 9.0.3 or newer because earlier releases carry CVE-2025-71176, and `ruff` and `mypy` are the `lint` extra.

## Coverage

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests --cov=guardline --cov-report=term-missing
```

The target is at least 90 percent line coverage of the package. The report lists the lines that no test reached. Report the real number in the pull request.

## Lint and Format

```bash
/path/to/guardline/.venv/bin/ruff check /path/to/guardline
```

```bash
/path/to/guardline/.venv/bin/ruff format --check /path/to/guardline
```

The configuration is in `pyproject.toml`: line length 100, target Python 3.11, and the rule sets `E`, `F`, `I`, `UP`, `B`, `SIM`, `W`, `S` and `RUF`. The `S` rules are the security rules, and a `noqa` for one must say why it is safe. To fix formatting, run `ruff format` without `--check`.

## Type Checking

```bash
/path/to/guardline/.venv/bin/mypy --config-file /path/to/guardline/pyproject.toml /path/to/guardline/guardline
```

The configuration runs `mypy --strict` on the `guardline` package. Tests are not type checked.

## Source Distribution

The source distribution leaves out `.github/`, `docs/` and the community files. Tests marked `repo_only` read those files, so they skip themselves when the files are missing, and the tests that ship in the sdist pass when run from an extracted copy. To check that, build the distributions, extract the sdist, install the wheel and run the tests there with the source package out of the way, so that the wheel is what gets imported:

```bash
cd /path/to/guardline && python3 -m build --outdir /path/to/dist
```

```bash
tar -xzf /path/to/dist/guardline-<version>.tar.gz -C /path/to/sdist && python3 -m venv /path/to/venv && /path/to/venv/bin/pip install /path/to/dist/guardline-<version>-py3-none-any.whl pytest && rm -r /path/to/sdist/guardline-<version>/guardline && cd /path/to/sdist/guardline-<version> && /path/to/venv/bin/python -m pytest
```

## Repository Tests

Three modules check the repository around the code.

- `tests/test_docs.py` checks the documentation and the files beside it: Title Case headings in every Markdown file, including the pull request template, one H1 per page, a purpose paragraph under each title, no frontmatter or provenance keys, no agent credit, no home directory in any page, a language tag on every code fence, relative links that resolve, absolute links in the README and its skeleton, one line per paragraph, no dash used as punctuation, no em or en dash in any text file, a final newline, the Keep a Changelog shape of the changelog, lowercase kebab-case filenames, no agent instruction files, the required community files, and a `.github` folder that holds only the templates, the banner and the release workflow.
- `tests/test_no_personal_terms.py` reads every tracked file and rejects the owner's email, private tool names, tracker ticket codes and absolute home paths. To check a private list of further terms, put one term per line in a text file outside the repository and name it in `GUARDLINE_FORBIDDEN_TERMS_FILE`; the test skips when the variable is not set, which is the case on GitHub, so the release guide runs it locally before every release.
- `tests/test_release_workflow.py` checks that every action is pinned to a full commit, that the build, test and publish jobs are separate, that only the publish job can request an identity token, that every `pip install` in the workflow uses hashes or installs the local artifact with `--no-deps`, and that the lock files pin every requirement with hashes. It also checks the packaging metadata.

`test_docs.py` and `test_release_workflow.py` carry the `repo_only` marker.

## The Banner

`.github/guardline-banner.svg` is written by `scripts/make-banner.py`, which needs `fonttools` and the DejaVu Sans Mono font files. `fonttools` is a script-only dependency and is not a dependency of the package. Edit the script, never the SVG:

```bash
cd /path/to/guardline && python3 -m pip install fonttools && python3 scripts/make-banner.py
```

## Adversarial Timing Tests

The adversarial timing tests in `tests/test_security.py` feed large inputs and take several seconds. To skip them while iterating:

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests --deselect /path/to/guardline/tests/test_security.py
```

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
- `test_docs_content.py`: what the pages say about Guardline stays true: the rules reference, the rule counts, the agent names, the TOML blocks, and the output shown in the tutorial.
- `test_self_scan.py`: Guardline finds no credential and no attribution in its own repository.

## Values in Tests

Test values are synthetic and assembled from fragments in `tests/samples.py`, so no test file holds a complete credential or a complete attribution line. A test that checks a value does not leak uses `assert_absent` from `tests/helpers.py`, which fails without printing the value. A plain `assert secret not in output` would print both operands on failure.
