# How-To Guides

How-to guides are recipes. Each one serves a reader who already knows the basics and has a specific goal, and gives the steps in order with explanation only where a step would otherwise surprise. For a first walk through the tool read the [Getting Started tutorial](../tutorials/getting-started.md), and for the reasons behind a step see the [Explanation](../explanation/README.md) pages.

## Set Up

- [Install](install.md): install the command with pipx, pip or from a checkout, and upgrade it.
- [Use with Claude Code](use-with-claude-code.md): register the hook in Claude Code settings, and read what a deny looks like.
- [Use with Pre-Commit](use-with-pre-commit.md): add the file hook and the commit message hook to a repository.
- [Choose Block or Report Mode](choose-block-or-report-mode.md): decide what a finding does, set it for the command line, Claude Code and pre-commit, and confirm it.

## Operate

- [Scan in CI](scan-in-ci.md): scan a branch, a diff or a commit message range in a CI job.
- [Troubleshooting](troubleshooting.md): match a symptom to its fix.

## Customize

- [Disable a Rule](disable-a-rule.md): turn rules off by id, by family or for a path.
- [Add a Custom Rule](add-a-custom-rule.md): write and check your own rule file, including personal style rules.
- [Quote Third-Party Attribution](quote-third-party-attribution.md): allow a quoted trailer inside a fenced code block.

## Contribute

- [Add a Rule](add-a-rule.md): add a built-in rule and see what the tests then require.
- [Run the Tests](run-the-tests.md): the suite, coverage, linting, type checking and the sdist check.
- [Cut a Release](cut-a-release.md): bump the version, tag and publish through trusted publishing.
