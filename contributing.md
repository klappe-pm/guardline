# contributing

Thank you for helping improve guardline. Open an issue to discuss a change before writing a large pull request. This page holds the rules every contribution follows; the walkthroughs and reference live under [developer-docs](developer-docs/README.md), starting with [first contribution](developer-docs/tutorials/first-contribution.md).

## setup

```bash
git clone https://github.com/klappe-pm/guardline && cd guardline && python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[test]'
```

## tests

Run the suite before every commit. [run the tests](developer-docs/how-to-guides/run-the-tests.md) covers the other checks.

```bash
python3 -m pytest
```

```bash
python3 -m pytest --cov=guardline
```

## guidelines

- Python 3.11 or newer, standard library only at runtime. `pytest`, `pytest-cov`, `ruff` and `mypy` are test dependencies.
- Rules are data. A new detection goes in a rule file under `guardline/data/rules/` with an id, a family, a description, a pattern and two examples: one that must fire and one look-alike that must not. See [add a rule](developer-docs/how-to-guides/add-a-rule.md).
- Package data is read through `importlib.resources`, never through a path built from `__file__`. See [package data](developer-docs/reference/package-data.md).
- Never print, log or return a matched secret. Findings carry the rule id and a position only, and a test proves it.
- Keep every pattern linear: no nested quantifiers, no adjacent overlapping repeats, at most 3 unbounded repeats, every repeat bounded where it can be. The rule loader rejects the unsafe shapes and a test feeds each rule adversarial input.
- Tests read fixtures only: never the live home directory, a real network or a real git remote. Test values are synthetic and assembled from fragments so that no test file holds a complete credential.
- Filenames and Markdown headings are lowercase kebab-case. Reserved names such as `README.md` and `LICENSE` keep their spelling.
- Write one line per Markdown paragraph and list item; do not hard-wrap prose.
- Do not use a dash as punctuation. Use a comma, colon, semicolon, period or parentheses, and write ranges as "3 to 5".
- Documentation goes in `docs/` for people who use guardline and `developer-docs/` for people who change it, in the folder the [documentation guide](docs/documentation-guide/README.md) names for its kind.
- Never commit a secret, credential, private key, `.env` file or `settings.local.json`. `.env.example` with placeholder values is allowed.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

## public-repository

Everything committed here is visible to anyone, so treat every file, commit, pull request and comment as published.

- Never add `models`, `providers` or `session-link` keys to the frontmatter of any Markdown file, and never add a session link anywhere.
- Never credit an agent, model, model provider or agent runtime as author or contributor in files, commits, pull requests or comments. The detection rules in `guardline/data/rules/` name vendors only as the thing they detect.
- Agent instruction files and runtime directories at the repository root are gitignored and never tracked.
- Do not copy anything from a private repository: no client names, personal paths, notes, plans or prompts. Examples and fixtures are synthetic.

## pull-requests

Keep each pull request to one change, describe what it does and how you tested it, and make sure the test suite, `ruff check`, `ruff format --check` and `mypy` pass. Add a line under `unreleased` in [changelog.md](changelog.md) for any user-visible change.

## license

By contributing, you agree that your contributions are licensed under the MIT license in [LICENSE](LICENSE).
