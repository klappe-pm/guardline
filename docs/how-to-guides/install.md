# Install

This guide covers every way to install the `guardline` command and how to upgrade it. Guardline needs Python 3.11 or newer and has no runtime dependencies. There is no PyPI package yet, so each method installs from the GitHub repository.

## With Pipx

`pipx` keeps the command in its own environment and puts it on your path:

```bash
pipx install git+https://github.com/klappe-pm/guardline
```

Confirm it runs:

```bash
guardline --version
```

## With Pip in a Virtual Environment

```bash
python3 -m venv /path/to/venv && /path/to/venv/bin/pip install git+https://github.com/klappe-pm/guardline
```

The command is then `/path/to/venv/bin/guardline`. Use that absolute path in hook settings, because a hook does not always run with your shell's path.

## From a Checkout

For development, or to pin a commit:

```bash
git clone https://github.com/klappe-pm/guardline /path/to/guardline && python3 -m venv /path/to/guardline/.venv && /path/to/guardline/.venv/bin/pip install -e '/path/to/guardline[test]'
```

## As a Pre-Commit Hook

You do not install the command yourself for this. pre-commit builds an environment from the repository. See [use with pre-commit](use-with-pre-commit.md).

## Upgrade

```bash
pipx upgrade guardline
```

For a pip install, rerun the `pip install` command with `--upgrade`. After an upgrade run `guardline rules check` to confirm the rule files load, and `guardline rules list` to see the active rules.

## Uninstall

```bash
pipx uninstall guardline
```
