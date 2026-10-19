# support

This page says where to get help with guardline and where to file what. guardline is maintained in the open on GitHub and has no paid or private support channel; every question and report goes through the repository, where it is visible to the next person with the same problem.

## before-you-ask

- Match your symptom against [troubleshooting](docs/how-to-guides/troubleshooting.md).
- Check the [changelog](changelog.md) for what has shipped.
- Search the existing [issues](https://github.com/klappe-pm/guardline/issues), open and closed.

## where-to-file

| what you have | where it goes |
| --- | --- |
| a bug: guardline did something other than what the documentation says | an [issue](https://github.com/klappe-pm/guardline/issues/new) with the command you ran, what you expected, what happened and the output of `guardline --version` |
| a false positive or a missed detection | an [issue](https://github.com/klappe-pm/guardline/issues/new) with a synthetic input that shows it and the rule id; never paste a real credential |
| a question about using guardline | an [issue](https://github.com/klappe-pm/guardline/issues/new) with what you are trying to do and what you tried |
| a request for a feature or a new rule | an [issue](https://github.com/klappe-pm/guardline/issues/new) describing the need before any code; see [contributing](contributing.md) |
| a suspected security vulnerability | a private report as described in [security.md](security.md); never a public issue |
| a mistake or gap in the documentation | an issue, or a pull request against the page; [documentation guide](docs/documentation-guide/README.md) says where a page goes |

## what-to-include

Paste command output as text inside a code fence rather than as a screenshot, and remove anything shaped like a credential before posting. guardline never prints a matched value, so its own output is safe to paste. If the problem involves a configuration file, include `guardline.toml` or the `[tool.guardline]` table.

## response-times

The project is maintained by one person alongside other work. Issues are read within a few days; fixes land as time allows and in order of impact.
