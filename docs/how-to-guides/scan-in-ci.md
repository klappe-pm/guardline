# Scan in CI

This guide runs Guardline in a CI job so a pull request that adds a credential or an attribution line fails the build. The command needs no network and no services. This repository ships no CI workflow of its own; the commands below work in any system that can run a command.

## Scan the Work Tree

```bash
guardline scan /path/to/checkout
```

The command walks the directory and enters every subdirectory except `.git`, so `node_modules` and virtual environments are scanned too; list them in `exclude` in the configuration if you do not want that. Binary files are scanned with NUL characters removed. A symbolic link is not read and is reported as a `guardline-file-skipped` finding, which fails the run in block mode. The command exits 1 if any finding is reported. Use `--format json` for a machine readable report.

## Scan Only What a Pull Request Adds

`guardline diff` scans only the lines a diff adds, so existing content is not reported again. Compare against the merge base:

```bash
guardline diff --repo /path/to/checkout --base origin/main
```

Findings are reported at the line numbers of the new file. Add `--staged` to scan the index instead, and a path list after the options to limit the files.

## Scan Commit Messages

Write the messages to a file and scan it:

```bash
git -C /path/to/checkout log --format=%B origin/main..HEAD > /path/to/messages.txt && guardline scan /path/to/messages.txt
```

## Scan Shell Scripts for Environment Dumps

Environment dump rules judge commands, not prose, so tell the scan to treat the files as shell:

```bash
guardline scan --shell /path/to/checkout/scripts
```

Expect some findings in scripts that legitimately print variables; disable those rules for the path in `guardline.toml` or exclude the files. See [disable a rule](disable-a-rule.md).

## Report First

Start with `--mode report`, which prints findings and exits 0, read the list, tune the configuration, then switch to the default block mode.
