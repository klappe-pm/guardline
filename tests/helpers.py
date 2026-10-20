"""Small helpers shared by the tests."""

from __future__ import annotations

import shlex
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import pytest

T = TypeVar("T")
MANIFEST = Path(__file__).resolve().parents[1] / ".pre-commit-hooks.yaml"


def assert_absent(secret: str, *outputs: str) -> None:
    """Fail without echoing ``secret`` when it appears in any of ``outputs``.

    A plain ``assert secret not in output`` would print both operands on failure,
    which is exactly the leak this suite guards against.
    """
    for output in outputs:
        if secret in output:
            pytest.fail("a matched value appeared in an output stream")


def rule_ids(findings: list) -> set[str]:  # type: ignore[type-arg]
    """Return the set of rule ids in a list of findings."""
    return {finding.rule_id for finding in findings}


def manifest_hooks() -> dict[str, dict[str, list[str]]]:
    """Read ``.pre-commit-hooks.yaml`` into a map of hook id to its entry, args and types.

    The file is small and flat, so a line reader is enough and keeps the suite free of a
    YAML dependency.
    """
    hooks: dict[str, dict[str, list[str]]] = {}
    current: dict[str, list[str]] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        key, _, value = line.lstrip("- ").partition(":")
        value = value.strip()
        if line.startswith("- id:"):
            current = hooks.setdefault(value, {"entry": [], "args": [], "types": []})
        elif key == "entry":
            current["entry"] = shlex.split(value)
        elif key in ("args", "types"):
            items = value.strip("[]").split(",")
            current[key] = [item.strip().strip("\"'") for item in items if item.strip()]
    return hooks


def pre_commit_argv(hook_id: str, files: list[str], args: list[str] | None = None) -> list[str]:
    """Return the arguments pre-commit gives ``guardline``: entry, then args, then file names.

    ``args`` stands for a user's ``args:`` override, which replaces the manifest's own.
    """
    hook = manifest_hooks()[hook_id]
    assert hook["entry"][0] == "guardline"
    return [*hook["entry"][1:], *(hook["args"] if args is None else args), *files]


def call_within(seconds: float, call: Callable[[], T]) -> T:
    """Run ``call`` and return its result, failing the test if it does not return in time.

    Used for code that must not block on a FIFO. The call runs in a daemon thread, so a
    regression fails the test instead of hanging the whole suite.
    """
    outcome: dict[str, object] = {}

    def target() -> None:
        try:
            outcome["value"] = call()
        except BaseException as error:
            outcome["error"] = error

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        pytest.fail(f"the call did not return within {seconds} seconds")
    if "error" in outcome:
        raise outcome["error"]  # type: ignore[misc]
    return outcome["value"]  # type: ignore[return-value]
