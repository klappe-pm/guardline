"""One input, one verdict: the hook, the scan, the diff and the API must agree."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from guardline import Scanner, scan_text
from guardline.cli import main
from guardline.hook import run_hook
from tests.samples import (
    CLEAN_COMMIT,
    COMMIT_WITH_TRAILER,
    ENV_DUMP_COMMANDS,
    ENV_SAFE_COMMANDS,
    FAKE_TOKEN,
    FOOTER,
    PERMALINK,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

TEXTS = [
    COMMIT_WITH_TRAILER,
    CLEAN_COMMIT,
    f"notes\n\n{FOOTER}\n",
    f"see {PERMALINK}\n",
    f"export T={FAKE_TOKEN}\n",
    "plain text with nothing in it\n",
]


def blocked_by_hook(text: str) -> bool:
    payload = json.dumps({"tool_name": "Write", "tool_input": {"content": text}})
    return "permissionDecision" in run_hook(payload, Scanner()).stdout


@pytest.mark.parametrize("text", TEXTS)
def test_api_hook_and_cli_scan_agree_on_text(
    text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    file = tmp_path / "input.txt"
    file.write_text(text, encoding="utf-8")
    api = bool(scan_text(text))
    assert blocked_by_hook(text) is api
    assert (main(["scan", str(file)]) == 1) is api


@pytest.mark.parametrize("text", TEXTS)
def test_the_same_rules_fire_through_the_hook_and_the_api(text: str) -> None:
    expected = {f.rule_id for f in scan_text(text)}
    payload = {"tool_name": "Write", "tool_input": {"content": text}}
    assert {f.rule_id for f in Scanner().scan_payload(payload)} == expected


@pytest.mark.parametrize("command", [*ENV_DUMP_COMMANDS, *ENV_SAFE_COMMANDS])
def test_commands_agree_between_the_hook_and_a_shell_scan(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "script.sh"
    script.write_text(command + "\n", encoding="utf-8")
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    hook_blocks = "permissionDecision" in run_hook(payload, Scanner()).stdout
    assert (main(["scan", "--shell", str(script)]) == 1) is hook_blocks


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_diff_scan_agrees_with_the_file_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def git(*args: str) -> None:
        subprocess.run(  # noqa: S603 (fixed argument list, no shell)
            ["git", "-C", str(tmp_path), *args],  # noqa: S607
            check=True,
            capture_output=True,
        )

    git("init", "-q", "-b", "main")
    git("config", "user.name", "T")
    git("config", "user.email", "t@example.com")
    monkeypatch.chdir(tmp_path)
    for index, text in enumerate(TEXTS):
        file = tmp_path / f"f{index}.txt"
        file.write_text(text, encoding="utf-8")
        git("add", file.name)
        scan_code = main(["scan", file.name])
        capsys.readouterr()
        diff_code = main(["diff", "--repo", str(tmp_path), "--staged", "--", file.name])
        capsys.readouterr()
        assert scan_code == diff_code, f"input {index} disagrees"
        git("commit", "-q", "-m", "x")


def hook_entries() -> list[tuple[str, list[str]]]:
    entries: list[tuple[str, list[str]]] = []
    current = ""
    for line in (REPO_ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("- id:"):
            current = line.split(":", 1)[1].strip()
        elif line.strip().startswith("entry:"):
            entries.append((current, shlex.split(line.split(":", 1)[1].strip())))
    return entries


def test_pre_commit_hooks_file_lists_both_hooks() -> None:
    assert [name for name, _ in hook_entries()] == ["guardline", "guardline-commit-msg"]


@pytest.mark.parametrize(("name", "entry"), hook_entries())
def test_each_pre_commit_entry_runs_the_installed_command(
    name: str, entry: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    assert entry[0] == "guardline"
    dirty = tmp_path / "dirty.txt"
    dirty.write_text(COMMIT_WITH_TRAILER, encoding="utf-8")
    clean = tmp_path / "clean.txt"
    clean.write_text(CLEAN_COMMIT, encoding="utf-8")
    assert main([*entry[1:], str(dirty)]) == 1
    assert main([*entry[1:], str(clean)]) == 0
