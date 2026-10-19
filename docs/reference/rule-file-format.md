# rule-file-format

This page describes the rule file format, version 1: every field of a rule, its default, and every check the loader makes. The built-in rules under `guardline/data/rules/` are files in this format, and a user rule file is loaded the same way. To write one, follow [add a custom rule](../how-to-guides/add-a-custom-rule.md).

## file

A rule file is TOML with a top level `schema_version` and an array of `[[rule]]` tables.

```toml
schema_version = 1

[[rule]]
id = "style-example"
family = "style"
description = "What the rule catches."
pattern = 'regular expression'
example_fires = "an input the rule must fire on"
example_clean = "a look-alike the rule must not fire on"
```

`schema_version` must be `1`. Any other value, and any other top level key, is an error. A file with no rules is valid. A rule id may appear once per file and may not reuse an id from a built-in rule or another loaded file.

## fields

| field | required | type | default | meaning |
| --- | --- | --- | --- | --- |
| `id` | yes | string | none | unique lowercase kebab-case identifier; used to disable the rule |
| `family` | yes | string | none | lowercase kebab-case group; the built-in families are `attribution`, `env-dump` and `token` |
| `description` | yes | string | none | one sentence saying what the rule catches; shown in every finding |
| `pattern` | yes | string | none | the regular expression, Python `re` syntax, searched with the multiline flag |
| `example_fires` | yes | string | none | an input on which the rule must fire |
| `example_clean` | yes | string | none | a look-alike input on which the rule must not fire |
| `scope` | no | `"text"`, `"args"` or `"word"` | `"text"` | what the pattern is matched against |
| `programs` | for `args` | list of strings | `[]` | base names of the programs an `args` rule applies to |
| `value_options` | no | list of strings | `[]` | for `args`: options whose next word is a value and is dropped before matching |
| `unless` | no | string | none | a second expression; when it matches, the rule does not fire |
| `ignore_case` | no | boolean | `true` for `text`, `false` for `args` and `word` | whether matching ignores case |

Both examples are required and must be non-empty. They are the rule's own test, and `guardline rules check` runs them.

## scopes

- `text`: the pattern is searched in whole text and every match is a finding at its start. The pattern must not match the empty string.
- `args`: for each simple command the shell splitter finds whose program (base name) is in `programs`, the arguments are joined with single spaces, the words that follow a `value_options` option are dropped, and the pattern is searched in the result. A command is reported at its best effort position. An `env` command that has no command left to run is reported to the rules as the program `env` with empty arguments.
- `word`: the pattern must match a whole word of the command, redirect targets included, from any program.

For `unless`, a `text` rule applies it to the matched text, and an `args` rule applies it to the joined arguments.

## load-time-checks

The loader rejects a file, with a message that names the file and the rule id and never quotes an example, when:

- the text is not valid TOML, or `schema_version` is not 1, or a key is unknown;
- an id or family is not lowercase kebab-case, or a required field is missing, empty or the wrong type;
- `scope` is not one of the three, `programs` is empty for `args`, or `programs` or `value_options` is set on another scope;
- a pattern or `unless` is not a valid regular expression, or is longer than 4000 characters;
- a pattern or `unless` is unsafe for hostile text. Each of these shapes is rejected: a nested quantifier (a repeat that is unbounded or allows more than 16 repetitions and that contains an optional repeat or a repeat allowing more than one repetition, such as `(a+)+`, `(?:\S+ )*` or `(?:a?){28}`); an alternation inside such a repeat (`(?:a|aa)+`); more than 3 unbounded repeats in one pattern; two adjacent wide repeats whose characters overlap (`a*a*`, `.*.*`, `\w+\w+`); a backreference. A bounded outer repeat of 16 or fewer, such as `(?:[a-z]+\.){0,8}`, is accepted because its cost is capped;
- a `text` pattern matches the empty string.

## examples-as-tests

For every built-in rule the test suite requires that the rule fires on `example_fires`, that it does not fire on `example_clean`, and that no other rule fires on `example_clean` either. `guardline rules check FILE` applies the first two checks to your file.

## writing-examples-without-holding-a-secret

An example for a credential rule must look like a credential, and a file that holds a complete credential trips the same rules it documents. The built-in files write the first character of each prefix as a TOML `\u` escape, so the decoded example matches and the file text does not. Do the same in your own files.
