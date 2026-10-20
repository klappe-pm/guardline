# use-with-claude-code

This guide registers guardline as a `PreToolUse` hook in Claude Code, so every tool call is judged before it runs: shell commands for environment dumps and secrets, file writes and edits for attribution and token-shaped values, and message bodies for the same. The decision comes back as JSON and a deny stops the tool call.

## let-init-write-it

`guardline init --hook claude-code` writes your configuration file and prints the settings snippet below with the absolute path of the command and of the file already filled in. The rest of this page explains each part, and the [choose block or report mode](choose-block-or-report-mode.md) guide covers the mode.

## settings-snippet

Add the hook to `~/.claude/settings.json` for every project, or to `.claude/settings.json` in one project. Use the absolute path of the command, because the hook environment may not have your shell path:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/venv/bin/guardline hook"
          }
        ]
      }
    ]
  }
}
```

An empty matcher or `*` runs the hook for every tool, which is what you want: the shell tool has a different name on each runtime, and guardline judges any tool input that carries a `command`, a `cmd`, or authored text fields.

## configuration-comes-only-from-config

The hook never searches for `guardline.toml` or `[tool.guardline]`. An agent that can write files could otherwise create one with `mode = "report"` or a long `disable` list and switch its own guard off. To use a configuration file, name it in the hook command, and keep it somewhere the agent cannot write:

```json
{ "type": "command", "command": "/path/to/venv/bin/guardline hook --config /etc/guardline/guardline.toml" }
```

The `rule_files` entries of that file must stay inside its directory. The hook also denies a Write, Edit or MultiEdit to any file named `guardline.toml`, to a `pyproject.toml` that holds or receives a `[tool.guardline]` table, and to the file named by `--config` and the files named by `--rules`. A person can lift that with `--allow-config-edit`. This protects the hook only against the edit tools: a shell command that writes the file is not covered, which is why the hook does not read discovered files at all, and why the file you name should be outside the agent's reach. `guardline scan` and `guardline diff` still discover configuration, because a person runs them.

## options

Add options to the command string. For example, to log findings without blocking while you tune rules:

```json
{ "type": "command", "command": "/path/to/venv/bin/guardline hook --mode report" }
```

Other options: `--disable RULE_ID` (repeatable), `--rules FILE` (repeatable), `--family NAME` (repeatable), `--config PATH`, `--allow-fenced-attribution`, `--allow-config-edit` and `--deny-with exit-code`. See the [cli reference](../reference/cli.md).

## what-a-deny-looks-like

In block mode a finding produces this on standard output, with exit code 0. The reason names rules and positions and never the matched value:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "guardline blocked this tool call with 1 finding(s): env-dump-printenv at tool_input.command line 1 column 1. Remove the flagged content and retry."}}
```

Claude Code reads that decision, blocks the tool call and shows the reason to the model, which can then change course. The hook never uses exit code 1 to block, because Claude Code treats exit 1 as a non-blocking error and runs the tool anyway. For a runtime that reads the exit code instead, use `--deny-with exit-code`: the reason goes to standard error and the exit code is 2.

## it-fails-closed

If the hook gets no payload, cannot read it, cannot load its configuration or crashes, it blocks the call and says why, instead of letting it through. In report mode the same failures are only printed. See the [hook protocol](../reference/hook-protocol.md).

## check-it-works

Pipe a payload through the hook by hand, using the same absolute path:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"printenv"}}' | /path/to/venv/bin/guardline hook
```

You should see the JSON deny decision above. If you see nothing, see [troubleshooting](troubleshooting.md).
