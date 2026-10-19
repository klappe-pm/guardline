"""Scan the lines a git diff adds.

Only added lines are judged, so existing content is not reported again. Findings are
mapped back to the line numbers of the new file. The module runs ``git`` with an
argument list, never through a shell, and never contacts a remote.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from guardline.engine import Scanner
from guardline.errors import GuardlineError
from guardline.model import Finding

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
GIT_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class AddedFile:
    """The lines a diff adds to one file: their new line numbers and their text."""

    path: str
    numbers: tuple[int, ...]
    lines: tuple[str, ...]


def parse_added_lines(diff_text: str) -> list[AddedFile]:
    """Parse ``git diff --unified=0`` output into the added lines of each file."""
    files: list[AddedFile] = []
    path: str | None = None
    numbers: list[int] = []
    lines: list[str] = []
    new_line = 0

    def flush() -> None:
        if path is not None and lines:
            files.append(AddedFile(path, tuple(numbers), tuple(lines)))

    in_header = False
    old_seen = False
    for raw in diff_text.split("\n"):
        if raw.startswith("diff --git "):
            flush()
            path, numbers, lines = None, [], []
            in_header, old_seen = True, False
        elif in_header:
            if raw.startswith("--- "):
                old_seen = True
            elif raw.startswith("+++ ") and old_seen:
                target = raw[4:].split("\t", 1)[0]
                path = None if target == "/dev/null" else target.removeprefix("b/")
            elif raw.startswith("@@"):
                in_header = False
                match = _HUNK.match(raw)
                new_line = int(match.group(1)) if match else 0
        elif raw.startswith("@@"):
            match = _HUNK.match(raw)
            new_line = int(match.group(1)) if match else 0
        elif raw.startswith("+") and path is not None:
            numbers.append(new_line)
            lines.append(raw[1:])
            new_line += 1
    flush()
    return files


def git_diff(
    repo: Path,
    *,
    staged: bool = False,
    base: str | None = None,
    paths: Sequence[str] = (),
) -> str:
    """Run ``git diff`` and return its output.

    Raises:
        GuardlineError: git is missing, the directory is not a repository, or the
            base looks like an option.
    """
    if base is not None and base.startswith("-"):
        raise GuardlineError("the base revision must not start with a dash")
    command = ["git", "-C", str(repo), "-c", "core.quotepath=off", "diff", "--no-color"]
    command += ["--no-ext-diff", "--unified=0", "--text"]
    if staged:
        command.append("--cached")
    if base is not None:
        command.append(base)
    command.append("--")
    command.extend(paths)
    try:
        done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            command, capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise GuardlineError(f"cannot run git: {error.__class__.__name__}") from None
    if done.returncode != 0:
        raise GuardlineError("git diff failed; is this a git repository and is the base valid?")
    return done.stdout


def scan_added(scanner: Scanner, added: Sequence[AddedFile]) -> list[Finding]:
    """Scan added lines per file and report findings at their new file line numbers."""
    findings: list[Finding] = []
    for item in added:
        text = "\n".join(item.lines)
        for finding in scanner.scan_text(text, item.path):
            index = min(finding.line, len(item.numbers)) - 1
            findings.append(
                Finding(
                    finding.rule_id,
                    finding.family,
                    finding.description,
                    finding.source,
                    finding.offset,
                    item.numbers[index],
                    finding.column,
                )
            )
    return findings
