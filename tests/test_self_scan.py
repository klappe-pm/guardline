"""Guardline finds nothing in its own repository: no complete credential, no agent credit."""

from __future__ import annotations

from pathlib import Path

import pytest

from guardline import Scanner
from tests.conftest import ROOT

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def repository_text_files() -> list[Path]:
    suffixes = {".md", ".py", ".toml", ".yaml", ".yml", ".cfg", ".txt", ".gitignore", ""}
    found = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or SKIP_DIRS & set(path.relative_to(ROOT).parts):
            continue
        if path.suffix in suffixes and path.stat().st_size < 1_000_000:
            found.append(path)
    return found


FILES = repository_text_files()


@pytest.mark.parametrize("path", FILES, ids=[p.relative_to(ROOT).as_posix() for p in FILES])
def test_guardline_finds_nothing_in_its_own_repository(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    scanner = Scanner(allow_fenced_attribution=True, families=["attribution", "token"])
    findings = scanner.scan_text(text, str(path.relative_to(ROOT)))
    if findings:
        pytest.fail(f"{path.relative_to(ROOT)} holds {sorted({f.rule_id for f in findings})}")
