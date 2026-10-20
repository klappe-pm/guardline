# Use with Pre-Commit

This guide adds Guardline to a repository as a [pre-commit](https://pre-commit.com/) hook repository. Two hooks are provided: `guardline` scans the staged files, and `guardline-commit-msg` scans the commit message. Both run in block mode, so a finding stops the commit, and both give the same verdict as the agent hook for the same text.

## Add the Hooks

Add this to `.pre-commit-config.yaml`. Pin `rev` to a tag or a commit once one exists; until the first release use the branch name:

```yaml
repos:
  - repo: https://github.com/klappe-pm/guardline
    rev: main
    hooks:
      - id: guardline
      - id: guardline-commit-msg
```

Install the hooks, including the commit message stage:

```bash
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

## What Each Hook Runs

- `guardline` runs `guardline scan --mode block --no-stdin --` on every staged file. It does not filter on the text tag, because pre-commit tags a file with a NUL byte, or one named like a PDF, as binary, and Guardline judges those files too. Symbolic links are not handed to it; use `guardline diff --staged` to cover them.
- `guardline-commit-msg` runs `guardline scan --mode block --no-stdin --commit-msg --` on the commit message file. Comment lines are scanned because git keeps them for `-m` and `-F` messages; only the diff after the scissors line is ignored.

## Pass Options

Add `args` to change behavior. pre-commit places them after the hook's entry and before the file names. They replace the hook's own `args`, which is the option terminator `--`, so end your list with `--`. Without it a staged file named like an option, such as `--mode=report`, would be read as an option and could change the scan:

```yaml
      - id: guardline
        args: [--disable, token-hex-run-near-keyword, --rules, rules/team.toml, --]
```

The entry also passes `--no-stdin`, so a staged file named `-` is scanned as a file and never read as standard input.

Configuration in `guardline.toml` or `[tool.guardline]` is read as usual, starting from the directory pre-commit runs in.

## Try It Without Committing

```bash
pre-commit run guardline --all-files
```

To see findings without blocking while you tune rules, set `args: [--mode, report, --]`. `guardline init --hook pre-commit` prints this snippet for the mode you choose, and the [choose block or report mode](choose-block-or-report-mode.md) guide explains why the argument is needed.
