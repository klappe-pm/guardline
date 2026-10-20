# Add a Custom Rule

This guide adds your own rule file to Guardline, checks it, and turns it on. Rules are data in the same format as the built-in ones, so anything Guardline ships can be copied and adapted. This is also where a team's own style rules go: Guardline ships detectors that are general guards and leaves personal or house style (prose punctuation, heading case, hard wrapping, project and client naming) to rule files like the one below.

## Write the Rule File

Create `rules/team.toml`. Every rule needs an id, a family, a description, a pattern and two examples, one that must fire and one look-alike that must not. This synthetic file holds two style rules for Markdown:

```toml
schema_version = 1

[[rule]]
id = "style-spaced-hyphen"
family = "style"
description = "A spaced hyphen used as a dash in prose."
pattern = '(?<=[A-Za-z0-9.,)]) - (?=[A-Za-z0-9(])'
example_fires = "The build is slow - rerun it."
example_clean = "Use the pre-commit hook; the range is 3 to 5."

[[rule]]
id = "style-heading-not-kebab"
family = "style"
description = "A Markdown heading that starts with a capital letter."
ignore_case = false
pattern = '^#{1,6} [A-Z]'
example_fires = "## Getting Started"
example_clean = "## getting-started"
```

The id must be lowercase kebab-case and must not be used by a built-in rule. The family can be any lowercase kebab-case name; a family that is not one of the built-in three simply groups your rules. The default scope is `text`, which matches the pattern against whole text line by line with case ignored. Use `ignore_case = false` for a case sensitive rule. Every field is described in the [rule file format](../reference/rule-file-format.md).

## Check It

```bash
guardline rules check /path/to/rules/team.toml
```

The command validates the file, then scans each rule's fire example and look-alike example and reports a rule whose fire example does not fire it or whose look-alike does. It prints `ok: 2 rule(s) validated` when both rules behave. Messages never quote your examples.

The loader also rejects patterns that can be slow on hostile text (a nested quantifier such as `(a+)+`, an alternation inside a wide repeat, more than 3 unbounded repeats, adjacent overlapping repeats such as `a*a*`, a backreference), a pattern that matches the empty string, a pattern or `unless` expression longer than 4000 characters, and an unknown key. Write patterns that are linear: bound repeats (`{0,200}` instead of `*`) wherever the text could be hostile.

## Turn It On

For one run:

```bash
guardline scan --rules /path/to/rules/team.toml /path/to/docs
```

For a project, in `guardline.toml` next to the file, where the path is relative to the configuration file:

```toml
rule_files = ["rules/team.toml"]
```

Rules from a file run everywhere the built-in rules do: `scan`, `diff`, `hook` and the pre-commit hooks. A custom text rule of any family except attribution also judges the whole text of a shell command in the hook.

## Turn One Off

Disable a custom rule by id exactly as you disable a built-in rule. See [disable a rule](disable-a-rule.md).

## Command Rules

A rule can also judge shell commands. Set `scope = "args"` with a `programs` list, and the pattern is matched against the command's arguments joined by single spaces. This rule flags `git push` with a force flag:

```toml
schema_version = 1

[[rule]]
id = "style-force-push"
family = "style"
description = "git push with a force flag."
scope = "args"
programs = ["git"]
pattern = '(?:^| )(?:-f|--force|--force-with-lease)(?: |$)'
example_fires = "git push --force origin main"
example_clean = "git push origin main"
```

Note that the example for a command rule is a whole command. The `programs` filter applies to the program name after wrappers such as `sudo` and `bash -c` are looked through.
