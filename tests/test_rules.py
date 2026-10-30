"""Every rule is data with two examples; this suite holds each rule to both."""

from __future__ import annotations

import os
import re
import time
from collections import Counter
from pathlib import Path

import pytest

from guardline import Scanner, builtin_rules, load_rule_file, verify_rule_examples
from guardline.errors import RuleError
from guardline.model import BUILTIN_FAMILIES, Rule
from guardline.rules import (
    has_nested_quantifier,
    merge_rules,
    parse_rules,
    unbounded_repeat_warning,
    unsafe_pattern_reason,
)
from tests.helpers import call_within

RULES = builtin_rules()
IDS = [rule.id for rule in RULES]


def run(scanner: Scanner, rule: Rule, text: str) -> set[str]:
    findings = scanner.scan_text(text) if rule.scope == "text" else scanner.scan_command(text)
    return {finding.rule_id for finding in findings}


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_rule_has_both_examples(rule: Rule) -> None:
    if not rule.example_fires.strip():
        pytest.fail(f"{rule.id}: example_fires is missing")
    if not rule.example_clean.strip():
        pytest.fail(f"{rule.id}: example_clean is missing")


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_fire_example_fires_its_rule(rule: Rule) -> None:
    if rule.id not in run(Scanner(RULES), rule, rule.example_fires):
        pytest.fail(f"{rule.id}: the fire example did not fire the rule")


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_clean_example_is_a_look_alike_that_stays_quiet(rule: Rule) -> None:
    fired = run(Scanner(RULES), rule, rule.example_clean)
    if fired:
        pytest.fail(f"{rule.id}: the clean example fired {sorted(fired)}")


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_verify_rule_examples_reports_no_problem(rule: Rule) -> None:
    assert verify_rule_examples(rule) == []


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_rule_pattern_has_no_nested_quantifier(rule: Rule) -> None:
    assert not has_nested_quantifier(rule.pattern)
    if rule.unless:
        assert not has_nested_quantifier(rule.unless)


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_rule_metadata_is_well_formed(rule: Rule) -> None:
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", rule.id)
    assert rule.id.startswith(rule.family.split("-")[0])
    assert rule.family in BUILTIN_FAMILIES
    assert rule.description.endswith(".")


def test_ids_are_unique() -> None:
    assert len(set(IDS)) == len(IDS)


def test_family_counts() -> None:
    counts = Counter(rule.family for rule in RULES)
    assert counts == {"attribution": 9, "env-dump": 14, "token": 22}


def test_rule_files_are_package_data() -> None:
    from importlib import resources

    names = sorted(
        item.name
        for item in resources.files("guardline").joinpath("data", "rules").iterdir()
        if item.name.endswith(".toml")
    )
    assert names == ["attribution.toml", "env-dump.toml", "token.toml"]


def test_a_rule_that_never_fires_is_caught_by_verification() -> None:
    broken = parse_rules(
        'schema_version = 1\n[[rule]]\nid = "x-a"\nfamily = "style"\ndescription = "d."\n'
        'pattern = "zzz"\nexample_fires = "nothing here"\nexample_clean = "nothing here"\n',
        "t.toml",
    )[0]
    problems = verify_rule_examples(broken)
    assert any("does not fire" in problem for problem in problems)


def test_a_rule_whose_clean_example_fires_is_caught_by_verification() -> None:
    broken = parse_rules(
        'schema_version = 1\n[[rule]]\nid = "x-b"\nfamily = "style"\ndescription = "d."\n'
        'pattern = "zzz"\nexample_fires = "zzz"\nexample_clean = "zzz again"\n',
        "t.toml",
    )[0]
    assert any("not a look-alike" in problem for problem in verify_rule_examples(broken))


GOOD = (
    'schema_version = 1\n[[rule]]\nid = "x-c"\nfamily = "style"\ndescription = "d."\n'
    'pattern = "zzz"\nexample_fires = "zzz"\nexample_clean = "aaa"\n'
)


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("not toml [", "not valid TOML"),
        ("schema_version = 2\n", "schema_version"),
        ("schema_version = 1\nextra = 1\n", "unknown top level"),
        ("schema_version = 1\nrule = 3\n", "array of tables"),
        (GOOD.replace('id = "x-c"\n', ""), "id is required"),
        (GOOD.replace('"x-c"', '"X_C"'), "kebab-case"),
        (GOOD.replace('family = "style"', 'family = "Bad Family"'), "kebab-case"),
        (GOOD.replace('example_clean = "aaa"\n', ""), "example_clean is required"),
        (GOOD.replace('example_fires = "zzz"\n', ""), "example_fires is required"),
        (GOOD.replace('example_clean = "aaa"', 'example_clean = "  "'), "example_clean"),
        (GOOD + "bogus = 1\n", "unknown key"),
        (GOOD.replace('pattern = "zzz"', 'pattern = "("'), "valid regular expression"),
        (GOOD.replace('pattern = "zzz"', 'pattern = "(a+)+b"'), "nested quantifier"),
        (GOOD.replace('pattern = "zzz"', 'pattern = "a*"'), "empty string"),
        (GOOD.replace('pattern = "zzz"', 'pattern = "' + "a" * 5000 + '"'), "longer than"),
        (GOOD + 'scope = "line"\n', "scope must be"),
        (GOOD + 'scope = "args"\n', "requires programs"),
        (GOOD + 'programs = ["ls"]\n', "scope args only"),
        (GOOD + 'ignore_case = "yes"\n', "ignore_case"),
        (GOOD + 'unless = "(a+)+"\n', "nested quantifier"),
        (GOOD + 'unless = ""\n', "unless must be"),
        (GOOD.replace('"zzz"\nexample_fires', '"zzz"\nprograms = [1]\nexample_fires'), "programs"),
    ],
)
def test_invalid_rule_files_are_rejected(text: str, fragment: str) -> None:
    with pytest.raises(RuleError, match=re.escape(fragment)):
        parse_rules(text, "t.toml")


def test_duplicate_ids_in_one_file_are_rejected() -> None:
    body = GOOD.split("[[rule]]")[1]
    with pytest.raises(RuleError, match="duplicate"):
        parse_rules("schema_version = 1\n[[rule]]" + body + "[[rule]]" + body, "t.toml")


def test_merge_rejects_an_id_that_is_taken() -> None:
    clash = parse_rules(GOOD.replace("x-c", RULES[0].id), "t.toml")
    with pytest.raises(RuleError, match="already used"):
        merge_rules(RULES, clash)


def test_error_messages_never_quote_examples() -> None:
    text = GOOD.replace('example_fires = "zzz"', 'example_fires = "SENTINEL-EXAMPLE"').replace(
        'pattern = "zzz"', 'pattern = "(a+)+"'
    )
    with pytest.raises(RuleError) as caught:
        parse_rules(text, "t.toml")
    assert "SENTINEL-EXAMPLE" not in str(caught.value)


def test_load_rule_file_reads_disk(tmp_path: Path) -> None:
    file = tmp_path / "mine.toml"
    file.write_text(GOOD, encoding="utf-8")
    assert [rule.id for rule in load_rule_file(file)] == ["x-c"]


def test_load_rule_file_reports_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(RuleError, match="cannot read"):
        load_rule_file(tmp_path / "absent.toml")


@pytest.mark.parametrize(
    ("pattern", "nested"),
    [
        ("(a+)+", True),
        ("(?:a*)*", True),
        ("(?:\\S+ )*", True),
        ("(?:a|b+)+c", True),
        ("(?:\\d+){0,40}", True),
        ("a+b+", False),
        ("(?:a+){0,4}", True),
        ("(?:[a-z0-9-]{1,63}\\.){0,8}x", False),
        ("(?=a+)b+", False),
        ("a{16,128}+(?!\\()", False),
        ("(", False),
    ],
)
def test_nested_quantifier_detection(pattern: str, nested: bool) -> None:
    assert has_nested_quantifier(pattern) is nested


# reading a rule file safely -------------------------------------------------------------------


def test_a_rule_file_that_is_not_utf8_is_a_rule_error(tmp_path: Path) -> None:
    path = tmp_path / "rules.toml"
    path.write_bytes(b"schema_version = 1\n# \xff\n")
    with pytest.raises(RuleError, match="UnicodeDecodeError"):
        load_rule_file(path)


def test_a_rule_file_nested_too_deeply_is_a_rule_error(tmp_path: Path) -> None:
    path = tmp_path / "rules.toml"
    path.write_text("schema_version = 1\nx = " + "[" * 5000 + "]" * 5000 + "\n", encoding="utf-8")
    with pytest.raises(RuleError, match="nested too deeply"):
        load_rule_file(path)


def test_parse_rules_reports_deep_nesting_as_a_rule_error() -> None:
    with pytest.raises(RuleError, match="nested too deeply"):
        parse_rules("x = " + "[" * 5000 + "]" * 5000 + "\n", "inline")


def test_an_oversized_rule_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "rules.toml"
    path.write_text("schema_version = 1\n#" + "a" * (1 << 20) + "\n", encoding="utf-8")
    with pytest.raises(RuleError, match="larger than"):
        load_rule_file(path)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a FIFO")
def test_a_fifo_rule_file_is_refused_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "rules.toml"
    os.mkfifo(fifo)
    with pytest.raises(RuleError, match="not a regular file"):
        call_within(10, lambda: load_rule_file(fifo))


# the audit sees the shapes that used to slip past it -------------------------------------------

AUDIT_BYPASSES = {
    # pattern: a hostile input that takes seconds if the loader accepts the pattern
    "a*A*;": "a" * 1500,
    r"\w*-?\w*;": "a" * 1500,
    ".*\u00e9*;": "\u00e9" * 1500,
    r"\d*[\u0660-\u0669]*;": "\u0661" * 1200,
    r"(?>(?:a+)+;)": "a" * 25,
    r"\w{0,100000}-?\w{0,100000}-?\w{0,100000}-?\w{0,100000};": "a" * 150,
    r"(?:(?:a{0,16}){0,16});": "a" * 24,
    r"(?:(?:(?:a{0,16}){0,16}){0,16});": "a" * 12,
    r"(?:a{1,2}){0,16};": "a" * 1000,
    r"(a*)a*;": "a" * 1500,
    r"a*(a*);": "a" * 1500,
    r"(a*)(a*);": "a" * 1500,
    r"(?i:a*)a*;": "a" * 1500,
    r"(?s:a*)a*;": "a" * 1500,
    r"(?P<n>a*)a*;": "a" * 1500,
    r"a*(?:x|a*);": "a" * 1500,
    r"(?:x|a*)a*;": "a" * 1500,
    r"\w+(-?)\w+;": "a" * 1500,
    r"(\w*)-?\w*;": "a" * 1500,
    r"\s*(\s*)x": " " * 1500,
    r"(?:a|a){0,16};": "a" * 20,
    r"(?:aa|a){0,16};": "a" * 20,
}


def rule_file_with(pattern: str) -> str:
    body = pattern.replace("\\", "\\\\").replace('"', '\\"')
    return (
        'schema_version = 1\n[[rule]]\nid = "probe"\nfamily = "probe"\ndescription = "d"\n'
        f'pattern = "{body}"\nexample_fires = "x"\nexample_clean = "y"\n'
    )


@pytest.mark.parametrize("pattern", sorted(AUDIT_BYPASSES))
def test_the_loader_rejects_or_bounds_a_super_linear_pattern(pattern: str) -> None:
    try:
        (rule,) = parse_rules(rule_file_with(pattern), "probe.toml")
    except RuleError:
        return
    started = time.perf_counter()
    rule.regex.search(AUDIT_BYPASSES[pattern])
    assert time.perf_counter() - started < 0.5


@pytest.mark.parametrize("pattern", sorted(AUDIT_BYPASSES))
def test_the_audit_names_a_reason_for_each_bypass(pattern: str) -> None:
    flags = re.MULTILINE | re.IGNORECASE
    assert unsafe_pattern_reason(pattern, flags) is not None


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_every_builtin_pattern_passes_the_audit_with_its_own_flags(rule: Rule) -> None:
    assert unsafe_pattern_reason(rule.pattern, rule.regex.flags) is None
    if rule.unless:
        assert unsafe_pattern_reason(rule.unless, rule.regex.flags) is None


@pytest.mark.parametrize(
    "pattern",
    [
        r"(?:-[A-Za-z]+(?: |$)){0,8}",
        r"(?:[a-z0-9-]{1,63}\.){0,8}x",
        r"(?:\.[a-z]*){1,8}",
        r"[a-z]+-[0-9]+",
        r"\d+(?:\.\d+)?",
        r"a{1,2}b?c",
    ],
)
def test_ordinary_shapes_are_still_accepted(pattern: str) -> None:
    assert unsafe_pattern_reason(pattern, re.IGNORECASE) is None


@pytest.mark.parametrize(
    "pattern",
    [
        r"(?:ab|cd){0,4}x",
        r"(?:foo|bar){1,3};",
        r"(\d+)(?:\.\d+)?",
        r"(a*)b*;",
        r"a*(?:x|y);",
        r"(?:x|y)a*;",
        r"(?i:a*)b*;",
        r"(?:a|b)x{0,16}",
    ],
)
def test_groups_and_alternations_that_cannot_overlap_are_accepted(pattern: str) -> None:
    assert unsafe_pattern_reason(pattern, re.IGNORECASE) is None


def test_a_scoped_case_flag_is_seen_inside_a_group() -> None:
    assert unsafe_pattern_reason(r"(?i:a*)A*;", 0) is not None
    assert unsafe_pattern_reason(r"(?i:a*)b*;", 0) is None


@pytest.mark.parametrize(
    "pattern", [r"(a)*a*;", r"(?:ab)*(?:ab)*;", r"a*(?=a)a*;", r"a*aaa*;", r"[ab]*ab[ab]*;"]
)
def test_documented_audit_gap_is_still_open(pattern: str) -> None:
    """Pinned by the known gaps in docs/explanation/security-model.md."""
    assert unsafe_pattern_reason(pattern, re.IGNORECASE) is None
    assert unbounded_repeat_warning(pattern, re.IGNORECASE) is not None


@pytest.mark.parametrize("pattern", [r"a*aa*;", r"a*a{2}a*;", r"a*a{1,3}a*;", r"\w+_\w+;"])
def test_the_audit_sees_an_overlap_across_a_literal(pattern: str) -> None:
    flags = re.IGNORECASE | re.MULTILINE | re.UNICODE
    assert unsafe_pattern_reason(pattern, flags) == "adjacent overlapping repeats"


@pytest.mark.parametrize("pattern", [r"a*;a*;", r"a*b{2}a*;", r"\d+\.\d+;", r"\w+-\w+;"])
def test_a_literal_outside_both_repeats_still_separates_them(pattern: str) -> None:
    flags = re.IGNORECASE | re.MULTILINE | re.UNICODE
    assert unsafe_pattern_reason(pattern, flags) is None


@pytest.mark.parametrize(
    "command",
    [
        "declare -" + "p" * 30000 + "!",
        "ps " + "e" * 30000 + "!",
        "ps -" + "E" * 30000 + "!",
        "security find-generic-password -" + "w" * 30000 + "!",
        "security dump-keychain -" + "d" * 30000 + "!",
    ],
    ids=["declare", "ps-bsd", "ps-flag", "security-print", "security-dump"],
)
def test_a_long_run_of_the_flag_letter_is_scanned_in_linear_time(command: str) -> None:
    """These rules once ran a repeat on each side of the letter they look for: ten seconds."""
    start = time.perf_counter()
    Scanner().scan_command(command)
    assert time.perf_counter() - start < 2.0


@pytest.mark.parametrize(
    "command",
    [
        "declare -p",
        "declare -xp",
        "ps -E",
        "ps -eE",
        "ps eww",
        "security find-generic-password -gw",
    ],
)
def test_the_flag_rules_still_fire_on_a_word_with_the_letter(command: str) -> None:
    assert {f.rule_id for f in Scanner().scan_command(command)}


def test_a_bound_over_1024_counts_as_unbounded() -> None:
    assert unsafe_pattern_reason(r"a{0,2000}b{0,2000}c{0,2000}d{0,2000}") == (
        "more than 3 unbounded repeats"
    )


def test_case_folding_cannot_hide_an_overlap() -> None:
    assert unsafe_pattern_reason("a*A*;", re.IGNORECASE) is not None
    assert unsafe_pattern_reason("a*A*;", 0) is None


def test_the_audit_uses_the_flags_of_the_rule(tmp_path: Path) -> None:
    text = rule_file_with("a*A*;").replace(
        'family = "probe"', 'family = "probe"\nignore_case = true'
    )
    with pytest.raises(RuleError, match="unsafe"):
        parse_rules(text, "probe.toml")
    case_sensitive = text.replace("ignore_case = true", "ignore_case = false")
    assert parse_rules(case_sensitive, "probe.toml")


# rules check warns about the shapes that stay quadratic ---------------------------------------


@pytest.mark.parametrize("pattern", ["[a-z]+;", r"(?=\w*;)\w"])
def test_a_single_unbounded_repeat_is_accepted_but_reported(pattern: str) -> None:
    assert unsafe_pattern_reason(pattern, re.IGNORECASE) is None
    assert unbounded_repeat_warning(pattern, re.IGNORECASE) is not None


def test_a_bounded_pattern_has_no_warning() -> None:
    assert unbounded_repeat_warning("[a-z]{1,40};", re.IGNORECASE) is None
