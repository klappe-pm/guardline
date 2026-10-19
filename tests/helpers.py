"""Small helpers shared by the tests."""

from __future__ import annotations

import pytest


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
