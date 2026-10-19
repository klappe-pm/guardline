# use-with-pre-commit

This guide adds guardline to a repository as a [pre-commit](https://pre-commit.com/) hook repository. Two hooks are provided: `guardline` scans the staged text files, and `guardline-commit-msg` scans the commit message. Both run in block mode, so a finding stops the commit, and both give the same verdict as the agent hook for the same text.

## add-the-hooks

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

## what-each-hook-runs

- `guardline` runs `guardline scan --mode block` on every staged file that pre-commit classifies as text.
- `guardline-commit-msg` runs `guardline scan --mode block --commit-msg` on the commit message file. Comment lines are scanned because git keeps them for `-m` and `-F` messages; only the diff after the scissors line is ignored.

## pass-options

Add `args` to change behavior. They are placed before the file names:

```yaml
      - id: guardline
        args: [--disable, token-hex-run-near-keyword, --rules, rules/team.toml]
```

Configuration in `guardline.toml` or `[tool.guardline]` is read as usual, starting from the directory pre-commit runs in.

## try-it-without-committing

```bash
pre-commit run guardline --all-files
```

To see findings without blocking while you tune rules, set `args: [--mode, report]`.
