"""Behaviour of the scanner across the three rule families."""

from __future__ import annotations

import time

import pytest

from guardline import Scanner, scan_command, scan_payload, scan_text
from guardline.engine import (
    DEFAULT_MAX_COMMAND_CHARS,
    DEFAULT_MAX_TEXT_CHARS,
    MAX_FINDINGS,
    MAX_PAYLOAD_LEAVES,
    TOO_LARGE_RULE,
    TRUNCATED_RULE,
    fenced_ranges,
    is_authoring_command,
    strip_value_options,
)
from guardline.rules import builtin_rules
from guardline.shell import SimpleCommand
from tests.helpers import rule_ids
from tests.samples import (
    AGENT,
    CLEAN_COMMIT,
    COMMIT_WITH_TRAILER,
    ENV_DUMP_COMMANDS,
    ENV_SAFE_COMMANDS,
    FAKE_AWS,
    FAKE_JWT,
    FAKE_PEM,
    FAKE_TOKEN,
    FOOTER,
    NOREPLY,
    PERMALINK,
    TRAILER,
)

# attribution -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        (COMMIT_WITH_TRAILER, "attribution-co-author-trailer"),
        (f"Assisted-By: {AGENT} Code", "attribution-assisted-by-trailer"),
        (f"Fix the parser. {FOOTER}", "attribution-generated-with-footer"),
        (f"_{FOOTER}_", "attribution-generated-with-footer"),
        ("Written by an AI " + "assistant", "attribution-generated-with-footer"),
        (f"Signed <{NOREPLY}>", "attribution-vendor-noreply-address"),
        (PERMALINK, "attribution-session-permalink"),
        (f"{AGENT}-Session: abc", "attribution-session-trailer"),
        ("\U0001f916 built this", "attribution-robot-byline"),
        (f"[{AGENT} Code](https://{AGENT.lower()}.ai/code)", "attribution-product-link"),
        (f"[{AGENT} Code](https://docs.{AGENT.lower()}.com/x)", "attribution-product-link"),
        (f"[{AGENT} Code](https://user@{AGENT.lower()}.ai/code)", "attribution-product-link"),
        (
            f"[{AGENT} Code](https://github.com/acme/{AGENT.lower()}-code)",
            "attribution-product-link",
        ),
        (f'git commit -m "Co-Authored-By: {AGENT} <x>"', "attribution-co-author-trailer"),
        (f"## sources\n\nCo-Authored-By: {AGENT} <x>", "attribution-co-author-trailer"),
    ],
)
def test_attribution_forms_are_found(text: str, rule: str) -> None:
    assert rule in rule_ids(scan_text(text))


@pytest.mark.parametrize(
    "text",
    [
        CLEAN_COMMIT,
        "fix: correct the off by one in staging",
        f"The {AGENT} Code CLI runs the hook.",
        f"fix: parse config files created by {AGENT} Code",
        f"Co-Authored-By: Jane Doe <jane@{AGENT.lower()}.com>",
        "",
        f"[{AGENT} Code issue](https://github.com/acme/{AGENT.lower()}-code/issues/21)",
        f"[{AGENT} Code pull](https://github.com/acme/{AGENT.lower()}-code/pull/9)",
        f"- [{AGENT} models](https://www.example.com/news/{AGENT.lower()}-models), Example, 2026.",
        f"[{AGENT} Code](https://{AGENT.lower()}.example.net/{AGENT.lower()})",
        'session-link: ""',
    ],
)
def test_clean_text_has_no_attribution(text: str) -> None:
    assert scan_text(text) == []


def test_session_link_key_is_not_exempt() -> None:
    text = f"---\nsession-link: {PERMALINK}\n---\n"
    assert "attribution-session-permalink" in rule_ids(scan_text(text))


def test_positions_are_one_based_line_and_column() -> None:
    findings = scan_text(f"line one\n\n  {TRAILER}\n")
    finding = next(f for f in findings if f.rule_id == "attribution-co-author-trailer")
    assert (finding.line, finding.column) == (3, 1)


# fenced exception --------------------------------------------------------------

QUOTED = f"Reviewing a commit:\n\n```text\n{TRAILER}\n```\n"


def test_fenced_attribution_is_reported_by_default() -> None:
    assert "attribution-co-author-trailer" in rule_ids(scan_text(QUOTED))


def test_fenced_attribution_is_allowed_only_with_the_switch() -> None:
    assert scan_text(QUOTED, allow_fenced_attribution=True) == []


def test_the_switch_does_not_cover_text_outside_the_fence() -> None:
    text = f"{TRAILER}\n\n{QUOTED}"
    found = scan_text(text, allow_fenced_attribution=True)
    assert [f.line for f in found if f.rule_id == "attribution-co-author-trailer"] == [1]


def test_an_unterminated_fence_exempts_nothing() -> None:
    text = f"```text\n{TRAILER}\n"
    assert scan_text(text, allow_fenced_attribution=True) != []


def test_a_shorter_closing_fence_does_not_close_the_block() -> None:
    text = f"````text\n```\n{TRAILER}\n"
    assert scan_text(text, allow_fenced_attribution=True) != []


def test_tilde_fences_and_longer_closers_work() -> None:
    text = f"~~~\n{TRAILER}\n~~~~\n"
    assert scan_text(text, allow_fenced_attribution=True) == []


def test_the_switch_never_hides_a_token_in_a_fence() -> None:
    text = f"```\ntoken: {FAKE_TOKEN}\n```\n"
    assert "token-github-token" in rule_ids(scan_text(text, allow_fenced_attribution=True))


def test_fenced_ranges_ignore_a_backtick_info_string() -> None:
    assert fenced_ranges("```a`b\nx\n```\n") == []
    assert fenced_ranges("```py\nx\n```\n") == [(6, 8)]


# tokens ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        (f"x = {FAKE_AWS}", "token-aws-access-key-id"),
        (f"export T={FAKE_TOKEN}", "token-github-token"),
        (f"jwt={FAKE_JWT}", "token-jwt"),
        (FAKE_PEM + "\nMIIB", "token-private-key-block"),
        ("api_key = '" + "abcdefghijklmnop1234" + "'", "token-generic-assignment"),
        ("password: " + "hunter2hunter2hunter2", "token-generic-assignment"),
        ("Authorization: Bearer " + "abcdefghijklmnopqrstuvwxyz", "token-bearer-token"),
        ("secret " + "0123456789abcdef0123456789abcdef", "token-hex-run-near-keyword"),
    ],
)
def test_token_shaped_values_are_found(text: str, rule: str) -> None:
    assert rule in rule_ids(scan_text(text))


@pytest.mark.parametrize(
    "text",
    [
        "plan the risk-and-cost-of-the-wrong-decision review",
        "api_key = settings.env.api_key",
        "token = os.environ.get_token(name)",
        "secret://namespace/key-name-here",
        "key = extract_keyspace(info_value_long)",
        "the ghp_ prefix is documented",
        "commit 0123456789abcdef0123456789abcdef01234567",
        "autodesk-management-console-service-name",
    ],
)
def test_token_look_alikes_are_quiet(text: str) -> None:
    assert scan_text(text) == []


# tokens: type identifiers and content keys are not credentials ------------------------------

GENERIC = "token-generic-assignment"
TOKENS = "Tok" + "ens"
KEY = "K" + "ey"
PASSWORD = "pass" + "word"
API_TOKEN = "API_" + "TOKEN"
COLLECTION = "Collection" + "Config"
LONG_VALUE = "abcdefghijklmnop" + "1234"
COPY_ATTRIBUTES = (f"title{KEY}", f"text{KEY}", "data-copy-" + KEY.lower())


def _generic_match_covers(text: str, value: str) -> bool:
    """Whether a generic assignment finding, rebuilt at its offset, spans ``value``.

    A finding reports where the matched name starts, never the value, so the match is
    rebuilt from the rule's own pattern to prove the credential is what was found.
    """
    rule = next(rule for rule in builtin_rules() if rule.id == GENERIC)
    for finding in scan_text(text):
        if finding.rule_id != GENERIC:
            continue
        match = rule.regex.match(text, finding.offset)
        if match is not None and value in match.group(0):
            return True
    return False


@pytest.mark.parametrize("prefix", ["", "+", "export "])
@pytest.mark.parametrize("name", [f"Design{TOKENS}", f"{TOKENS[:-1]}Sets"])
def test_a_typed_declaration_opening_an_object_is_quiet(prefix: str, name: str) -> None:
    assert scan_text(f"{prefix}const {name}: {COLLECTION} = {{") == []
    assert scan_text(f"{prefix}const {name}: {COLLECTION} = {{}}") == []


@pytest.mark.parametrize("prefix", ["", "+"])
@pytest.mark.parametrize("name", [f"Design{TOKENS}", f"{TOKENS[:-1]}Sets"])
def test_a_generic_type_in_a_schema_field_is_quiet(prefix: str, name: str) -> None:
    slug = (
        "design-" + TOKENS.lower() if name.startswith("Design") else TOKENS[:-1].lower() + "-sets"
    )
    assert scan_text(f"{prefix}    '{slug}': {name}Select<false> | {name}Select<true>;") == []
    assert scan_text(f"{prefix}{TOKENS.lower()}: Array<{name}>;") == []


@pytest.mark.parametrize("attribute", COPY_ATTRIBUTES)
@pytest.mark.parametrize(
    "path",
    [
        "pages.referrals.good-work-starts-with-a-good",
        "pages.referrals.make-an-introduction",
        "pages.referrals.senior-advisory-is-500-to-1",
        "pages.forms.labels.current-" + PASSWORD,
        "pages.forms.labels." + PASSWORD,
        "pages.home.monogram",
        "global.site.email",
        "pages.contact.form.rate",
    ],
)
def test_a_content_key_of_dotted_words_is_quiet(attribute: str, path: str) -> None:
    text = f'<PageIntro {attribute}="{path}" />'
    assert scan_text(text) == []
    assert scan_payload({"tool_name": "Write", "tool_input": {"content": text}}) == []
    assert GENERIC in rule_ids(scan_text(f'  "{attribute}": "{path}",'))


def test_public_copy_property_inside_a_jsx_prop_is_quiet() -> None:
    path = "pages.contact.form.rate"
    text = f'<Input props={{{{"data-copy-key": "{path}"}}}} />'
    assert scan_text(text) == []


@pytest.mark.parametrize("name", [API_TOKEN, "api" + KEY, PASSWORD])
@pytest.mark.parametrize(
    "initializer",
    [
        f"'{LONG_VALUE}'",
        f'"{LONG_VALUE}"',
        f"`{LONG_VALUE}`",
        f"\n  '{LONG_VALUE}'",
        f"/* value */ '{LONG_VALUE}'",
        f"{{ value: '{LONG_VALUE}' }}",
    ],
)
def test_a_type_annotation_does_not_hide_a_credential_initializer(
    name: str, initializer: str
) -> None:
    text = f"const {name}: {COLLECTION} = {initializer}"
    assert _generic_match_covers(text, LONG_VALUE)
    assert _generic_match_covers(f"+{text}", LONG_VALUE)


def test_a_python_annotation_does_not_hide_a_credential_initializer() -> None:
    assert _generic_match_covers(f'api_{KEY.lower()}: str = "{LONG_VALUE}"', LONG_VALUE)


@pytest.mark.parametrize("shape", ["direct", "nested", "array"])
def test_a_typed_object_does_not_hide_a_credential_on_its_opening_line(shape: str) -> None:
    fields = {
        "direct": f"value: '{LONG_VALUE}'",
        "nested": f"config: {{ value: '{LONG_VALUE}' }}",
        "array": f"fields: [{{ value: '{LONG_VALUE}' }}]",
    }
    text = f"export const Design{TOKENS}: {COLLECTION} = {{ {fields[shape]} }}"
    assert _generic_match_covers(text, LONG_VALUE)


def test_a_typed_object_with_short_strings_is_quiet() -> None:
    text = f"export const Design{TOKENS}: {COLLECTION} = {{ slug: 'design', fields: [] }}"
    assert scan_text(text) == []


def test_a_named_credential_inside_a_typed_object_is_found_by_its_own_name() -> None:
    text = f"export const Design{TOKENS}: {COLLECTION} = {{\n  {PASSWORD}: '{LONG_VALUE}',\n}}"
    assert _generic_match_covers(text, LONG_VALUE)


def test_an_unnamed_literal_on_a_later_line_of_a_typed_object_is_found() -> None:
    text = f"export const Design{TOKENS}: {COLLECTION} = {{\n  value: '{LONG_VALUE}',\n}}"
    assert _generic_match_covers(text, LONG_VALUE)


def test_a_later_literal_in_a_typed_object_is_found_after_a_short_string() -> None:
    text = (
        f"export const Design{TOKENS}: {COLLECTION} = {{\n"
        f"  label: 'short',\n  value: '{LONG_VALUE}',\n}}"
    )
    assert _generic_match_covers(text, LONG_VALUE)


def test_a_literal_after_a_closed_typed_object_does_not_match_its_declaration() -> None:
    text = f"export const Design{TOKENS}: {COLLECTION} = {{}}\nconst note = '{LONG_VALUE}'"
    assert GENERIC not in rule_ids(scan_text(text))


@pytest.mark.parametrize("attribute", COPY_ATTRIBUTES)
@pytest.mark.parametrize(
    "value",
    ["example.service.private.v4lue", "Example.Service.Private.Value", "example.servicevalue"],
)
def test_a_dotted_value_with_a_token_trait_stays_a_finding(attribute: str, value: str) -> None:
    text = f'<Heading {attribute}="{value}" />'
    assert GENERIC in rule_ids(scan_text(text))
    assert GENERIC in rule_ids(
        scan_payload({"tool_name": "Write", "tool_input": {"content": text}})
    )


def test_a_passphrase_of_dotted_lowercase_words_is_found() -> None:
    assert GENERIC in rule_ids(scan_text(f'{PASSWORD} = "correct.horse.battery.staple"'))
    assert GENERIC in rule_ids(scan_text(f'{PASSWORD} = "correct-horse-battery-staple"'))


@pytest.mark.parametrize("name", [PASSWORD, "api_secret"])
@pytest.mark.parametrize("value", ["correct.horse.battery.staple", "pages.forms.labels.password"])
@pytest.mark.parametrize("quote", ["", '"'])
def test_dotted_credentials_are_found_outside_public_copy_attributes(
    name: str, value: str, quote: str
) -> None:
    text = f"{name} = {quote}{value}{quote}"
    assert _generic_match_covers(text, value)
    payload = {"tool_name": "Write", "tool_input": {"content": text}}
    assert GENERIC in rule_ids(scan_payload(payload))


@pytest.mark.parametrize("suffix", [" = marker", "<marker>;"])
def test_a_credential_with_a_code_like_suffix_is_found(suffix: str) -> None:
    text = f"api_secret: {LONG_VALUE}{suffix}"
    assert _generic_match_covers(text, LONG_VALUE)


@pytest.mark.parametrize("attribute", COPY_ATTRIBUTES)
def test_public_copy_attribute_does_not_exempt_an_unrelated_namespace(attribute: str) -> None:
    text = f'<Heading {attribute}="correct.horse.battery.staple" />'
    assert GENERIC in rule_ids(scan_text(text))


def test_a_prefixed_attribute_does_not_inherit_the_public_copy_exception() -> None:
    text = f'<Heading private-{COPY_ATTRIBUTES[0]}="pages.forms.labels.password" />'
    assert GENERIC in rule_ids(scan_text(text))


@pytest.mark.parametrize("attribute", COPY_ATTRIBUTES)
def test_a_vendor_token_in_a_content_attribute_is_found(attribute: str) -> None:
    text = f'<Heading {attribute}="{FAKE_TOKEN}" />'
    assert "token-github-token" in rule_ids(scan_text(text))
    payload = {"tool_name": "Write", "tool_input": {"content": text}}
    assert "token-github-token" in rule_ids(scan_payload(payload))


@pytest.mark.parametrize(
    "value",
    [
        "Pages.Referrals.Good-Work-Starts",
        "pages.referrals.h2-heading-text",
        "pages.referrals.good-work.",
        "pages.referrals..good-work",
        "pages.referrals.good--work",
        "ya29.a0afh6smbx-abcdefghijk.x",
    ],
)
def test_a_dotted_value_that_is_not_a_content_key_stays_a_finding(value: str) -> None:
    assert GENERIC in rule_ids(scan_text(f'"{PASSWORD.capitalize()}": "{value}"'))
    if "-" in value:  # an unquoted chain of plain identifiers was already a reference
        assert GENERIC in rule_ids(scan_text(f"{KEY}={value}"))


@pytest.mark.parametrize(
    "text",
    [
        f"{TOKENS.lower()}: " + "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXo=",
        f"{TOKENS[:-1].lower()}: " + "a" * 128 + "=",
        f"{TOKENS.lower()}: Design{TOKENS}Select<br>",
        f"{KEY}=ya29.a0AfH6SMBx-abcdefghijk",
        f"const {TOKENS}: Foo = '{LONG_VALUE[:16]}'",
        f"{PASSWORD}: {LONG_VALUE} == other",
    ],
)
def test_a_value_that_only_resembles_code_stays_a_finding(text: str) -> None:
    assert GENERIC in rule_ids(scan_text(text))


def test_a_finding_reports_kind_and_position_but_not_the_value() -> None:
    text = f"line\nexport T={FAKE_TOKEN}\n"
    finding = next(f for f in scan_text(text) if f.rule_id == "token-github-token")
    assert (finding.line, finding.column) == (2, 10)
    assert FAKE_TOKEN not in repr(finding)
    assert FAKE_TOKEN not in finding.format_text()


# shell commands --------------------------------------------------------------


@pytest.mark.parametrize("command", ENV_DUMP_COMMANDS)
def test_environment_dumps_are_found(command: str) -> None:
    findings = scan_command(command)
    if not any(f.family == "env-dump" for f in findings):
        pytest.fail("an environment dump command was not found")


@pytest.mark.parametrize("command", ENV_SAFE_COMMANDS)
def test_safe_commands_are_quiet(command: str) -> None:
    findings = scan_command(command)
    if findings:
        pytest.fail(f"a safe command produced {sorted(rule_ids(findings))}")


def test_a_secret_passed_as_a_command_argument_is_found() -> None:
    assert "token-github-token" in rule_ids(scan_command(f"curl -H 'X: {FAKE_TOKEN}' host"))


def test_attribution_is_judged_only_in_publishing_commands() -> None:
    quoted = f"grep 'Co-Authored-By: {AGENT} <x>' notes.txt"
    assert scan_command(quoted) == []
    commit = f'git commit -m "fix" -m "Co-Authored-By: {AGENT} <x>"'
    assert "attribution-co-author-trailer" in rule_ids(scan_command(commit))


def test_attribution_in_a_heredoc_commit_message_is_found() -> None:
    command = f"git commit -F - <<'EOF'\nfix: x\n\n{TRAILER}\nEOF\n"
    assert "attribution-co-author-trailer" in rule_ids(scan_command(command))


def test_attribution_in_the_standard_heredoc_commit_form_is_found() -> None:
    command = f"git commit -m \"$(cat <<'EOF'\nfix: x\n\n{FOOTER}\nEOF\n)\""
    assert "attribution-generated-with-footer" in rule_ids(scan_command(command))


def test_a_pull_request_body_is_judged() -> None:
    command = f"gh pr create --title t --body '{FOOTER}'"
    assert "attribution-generated-with-footer" in rule_ids(scan_command(command))


def test_reading_commands_are_not_publishing() -> None:
    assert scan_command(f"gh pr list --search '{FOOTER}'") == []


@pytest.mark.parametrize(
    ("program", "args", "expected"),
    [
        ("git", ("commit", "-m", "x"), True),
        ("git", ("-C", "/tmp/r", "tag", "-m", "x"), True),  # noqa: S108
        ("git", ("status",), False),
        ("gh", ("pr", "create"), True),
        ("gh", ("pr", "view"), False),
        ("gh", ("api", "x", "-f", "body=y"), True),
        ("gh", ("api", "x", "-X", "POST"), True),
        ("gh", ("api", "x"), False),
        ("glab", ("mr", "create"), True),
        ("glab", ("mr", "list"), False),
        ("echo", ("commit",), False),
    ],
)
def test_authoring_command_detection(program: str, args: tuple[str, ...], expected: bool) -> None:
    assert is_authoring_command(SimpleCommand(program, args, args, 0)) is expected


def test_strip_value_options_drops_values_and_keeps_clusters() -> None:
    options = frozenset({"-o", "-u", "--sort"})
    assert strip_value_options(["-u", "deploy", "e"], options) == ["-u", "e"]
    assert strip_value_options(["-eo", "pid"], options) == ["-eo"]
    assert strip_value_options(["--sort", "x", "-E"], options) == ["--sort", "-E"]


def test_command_findings_carry_a_position() -> None:
    finding = scan_command("ls\necho hi\nenv\n")[0]
    assert (finding.rule_id, finding.line) == ("env-dump-env-no-command", 3)


# limits and options ------------------------------------------------------------


def test_text_over_the_limit_is_one_engine_finding() -> None:
    findings = Scanner(max_text_chars=10).scan_text("x" * 11, "big.txt")
    assert [(f.rule_id, f.family, f.source) for f in findings] == [
        (TOO_LARGE_RULE, "engine", "big.txt")
    ]


def test_a_command_over_the_limit_is_one_engine_finding() -> None:
    findings = Scanner(max_command_chars=10).scan_command("echo " + "x" * 20)
    assert [f.rule_id for f in findings] == [TOO_LARGE_RULE]


def test_findings_are_truncated_with_a_marker() -> None:
    findings = scan_text((FAKE_TOKEN + "\n") * (MAX_FINDINGS + 50))
    assert len(findings) == MAX_FINDINGS + 1
    assert findings[-1].rule_id == TRUNCATED_RULE


def test_families_option_limits_the_rules() -> None:
    scanner = Scanner(families=["token"])
    assert scanner.scan_text(TRAILER) == []
    assert scanner.scan_text(f"x {FAKE_TOKEN}") != []


# payloads --------------------------------------------------------------------


def test_payload_command_and_text_fields_are_judged() -> None:
    bash = {"tool_name": "Bash", "tool_input": {"command": "printenv"}}
    assert {f.source for f in scan_payload(bash)} == {"tool_input.command"}
    write = {"tool_name": "Write", "tool_input": {"file_path": "a.md", "content": TRAILER}}
    assert {f.source for f in scan_payload(write)} == {"tool_input.content"}


def test_payload_edits_and_list_commands_are_judged() -> None:
    multi = {"tool_input": {"edits": [{"new_string": "ok"}, {"new_string": TRAILER}, 3]}}
    assert {f.source for f in scan_payload(multi)} == {"tool_input.edits[1].new_string"}
    listed = {"tool_input": {"cmd": ["bash", "-c", "env"]}}
    assert rule_ids(scan_payload(listed)) == {"env-dump-env-no-command"}


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "text",
        [],
        {},
        {"tool_input": "env"},
        {"tool_name": "TodoWrite", "tool_input": {"content": TRAILER}},
        {"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}},
    ],
)
def test_payloads_with_nothing_to_judge_are_clean(payload: object) -> None:
    assert scan_payload(payload) == []


def test_a_command_too_complex_to_split_is_one_engine_finding() -> None:
    findings = scan_command("$(" * 30000)
    assert [(f.rule_id, f.family) for f in findings] == [
        ("guardline-command-too-complex", "engine")
    ]


# a payload is bounded as a whole, not only leaf by leaf ---------------------------------------


def test_many_large_leaves_are_refused_as_a_whole() -> None:
    leaf = "a" * (DEFAULT_MAX_TEXT_CHARS - 1)
    edits = [{"old_string": "a", "new_string": leaf}] * 6
    payload = {"tool_name": "MultiEdit", "tool_input": {"file_path": "x.md", "edits": edits}}
    started = time.perf_counter()
    findings = Scanner().scan_payload(payload)
    assert time.perf_counter() - started < 1.0
    assert [f.rule_id for f in findings] == ["guardline-input-too-large"]
    assert f"longer than {DEFAULT_MAX_TEXT_CHARS} characters" in findings[0].description


def test_command_leaves_together_are_bounded_by_the_command_limit() -> None:
    command = "echo " + "a" * (DEFAULT_MAX_COMMAND_CHARS // 2)
    payload = {"tool_name": "Bash", "tool_input": {"commands": [{"command": command}] * 3}}
    findings = Scanner().scan_payload(payload)
    assert [f.rule_id for f in findings] == ["guardline-input-too-large"]
    assert f"longer than {DEFAULT_MAX_COMMAND_CHARS} characters" in findings[0].description


def test_leaves_that_fit_together_are_still_judged_one_by_one() -> None:
    payload = {"tool_name": "mcp", "tool_input": {"a": "x " * 100, "b": [f"key = {FAKE_TOKEN}"]}}
    assert rule_ids(Scanner().scan_payload(payload)) >= {"token-github-token"}


def test_findings_across_many_leaves_are_capped() -> None:
    leaf = " ".join(f"{FAKE_TOKEN[:-1]}{i % 10}" for i in range(600))
    payload = {"tool_name": "mcp", "tool_input": {"v": [leaf] * 40}}
    findings = Scanner().scan_payload(payload)
    assert len(findings) <= MAX_FINDINGS + 1
    assert findings[-1].rule_id == "guardline-findings-truncated"


# one value at the documented limit scans quickly ------------------------------------------------


@pytest.mark.parametrize("piece", ['"Co-Authored-By:', '"Assisted-By:'])
def test_one_text_value_made_of_quoted_trailer_openings_scans_within_a_second(piece: str) -> None:
    text = (piece * (DEFAULT_MAX_TEXT_CHARS // len(piece) + 1))[:DEFAULT_MAX_TEXT_CHARS]
    started = time.perf_counter()
    Scanner().scan_text(text)
    assert time.perf_counter() - started < 1.0


def test_a_trailer_in_a_quoted_string_is_still_found() -> None:
    agent = "Cl" + "aude"
    assert "attribution-co-author-trailer" in rule_ids(
        Scanner().scan_text(f'msg = "Co-Authored-By: {agent} <x@example.com>"')
    )
    assert "attribution-assisted-by-trailer" in rule_ids(
        Scanner().scan_text(f"say 'Assisted-By: {agent}'")
    )


# the leaf limit is the documented one: more than 2000 strings is too many ---------------------


def test_exactly_the_leaf_limit_of_strings_is_judged_whole() -> None:
    payload = {"tool_name": "mcp__x__y", "tool_input": ["x"] * MAX_PAYLOAD_LEAVES}
    assert Scanner().scan_payload(payload) == []


def test_more_than_the_leaf_limit_of_strings_is_reported() -> None:
    payload = {"tool_name": "mcp__x__y", "tool_input": ["x"] * (MAX_PAYLOAD_LEAVES + 1)}
    assert "guardline-command-too-complex" in rule_ids(Scanner().scan_payload(payload))


# a dictionary key of a tool input is text too ----------------------------------------------------


def test_a_token_in_a_tool_input_key_is_found_without_echoing_the_key() -> None:
    payload = {"tool_name": "mcp__x__y", "tool_input": {f"key = {FAKE_TOKEN}": "v"}}
    findings = Scanner().scan_payload(payload)
    assert any(f.family == "token" for f in findings)
    assert FAKE_TOKEN not in repr(findings)
    assert all("key =" not in f.source for f in findings)


def test_a_token_in_a_nested_tool_input_key_is_found() -> None:
    payload = {"tool_name": "mcp__x__y", "tool_input": {"a": [{FAKE_TOKEN: 1, "b": "v"}]}}
    assert any(f.family == "token" for f in Scanner().scan_payload(payload))


def test_attribution_in_a_tool_input_key_is_not_judged() -> None:
    payload = {"tool_name": "mcp__x__y", "tool_input": {TRAILER: "v"}}
    assert Scanner().scan_payload(payload) == []


def test_keys_have_a_limit_of_their_own() -> None:
    at_limit = {f"k{i}": None for i in range(2000)}
    over = {f"k{i}": None for i in range(2001)}
    assert Scanner().scan_payload({"tool_name": "mcp__x__y", "tool_input": at_limit}) == []
    findings = Scanner().scan_payload({"tool_name": "mcp__x__y", "tool_input": over})
    assert "guardline-command-too-complex" in rule_ids(findings)


def test_keys_do_not_count_toward_the_string_limit() -> None:
    payload = {"tool_name": "mcp__x__y", "tool_input": {"items": ["x"] * MAX_PAYLOAD_LEAVES}}
    assert Scanner().scan_payload(payload) == []
    payload = {"tool_name": "mcp__x__y", "tool_input": {"items": ["x"] * (MAX_PAYLOAD_LEAVES + 1)}}
    assert "guardline-command-too-complex" in rule_ids(Scanner().scan_payload(payload))


def test_a_multi_edit_of_999_edits_is_not_too_complex() -> None:
    edits = [{"old_string": f"a{i}", "new_string": f"b{i}"} for i in range(999)]
    payload = {"tool_name": "MultiEdit", "tool_input": {"file_path": "notes.txt", "edits": edits}}
    assert "guardline-command-too-complex" not in rule_ids(Scanner().scan_payload(payload))


def test_a_multi_edit_with_too_many_strings_is_still_too_complex() -> None:
    edits = [{"old_string": f"a{i}", "new_string": f"b{i}"} for i in range(1000)]
    payload = {"tool_name": "MultiEdit", "tool_input": {"file_path": "notes.txt", "edits": edits}}
    assert "guardline-command-too-complex" in rule_ids(Scanner().scan_payload(payload))


def test_keys_count_toward_the_size_bound() -> None:
    payload = {"tool_name": "mcp__x__y", "tool_input": {"k" * 60: "v" * 30}}
    assert TOO_LARGE_RULE in rule_ids(Scanner(max_text_chars=80).scan_payload(payload))
    assert Scanner(max_text_chars=100).scan_payload(payload) == []


def test_ordinary_tool_inputs_are_unchanged_by_scanning_keys() -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls -la", "description": "list"}}
    assert Scanner().scan_payload(payload) == []
