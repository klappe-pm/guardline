# Quote Third-Party Attribution

This guide covers the one exception to the attribution rules: quoting someone else's text that contains a trailer or a footer, such as a review of a commit you did not write. By default the quotation is reported like any other attribution. With an explicit switch, attribution inside a closed fenced code block is allowed, and nothing else changes.

## The Switch

Pass `--allow-fenced-attribution`. It works on `scan`, `diff` and `hook`:

```bash
guardline scan --allow-fenced-attribution /path/to/review.md
```

The same text, without the fence, is still reported:

````markdown
The commit under review ends with this trailer:

```text
Co-Authored-By: Codex <dev@example.com>
```
````

## What Counts as a Fence

A fence is three or more backticks or tildes at the start of a line, indented at most three spaces. The block closes on a fence of the same character that is at least as long and has no text after it. Only the lines between the fences are exempt.

- A fence that is never closed exempts nothing.
- A closing fence shorter than the opening one does not close the block.
- Only attribution rules are affected. A token-shaped value inside a fence is still reported.

## In an Agent Hook

Add the switch to the hook command only for the session that needs it. A switch left in a settings file applies to every call, so remove it afterwards:

```json
{ "type": "command", "command": "/path/to/venv/bin/guardline hook --allow-fenced-attribution" }
```

## Why It Is Not a Config Key

An exception that anyone can commit into a configuration file stops being an exception. The switch is deliberate and per run, mirroring the escape hatch of the shell hooks Guardline was ported from, which was an environment variable set for one write.
