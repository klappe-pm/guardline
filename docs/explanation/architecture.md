# Architecture

This page explains how the modules fit together and why. It is for a contributor who needs the picture before changing a detector, the shell splitter or an entry point. The module list is in [source layout](../reference/source-layout.md), and the user facing reasons are in [design](design.md).

## The Flow

Every entry point ends in a `Scanner`. The path is the same regardless of where the text comes from:

1. An entry point obtains text. `cli.py` reads files, standard input or a git diff (`initcmd.py` is not an entry point to the scanner: it only writes the configuration file that `config.py` reads); `hook.py` reads a JSON payload; library callers pass strings.
2. `config.py` finds the configuration, loads extra rule files through `rules.py`, applies disables and builds a `Scanner` over the resulting rules.
3. `engine.py` decides how to judge the text. Plain text goes through the `text` scope rules. A shell command goes to `shell.py`, which returns simple commands, and the `args` and `word` scope rules are applied to each. A payload is split into its command and its authored text fields and each goes the matching way.
4. Matches become `Finding` objects that carry a rule id and a position and nothing else.
5. The entry point turns findings into its own verdict: lines and an exit status for `scan` and `diff`, a JSON decision for `hook`.

Because steps 2 to 4 are shared, a rule added to a file is live in the hook, the scan, the diff and the pre-commit hooks at once, and the consistency tests only need to compare entry points.

## Rules and the Parser

`rules.py` knows nothing about shells. `shell.py` knows nothing about rules. The seam between them is `SimpleCommand` (program, arguments, words, offset). The splitter's job is to answer "what would this shell run", looking through pipes, substitutions, heredocs and wrappers, and to emit each program it finds, wrappers included. A rule's job is to say whether a given program with given arguments is a problem.

Two small conventions keep rules expressive without code. An `env` command with nothing left to run is emitted as the program `env` with no arguments, so the rule is just the pattern `^$`. Options that take a value are listed in a rule's `value_options` and dropped before matching, so `ps -u deploy` does not read `deploy` as an option word.

## Decoding Before Judging

`shell.py` owns a small lexer rather than using `shlex`, because the quoting rules that matter here (`$'...'` with its escapes, `$"..."`, backslash-newline) are not shlex's. Comments are blanked first by a quote aware pass so that `; env` after an escaped quote inside `$'...'` is still a command. Every limit the splitter has (token budget, nesting depth, command count) sets `exhausted`, and the engine turns that into a finding, because a limit that returns quietly is a bypass.

## Attribution in Commands

Attribution is about what gets published, not about every string in a command. A `grep` for a trailer is not a violation. So `engine.py` applies attribution rules only to the arguments of a publishing command (`is_authoring_command`) and to data heredoc bodies when such a command is present, while the other text rules run over the whole command because a secret anywhere on a command line is a leak.

## Why the Engine Owns Limits

Size limits, the cap on findings and the fenced code exception live in `Scanner`, not in the entry points, so no entry point can forget them. The scanner also walks a tool payload to any depth: a key named `command` or `cmd` is a shell command, authored text keys get every family, and every other string, a dictionary key included, gets the token and custom rules. Key names that Guardline does not know are labelled `*` in sources, so a key can never leak into a finding. The hook builds its scanner without configuration discovery on purpose.

The fenced exception applies only to the attribution family and is a constructor argument with no configuration key.

## Fail-Closed Boundary

Only `hook.py` and `cli.py` catch exceptions. The engine and the parser let errors propagate so a bug is not turned into "no findings". The hook converts an exception into a deny in block mode and reports only the exception class name, because the message could carry the input.

## Performance Notes

The cost of a scan is the sum, over rules, of one linear pass. The shell parser makes one pass per nested command string and is bounded by depth and by the number of commands. Hot spots are rules whose prefix can occur densely in hostile text, which is why prefix patterns are anchored at a token boundary and capped.

## Extending

- A new detection that is a pattern: add a rule ([add a rule](../how-to-guides/add-a-rule.md)).
- A new wrapper that runs another command: add a branch to `_Walker._wrapper` in `shell.py`.
- A new field that carries authored text in a tool payload: add it to `_MESSAGE_FIELDS` in `engine.py` and to the [hook protocol](../reference/hook-protocol.md).
- A new entry point: build a `Scanner` with `config.build_scanner` and turn its findings into a verdict. Do not copy detector logic.
