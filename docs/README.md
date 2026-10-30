# Documentation

Guardline is one detector library for coding agent guardrails: the same rules run from an agent runtime hook, a pre-commit hook and a command line scan. These pages cover installing and using it, looking things up, and changing the code. They follow the four [Diátaxis](https://diataxis.fr/) quadrants, so the folder a page sits in tells you what kind of page it is.

## Tutorials

Lessons that take you through a task from start to finish. [Getting Started](tutorials/getting-started.md) goes from an empty virtual environment to a scan, a hook decision, a configuration file written by `guardline init` and a disabled rule. [First Contribution](tutorials/first-contribution.md) goes from a fresh clone to a passing test suite and a rule ready for review. Index: [Tutorials](tutorials/README.md).

## How-To Guides

Recipes for a specific goal, for someone who already knows the basics.

- Set up: [Install](how-to-guides/install.md), [Use with Claude Code](how-to-guides/use-with-claude-code.md), [Use with Pre-Commit](how-to-guides/use-with-pre-commit.md), [Choose Block or Report Mode](how-to-guides/choose-block-or-report-mode.md).
- Operate: [Scan in CI](how-to-guides/scan-in-ci.md), [Troubleshooting](how-to-guides/troubleshooting.md).
- Customize: [Disable a Rule](how-to-guides/disable-a-rule.md), [Add a Custom Rule](how-to-guides/add-a-custom-rule.md), [Quote Third-Party Attribution](how-to-guides/quote-third-party-attribution.md).
- Contribute: [Add a Rule](how-to-guides/add-a-rule.md), [Run the Tests](how-to-guides/run-the-tests.md), [Cut a Release](how-to-guides/cut-a-release.md).

Index: [How-To Guides](how-to-guides/README.md).

## Reference

Lookup pages that describe the machinery as it is. [CLI](reference/cli.md) lists every subcommand, option and exit status, [Configuration](reference/configuration.md) lists every key in `guardline.toml`, [Rule File Format](reference/rule-file-format.md) lists every field of a rule, [Rules](reference/rules.md) lists all 45 built-in rules, [Hook Protocol](reference/hook-protocol.md) describes the payload and the decision, [Python API](reference/python-api.md) lists every public function and class, [Package Data](reference/package-data.md) describes the shipped rule files and how they are read, and [Source Layout](reference/source-layout.md) maps every module and test file. Index: [Reference](reference/README.md).

## Explanation

Background and reasons, for a reader who wants to understand rather than act. [Design](explanation/design.md) explains why the rules are data and why there are three entry points, [Security Model](explanation/security-model.md) states the threat model and lists the bypasses that are known and open, and [Architecture](explanation/architecture.md) explains how a scan flows through the modules. Index: [Explanation](explanation/README.md).
