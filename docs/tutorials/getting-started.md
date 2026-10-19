# getting-started

This tutorial takes a new user from an empty virtual environment to a working setup. You install the command, scan a commit message, judge a tool call the way an agent hook does, and turn one rule off with a configuration file. It follows one path and explains only what that path needs. For the full command surface see the [cli reference](../reference/cli.md), and for every configuration key see [configuration](../reference/configuration.md).

## what-you-need

- Python 3.11 or newer.
- `pip` and the `venv` module.
- A scratch directory you can write to. The examples use `/tmp/guardline-tour`.

## install-the-command

Create a virtual environment and install guardline into it. Until the package reaches PyPI, install from the repository:

```bash
python3 -m venv /tmp/guardline-tour/venv && /tmp/guardline-tour/venv/bin/pip install git+https://github.com/klappe-pm/guardline
```

Confirm the command runs:

```bash
/tmp/guardline-tour/venv/bin/guardline --version
```

The [install guide](../how-to-guides/install.md) covers other install methods and upgrading.

## scan-a-file

Write a commit message that carries a Co-Authored-By trailer naming a coding agent. The trailer rule recognises the agent and vendor names listed in the [rules reference](../reference/rules.md); `Codex` is one of them:

```bash
printf 'fix: parser\n\nCo-Authored-By: Codex <dev@example.com>\n' > /tmp/guardline-tour/message.txt
```

Scan it:

```bash
/tmp/guardline-tour/venv/bin/guardline scan /tmp/guardline-tour/message.txt
```

guardline prints one line per finding, with the file, the line and column, the rule id, the family and what the rule catches. The command exits 1 because the default mode is `block`. It never prints the matched text.

```text
/tmp/guardline-tour/message.txt:3:1: attribution-co-author-trailer [attribution] A Co-Authored-By trailer whose name part names a coding agent or its vendor.
```

Run it again in report mode and check the exit status:

```bash
/tmp/guardline-tour/venv/bin/guardline scan --mode report /tmp/guardline-tour/message.txt; echo "exit $?"
```

Report mode prints the same findings and exits 0, which is how you try the rules on a repository before you let them block anything.

## judge-a-tool-call

An agent runtime sends a JSON description of each tool call to a hook on standard input. Send one by hand, a shell command that prints the whole environment:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"printenv"}}' | /tmp/guardline-tour/venv/bin/guardline hook
```

The answer is a JSON deny decision on standard output, and the command exits 0, because that is how Claude Code reads a decision. Try a harmless command and see that nothing is printed:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}' | /tmp/guardline-tour/venv/bin/guardline hook
```

The [hook protocol reference](../reference/hook-protocol.md) describes the payload and the decision in full, and [use with claude code](../how-to-guides/use-with-claude-code.md) shows how to register the hook.

## turn-a-rule-off

Create `/tmp/guardline-tour/guardline.toml` with one disabled rule:

```toml
disable = ["attribution-co-author-trailer"]
```

Scan again with that file:

```bash
/tmp/guardline-tour/venv/bin/guardline scan --config /tmp/guardline-tour/guardline.toml /tmp/guardline-tour/message.txt
```

The trailer rule is gone, so the scan is clean unless another rule still matches. Every rule id is listed by `guardline rules list`, and an id that names no rule is an error, so a typo cannot silently leave a rule on.

## next-steps

- Wire guardline into a repository: [use with pre-commit](../how-to-guides/use-with-pre-commit.md).
- Add your own rule: [add a custom rule](../how-to-guides/add-a-custom-rule.md).
- Understand what guardline does and does not stop: [security model](../explanation/security-model.md).
