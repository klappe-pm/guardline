# troubleshooting

This page matches a symptom to its cause and fix. Each entry starts from what you see. If your symptom is not here, [support](../../support.md) says where to file it.

## the-hook-does-nothing

- Run the payload by hand with the absolute path to the command, as in [use with claude code](use-with-claude-code.md). If that denies and the runtime does not, the settings entry is wrong: check the `matcher` and that the command path exists.
- A runtime hook often has a short path. Use `/path/to/venv/bin/guardline`, not `guardline`.
- If you set `--mode report` the hook prints findings to standard error and allows the call.

## a-deny-with-no-obvious-cause

The reason names the rule id and the position, for example `env-dump-ps-bsd-environment-word at tool_input.command line 1 column 1`. Look the id up in the [rules reference](../reference/rules.md). The position is the line and column inside the named field, and for a command it is the best effort offset of the simple command that matched.

## a-false-positive

Confirm the rule with a synthetic input, then either disable it ([disable a rule](disable-a-rule.md)) or file an issue with the rule id and the input. Common cases: a long hexadecimal value right after the word `key` (`token-hex-run-near-keyword`), and a documentation line that quotes a trailer (see [quote third party attribution](quote-third-party-attribution.md)).

## guardline-input-too-large

The input is longer than the limit (1 MiB of text or 64 KiB of shell command by default), so it was not scanned and the scan reports this finding instead of passing. Exclude the file, or raise `max_text_chars` or `max_command_chars` in the configuration. Raising the limit raises the worst case scan time.

## guardline-command-too-complex

The shell command has more than 100000 words across everything nested in it, or nests quoting and substitution too deeply, so guardline could not split it and reports this finding instead of passing it. Break the command up, or move the logic into a script file and run that.

## guardline-file-skipped

A directory scan met a symbolic link or special file and did not read it, so it reports the path instead of passing it. Scan the link's target, name the link on the command line (a named file is always read), or exclude it with `exclude` in the configuration.

## guardline-config-edit

The hook denied a Write, Edit or MultiEdit to `guardline.toml`, to a pyproject.toml that holds or receives a `[tool.guardline]` table, or to the hook's own `--config` or `--rules` file. The agent is not allowed to change the configuration of its own guard. A person edits the file, or runs the hook with `--allow-config-edit` for the session that needs it.

## the-hook-ignores-my-guardline-toml

By design. The hook reads a configuration file only when its command names one with `--config PATH`. See [use with claude code](use-with-claude-code.md).

## unknown-rule-id-in-disable

`guardline: error: unknown rule id(s) in disable: ...` means the id is misspelled or belongs to a rule file that was not loaded. Run `guardline rules list` and copy the id.

## configuration-errors

`unknown key(s)` means the file uses a key guardline does not read. `allow_fenced_attribution` is not a key on purpose. See [configuration](../reference/configuration.md). In the hook, a configuration error blocks the call in block mode, so fix the file.

## a-custom-rule-is-rejected

`guardline rules check /path/to/rules.toml` prints the problem. The usual causes are a pattern that can be slow on hostile text (a nested quantifier such as `(a+)+`, adjacent overlapping repeats such as `a*a*`, more than 3 unbounded repeats, an alternation inside a wide repeat, a backreference), a pattern that matches the empty string, an id that is not lowercase kebab-case, or a missing `example_fires` or `example_clean`. Messages never quote your examples. See [rule file format](../reference/rule-file-format.md).

## scan-says-nothing-for-my-shell-script

Environment dump rules judge commands. Pass `--shell`. Without it the file is scanned as text, and only the text rules run. Scripts that fall outside what the shell splitter understands are listed in the [security model](../explanation/security-model.md).

## the-diff-command-fails

`git diff failed` means the directory is not a repository, git is missing, or the base revision is wrong. A base that starts with a dash is refused.
