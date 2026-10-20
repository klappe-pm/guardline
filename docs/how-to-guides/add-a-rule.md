# Add a Rule

This guide adds a built-in rule: where it goes, what it must contain, and what the tests then require. For a rule that only you need, ship a rule file instead ([add a custom rule](add-a-custom-rule.md)).

## Choose the Family

- `attribution`: authored text that credits an agent. File: `guardline/data/rules/attribution.toml`.
- `env-dump`: a shell command that prints an environment or a secret. File: `guardline/data/rules/env-dump.toml`.
- `token`: a token-shaped value. File: `guardline/data/rules/token.toml`.

A new family needs a new file, an entry in `BUILTIN_FAMILIES` in `guardline/model.py`, and a line in the family count test.

## Write the Entry

Add a `[[rule]]` table. The fields are in the [rule file format](../reference/rule-file-format.md). The rules that matter most for a built-in rule:

- the id starts with the family name and is lowercase kebab-case;
- `description` is one sentence ending in a period;
- the pattern has no nested quantifier and every repeat that can meet hostile text is bounded; a prefix pattern starts with a lookbehind for a token boundary;
- `example_fires` fires the rule and `example_clean` is a look-alike that a careless pattern would flag. `example_clean` must not fire any rule, not only this one;
- an example that looks like a credential or an attribution line writes the first character as a TOML `\u` escape so the file does not match its own rules.

## For an Env-Dump Rule

Use `scope = "args"` with `programs`, or `scope = "word"`. The shell splitter already looks through wrappers, so the rule only needs to describe the simple command. If the program has options that take a value (`ps -u deploy`), list them in `value_options` so a value is not read as an operand. For a command that is only a problem with no operands, such as `env` or `set`, the pattern is `^$`.

If a form needs the parser to change, for example a new wrapper that runs another command, edit `_Walker._wrapper` in `guardline/shell.py` and add a case to `tests/test_shell.py` and a command to `ENV_DUMP_COMMANDS` in `tests/samples.py`.

## Run the Tests

```bash
/path/to/guardline/.venv/bin/python -m pytest /path/to/guardline/tests/test_rules.py /path/to/guardline/tests/test_security.py
```

The rule tests are parametrized over every rule, so the new rule is picked up with no test change. They check that both examples exist, that the rule fires on one and not the other, that no rule fires on the look-alike, that the pattern has no nested quantifier, and that the rule survives inputs built from its own example in shapes meant to be slow. Update the pinned family counts in `test_family_counts` and in `test_cli.py` (the rule count) because adding a rule is meant to be a visible decision.

## Update the Documentation

Add a row to `docs/reference/rules.md`, update the rule counts in `README.md`, `docs/README.md`, `docs/reference/README.md` and `changelog.md`, and add the bypasses you know about to the [security model](../explanation/security-model.md). `tests/test_docs.py` fails if a built-in rule id is missing from the rules reference.
