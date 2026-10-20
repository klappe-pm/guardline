"""Scanning the lines a git diff adds, against a throwaway local repository."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from guardline import Scanner
from guardline.cli import main
from guardline.diffscan import AddedFile, git_diff, parse_added_lines, scan_added
from guardline.errors import GuardlineError
from tests.samples import FAKE_TOKEN, TRAILER

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def git(repo: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603 - fixed argument list, no shell
        ["git", "-C", str(repo), "-c", "user.name=T", "-c", "user.email=t@example.com", *args],  # noqa: S607
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "keep.txt").write_text(f"old\n{TRAILER}\n", encoding="utf-8")
    git(tmp_path, "add", "keep.txt")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


DIFF = (
    "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1,0 +5,2 @@\n+one\n+two\n"
    "@@ -9 +20 @@\n-gone\n+three\n"
    "diff --git a/old.py b/old.py\n--- a/old.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n"
)


def test_parse_added_lines_maps_new_line_numbers() -> None:
    files = parse_added_lines(DIFF)
    assert files == [AddedFile("f.py", (5, 6, 20), ("one", "two", "three"))]


def test_scan_added_reports_new_file_line_numbers() -> None:
    added = [AddedFile("f.py", (10, 11), ("fine", TRAILER))]
    finding = scan_added(Scanner(), added)[0]
    assert (finding.source, finding.line) == ("f.py", 11)


def test_existing_content_is_not_reported_only_additions(repo: Path) -> None:
    (repo / "new.txt").write_text(f"a\nb\ntoken = {FAKE_TOKEN}\n", encoding="utf-8")
    git(repo, "add", "new.txt")
    findings = scan_added(Scanner(), parse_added_lines(git_diff(repo, staged=True)))
    assert {f.source for f in findings} == {"new.txt"}
    assert {f.line for f in findings} == {3}


def test_worktree_diff_and_base(repo: Path) -> None:
    (repo / "keep.txt").write_text(f"old\n{TRAILER}\nadded {TRAILER}\n", encoding="utf-8")
    worktree = parse_added_lines(git_diff(repo))
    assert [f.path for f in worktree] == ["keep.txt"]
    assert parse_added_lines(git_diff(repo, base="HEAD", paths=["keep.txt"]))[0].numbers == (3,)


def test_diff_command_exit_codes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "new.txt").write_text(f"{TRAILER}\n", encoding="utf-8")
    git(repo, "add", "new.txt")
    assert main(["diff", "--repo", str(repo), "--staged", "--no-config", "--format", "json"]) == 1
    document = json.loads(capsys.readouterr().out)
    assert document["blocked"] is True
    assert main(["diff", "--repo", str(repo), "--staged", "--no-config", "--mode", "report"]) == 0
    capsys.readouterr()
    git(repo, "commit", "-q", "-m", "more")
    assert main(["diff", "--repo", str(repo), "--staged", "--no-config"]) == 0


def test_git_diff_rejects_an_option_looking_base(repo: Path) -> None:
    with pytest.raises(GuardlineError, match="must not start with a dash"):
        git_diff(repo, base="--output=x")


def test_git_diff_outside_a_repository_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(GuardlineError, match="git diff failed"):
        git_diff(tmp_path / "nowhere")


def test_a_missing_git_binary_is_an_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(GuardlineError, match="cannot run git"):
        git_diff(tmp_path)


# the output of git diff is judged as git printed it -------------------------------------------


def test_diff_judges_a_file_with_a_byte_that_is_not_utf8(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "notes.txt").write_bytes(b"caf\xe9\nkey = " + FAKE_TOKEN.encode() + b"\n")
    git(repo, "add", "notes.txt")
    assert main(["diff", "--repo", str(repo), "--staged"]) == 1
    assert "token-github-token" in capsys.readouterr().out


def test_git_diff_returns_text_for_invalid_utf8(repo: Path) -> None:
    (repo / "notes.txt").write_bytes(b"caf\xe9\n")
    git(repo, "add", "notes.txt")
    assert "caf�" in git_diff(repo, staged=True)


@pytest.mark.skipif(shutil.which("sed") is None, reason="needs sed for the textconv driver")
def test_diff_ignores_textconv_drivers(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / ".gitattributes").write_text("*.env diff=hide\n", encoding="utf-8")
    git(repo, "config", "diff.hide.textconv", "sed s/ghp_/xxx_/")
    (repo / "app.env").write_text(f"key = {FAKE_TOKEN}\n", encoding="utf-8")
    git(repo, "add", ".gitattributes", "app.env")
    assert main(["diff", "--repo", str(repo), "--staged"]) == 1
    assert "token-github-token" in capsys.readouterr().out
