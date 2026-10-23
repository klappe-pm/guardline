# Support

This page says where to get help with Guardline and where to file what. Guardline is maintained in the open on GitHub and has no paid or private support channel; every question and report goes through the repository, where it is visible to the next person with the same problem.

## Before You Ask

- Match your symptom against [Troubleshooting](docs/how-to-guides/troubleshooting.md).
- Check the [changelog](CHANGELOG.md) for what has shipped.
- Search the existing [issues](https://github.com/klappe-pm/guardline/issues), open and closed.

## Where to File

| what you have | where it goes |
| --- | --- |
| a bug: Guardline did something other than what the documentation says | a [bug report](https://github.com/klappe-pm/guardline/issues/new?template=bug-report.yml) with the command you ran, what you expected, what happened and the output of `guardline --version` |
| a false positive or a missed detection | a [bug report](https://github.com/klappe-pm/guardline/issues/new?template=bug-report.yml) with a synthetic input that shows it and the rule id; never paste a real credential |
| a question about using Guardline | a [question](https://github.com/klappe-pm/guardline/issues/new?template=question.yml) with what you are trying to do and what you tried |
| a request for a feature or a new rule | a [feature request](https://github.com/klappe-pm/guardline/issues/new?template=feature-request.yml) describing the need before any code; see [Contributing](CONTRIBUTING.md) |
| a suspected security vulnerability | a private report as described in [SECURITY.md](SECURITY.md); never a public issue |
| a mistake or gap in the documentation | an issue, or a pull request against the page; the [docs index](docs/README.md) shows where a page goes |

## What to Include

Paste command output as text inside a code fence rather than as a screenshot, and remove anything shaped like a credential before posting. Guardline never prints a matched value, so its own output is safe to paste. If the problem involves a configuration file, include `guardline.toml` or the `[tool.guardline]` table.

## Response Times

The project is maintained by one person alongside other work. Issues are read within a few days; fixes land as time allows and in order of impact.
