"""The opt-in exemption for a session link recorded as a document's provenance field."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from guardline import Scanner
from guardline.cli import main


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def invoke(*argv: str, stdin: str = "") -> tuple[int, str, str]:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return invoke


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path

# Built from escapes so the repository's own self scan never sees a real session link.
LINK = "https://\u0063laude.ai/code/session_01AbCdEfGhIj"
FRONTMATTER = f'---\nmodels: [m]\nsession-link: "{LINK}"\n---\n\n# Note\n'


def ids(findings):  # type: ignore[no-untyped-def]
    return [finding.rule_id for finding in findings]


def test_off_by_default() -> None:
    assert "attribution-session-permalink" in ids(Scanner().scan_text(FRONTMATTER, "docs/a.md"))


def test_field_allowed_in_docs_and_local_markdown() -> None:
    scanner = Scanner(allow_session_link_field=True)
    for source in ("docs/a.md", "repo/docs/plans/b.md", "local/handoff.md", "docs/c.mdx", "<text>", "tool_input.content"):
        assert scanner.scan_text(FRONTMATTER, source) == [], source
    assert scanner.scan_text(f"session-link: {LINK}\n", "docs/bare.md") == []


def test_field_refused_outside_docs_and_local_or_outside_markdown() -> None:
    scanner = Scanner(allow_session_link_field=True)
    for source in ("README.md", "src/notes.md", "docs/config.yaml", "local/run.txt"):
        assert "attribution-session-permalink" in ids(scanner.scan_text(FRONTMATTER, source)), source


def test_only_the_whole_key_line_qualifies() -> None:
    scanner = Scanner(allow_session_link_field=True)
    for text in (
        f"See {LINK} for context.\n",
        f"  session-link: {LINK}\n",
        f"session-link: {LINK} and more\n",
        f"note: session-link: {LINK}\n",
        f"other-link: {LINK}\n",
    ):
        assert "attribution-session-permalink" in ids(scanner.scan_text(text, "docs/a.md")), text


def test_other_attribution_rules_still_fire_in_the_same_file() -> None:
    scanner = Scanner(allow_session_link_field=True)
    trailer = "\u0043o-Authored-By: \u0043laude <noreply@\u0061nthropic.com>"
    found = ids(scanner.scan_text(FRONTMATTER + f"\n{trailer}\n", "docs/a.md"))
    assert "attribution-session-permalink" not in found
    assert any(rule.startswith("attribution-") for rule in found)


def test_commands_never_qualify() -> None:
    scanner = Scanner(allow_session_link_field=True)
    assert "attribution-session-permalink" in ids(scanner.scan_command(f"git commit -m 'session-link: {LINK}'"))


def test_cli_scan_and_hook_switch(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    docs = isolated / "docs"
    docs.mkdir()
    note = docs / "note.md"
    note.write_text(FRONTMATTER, encoding="utf-8")
    assert run("scan", str(note))[0] == 1
    assert run("scan", "--allow-session-link-field", str(note))[0] == 0
    readme = isolated / "README.md"
    readme.write_text(FRONTMATTER, encoding="utf-8")
    assert run("scan", "--allow-session-link-field", str(readme))[0] == 1
    body = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(note), "content": FRONTMATTER}})
    assert "deny" in run("hook", stdin=body)[1]
    assert run("hook", "--allow-session-link-field", stdin=body)[1] == ""


def test_diff_switch(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    git = lambda *args: subprocess.run(["git", "-C", str(isolated), *args], check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base")
    (isolated / "docs").mkdir()
    (isolated / "docs" / "note.md").write_text(FRONTMATTER, encoding="utf-8")
    git("add", "-A")
    assert run("diff", "--repo", str(isolated), "--base", "HEAD", "--staged")[0] == 1
    assert run("diff", "--repo", str(isolated), "--base", "HEAD", "--staged", "--allow-session-link-field")[0] == 0
