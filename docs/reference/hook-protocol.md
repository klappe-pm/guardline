# Hook Protocol

This page describes what `guardline hook` reads, which parts of a tool call it judges, and exactly what it writes. The payload format is the Claude Code `PreToolUse` JSON object.

## Input

One JSON object on standard input. Empty input is not allowed: in block mode it is a deny, because a hook that is handed nothing has not judged anything. Invalid UTF-8 bytes are replaced and the payload is still judged.

| field | meaning |
| --- | --- |
| `hook_event_name` | copied into the decision as `hookEventName`; default `PreToolUse` |
| `tool_name` | only `TodoWrite` is special: it is local bookkeeping and is never judged |
| `tool_input` | a mapping; everything judged comes from here. Anything else, or no mapping, has nothing to judge |

## What Is Judged

From `tool_input`:

- `command` or `cmd`, a string or a list of words (a list is joined as shell words). The shell command rules judge each simple command, text rules of every family except attribution judge the whole command text (so a secret passed as an argument is found), and attribution rules judge the text a publishing command carries: a `git commit`, `tag`, `notes`, `merge`, `commit-tree`, `revert` or `cherry-pick`, a `gh pr`, `issue`, `release` or `gist` verb that writes, a `gh api` call with a body or a non-GET method, and `glab mr`, `issue` or `release`, plus data heredoc bodies when such a command is present.
- the authored text fields `content`, `new_string`, `new_source`, `body`, `commit_message`, `message`, `title`, `description` and `text`, judged by the text rules of every family.
- each `edits` entry's `new_string`.

Findings are labelled with their field, for example `tool_input.content` or `tool_input.edits[1].new_string`.

## Output

In block mode with a finding, the default `--deny-with json` writes this to standard output and exits 0:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "guardline blocked this tool call with 1 finding(s): token-github-token at tool_input.command line 1 column 14. Remove the flagged content and retry."
  }
}
```

The reason is also written to standard error. With `--deny-with exit-code`, standard output stays empty, the reason goes to standard error and the exit code is 2. The reason lists at most ten findings by rule id and position and counts the rest. It never contains matched text. A finding that stands for a limit, such as `guardline-input-too-large`, also names the limit in parentheses, for example `(The input is longer than 65536 characters and was not scanned)`. When an attribution rule fired, it also names `--allow-fenced-attribution`.

With no finding the hook writes nothing and exits 0. In report mode it writes the findings to standard error, one per line, and exits 0.

## Exit Codes

| code | meaning |
| --- | --- |
| 0 | allowed, or denied through the JSON decision, or report mode |
| 2 | denied, with `--deny-with exit-code` |

The hook never exits 1. Claude Code treats exit 1 as a non-blocking error and runs the tool anyway.

## Failure Handling

| situation | block mode | report mode |
| --- | --- | --- |
| empty input | deny | print and allow |
| input is not valid JSON | deny | print and allow |
| input nested too deeply for the JSON parser | deny, saying the payload nests too deeply to parse | print and allow |
| the JSON parser fails in any other way | deny, naming the exception class only | print and allow |
| a scanner exception | deny, naming the exception class only | print and allow |
| a configuration or rule file error | deny, with the error message | print and allow |
| input over the size limit | deny with a `guardline-input-too-large` finding | print and allow |
| a command too complex to split | deny with a `guardline-command-too-complex` finding | print and allow |

The deny messages never contain matched text or exception messages, which could carry the input.
