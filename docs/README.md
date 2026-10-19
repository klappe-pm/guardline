# docs

Documentation for people who use guardline: you run the command, wire it into an agent runtime or a repository, and tune its rules. It is arranged by the four [Diátaxis](https://diataxis.fr/) quadrants, so the folder a page sits in tells you what kind of page it is. If you change guardline itself, the same shape exists under [developer-docs](../developer-docs/README.md).

## tutorials

Lessons that take you through a task from start to finish, for someone who has not done it before. Start with [getting started](tutorials/getting-started.md), which goes from an empty virtual environment to a scan, a hook decision and a configuration file. Index: [tutorials](tutorials/README.md).

## how-to-guides

Recipes for a specific goal, for someone who already knows the basics. [install](how-to-guides/install.md) covers every install method, [use with claude code](how-to-guides/use-with-claude-code.md) holds the hook settings snippet, [use with pre-commit](how-to-guides/use-with-pre-commit.md) wires guardline into a repository, [scan in ci](how-to-guides/scan-in-ci.md) scans a branch or a diff, [disable a rule](how-to-guides/disable-a-rule.md) turns rules off, [add a custom rule](how-to-guides/add-a-custom-rule.md) adds your own, including personal style rules, [quote third party attribution](how-to-guides/quote-third-party-attribution.md) covers the fenced code switch, and [troubleshooting](how-to-guides/troubleshooting.md) matches a failure to its fix. Index: [how-to guides](how-to-guides/README.md).

## reference

Lookup pages that describe the machinery as it is, with no instruction attached. [cli](reference/cli.md) lists every subcommand, option and exit status, [configuration](reference/configuration.md) lists every key in `guardline.toml`, [rule file format](reference/rule-file-format.md) lists every field of a rule, [rules](reference/rules.md) lists all 43 built-in rules, [hook protocol](reference/hook-protocol.md) describes the payload and the decision, and [python api](reference/python-api.md) lists every public function and class. Index: [reference](reference/README.md).

## explanation

Discussion that gives background and reasons, for a reader who wants to understand rather than act. [design](explanation/design.md) explains why the rules are data and why there are three entry points, and [security model](explanation/security-model.md) states the threat model and lists the bypasses that are known and open. Index: [explanation](explanation/README.md).

## documentation-guide

How this documentation is organised and how to add to it. [documentation guide](documentation-guide/README.md) says which folder a new page belongs in.
