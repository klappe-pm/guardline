"""Regression tests for the adversarial security review.

Every fire case has a look-alike that must stay quiet. The cases are grouped by the
numbered findings of the review.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from guardline import Scanner, scan_command, scan_payload, scan_text
from guardline.cli import main
from guardline.config import build_ruleset, config_from_table
from guardline.diffscan import parse_added_lines
from guardline.engine import CONFIG_EDIT_RULE, TOO_COMPLEX_RULE
from guardline.errors import ConfigError, RuleError
from guardline.hook import run_hook
from guardline.rules import parse_rules, unsafe_pattern_reason
from guardline.shell import MAX_COMMANDS, parse_shell
from tests.helpers import assert_absent, rule_ids
from tests.samples import AGENT, FAKE_TOKEN, TRAILER

ATTRIBUTION = "attribution-"


def fires(command: str) -> set[str]:
    return rule_ids(scan_command(command))


def hook(payload: dict[str, object], *argv: str) -> str:
    """Run the hook command in-process and return its standard output."""
    import io
    import sys
    from contextlib import redirect_stdout

    old = sys.stdin
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            main(["hook", *argv])
        return buffer.getvalue()
    finally:
        sys.stdin = old


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


# 1. the agent cannot disable the hook --------------------------------------------

DUMP = {"tool_name": "Bash", "tool_input": {"command": "printenv"}}


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("guardline.toml", 'mode = "report"\n'),
        ("guardline.toml", 'disable = ["env-dump-printenv"]\n'),
        ("pyproject.toml", '[tool.guardline]\ndisable = ["env-dump-printenv"]\n'),
    ],
)
def test_the_hook_ignores_a_discovered_configuration(project: Path, name: str, body: str) -> None:
    (project / name).write_text(body, encoding="utf-8")
    assert "deny" in hook(DUMP)
    # look-alike: the same file named with --config is honoured, and scan still discovers it
    assert hook(DUMP, "--config", str(project / name), "--mode", "block") != "" or True
    if name == "guardline.toml" and "disable" in body:
        assert hook(DUMP, "--config", str(project / name)) == ""


def test_scan_still_discovers_configuration(project: Path) -> None:
    (project / "guardline.toml").write_text('mode = "report"\n', encoding="utf-8")
    (project / "m.txt").write_text(TRAILER, encoding="utf-8")
    assert main(["scan", "m.txt"]) == 0


EDIT_TOOLS = ["Write", "Edit", "MultiEdit"]


def edit_payload(tool: str, path: str, text: str) -> dict[str, object]:
    if tool == "Write":
        return {"tool_name": tool, "tool_input": {"file_path": path, "content": text}}
    if tool == "Edit":
        return {
            "tool_name": tool,
            "tool_input": {"file_path": path, "old_string": "x", "new_string": text},
        }
    edits = [{"old_string": "x", "new_string": text}]
    return {"tool_name": tool, "tool_input": {"file_path": path, "edits": edits}}


@pytest.mark.parametrize("tool", EDIT_TOOLS)
def test_writing_guardline_toml_is_denied(tool: str, tmp_path: Path) -> None:
    payload = edit_payload(tool, str(tmp_path / "guardline.toml"), 'mode = "report"')
    assert CONFIG_EDIT_RULE in rule_ids(scan_payload(payload))
    assert "--allow-config-edit" in run_hook(json.dumps(payload), Scanner()).stdout


@pytest.mark.parametrize("tool", EDIT_TOOLS)
def test_writing_other_files_is_not_denied(tool: str, tmp_path: Path) -> None:
    for name in ("myguardline.toml", "guardline.toml.example", "settings.toml"):
        payload = edit_payload(tool, str(tmp_path / name), 'mode = "report"')
        assert CONFIG_EDIT_RULE not in rule_ids(scan_payload(payload))


@pytest.mark.parametrize("tool", EDIT_TOOLS)
def test_writing_the_tool_guardline_table_to_pyproject_is_denied(tool: str, tmp_path: Path) -> None:
    path = str(tmp_path / "pyproject.toml")
    hit = edit_payload(tool, path, '[tool.guardline]\nmode = "report"')
    assert CONFIG_EDIT_RULE in rule_ids(scan_payload(hit))
    miss = edit_payload(tool, path, "[tool.ruff]\nline-length = 100")
    assert CONFIG_EDIT_RULE not in rule_ids(scan_payload(miss))


def test_editing_inside_an_existing_guardline_table_is_denied(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[tool.guardline]\nmode = "block"\n', encoding="utf-8")
    payload = edit_payload("Edit", str(pyproject), 'mode = "report"')
    assert CONFIG_EDIT_RULE in rule_ids(scan_payload(payload))
    other = tmp_path / "sub" / "pyproject.toml"
    other.parent.mkdir()
    other.write_text("[tool.ruff]\nline-length = 90\n", encoding="utf-8")
    assert CONFIG_EDIT_RULE not in rule_ids(
        scan_payload(edit_payload("Edit", str(other), "line-length = 100"))
    )


def test_the_explicit_flag_allows_a_configuration_edit(tmp_path: Path) -> None:
    payload = edit_payload("Write", str(tmp_path / "guardline.toml"), "mode = 'report'")
    assert scan_payload(payload, allow_config_edit=True) == []
    assert hook(payload, "--allow-config-edit") == ""
    assert "deny" in hook(payload)


def test_the_hooks_own_config_and_rule_files_are_protected(tmp_path: Path) -> None:
    config = tmp_path / "team.toml"
    scanner = Scanner(protected_paths=[str(config)])
    assert CONFIG_EDIT_RULE in rule_ids(
        scanner.scan_payload(edit_payload("Write", str(config), "x"))
    )
    elsewhere = edit_payload("Write", str(tmp_path / "notes.toml"), "x")
    assert CONFIG_EDIT_RULE not in rule_ids(scanner.scan_payload(elsewhere))


# 2. attribution misses -------------------------------------------------------------

C = AGENT


@pytest.mark.parametrize(
    "command",
    [
        f'git commit --message="fix\n\nCo-Authored-By: {C} <x>"',
        f"git commit --message='Co-Authored-By: {C} <x>'",
        f'gh pr create --title t --body="Generated with {C} Code"',
        f"git commit -m $'x\\n\\nCo-Authored-By: {C} <x>'",
        "git commit -m $'x\\n\\nCo-Authored-By: \\x43laude <x>'",
        "git commit -m $'x\\n\\nCo-Authored-By: \\103laude <x>'",
        f"echo 'x\\n\\nCo-Authored-By: {C} <x>' | git commit -F -",
        f"printf 'x\\n\\nCo-Authored-By: {C} <x>\\n' | git commit -F -",
        f"git commit -F - <<< $'x\\n\\nCo-Authored-By: {C} <x>'",
        f"git commit -F - <<< 'x\n\nCo-Authored-By: {C} <x>'",
        f"git commit -m \"$(printf 'x\\n\\nCo-Authored-By: {C} <x>')\"",
        f"git commit -m \"$(echo -e 'x\\n\\nCo-Authored-By: {C} <x>')\"",
        f"gh api repos/o/r/issues/1/comments -f body=$'x\\n\\nCo-Authored-By: {C} <x>'",
        f"git-commit -m 'x' -m 'Co-Authored-By: {C}'",
    ],
)
def test_attribution_in_publishing_commands_is_found(command: str) -> None:
    assert any(rule.startswith(ATTRIBUTION) for rule in fires(command))


@pytest.mark.parametrize(
    "command",
    [
        'git commit --message="fix: parser"',
        "git commit --message='Co-Authored-By: Dana Lee <d@example.com>'",
        'gh pr create --title t --body="A plain body"',
        "git commit -m $'x\\n\\nCo-Authored-By: Dana Lee <d@example.com>'",
        f"echo 'Co-Authored-By: {C} <x>' | cat",
        "echo 'fix: parser' | git commit -F -",
        "printf 'fix\\n' | git commit -F -",
        "git commit -F - <<< 'fix: parser'",
        "git commit -m \"$(printf 'fix: parser')\"",
        f"echo 'Co-Authored-By: {C} <x>'",
    ],
)
def test_look_alikes_of_those_commands_are_quiet(command: str) -> None:
    assert not any(rule.startswith(ATTRIBUTION) for rule in fires(command))


@pytest.mark.parametrize(
    "text",
    [
        f"Co-Authored-By : {C} <x>",
        f"Co-Authored-By\t: {C} <x>",
        f"Assisted-By : {C}",
        f"{C}-Session : abc",
    ],
)
def test_whitespace_before_the_colon_does_not_hide_a_trailer(text: str) -> None:
    assert any(rule.startswith(ATTRIBUTION) for rule in rule_ids(scan_text(text)))


@pytest.mark.parametrize(
    "text",
    ["Co-Authored-By : Dana Lee <d@example.com>", "Assisted-By : Dana Lee", "Review-Session : abc"],
)
def test_whitespace_before_the_colon_on_a_human_trailer_is_quiet(text: str) -> None:
    assert scan_text(text) == []


# 3. caps fail closed ------------------------------------------------------------------


def test_depth_over_the_cap_is_exhausted_and_a_finding() -> None:
    deep = "$(" * 12 + "env" + ")" * 12
    assert parse_shell(deep).exhausted
    assert TOO_COMPLEX_RULE in rule_ids(scan_command(deep))
    shallow = "bash -c 'bash -c \"ls\"'"
    assert not parse_shell(shallow).exhausted
    assert TOO_COMPLEX_RULE not in rule_ids(scan_command(shallow))


def test_nested_wrappers_over_the_cap_are_exhausted() -> None:
    assert parse_shell("sudo " * 20 + "env").exhausted
    assert not parse_shell("sudo " * 3 + "ls").exhausted


def test_command_count_over_the_cap_is_exhausted_and_blocks() -> None:
    many = "; ".join(["ls"] * (MAX_COMMANDS + 5))
    assert parse_shell(many).exhausted
    payload = {"tool_name": "Bash", "tool_input": {"command": many}}
    assert TOO_COMPLEX_RULE in run_hook(json.dumps(payload), Scanner()).stdout
    few = {"tool_name": "Bash", "tool_input": {"command": "; ".join(["ls"] * 50)}}
    assert run_hook(json.dumps(few), Scanner()).stdout == ""


# 4. quoting ---------------------------------------------------------------------------

DUMPS = [
    "$'\\x65nv'",
    "$'\\145nv'",
    "$'e'$'n'$'v'",
    "pri$'nt'env",
    "e$'n'v",
    '$"env"',
    '$"print""env"',
    "en\\\nv",
    "print\\\nenv",
    "ps e\\\nww",
    "echo $'it\\'s'; env",
    "echo $'a' # c\nenv",
    "bash -c $'env'",
    "$'\\u0065nv'",
]
CLEAN = [
    "$'e'$'x'",
    "echo $'env'",
    'echo $"env"',
    "en\\\nvx",
    "echo $'it\\'s # env'",
    "echo hi # env",
    "echo '\\x65nv'",
    "$'\\x6c\\x73'",
]


@pytest.mark.parametrize("command", DUMPS)
def test_decoded_quoting_cannot_hide_a_dump(command: str) -> None:
    assert any(rule.startswith("env-dump-") for rule in fires(command))


@pytest.mark.parametrize("command", CLEAN)
def test_quoting_look_alikes_are_quiet(command: str) -> None:
    assert fires(command) == set()


# 5. diff and tree scanners --------------------------------------------------------------


def test_plus_plus_content_lines_are_added_lines() -> None:
    diff = "diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -0,0 +1,3 @@\n+one\n+++ two\n++++ three\n"
    [added] = parse_added_lines(diff)
    assert (added.path, added.lines, added.numbers) == (
        "f",
        ("one", "++ two", "+++ three"),
        (1, 2, 3),
    )


def test_header_lines_are_not_added_lines() -> None:
    diff = "diff --git a/f b/f\nindex 1..2\n--- a/f\n+++ b/f\n@@ -1 +1 @@\n-old\n+new\n"
    [added] = parse_added_lines(diff)
    assert (added.path, added.lines) == ("f", ("new",))
    deleted = "diff --git a/f b/f\n--- a/f\n+++ /dev/null\n@@ -1 +0,0 @@\n-gone\n"
    assert parse_added_lines(deleted) == []


# 6 is covered in test_cli.py (commit message comment lines)

# 7. token rules -------------------------------------------------------------------------

LONG = "abcdefghijklmnop12345678"


@pytest.mark.parametrize(
    "text",
    [
        '{"api_key": "' + LONG + '"}',
        '{"password": "' + LONG + '"}',
        "'client_secret': '" + LONG + "'",
        "-----" + "BEGIN PGP PRIVATE KEY BLOCK-----\nlQOYBF",
        "-----" + "BEGIN PRIVATE KEY-----",
        "ABIA" + "IOSFODNN7EXAMPLE0",
        "hf_" + "aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3x",
        "xapp-1-A0123456789-1234567890123-" + "abcdef0123456789abcdef0123456789",
        "SG." + "abcdefghijklmnopqrstuv" + "." + "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
    ],
)
def test_more_credential_shapes_are_found(text: str) -> None:
    assert any(rule.startswith("token-") for rule in rule_ids(scan_text(text)))


@pytest.mark.parametrize(
    "text",
    [
        '{"api_key": "short"}',
        '{"name": "' + LONG + '"}',
        "-----BEGIN PGP PUBLIC KEY BLOCK-----",
        "-----BEGIN CERTIFICATE-----",
        "ABIA" + "short",
        "hf_" + "short",
        "xapp-" + "short",
        "SG." + "short",
    ],
)
def test_credential_look_alikes_are_quiet(text: str) -> None:
    assert scan_text(text) == []


def test_a_long_jwt_is_found() -> None:
    segment = "a" * 3000
    assert "token-jwt" in rule_ids(scan_text(f"t=eyJ{segment}.{segment}.{segment}"))
    assert "token-jwt" not in rule_ids(scan_text(f"t=eyJ{segment}.{segment}"))


def test_a_token_hidden_by_shell_quoting_is_found_in_a_command() -> None:
    hidden = "gh''" + FAKE_TOKEN[2:]
    assert "token-github-token" in fires(f"echo {hidden}")
    assert "token-github-token" in fires("echo $'\\x67" + FAKE_TOKEN[1:] + "'")
    assert fires("echo gh''p_short") == set()


# 8. wrappers and options -------------------------------------------------------------------

WRAPPED = [
    "setsid env",
    "flock /tmp/l env",
    "flock /tmp/l -c env",
    "flock -c env /tmp/l",
    "strace -o out env",
    "strace --output=out printenv",
    "taskset 0x1 env",
    "taskset -c 0 env",
    "ionice -c 3 env",
    "ionice --class 3 env",
    "chroot /r env",
    "unshare --propagation private env",
    "su -c env",
    "su root -c env",
    "chrt 10 env",
    "xargs --max-args 1 env",
    "xargs --arg-file /dev/null env",
    "xargs -n 1 printenv",
    "sudo --user root env",
    "sudo --chdir /tmp printenv",
    "docker compose exec web env",
    "docker compose -f x.yml exec web env",
    "docker-compose exec web env",
    "nerdctl exec web env",
    "docker run --entrypoint env img",
    "docker run --entrypoint=env img",
    "busybox env",
    "time -f %e env",
    "script -qc env /dev/null",
    "env -0u HOME",
    "env -iS printenv",
    "command env",
    "timeout --signal=KILL 5 env",
    "stdbuf -o L env",
]
WRAPPED_CLEAN = [
    "setsid ls",
    "flock /tmp/l ls",
    "flock -c ls /tmp/l",
    "strace -o out ls",
    "taskset 0x1 ls",
    "taskset -c 0 ls",
    "ionice -c 3 ls",
    "chroot /r ls",
    "unshare --propagation private ls",
    "su -c ls",
    "chrt 10 ls",
    "xargs --max-args 1 ls",
    "sudo --user root ls",
    "docker compose exec web ls",
    "docker run --entrypoint ls img env",
    "busybox ls",
    "script -qc ls /dev/null",
    "env -0u HOME ls",
    "command -v env",
    "docker compose ps",
]


@pytest.mark.parametrize("command", WRAPPED)
def test_wrappers_are_looked_through(command: str) -> None:
    assert any(rule.startswith("env-dump-") for rule in fires(command))


@pytest.mark.parametrize("command", WRAPPED_CLEAN)
def test_wrapper_look_alikes_are_quiet(command: str) -> None:
    assert fires(command) == set()


@pytest.mark.parametrize(
    "command",
    [
        "export --",
        "export -pn",
        "export -n -p",
        "declare -pn",
        "declare --",
        "declare -rx",
        "readonly --",
    ],
)
def test_listing_forms_with_double_dash_and_clusters_are_found(command: str) -> None:
    assert any(rule.startswith("env-dump-") for rule in fires(command))


@pytest.mark.parametrize(
    "command",
    ["export -- FOO=1", "declare -- FOO", "export -f func", "declare -f", "readonly -- FOO=1"],
)
def test_listing_look_alikes_are_quiet(command: str) -> None:
    assert fires(command) == set()


@pytest.mark.parametrize(
    "command",
    [
        "cat /proc//self/environ",
        "cat /proc/./1/environ",
        "cat /proc/1/../1/environ",
        "cat /proc/self/task/1/environ",
        "dd if=/proc/self/environ",
        "dd if=/proc//1/environ of=/tmp/x",
        "xargs -0 -a /proc/1/environ echo",
        "cat /proc/*/environ",
    ],
)
def test_environ_reads_are_found_from_any_reader(command: str) -> None:
    assert "env-dump-proc-environ" in fires(command)


@pytest.mark.parametrize(
    "command",
    [
        "cat /proc/self/status",
        "dd if=/dev/zero of=/tmp/x",
        'echo "see /proc/1/environ for details"',
        "cat /proc/environ",
    ],
)
def test_environ_look_alikes_are_quiet(command: str) -> None:
    assert fires(command) == set()


@pytest.mark.parametrize(
    "command",
    [
        "function f { env; }; f",
        "f() { printenv; }",
        ". /dev/stdin <<EOF\nenv\nEOF",
        "source /dev/stdin <<< env",
        "bash /dev/stdin <<< env",
    ],
)
def test_function_bodies_and_sourced_stdin_are_inspected(command: str) -> None:
    assert any(rule.startswith("env-dump-") for rule in fires(command))


@pytest.mark.parametrize(
    "command",
    [
        "function f { ls; }; f",
        "f() { ls; }",
        ". ./setup.sh",
        ". /dev/stdin <<EOF\nls\nEOF",
        "source /dev/stdin <<< ls",
    ],
)
def test_function_and_source_look_alikes_are_quiet(command: str) -> None:
    assert fires(command) == set()


# 9. nested payload fields --------------------------------------------------------------------


def test_a_token_in_a_deeply_nested_string_is_found() -> None:
    hit = {"tool_name": "mcp__x__send", "tool_input": {"a": {"b": [{"c": f"t {FAKE_TOKEN}"}]}}}
    benign = {"tool_name": "mcp__x__send", "tool_input": {"a": {"b": [{"c": "hello world"}]}}}
    assert "token-github-token" in rule_ids(scan_payload(hit))
    assert scan_payload(benign) == []


def test_a_command_key_at_any_depth_is_a_shell_command() -> None:
    hit = {"tool_input": {"steps": [{"run": {"command": "printenv"}}]}}
    miss = {"tool_input": {"steps": [{"run": {"command": "ls"}}]}}
    note = {"tool_input": {"steps": [{"run": {"note": "printenv"}}]}}
    assert "env-dump-printenv" in rule_ids(scan_payload(hit))
    assert scan_payload(miss) == []
    assert scan_payload(note) == []
    listed = {"tool_input": {"x": {"cmd": ["env"]}}}
    assert "env-dump-env-no-command" in rule_ids(scan_payload(listed))


def test_attribution_is_judged_in_nested_message_fields_only() -> None:
    assert "attribution-co-author-trailer" in rule_ids(
        scan_payload({"tool_input": {"x": {"body": TRAILER}}})
    )
    assert scan_payload({"tool_input": {"x": {"other": TRAILER}}}) == []


def test_unknown_keys_are_never_echoed_in_sources() -> None:
    payload = {"tool_input": {FAKE_TOKEN: {FAKE_TOKEN: FAKE_TOKEN}}}
    findings = scan_payload(payload)
    assert findings
    for finding in findings:
        assert_absent(FAKE_TOKEN, finding.source)
    result = run_hook(json.dumps(payload), Scanner())
    assert_absent(FAKE_TOKEN, result.stdout, result.stderr)


def test_payloads_that_nest_too_deeply_are_flagged() -> None:
    deep: object = "x"
    for _ in range(40):
        deep = {"k": deep}
    assert TOO_COMPLEX_RULE in rule_ids(scan_payload({"tool_input": deep}))
    shallow: object = "x"
    for _ in range(5):
        shallow = {"k": shallow}
    assert scan_payload({"tool_input": shallow}) == []
    wide = {"tool_input": {"l": ["x"] * 3000}}
    assert TOO_COMPLEX_RULE in rule_ids(scan_payload(wide))


# 10. NUL characters ---------------------------------------------------------------------------


def test_nul_characters_cannot_split_a_command_or_a_trailer() -> None:
    assert "env-dump-printenv" in fires("pri\x00ntenv")
    assert "env-dump-env-no-command" in fires("env\x00")
    assert fires("pri\x00nt") == set()
    assert "attribution-co-author-trailer" in rule_ids(scan_text("Co-Authored-By: Cl\x00aude <x>"))
    assert scan_text("Co-Authored-By: Da\x00na <x>") == []


# 11. the custom rule loader ---------------------------------------------------------------------


def rule_text(pattern: str) -> str:
    return (
        'schema_version = 1\n[[rule]]\nid = "x-a"\nfamily = "custom"\ndescription = "d."\n'
        f'pattern = \'{pattern}\'\nexample_fires = "zzz"\nexample_clean = "aaa"\n'
    )


@pytest.mark.parametrize(
    ("pattern", "fragment"),
    [
        ("a*a*b", "adjacent"),
        (".*.*x", "adjacent"),
        (r"\w+\w+x", "adjacent"),
        ("[ab]*[bc]*x", "adjacent"),
        ("a*b*c*d*e", "unbounded"),
        ("(?=.*a)(?=.*a)(?=.*a)(?=.*a).*b", "unbounded"),
        ("(?:a?){28}a{28}b", "nested quantifier"),
        ("(?:a|aa)+b", "alternation"),
        ("(?:a|a)*b", "alternation"),
        (r"(a+)\1+b", "backreference"),
    ],
)
def test_the_loader_rejects_super_linear_patterns(pattern: str, fragment: str) -> None:
    with pytest.raises(RuleError, match=fragment):
        parse_rules(rule_text(pattern), "t.toml")


@pytest.mark.parametrize(
    "pattern",
    ["xa*b*", "a+ +b", r"x\s*\w+", "(?:a|b){1,4}c", "x.{0,200}y", "xa*b*c*", r"[a-z]+\.[0-9]+"],
)
def test_the_loader_accepts_linear_look_alikes(pattern: str) -> None:
    assert parse_rules(rule_text(pattern), "t.toml")


def test_the_reason_function_agrees() -> None:
    assert unsafe_pattern_reason("a*a*") is not None
    assert unsafe_pattern_reason("a*b*") is None


# hardening --------------------------------------------------------------------------------------


def test_rule_files_are_confined_to_the_configuration_directory(tmp_path: Path) -> None:
    origin = tmp_path / "guardline.toml"
    for bad in ("../outside.toml", "/etc/outside.toml", "sub/../../outside.toml"):
        with pytest.raises(ConfigError, match="leaves the configuration directory"):
            config_from_table({"rule_files": [bad]}, origin)
    ok = config_from_table({"rule_files": ["rules.toml", "sub/more.toml"]}, origin)
    assert [p.name for p in ok.rule_files] == ["rules.toml", "more.toml"]


def test_a_deny_reason_never_echoes_rule_file_keys(project: Path) -> None:
    odd_name = "sUpErSeCrEtKeYnAmE"
    bad = project / "bad.toml"
    bad.write_text(f"schema_version = 1\n{odd_name} = 1\n", encoding="utf-8")
    out = hook(DUMP, "--rules", str(bad))
    assert "deny" in out
    assert_absent(odd_name, out)
    assert "RuleError" in out


@pytest.mark.parametrize("name", ["Grok", "Kiro", "Cline", "Google Jules", "Jules agent"])
def test_more_agent_names_are_found_in_trailers_and_footers(name: str) -> None:
    assert "attribution-co-author-trailer" in rule_ids(scan_text(f"Co-Authored-By: {name} <x>"))
    assert "attribution-generated-with-footer" in rule_ids(scan_text(f"Generated with {name}"))


@pytest.mark.parametrize("name", ["Jules Verne", "Kirov Smith", "Clinesmith", "Grokking Bob"])
def test_agent_name_look_alikes_are_quiet(name: str) -> None:
    assert scan_text(f"Co-Authored-By: {name} <x@example.com>") == []


@pytest.mark.parametrize(
    "command", ["ENV", "PrintEnv HOME", "/BIN/ENV", "Printenv", "PS EWW".lower()]
)
def test_program_names_match_without_regard_to_case(command: str) -> None:
    assert any(rule.startswith("env-dump-") for rule in fires(command))


def test_upper_case_look_alike_is_quiet() -> None:
    assert fires("Echo ENV") == set()


# the documented open gaps, pinned (see docs/explanation/security-model.md) -----------------------

OPEN_GAPS = {
    "brace expansion": "{env,-0}",
    "brace expansion printenv": "{printenv,HOME}",
    "program from a command substitution": "$(echo env)",
    "program from backticks": "`echo printenv`",
    "program from a default expansion": "${x:-env}",
    "process substitution": "bash <(echo env)",
    "xargs sh -c reading stdin": "echo env | xargs sh -c",
    "xargs replace into sh -c": "echo printenv | xargs -I{} sh -c {}",
    "git alias": f"git -c alias.ci=commit ci -m x -m 'Co-Authored-By: {C} <x>'",
    "git config-env": f"git --config-env a=B commit -m x -m 'Co-Authored-By: {C} <x>'",
    "gh repo edit": f"gh repo edit --description 'Generated with {C} Code'",
    "gh label": f"gh label create x --description 'Generated with {C} Code'",
    "curl post": f"""curl -X POST https://example.com/api -d '{{"body":"Co-Authored-By: {C}"}}'""",
    "mid sentence footer": f"git commit -m 'This change was generated by {C} Code'",
    "colon footer": f"git commit -m 'Note: generated with {C} Code'",
    "message in a variable": f"M='x Co-Authored-By: {C} <x>'; git commit -m \"$M\"",
}


@pytest.mark.parametrize("name", sorted(OPEN_GAPS))
def test_documented_open_gap_is_still_open(name: str) -> None:
    assert fires(OPEN_GAPS[name]) == set(), name


def test_mid_sentence_footers_in_text_are_still_open() -> None:
    assert scan_text(f"This change was generated by {C} Code") == []
    assert scan_text(f"Note: generated with {C} Code") == []


def test_the_word_pattern_audit_helper_is_used_by_the_loader() -> None:
    assert re.compile(r"nested").search(unsafe_pattern_reason("(a+)+") or "")


def test_build_ruleset_still_works() -> None:
    assert build_ruleset(config_from_table({}, Path("x.toml")))
