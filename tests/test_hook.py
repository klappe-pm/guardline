"""The agent runtime hook."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from guardline import Scanner
from guardline.cli import main
from guardline.engine import DEFAULT_MAX_TEXT_CHARS
from guardline.hook import HookResult, deny_reason, run_hook, startup_failure
from tests.helpers import assert_absent
from tests.samples import FAKE_TOKEN, TRAILER


def payload(**tool_input: object) -> str:
    return json.dumps(
        {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": tool_input}
    )


def test_a_clean_call_is_allowed_silently() -> None:
    assert run_hook(payload(command="ls -la"), Scanner()) == HookResult(0)


def test_empty_input_is_denied_in_block_mode_and_only_reported_in_report_mode() -> None:
    assert "the hook payload is empty" in run_hook("  \n", Scanner()).stdout
    assert json.loads(run_hook("", Scanner()).stdout)
    reported = run_hook("", Scanner(), mode="report")
    assert (reported.exit_code, reported.stdout) == (0, "")
    assert "payload is empty" in reported.stderr


def test_a_dump_is_denied_with_json_and_exit_zero() -> None:
    result = run_hook(payload(command="printenv"), Scanner())
    assert result.exit_code == 0
    decision = json.loads(result.stdout)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    assert "env-dump-printenv" in decision["permissionDecisionReason"]


def test_exit_code_style_denies_with_two_and_empty_stdout() -> None:
    result = run_hook(payload(command="printenv"), Scanner(), deny_with="exit-code")
    assert (result.exit_code, result.stdout) == (2, "")
    assert "env-dump-printenv" in result.stderr


def test_a_deny_never_uses_exit_one() -> None:
    for deny_with in ("json", "exit-code"):
        assert run_hook(payload(command="env"), Scanner(), deny_with=deny_with).exit_code != 1


def test_report_mode_allows_and_prints_findings() -> None:
    result = run_hook(payload(command="printenv"), Scanner(), mode="report")
    assert (result.exit_code, result.stdout) == (0, "")
    assert "env-dump-printenv" in result.stderr


def test_event_name_follows_the_payload() -> None:
    body = json.dumps({"hook_event_name": "Other", "tool_input": {"command": "env"}})
    decision = json.loads(run_hook(body, Scanner()).stdout)["hookSpecificOutput"]
    assert decision["hookEventName"] == "Other"


def test_unreadable_payload_fails_closed_in_block_mode() -> None:
    result = run_hook("{not json", Scanner())
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "blocked rather than passed unchecked" in result.stdout


def test_unreadable_payload_is_only_reported_in_report_mode() -> None:
    result = run_hook("{not json", Scanner(), mode="report")
    assert (result.exit_code, result.stdout) == (0, "")
    assert "not valid JSON" in result.stderr


def test_a_scanner_crash_fails_closed() -> None:
    class Broken(Scanner):
        def scan_payload(self, payload: object) -> list:  # type: ignore[type-arg]
            raise RuntimeError(FAKE_TOKEN)

    result = run_hook(payload(command="ls"), Broken())
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "RuntimeError" in result.stdout
    assert_absent(FAKE_TOKEN, result.stdout, result.stderr)


def test_startup_failure_denies_in_block_mode_and_reports_in_report_mode() -> None:
    assert json.loads(startup_failure("bad config", "block").stdout)
    assert startup_failure("bad config", "report").exit_code == 0
    assert startup_failure("bad config", "block", "exit-code").exit_code == 2


def test_deny_reason_lists_ten_findings_and_counts_the_rest() -> None:
    findings = Scanner().scan_text((TRAILER + "\n") * 6)
    reason = deny_reason(findings)
    assert "and 2 more" in reason
    assert "--allow-fenced-attribution" in reason


@pytest.mark.parametrize("field", ["content", "new_string", "body", "message"])
def test_text_fields_are_judged(field: str) -> None:
    result = run_hook(payload(**{field: TRAILER}), Scanner())
    assert "attribution-co-author-trailer" in result.stdout


# the hook through the command line ---------------------------------------------------------


def run_hook_command(
    argv: list[str],
    stdin: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str]:
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    code = main(["hook", *argv])
    return code, capsys.readouterr().out


def test_the_hook_denies_when_its_config_leaves_no_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "guardline.toml"
    config.write_text('mode = "block"\nfamilies = []\n', encoding="utf-8")
    code, out = run_hook_command(
        ["--config", str(config)], payload(command=f"echo {FAKE_TOKEN}"), monkeypatch, capsys
    )
    assert code == 0
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "ConfigError" in out


def test_the_hook_denies_when_its_config_disables_every_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from guardline import builtin_rules

    ids = ", ".join(f'"{rule.id}"' for rule in builtin_rules())
    config = tmp_path / "guardline.toml"
    config.write_text(f'mode = "block"\ndisable = [{ids}]\n', encoding="utf-8")
    _, out = run_hook_command(
        ["--config", str(config)], payload(command=f"echo {FAKE_TOKEN}"), monkeypatch, capsys
    )
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


# rule files named by the hook's configuration are protected --------------------------------

HOUSE_RULES = (
    'schema_version = 1\n[[rule]]\nid = "house-codename"\nfamily = "house"\n'
    'description = "Internal codename."\npattern = "bluefalcon"\n'
    'example_fires = "bluefalcon"\nexample_clean = "redfalcon"\n'
)


def rule_file_setup(tmp_path: Path) -> tuple[Path, Path]:
    rule = tmp_path / "house.toml"
    rule.write_text(HOUSE_RULES, encoding="utf-8")
    config = tmp_path / "guardline.toml"
    config.write_text('mode = "block"\nrule_files = ["house.toml"]\n', encoding="utf-8")
    return config, rule


def edit_payload(target: Path) -> str:
    return json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(target),
                "old_string": "Internal codename.",
                "new_string": "Nothing.",
            },
        }
    )


def test_the_hook_protects_the_rule_files_its_config_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config, rule = rule_file_setup(tmp_path)
    _, out = run_hook_command(["--config", str(config)], edit_payload(rule), monkeypatch, capsys)
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "guardline-config-edit" in out


def test_a_person_can_lift_the_rule_file_protection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config, rule = rule_file_setup(tmp_path)
    argv = ["--config", str(config), "--allow-config-edit"]
    _, out = run_hook_command(argv, edit_payload(rule), monkeypatch, capsys)
    assert out == ""


def test_a_file_the_config_does_not_name_stays_editable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config, _ = rule_file_setup(tmp_path)
    other = tmp_path / "notes.toml"
    other.write_text("x = 1\n", encoding="utf-8")
    _, out = run_hook_command(["--config", str(config)], edit_payload(other), monkeypatch, capsys)
    assert out == ""


# a path that never produces data cannot hang the hook ---------------------------------------


def hook_process(option: str, path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (fixed argument list, no shell)
        [sys.executable, "-m", "guardline", "hook", option, str(path)],
        input=payload(command="ls"),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a FIFO")
@pytest.mark.parametrize("option", ["--config", "--rules"])
def test_a_fifo_named_by_the_hook_is_denied_without_hanging(tmp_path: Path, option: str) -> None:
    fifo = tmp_path / "named.toml"
    os.mkfifo(fifo)
    try:
        done = hook_process(option, fifo)
    except subprocess.TimeoutExpired:
        pytest.fail(f"the hook blocked reading a FIFO named by {option}")
    assert json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


# the deny message says which limit was hit ----------------------------------------------------


def reason_of(result: HookResult) -> str:
    return str(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"])


def test_an_oversize_deny_says_which_limit() -> None:
    result = run_hook(payload(command="ls " + "a" * 70_000), Scanner())
    assert "longer than 65536 characters" in reason_of(result)


def test_a_finding_from_a_rule_is_named_by_id_and_position_only() -> None:
    result = run_hook(payload(command="printenv"), Scanner())
    reason = reason_of(result)
    assert "env-dump-printenv at tool_input.command line 1 column 1" in reason
    assert "line 1 column 1." in reason


def test_a_deeply_nested_payload_is_named_as_such() -> None:
    stdin = '{"tool_name": "Bash", "tool_input": {"x": ' + "[" * 5000 + "1" + "]" * 5000 + "}}"
    reason = reason_of(run_hook(stdin, Scanner()))
    assert "nests too deeply to parse" in reason
    assert "scanner failed" not in reason


def test_a_parser_failure_other_than_bad_json_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(text: str) -> object:
        raise MemoryError

    monkeypatch.setattr("guardline.hook.json.loads", explode)
    result = run_hook(payload(command="ls"), Scanner())
    monkeypatch.undo()
    assert '"deny"' in result.stdout
    assert "could not be read (MemoryError)" in reason_of(result)


# the whole payload is bounded before it is parsed -----------------------------------------------


def test_a_payload_over_the_size_limit_is_refused_before_parsing() -> None:
    stdin = payload(command="ls", filler="a" * (8 * DEFAULT_MAX_TEXT_CHARS))
    started = time.perf_counter()
    result = run_hook(stdin, Scanner())
    assert time.perf_counter() - started < 0.5
    assert '"deny"' in result.stdout
    assert f"longer than {4 * DEFAULT_MAX_TEXT_CHARS} bytes" in reason_of(result)


def test_a_payload_over_the_limit_in_bytes_but_not_in_characters_is_refused() -> None:
    limit = 4 * DEFAULT_MAX_TEXT_CHARS
    body = {"command": "ls", "filler": "é" * (limit // 2 + 1)}
    stdin = json.dumps({"tool_name": "Bash", "tool_input": body}, ensure_ascii=False)
    assert len(stdin) < limit < len(stdin.encode("utf-8"))
    assert f"longer than {limit} bytes" in reason_of(run_hook(stdin, Scanner(), mode="block"))


def test_a_payload_at_the_limit_is_still_judged() -> None:
    limit = 4 * DEFAULT_MAX_TEXT_CHARS
    stdin = payload(command="ls")
    assert len(stdin) < limit
    assert run_hook(stdin, Scanner()) == HookResult(0)


def test_the_command_line_reads_only_a_bounded_amount_of_standard_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    limit = 4 * DEFAULT_MAX_TEXT_CHARS
    requested: list[int] = []

    class Pipe:
        def __init__(self, data: bytes) -> None:
            self.data = data

        def read(self, size: int = -1) -> bytes:
            requested.append(size)
            return self.data if size < 0 else self.data[:size]

    class Stdin:
        buffer = Pipe(b"{" + b" " * (8 * DEFAULT_MAX_TEXT_CHARS) + b"}")

    monkeypatch.setattr("sys.stdin", Stdin())
    assert main(["hook", "--no-config"]) == 0
    assert requested == [limit + 1]
    assert "longer than" in reason_of(HookResult(0, capsys.readouterr().out))
