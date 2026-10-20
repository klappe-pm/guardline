# Choose Block or Report Mode

This guide helps you decide between block and report mode, set the one you choose in every place Guardline runs, and confirm what is active. The mode decides what a finding does: in block mode it stops the action, and in report mode it is only printed. Block is the default because a guardrail that cannot stop anything is easy to ignore, but the choice is yours.

## What Each Mode Does

| where | block | report |
| --- | --- | --- |
| `guardline scan` and `guardline diff` | print findings, exit 1 | print findings, exit 0 |
| `guardline hook` | deny the tool call | allow the tool call and print the findings |
| a failure to start, such as an unreadable configuration | deny the tool call | print the failure and allow |

Report mode is for learning what the rules catch in your repository before you let them stop anything. Block mode is for when you trust the rules and want the guard to hold.

## Pick with Init

Run `guardline init` and answer the mode question, or pass the answers as flags:

```bash
guardline init --mode report --families all --target guardline.toml --hook none
```

The command writes `mode = "report"` to `guardline.toml`, or to a `[tool.guardline]` table when you choose `pyproject.toml`. See the [cli reference](../reference/cli.md) for every flag.

## Change the Mode Later

Edit the `mode` key in the file, or run `guardline init --force` again with the other mode. To try the other mode for one run without touching the file, pass `--mode` to the command:

```bash
guardline scan --mode report /path/to/file.txt
```

The `--mode` option always wins over the file.

## Apply the Mode in Claude Code

The agent hook never searches for configuration, so a `guardline.toml` next to your project does not change it. The hook uses your mode only when its command names the file with `--config`. Run `guardline init --hook claude-code` and it prints the settings snippet with that option and an absolute path already filled in. The reason is in the [use with claude code](use-with-claude-code.md) guide: an agent that can write files could otherwise create a configuration that switches its own guard off.

If you keep the mode in the file, keep the file where the agent cannot write it. The hook denies edits made through the agent's edit tools, and it does not see a shell command that writes the file.

## Apply the Mode in Pre-Commit

The two pre-commit hooks pass `--mode block` themselves, and the last `--mode` on a command line wins. To use report mode, set it in the hook arguments, and end them with `--`: your `args` replace the hook's own, and the `--` is what keeps a staged file named like an option from being read as one. `guardline init --hook pre-commit` prints this for you:

```yaml
repos:
  - repo: https://github.com/klappe-pm/guardline
    rev: main
    hooks:
      - id: guardline
        args: [--mode, report, --]
      - id: guardline-commit-msg
        args: [--mode, report, --]
```

The rule families in your configuration file still apply, because the scan hooks find the file by searching up from the repository.

## Confirm What Is Active

```bash
guardline config show
```

It prints the file the settings came from, the mode and where the mode came from, the enabled families and the disabled rule ids. Run it from the directory the scan runs in. To check the file the hook uses, pass the same option the hook command has: `guardline config --config /path/to/guardline.toml show`.
