"""Shared test configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ONLY = (".github", "docs", "CONTRIBUTING.md")
"""Paths that exist in a clone but not in the source distribution."""


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip the tests marked `repo_only` when the repository files they read are absent.

    The source distribution carries the package and its tests but not `.github/`, `docs/` or the
    community files, so a suite run from an extracted sdist must not fail on their absence.
    """
    missing = [name for name in REPOSITORY_ONLY if not (ROOT / name).exists()]
    if not missing:
        return
    skip = pytest.mark.skip(reason=f"the source distribution omits {', '.join(missing)}")
    for item in items:
        if "repo_only" in item.keywords:
            item.add_marker(skip)
