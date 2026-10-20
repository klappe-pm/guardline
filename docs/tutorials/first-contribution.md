# First Contribution

This tutorial takes a new contributor from a clone of the repository to a tested change. You set up a virtual environment, run the suite, add a small rule to a rule file with its two examples, watch the test suite pick it up, and finish with the checks a pull request needs. It follows one path; the [Contributing](../../CONTRIBUTING.md) page holds the rules every contribution follows.

## What You Need

- Python 3.11 or newer and `git`.
- A clone of the repository. The examples use `/path/to/guardline`.

## Set Up

```bash
python3 -m venv /path/to/guardline/.venv && /path/to/guardline/.venv/bin/pip install -e '/path/to/guardline[test]'
```

## Run the Suite

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests
```

Everything should pass on Linux. Tests that need `git` are skipped with a reason when it is missing.

## Add a Rule

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

## See the Tests Pick It Up

The rule tests are parametrized over every rule in the package, so no test file changes. Run them:

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests/test_rules.py
```

They fail until you also update the expected family count in `test_family_counts`, because the count is pinned on purpose: adding a rule is a visible decision. Change the expected `token` count and run again. Then break the rule on purpose, for example change `{24}` to `{25}`, and see `test_fire_example_fires_its_rule` fail for `token-acme-key` without echoing the example. Put it back.

## Finish

Update the rule counts where they are written (the README, `docs/reference/rules.md`, the changelog), add the rule to the table in `docs/reference/rules.md`, and add a line under Unreleased in `CHANGELOG.md`. Then run the checks:

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests --cov=guardline
```

```bash
/path/to/guardline/.venv/bin/ruff check /path/to/guardline && /path/to/guardline/.venv/bin/ruff format --check /path/to/guardline && /path/to/guardline/.venv/bin/mypy --config-file /path/to/guardline/pyproject.toml /path/to/guardline/guardline
```

## Next Steps

- The full recipe, with what the tests require of a new rule: [add a rule](../how-to-guides/add-a-rule.md).
- How a scan flows through the code: [architecture](../explanation/architecture.md).
