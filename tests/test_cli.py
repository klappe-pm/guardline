"""The guardline command line."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pytest

from guardline import builtin_rules
from guardline.cli import _blank_after_scissors, build_parser, main
from tests.helpers import assert_absent, manifest_hooks, pre_commit_argv
from tests.samples import AGENT, CLEAN_COMMIT, COMMIT_WITH_TRAILER, FAKE_TOKEN, TRAILER


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def invoke(*argv: str, stdin: str = "") -> tuple[int, str, str]:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return invoke


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run every CLI test from an empty directory with its own .git marker."""
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_scan_a_dirty_file_blocks_by_default(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    file = write(isolated / "msg.txt", COMMIT_WITH_TRAILER)
    code, out, _ = run("scan", str(file))
    assert code == 1
    assert "attribution-co-author-trailer" in out
    assert f"{file}:5:1:" in out


def test_report_mode_prints_and_exits_zero(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    file = write(isolated / "msg.txt", COMMIT_WITH_TRAILER)
    code, out, _ = run("scan", "--mode", "report", str(file))
    assert (code, "attribution-co-author-trailer" in out) == (0, True)


def test_a_clean_file_exits_zero_and_prints_nothing(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    file = write(isolated / "ok.txt", CLEAN_COMMIT)
    assert run("scan", str(file)) == (0, "", "")


def test_json_format(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    file = write(isolated / "msg.txt", COMMIT_WITH_TRAILER)
    code, out, _ = run("scan", "--format", "json", str(file))
    document = json.loads(out)
    assert code == 1
    assert document["blocked"] is True
    assert document["mode"] == "block"
    assert {"rule", "family", "line", "column", "offset", "source"} <= set(document["findings"][0])


def test_json_report_mode_is_not_blocked(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    file = write(isolated / "msg.txt", COMMIT_WITH_TRAILER)
    _, out, _ = run("scan", "--format", "json", "--mode", "report", str(file))
    assert json.loads(out)["blocked"] is False


def test_scan_reads_stdin(run) -> None:  # type: ignore[no-untyped-def]
    code, out, _ = run("scan", "-", stdin=TRAILER)
    assert code == 1
    assert "<stdin>:1:1:" in out
    assert run("scan", stdin=CLEAN_COMMIT)[0] == 0


def test_scan_walks_directories_and_reports_what_it_skips(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    (isolated / "pkg").mkdir()
    write(isolated / "pkg" / "a.txt", TRAILER)
    write(isolated / "pkg" / "clean.txt", CLEAN_COMMIT)
    (isolated / "pkg" / "link.txt").symlink_to(isolated / "pkg" / "a.txt")
    code, out, _ = run("scan", "--format", "json", ".")
    findings = json.loads(out)["findings"]
    assert code == 1
    skipped = {f["source"] for f in findings if f["rule"] == "guardline-file-skipped"}
    assert skipped == {str(Path("pkg") / "link.txt")}
    flagged = {f["source"] for f in findings if f["family"] == "attribution"}
    assert flagged == {str(Path("pkg") / "a.txt")}


def test_a_skipped_file_alone_fails_block_mode_and_not_report_mode(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    write(isolated / "real.txt", CLEAN_COMMIT)
    (isolated / "link.txt").symlink_to(isolated / "real.txt")
    assert run("scan", ".")[0] == 1
    assert run("scan", "--mode", "report", ".")[0] == 0
    # look-alike: the same tree without the link is clean, and a named link is read
    (isolated / "link.txt").unlink()
    assert run("scan", ".")[0] == 0
    (isolated / "link.txt").symlink_to(isolated / "real.txt")
    assert run("scan", "link.txt")[0] == 0


def test_node_modules_and_venvs_are_scanned_unless_excluded(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    for name in ("node_modules", "venv", ".venv", "__pycache__"):
        (isolated / name).mkdir()
        write(isolated / name / "b.txt", TRAILER)
    code, out, _ = run("scan", "--format", "json", ".")
    sources = {f["source"] for f in json.loads(out)["findings"]}
    assert code == 1
    assert {
        str(Path(n) / "b.txt") for n in ("node_modules", "venv", ".venv", "__pycache__")
    } <= sources
    write(
        isolated / "guardline.toml",
        'exclude = ["node_modules/*", "venv/*", ".venv/*", "__pycache__/*"]\n',
    )
    assert run("scan", ".")[0] == 0


def test_dot_git_is_the_only_directory_never_entered(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    write(isolated / ".git" / "COMMIT_EDITMSG", TRAILER)
    assert run("scan", ".")[0] == 0


def test_files_with_nul_bytes_are_scanned_with_the_nuls_removed(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    dirty = isolated / "dirty.bin"
    dirty.write_bytes(
        TRAILER.encode().replace(b"Co-", b"Co\0-").replace(AGENT.encode(), b"Cl\0aude")
    )
    assert run("scan", str(dirty))[0] == 1
    clean = isolated / "clean.bin"
    clean.write_bytes(b"\0\1\2 nothing to see \0" + CLEAN_COMMIT.encode())
    assert run("scan", str(clean))[0] == 0


def test_exclude_globs_from_config(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    write(isolated / "guardline.toml", 'exclude = ["*.md"]\n')
    write(isolated / "notes.md", TRAILER)
    assert run("scan", "notes.md")[0] == 0
    write(isolated / "notes.txt", TRAILER)
    assert run("scan", "notes.md", "notes.txt")[0] == 1


def test_oversize_file_is_reported_not_read(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    write(isolated / "guardline.toml", "max_text_chars = 50\n")
    write(isolated / "big.txt", "x" * 200)
    code, out, _ = run("scan", "big.txt")
    assert code == 1
    assert "guardline-input-too-large" in out


def test_shell_flag_judges_commands(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    script = write(isolated / "run.sh", "ls\nprintenv\n")
    code, out, _ = run("scan", "--shell", str(script))
    assert code == 1
    assert f"{script}:2:1:" in out
    assert run("scan", str(script))[0] == 0


SCISSORS_LINE = "# ------------------------ >8 ------------------------"


def test_commit_msg_keeps_comment_lines_git_keeps(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    message = write(isolated / "COMMIT_EDITMSG", f"fix: x\n\n# {TRAILER}\n")
    assert run("scan", "--commit-msg", str(message))[0] == 1
    clean = write(isolated / "MSG2", "fix: x\n\n# an ordinary comment line\n")
    assert run("scan", "--commit-msg", str(clean))[0] == 0


def test_commit_msg_ignores_only_the_diff_after_the_scissors_line(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    below = write(isolated / "M1", f"fix: x\n\n{SCISSORS_LINE}\n+{TRAILER}\n")
    assert run("scan", "--commit-msg", str(below))[0] == 0
    assert run("scan", str(below))[0] == 1
    above = write(isolated / "M2", f"fix: x\n\n{TRAILER}\n{SCISSORS_LINE}\n+ignored\n")
    assert run("scan", "--commit-msg", str(above))[0] == 1


def test_blank_after_scissors_keeps_offsets() -> None:
    text = f"a\n{SCISSORS_LINE}\r\nb"
    blanked = _blank_after_scissors(text)
    assert blanked == "a\n" + " " * len(SCISSORS_LINE) + "\r\n" + " "
    assert _blank_after_scissors("a\n# b\nc") == "a\n# b\nc"


def test_family_and_disable_options(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    file = write(isolated / "m.txt", TRAILER)
    assert run("scan", "--family", "token", str(file))[0] == 0
    code, out, _ = run(
        "scan",
        "--disable", "attribution-co-author-trailer",
        "--disable", "attribution-vendor-noreply-address",
        str(file),
    )  # fmt: skip
    assert (code, out) == (0, "")


def test_unknown_disable_is_an_error(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    file = write(isolated / "m.txt", "x")
    code, _, err = run("scan", "--disable", "no-such-rule", str(file))
    assert code == 2
    assert "no-such-rule" in err


def test_fenced_switch(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    file = write(isolated / "m.md", f"quote:\n\n```\n{TRAILER}\n```\n")
    assert run("scan", str(file))[0] == 1
    assert run("scan", "--allow-fenced-attribution", str(file))[0] == 0


def test_missing_file_is_a_usage_error(run) -> None:  # type: ignore[no-untyped-def]
    code, _, err = run("scan", "absent.txt")
    assert code == 2
    assert "cannot read" in err


def test_custom_rule_file_from_the_command_line(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    rules = write(
        isolated / "mine.toml",
        'schema_version = 1\n[[rule]]\nid = "style-no-todo"\nfamily = "style"\n'
        'description = "No TODO markers."\npattern = "TODO"\n'
        'example_fires = "TODO fix"\nexample_clean = "done"\n',
    )
    file = write(isolated / "m.txt", "TODO later")
    code, out, _ = run("scan", "--rules", str(rules), str(file))
    assert code == 1
    assert "style-no-todo" in out
    assert run("rules", "check", str(rules))[0] == 0


def test_rules_list_text_and_json(run) -> None:  # type: ignore[no-untyped-def]
    code, out, _ = run("rules", "list")
    assert code == 0
    assert len(out.splitlines()) == len(builtin_rules())
    _, js, _ = run("rules", "list", "--format", "json")
    assert len(json.loads(js)) == len(builtin_rules())
    assert all(item["builtin"] for item in json.loads(js))


def test_rules_check_builtin(run) -> None:  # type: ignore[no-untyped-def]
    assert run("rules", "check") == (0, f"ok: {len(builtin_rules())} rule(s) validated\n", "")


def test_rules_check_reports_a_bad_example(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    rules = write(
        isolated / "bad.toml",
        'schema_version = 1\n[[rule]]\nid = "style-bad"\nfamily = "style"\n'
        'description = "Bad."\npattern = "zzz"\n'
        'example_fires = "nope"\nexample_clean = "nope"\n',
    )
    code, _, err = run("rules", "check", str(rules))
    assert code == 1
    assert "style-bad" in err
    assert "nope" not in err


def test_rules_check_rejects_an_invalid_file(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    rules = write(isolated / "bad.toml", "schema_version = 9\n")
    code, _, err = run("rules", "check", str(rules))
    assert (code, "schema_version" in err) == (2, True)


def test_hook_command(run) -> None:  # type: ignore[no-untyped-def]
    body = json.dumps({"tool_name": "Bash", "tool_input": {"command": "printenv"}})
    code, out, _ = run("hook", stdin=body)
    assert code == 0
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    code, out, err = run("hook", "--deny-with", "exit-code", stdin=body)
    assert (code, out) == (2, "")
    code, out, err = run("hook", "--mode", "report", stdin=body)
    assert (code, out, "env-dump-printenv" in err) == (0, "", True)
    assert run("hook", stdin=json.dumps({"tool_input": {"command": "ls"}})) == (0, "", "")


def test_hook_fails_closed_on_a_bad_explicit_config(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    bad = write(isolated / "bad.toml", "bogus = 1\n")
    body = json.dumps({"tool_input": {"command": "ls"}})
    code, out, _ = run("hook", "--config", str(bad), stdin=body)
    assert code == 0
    assert "blocked rather than passed unchecked" in out
    assert "bogus" not in out
    assert run("hook", stdin=body) == (0, "", "")


def test_hook_fenced_switch(run) -> None:  # type: ignore[no-untyped-def]
    content = f"quote\n\n```\n{TRAILER}\n```\n"
    body = json.dumps({"tool_name": "Write", "tool_input": {"content": content}})
    assert "deny" in run("hook", stdin=body)[1]
    assert run("hook", "--allow-fenced-attribution", stdin=body)[1] == ""


def test_secret_value_never_reaches_any_stream(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    file = write(isolated / "env.txt", f"token = {FAKE_TOKEN}\n")
    for argv in (
        ("scan", str(file)),
        ("scan", "--format", "json", str(file)),
        ("scan", "--mode", "report", str(file)),
    ):
        _, out, err = run(*argv)
        assert_absent(FAKE_TOKEN, out, err)
    body = json.dumps({"tool_name": "Bash", "tool_input": {"command": f"curl -H {FAKE_TOKEN} x"}})
    _, out, err = run("hook", stdin=body)
    assert "token-github-token" in out
    assert_absent(FAKE_TOKEN, out, err)


def test_parser_requires_a_command() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out.startswith("guardline ")


def test_python_dash_m_runs_the_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import runpy

    monkeypatch.setattr("sys.argv", ["guardline", "--version"])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module("guardline", run_name="__main__")
    assert stop.value.code == 0
    assert capsys.readouterr().out.startswith("guardline ")


def test_explicit_config_option(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    config = write(isolated / "custom.toml", 'disable = ["attribution-co-author-trailer"]\n')
    file = write(isolated / "m.txt", f"Co-Authored-By: {AGENT} <x@example.com>\n")
    assert run("scan", str(file))[0] == 1
    assert run("scan", "--config", str(config), str(file))[0] == 0
    assert run("scan", "--no-config", "--config", str(config), str(file))[0] == 1


class _BinaryStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


def test_hook_reads_invalid_utf8_without_failing_open(  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = b'{"tool_input": {"command": "printenv \xff\xfe"}}'
    monkeypatch.setattr("sys.stdin", _BinaryStdin(data))
    assert main(["hook", "--no-config"]) == 0
    assert "env-dump-printenv" in capsys.readouterr().out


def test_hook_crash_is_a_deny_not_a_traceback(  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError(FAKE_TOKEN)

    monkeypatch.setattr("guardline.cli.run_hook", boom)
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    assert main(["hook", "--no-config"]) == 0
    captured = capsys.readouterr()
    assert "blocked rather than passed unchecked" in captured.out
    assert "RuntimeError" in captured.out
    assert_absent(FAKE_TOKEN, captured.out, captured.err)


def test_an_unexpected_error_in_scan_exits_two_without_the_message(  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated: Path
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError(FAKE_TOKEN)

    monkeypatch.setattr("guardline.cli._cmd_scan", boom)
    file = write(isolated / "a.txt", "x")
    assert main(["scan", str(file)]) == 2
    captured = capsys.readouterr()
    assert "internal error (RuntimeError)" in captured.err
    assert_absent(FAKE_TOKEN, captured.out, captured.err)


# a staged file name is data, never an option -------------------------------------------------


def run_precommit(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    try:
        code = main(argv)
    except SystemExit as stop:  # --help leaves through argparse with code 0
        code = int(stop.code or 0)
    capsys.readouterr()
    return code


@pytest.mark.parametrize("name", ["--mode=report", "--help", "--family=env-dump"])
def test_a_file_name_that_looks_like_an_option_cannot_change_the_scan(
    name: str,
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write(isolated / "secret.txt", f"key = {FAKE_TOKEN}\n")
    write(isolated / name, "x\n")
    argv = pre_commit_argv("guardline", [name, "secret.txt"])
    assert run_precommit(argv, monkeypatch, capsys) == 1


@pytest.mark.parametrize("name", ["--mode=report", "--help"])
def test_a_report_mode_override_keeps_the_terminator(
    name: str,
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A user's args replace the manifest's, so the init snippet has to carry the --."""
    write(isolated / "secret.txt", f"key = {FAKE_TOKEN}\n")
    write(isolated / name, "x\n")
    argv = pre_commit_argv("guardline", [name, "secret.txt"], ["--mode", "report", "--"])
    assert run_precommit(argv, monkeypatch, capsys) == 0
    assert not (isolated / "report").exists()


def test_a_file_named_dash_is_scanned_as_a_file_not_stdin(
    isolated: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(isolated / "-", f"key = {FAKE_TOKEN}\n")
    argv = pre_commit_argv("guardline", ["-"])
    assert run_precommit(argv, monkeypatch, capsys) == 1


def test_no_stdin_scans_nothing_when_no_path_is_given(
    run,
    isolated: Path,  # type: ignore[no-untyped-def]
) -> None:
    code, out, _ = run("scan", "--no-stdin", stdin=f"key = {FAKE_TOKEN}\n")
    assert (code, out) == (0, "")


def test_stdin_is_still_the_default_without_no_stdin(run) -> None:  # type: ignore[no-untyped-def]
    code, out, _ = run("scan", "-", stdin=f"key = {FAKE_TOKEN}\n")
    assert code == 1
    assert "token-github-token" in out


def test_both_hooks_end_their_options_and_ignore_stdin() -> None:
    hooks = manifest_hooks()
    for hook_id in ("guardline", "guardline-commit-msg"):
        hook = hooks[hook_id]
        assert "--no-stdin" in hook["entry"], hook_id
        assert hook["args"] == ["--"], hook_id


def test_the_file_hook_does_not_filter_on_the_text_tag() -> None:
    """pre-commit's identify tags a file with a NUL byte, or a .pdf name, as binary.

    guardline strips NUL and decodes with replacement precisely so that such files are
    judged, so the hook must not hand it only the files tagged as text.
    """
    types = manifest_hooks()["guardline"]["types"]
    assert "text" not in types
    assert types == ["file"]


def all_parsers(parser: argparse.ArgumentParser) -> list[argparse.ArgumentParser]:
    found = [parser]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                found.extend(all_parsers(child))
    return found


def test_no_parser_accepts_an_abbreviated_option() -> None:
    parsers = all_parsers(build_parser())
    assert len(parsers) >= 10
    assert [p.prog for p in parsers if p.allow_abbrev] == []


@pytest.mark.parametrize(
    "argv",
    [
        ["scan", "--mod", "report"],
        ["scan", "--fam", "token"],
        ["hook", "--deny", "exit-code"],
        ["diff", "--stag"],
        ["rules", "list", "--form", "json"],
        ["config", "show", "--form", "json"],
        ["init", "--yes", "--for"],
    ],
)
def test_an_abbreviated_option_is_a_usage_error(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stop:
        main(argv)
    assert stop.value.code == 2
    capsys.readouterr()


# rules check reports a custom pattern with an unbounded repeat ---------------------------------


def test_rules_check_warns_about_an_unbounded_repeat_but_still_passes(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    rules = write(
        isolated / "house.toml",
        'schema_version = 1\n[[rule]]\nid = "house-word"\nfamily = "house"\n'
        'description = "A word."\npattern = "[a-z]+;"\n'
        'example_fires = "ab;"\nexample_clean = "ab"\n',
    )
    code, out, err = run("rules", "check", str(rules))
    assert code == 0
    assert out == "ok: 1 rule(s) validated\n"
    assert "warning: rule house-word: pattern has an unbounded repeat" in err


def test_rules_check_on_the_built_in_rules_prints_no_warning(run) -> None:  # type: ignore[no-untyped-def]
    assert run("rules", "check")[2] == ""


# a family choice that leaves no rule for file text ---------------------------------------------


def test_a_file_scan_with_no_text_rule_is_a_configuration_error(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    file = write(isolated / "s.txt", f"key = {FAKE_TOKEN}\n")
    code, out, err = run("scan", "--no-config", "--family", "env-dump", "--no-stdin", str(file))
    assert (code, out) == (2, "")
    assert "no active rule judges text" in err
    assert FAKE_TOKEN not in err


def test_the_pre_commit_file_hooks_fail_when_the_configuration_leaves_no_text_rule(  # type: ignore[no-untyped-def]
    run, isolated: Path
) -> None:
    write(isolated / "guardline.toml", 'families = ["env-dump"]\n')
    file = write(isolated / "s.txt", f"key = {FAKE_TOKEN}\n")
    for extra in ((), ("--commit-msg",)):
        code, _, err = run("scan", "--mode", "block", "--no-stdin", *extra, "--", str(file))
        assert code == 2, extra
        assert "no active rule judges text" in err


def test_a_shell_scan_needs_no_text_rule(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    file = write(isolated / "c.sh", "printenv\n")
    code, out, _ = run("scan", "--no-config", "--family", "env-dump", "--shell", str(file))
    assert code == 1
    assert "env-dump-printenv" in out


def test_a_scan_with_a_text_rule_is_unchanged(run, isolated: Path) -> None:  # type: ignore[no-untyped-def]
    file = write(isolated / "s.txt", f"key = {FAKE_TOKEN}\n")
    code, out, _ = run("scan", "--no-config", "--family", "token", "--no-stdin", str(file))
    assert (code, "token-github-token" in out) == (1, True)
