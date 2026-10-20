"""The agent runtime hook: a tool call payload in, an exit code and a JSON decision out.

The payload format is the Claude Code ``PreToolUse`` JSON object. In block mode a
finding produces a deny decision. By default the decision is JSON on standard output
with exit code 0, which is how Claude Code reads a decision. ``deny_with="exit-code"``
writes the reason to standard error and exits 2 instead, for runtimes that read the
exit code. An exit code of 1 is never used to block, because Claude Code treats it as
a non blocking error and runs the tool anyway.

The hook fails closed: in block mode a payload it cannot read, or a scanner failure,
is a deny, not an allow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from guardline.engine import ATTRIBUTION_FAMILY, CONFIG_EDIT_RULE, Scanner
from guardline.model import ENGINE_FAMILY, Finding

DENY_CODE = 2
"""The exit code that blocks a tool call when ``deny_with`` is ``exit-code``."""

MAX_LISTED = 10
"""Most findings named in a deny reason."""


@dataclass(frozen=True)
class HookResult:
    """What the hook process should do: write these streams and exit with this code."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""


def deny_reason(findings: list[Finding]) -> str:
    """Build the human readable reason for a deny. It names rules and positions, never values."""
    listed = [
        f"{f.rule_id} at {f.source} line {f.line} column {f.column}"
        # An engine finding stands for a limit, and its description names the limit.
        + (f" ({f.description.rstrip('.')})" if f.family == ENGINE_FAMILY else "")
        for f in findings
    ]
    more = len(listed) - MAX_LISTED
    text = "; ".join(listed[:MAX_LISTED]) + (f"; and {more} more" if more > 0 else "")
    reason = (
        f"guardline blocked this tool call with {len(findings)} finding(s): {text}. "
        "Remove the flagged content and retry."
    )
    if any(f.family == ATTRIBUTION_FAMILY for f in findings):
        reason += (
            " To quote a third party's attribution inside a closed fenced code block, "
            "run the hook with --allow-fenced-attribution."
        )
    if any(f.rule_id == CONFIG_EDIT_RULE for f in findings):
        reason += (
            " A guardline configuration file is protected from edits by the agent; "
            "a person can allow it by running the hook with --allow-config-edit."
        )
    return reason


def _decision(reason: str, event: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": event,
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


def _deny(reason: str, event: str, deny_with: str) -> HookResult:
    if deny_with == "exit-code":
        return HookResult(DENY_CODE, stderr=reason + "\n")
    return HookResult(0, stdout=_decision(reason, event) + "\n", stderr=reason + "\n")


def run_hook(
    stdin_text: str,
    scanner: Scanner,
    *,
    mode: str = "block",
    deny_with: str = "json",
) -> HookResult:
    """Judge one tool call payload.

    Args:
        stdin_text: the payload text read from standard input.
        scanner: the scanner to judge with.
        mode: ``block`` denies on any finding, ``report`` prints findings and allows.
        deny_with: ``json`` or ``exit-code``, the way a deny is signalled.

    Returns:
        The streams to write and the exit code to use.
    """
    event = "PreToolUse"
    if not stdin_text.strip():
        return _failure("the hook payload is empty", mode, event, deny_with)
    try:
        payload: Any = json.loads(stdin_text)
    except RecursionError:
        return _failure("the hook payload nests too deeply to parse", mode, event, deny_with)
    except json.JSONDecodeError:
        return _failure("the hook payload is not valid JSON", mode, event, deny_with)
    except Exception as error:
        name = error.__class__.__name__
        return _failure(f"the hook payload could not be read ({name})", mode, event, deny_with)
    try:
        if isinstance(payload, dict) and isinstance(payload.get("hook_event_name"), str):
            event = payload["hook_event_name"]
        findings = scanner.scan_payload(payload)
    except Exception as error:
        return _failure(f"the scanner failed ({error.__class__.__name__})", mode, event, deny_with)
    if not findings:
        return HookResult(0)
    if mode == "report":
        return HookResult(0, stderr="".join(f.format_text() + "\n" for f in findings))
    return _deny(deny_reason(findings), event, deny_with)


def _failure(message: str, mode: str, event: str, deny_with: str) -> HookResult:
    text = f"guardline could not judge this call: {message}."
    if mode == "report":
        return HookResult(0, stderr=text + "\n")
    return _deny(text + " The call is blocked rather than passed unchecked.", event, deny_with)


def startup_failure(message: str, mode: str, deny_with: str = "json") -> HookResult:
    """Return the result for a hook that could not start, such as a bad configuration."""
    return _failure(message, mode, "PreToolUse", deny_with)
