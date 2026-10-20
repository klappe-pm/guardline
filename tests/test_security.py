"""Security properties: no value echo, bounded work, fail closed, documented bypasses."""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest

from guardline import Finding, Scanner, builtin_rules, scan_command, scan_payload, scan_text
from guardline.cli import main
from guardline.hook import run_hook
from guardline.model import Rule
from tests.helpers import assert_absent
from tests.samples import (
    AGENT,
    FAKE_AWS,
    FAKE_JWT,
    FAKE_PEM,
    FAKE_TOKEN,
    FOOTER,
    TRAILER,
)

SECRETS = {
    "github": FAKE_TOKEN,
    "aws": FAKE_AWS,
    "jwt": FAKE_JWT,
    "assignment": "Zq9Xk2Zq9Xk2Zq9Xk2Zq",
    "hex": "0123456789abcdef0123456789abcdef",
    "bearer": "abcdefghijklmnopqrstuvwxyz0123",
}


def contexts(secret: str) -> list[str]:
    return [
        f"token = {secret}\n",
        f"x {secret} y",
        f"curl -H 'Authorization: Bearer {secret}' host",
        f"secret: {secret}",
        f"key={secret}",
    ]


@pytest.mark.parametrize("name", sorted(SECRETS))
def test_findings_never_contain_the_matched_value(name: str) -> None:
    secret = SECRETS[name]
    seen = 0
    for context in contexts(secret):
        for finding in [*scan_text(context), *scan_command(context)]:
            seen += 1
            assert_absent(
                secret, repr(finding), finding.format_text(), json.dumps(finding.to_dict())
            )
    assert seen > 0


@pytest.mark.parametrize("name", sorted(SECRETS))
def test_hook_cli_and_reports_never_echo_the_value(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = SECRETS[name]
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    file = tmp_path / "leak.txt"
    file.write_text(f"token = {secret}\n", encoding="utf-8")
    body = json.dumps({"tool_name": "Bash", "tool_input": {"command": f"echo {secret}"}})
    write = json.dumps({"tool_name": "Write", "tool_input": {"content": f"token = {secret}"}})
    for argv in (
        ["scan", str(file)],
        ["scan", "--format", "json", str(file)],
        ["scan", "--shell", str(file)],
        ["scan", "--mode", "report", str(file)],
    ):
        main(argv)
        captured = capsys.readouterr()
        assert_absent(secret, captured.out, captured.err)
    for stdin in (body, write):
        for mode in ("block", "report"):
            for deny_with in ("json", "exit-code"):
                result = run_hook(stdin, Scanner(), mode=mode, deny_with=deny_with)
                assert_absent(secret, result.stdout, result.stderr)
    monkeypatch.setattr("sys.stdin", io.StringIO(body))
    main(["hook"])
    captured = capsys.readouterr()
    assert_absent(secret, captured.out, captured.err)


def test_an_exception_message_does_not_carry_the_value() -> None:
    class Boom(Scanner):
        def scan_payload(self, payload: object) -> list[Finding]:
            raise ValueError(FAKE_TOKEN)

    result = run_hook(json.dumps({"tool_input": {"command": "x"}}), Boom())
    assert_absent(FAKE_TOKEN, result.stdout, result.stderr)


def test_the_rule_for_a_value_is_named_by_kind() -> None:
    finding = scan_text(f"export T={FAKE_TOKEN}")[0]
    assert finding.rule_id == "token-github-token"
    assert FAKE_PEM not in repr(scan_text(FAKE_PEM))


# bounded work --------------------------------------------------------------------

BIG = 600_000
TIME_LIMIT_SECONDS = 5.0

ADVERSARIAL_TEXT = {
    "jwt-heads": "eyJ " * (BIG // 4),
    "jwt-dots": "eyJaaaaa." * (BIG // 9),
    "keyword-flood": "KEY" * (BIG // 3),
    "assignments": "key=A" * (BIG // 5),
    "one-long-word": "a" * BIG,
    "sk-flood": "sk-" * (BIG // 3),
    "trailer-flood": "Co-Authored-By: " * (BIG // 16),
    "bracket-flood": "[Claude " * (BIG // 8),
    "generated-flood": "Generated  " * (BIG // 11),
    "sentence-flood": ".  " * (BIG // 3) + "Created by",
    "quote-flood": "'" * BIG,
    "github-pat-flood": "github_pat_" * (BIG // 11),
    "keyword-then-long-hex": "key" + "a" * BIG,
    "unclosed-link": "[x](https://" + "a." * (BIG // 2),
    "noreply-flood": "noreply@" * (BIG // 8),
    "bearer-flood": "Bearer " * (BIG // 7),
}


@pytest.mark.parametrize("name", sorted(ADVERSARIAL_TEXT))
def test_large_adversarial_text_finishes_quickly(name: str) -> None:
    text = ADVERSARIAL_TEXT[name][:BIG]
    started = time.perf_counter()
    scan_text(text)
    assert time.perf_counter() - started < TIME_LIMIT_SECONDS


ADVERSARIAL_COMMANDS = {
    "env-flood": "env " * 15000,
    "quote-flood": "'" * 60000,
    "paren-flood": "(" * 30000,
    "dollar-paren-flood": "$(" * 30000,
    "nested-bash": "bash -c '" * 5000,
    "pipe-flood": "a|" * 30000,
    "backtick-flood": "echo `" * 10000,
    "heredoc-flood": "cat <<E\n" * 8000,
    "sudo-flood": "sudo " * 12000,
}


@pytest.mark.parametrize("name", sorted(ADVERSARIAL_COMMANDS))
def test_large_adversarial_commands_finish_quickly(name: str) -> None:
    started = time.perf_counter()
    scan_command(ADVERSARIAL_COMMANDS[name][:65000])
    assert time.perf_counter() - started < TIME_LIMIT_SECONDS


def _variants(rule: Rule) -> list[str]:
    example = rule.example_fires
    pieces = [example, example[:-1], example[: max(1, len(example) // 2)], example[1:]]
    size = 300_000 if rule.scope == "text" else 30_000
    joiners = ["\n", ""] if rule.scope == "text" else [" ", ";"]
    return [
        (piece + joiner) * (size // (len(piece) + len(joiner)))
        for piece in pieces
        for joiner in joiners
    ]


@pytest.mark.parametrize("rule", builtin_rules(), ids=lambda rule: rule.id)
def test_each_rule_is_linear_on_inputs_built_from_its_own_example(rule: Rule) -> None:
    scanner = Scanner([rule])
    run = scanner.scan_text if rule.scope == "text" else scanner.scan_command
    for variant in _variants(rule):
        started = time.perf_counter()
        run(variant)
        assert time.perf_counter() - started < TIME_LIMIT_SECONDS


def test_input_over_the_limit_is_refused_before_any_matching() -> None:
    started = time.perf_counter()
    findings = Scanner(max_text_chars=1000).scan_text("key=A" * 10_000_000)
    assert [f.rule_id for f in findings] == ["guardline-input-too-large"]
    assert time.perf_counter() - started < 1.0


# fail closed ----------------------------------------------------------------------


def test_the_hook_blocks_when_it_cannot_judge() -> None:
    assert "deny" in run_hook("[unclosed", Scanner()).stdout


def test_a_huge_command_is_blocked_not_skipped() -> None:
    huge = "echo " + "x" * 70_000
    result = run_hook(json.dumps({"tool_input": {"command": huge}}), Scanner())
    assert "guardline-input-too-large" in result.stdout


# bypasses we know about -------------------------------------------------------------
#
# Each entry is a command or text that a human would call a violation and that
# guardline does not flag. The list is documented in docs/explanation/security-model.md.
# The test pins the current behaviour so the documentation stays true: if a change
# starts catching one, remove it here and from the document.

KNOWN_COMMAND_BYPASSES = {
    "interpreter prints the environment": "python3 -c 'import os; print(os.environ)'",
    "perl prints the environment": "perl -e 'print qq{$_=$ENV{$_}\\n} for keys %ENV'",
    "awk prints the environment": "awk 'BEGIN{for (k in ENVIRON) print k, ENVIRON[k]}'",
    "program name built from a variable": "p=pri; q=ntenv; $p$q",
    "encoded command": "echo cHJpbnRlbnY= | base64 -d | sh",
    "environ path built in pieces": "cat /proc/$(echo 1)/en''viron",
    "script file runs the dump": "sh ./dump-env.sh",
    "alias or function defined elsewhere": "mydump",
    "ruby prints the environment": "ruby -e 'puts ENV.to_a'",
    "node prints the environment": "node -p 'process.env'",
    "second find exec after an escaped semicolon": "find . -exec echo a \\; -exec printenv \\;",
    "attribution written by a shell redirect": f"echo 'Co-Authored-By: {AGENT} <x>' >> notes.md",
}

KNOWN_TEXT_BYPASSES = {
    "quote character before the agent name in a trailer": "Co-Authored-By: Dana's " + AGENT,
    "zero width space inside a vendor name": "Co-Authored-By: "
    + AGENT[:2]
    + "\u200b"
    + AGENT[2:]
    + " <x>",
    "lookalike letter in a vendor name": "Co-Authored-By: "
    + AGENT[:1]
    + "\u0456"
    + AGENT[2:]
    + " <x>",
    "footer without the verb": "Made using " + AGENT + " Code",
    "unlisted vendor in a trailer": "Co-Authored-By: Initech Autocoder <x@example.com>",
    "token split across lines": FAKE_TOKEN[:20] + "\n" + FAKE_TOKEN[20:],
    "token with a separator inserted": FAKE_TOKEN[:10] + "-" + FAKE_TOKEN[10:],
    "token base64 encoded": "dG9rZW4gPSBnaHBfWnE5WGsyWnE5WGsyWnE5WGsyWnE5WGsyWnE5WGsyWnE5WGsy",
    "unlisted credential format": "internal-" + "Zq9Xk2" * 8,
    "private key without the header line": "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7",
}


@pytest.mark.parametrize("name", sorted(KNOWN_COMMAND_BYPASSES))
def test_known_command_bypass_is_still_open(name: str) -> None:
    assert scan_command(KNOWN_COMMAND_BYPASSES[name]) == [], name


@pytest.mark.parametrize("name", sorted(KNOWN_TEXT_BYPASSES))
def test_known_text_bypass_is_still_open(name: str) -> None:
    assert scan_text(KNOWN_TEXT_BYPASSES[name]) == [], name


def test_attribution_in_a_file_a_command_names_is_not_read() -> None:
    command = "git commit -F message.txt"
    assert scan_command(command) == []
    assert scan_payload({"tool_input": {"command": command}}) == []


def test_footer_helper_text_is_really_a_footer() -> None:
    assert scan_text(FOOTER) != []
    assert scan_text(TRAILER) != []
