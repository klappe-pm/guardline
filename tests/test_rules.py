"""Every rule is data with two examples; this suite holds each rule to both."""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

import pytest

from guardline import Scanner, builtin_rules, load_rule_file, verify_rule_examples
from guardline.errors import RuleError
from guardline.model import BUILTIN_FAMILIES, Rule
from guardline.rules import has_nested_quantifier, merge_rules, parse_rules
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
    assert counts == {"attribution": 9, "env-dump": 14, "token": 20}


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
        ("(?:a+){0,4}", False),
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
