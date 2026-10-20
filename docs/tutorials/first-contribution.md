# First Contribution

This tutorial takes you from a fresh clone to a change that is ready for review. You set up a development environment, run the test suite, make one small change and check it. It follows one path and explains only what that path needs; [Contributing](../../CONTRIBUTING.md) holds the guidelines it applies, and the [how-to guides](../how-to-guides/README.md) cover each step in more depth.

## What You Need

- Python 3.11 or newer.
- `git`, and a GitHub account if you intend to open a pull request.

The commands use `/path/to/guardline` for your clone. Replace it with the real location.

## Clone and Install

```bash
git clone https://github.com/klappe-pm/guardline /path/to/guardline && python3 -m venv /path/to/guardline/.venv && /path/to/guardline/.venv/bin/pip install -e '/path/to/guardline[test,lint]'
```

This installs Guardline as an editable package with the `test` extra (`pytest` and `pytest-cov`) and the `lint` extra (`ruff` and `mypy`). The package itself has no runtime dependencies.

## Run the Tests

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests
```

Everything should pass on Linux. Tests that need `git` are skipped with a reason when it is missing. See [Run the Tests](../how-to-guides/run-the-tests.md) for the other checks.

## Make a Change

Pick something small for a first change: a wording fix in a page under `docs/`, a missing edge case in `tests/`, or a new rule. This tutorial adds a rule, because it shows how the tests follow the data.

Suppose you want a rule for a made up credential format, `acme_` followed by 24 letters or digits. Open `guardline/data/rules/token.toml` and add a table at the end:

```toml
[[rule]]
id = "token-acme-key"
family = "token"
description = "An Acme API key."
ignore_case = false
pattern = '(?<![A-Za-z0-9])acme_[A-Za-z0-9]{24}'
example_fires = "acme_0123456789abcdefghijklmn"
example_clean = "the acme_ prefix marks an Acme key"
```

Notes on this entry: the id starts with the family; the pattern starts at a token boundary and has a bounded repeat, which keeps it linear; the fire example writes the first character as `a` so the file does not hold a string that matches its own rule; and the look-alike is a near miss that a careless pattern would flag.

The rule tests are parametrized over every rule in the package, so no test file changes. Run them:

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests/test_rules.py
```

They fail until you also update the expected family count in `test_family_counts`, because the count is pinned on purpose: adding a rule is a visible decision. Change the expected `token` count and run again. Then break the rule on purpose, for example change `{24}` to `{25}`, and see `test_fire_example_fires_its_rule` fail for `token-acme-key` without echoing the example. Put it back.

## Check It

Update the rule counts where they are written (the README, `docs/reference/rules.md`, the changelog) and add the rule to the table in `docs/reference/rules.md`. Then run the checks:

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests --cov=guardline
```

```bash
/path/to/guardline/.venv/bin/ruff check /path/to/guardline && /path/to/guardline/.venv/bin/ruff format --check /path/to/guardline && /path/to/guardline/.venv/bin/mypy --config-file /path/to/guardline/pyproject.toml /path/to/guardline/guardline
```

## Commit

Commit with a [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) message, for example `feat: detect an Acme API key` or `docs: clarify the report mode`. Add a line under Unreleased in [the changelog](../../CHANGELOG.md) if the change is visible to a user. Keep the change to one thing, and say in the pull request what it does and how you tested it.

## Next Steps

- Read [Add a Rule](../how-to-guides/add-a-rule.md) for the full recipe, with what the tests require of a new rule.
- Read [Architecture](../explanation/architecture.md) to see how a scan flows through the code.
