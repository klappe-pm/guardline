"""Small helpers shared by the tests."""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest

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
