"""Load, validate and verify rule files.

Rules are data. The built-in rules ship as TOML under ``guardline/data/rules`` and
are read through ``importlib.resources``. A user adds rules with a file in the
same format. See ``docs/reference/rule-file-format.md``.
"""

from __future__ import annotations

import functools
import re
import tomllib
from collections.abc import Sequence
from importlib import resources
from pathlib import Path
from typing import Any

from guardline.audit import (  # noqa: F401 (re-exported)
    MAX_UNBOUNDED_REPEATS,
    unbounded_repeat_warning,
    unsafe_pattern_reason,
)
from guardline.errors import RuleError
from guardline.fileio import FileRefused, read_small_file
from guardline.model import SCOPES, Rule

SCHEMA_VERSION = 1
"""The only rule file schema version this release reads."""

MAX_PATTERN_CHARS = 4000
"""Longest accepted pattern or unless expression, in characters."""

_KEBAB = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_ALLOWED_KEYS = frozenset(
    {
        "id",
        "family",
        "description",
        "pattern",
        "scope",
        "programs",
        "value_options",
        "unless",
        "ignore_case",
        "example_fires",
        "example_clean",
    }
)


def has_nested_quantifier(pattern: str, flags: int = 0) -> bool:
    """Return True when ``unsafe_pattern_reason`` finds a problem with ``pattern``."""
    return unsafe_pattern_reason(pattern, flags) is not None


def _fail(origin: str, rule_id: str, message: str) -> RuleError:
    return RuleError(f"{origin}: rule {rule_id}: {message}")


def _string(table: dict[str, Any], key: str, origin: str, rule_id: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _fail(origin, rule_id, f"{key} is required and must be a non-empty string")
    return value


def _string_list(table: dict[str, Any], key: str, origin: str, rule_id: str) -> frozenset[str]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise _fail(origin, rule_id, f"{key} must be a list of non-empty strings")
    return frozenset(value)


def _compile(
    source: str, flags: int, origin: str, rule_id: str, label: str, *, allow_empty: bool
) -> re.Pattern[str]:
    if len(source) > MAX_PATTERN_CHARS:
        raise _fail(origin, rule_id, f"{label} is longer than {MAX_PATTERN_CHARS} characters")
    try:
        compiled = re.compile(source, flags)
    except re.error as error:
        raise _fail(
            origin, rule_id, f"{label} is not a valid regular expression: {error}"
        ) from None
    reason = unsafe_pattern_reason(source, flags)
    if reason:
        raise _fail(origin, rule_id, f"{label} is unsafe: {reason}")
    if not allow_empty and compiled.search("") is not None:
        raise _fail(origin, rule_id, f"{label} matches the empty string")
    return compiled


def _build_rule(table: dict[str, Any], origin: str) -> Rule:
    raw_id = table.get("id")
    rule_id = raw_id if isinstance(raw_id, str) else "<missing id>"
    unknown = sorted(set(table) - _ALLOWED_KEYS)
    if unknown:
        raise _fail(origin, rule_id, f"unknown key(s): {', '.join(unknown)}")
    rule_id = _string(table, "id", origin, rule_id)
    if not _KEBAB.fullmatch(rule_id):
        raise _fail(origin, rule_id, "id must be lowercase kebab-case")
    family = _string(table, "family", origin, rule_id)
    if not _KEBAB.fullmatch(family):
        raise _fail(origin, rule_id, "family must be lowercase kebab-case")
    description = _string(table, "description", origin, rule_id)
    pattern = _string(table, "pattern", origin, rule_id)
    example_fires = _string(table, "example_fires", origin, rule_id)
    example_clean = _string(table, "example_clean", origin, rule_id)
    scope = table.get("scope", "text")
    if scope not in SCOPES:
        raise _fail(origin, rule_id, f"scope must be one of {', '.join(SCOPES)}")
    programs = _string_list(table, "programs", origin, rule_id)
    value_options = _string_list(table, "value_options", origin, rule_id)
    if scope == "args" and not programs:
        raise _fail(origin, rule_id, "scope args requires programs")
    if scope != "args" and (programs or value_options):
        raise _fail(origin, rule_id, "programs and value_options apply to scope args only")
    ignore_case = table.get("ignore_case", scope == "text")
    if not isinstance(ignore_case, bool):
        raise _fail(origin, rule_id, "ignore_case must be true or false")
    unless = table.get("unless")
    if unless is not None and (not isinstance(unless, str) or not unless):
        raise _fail(origin, rule_id, "unless must be a non-empty string")
    flags = re.MULTILINE | (re.IGNORECASE if ignore_case else 0)
    allow_empty = scope != "text"
    regex = _compile(pattern, flags, origin, rule_id, "pattern", allow_empty=allow_empty)
    unless_regex = (
        _compile(unless, flags, origin, rule_id, "unless", allow_empty=True) if unless else None
    )
    return Rule(
        id=rule_id,
        family=family,
        description=description,
        pattern=pattern,
        scope=scope,
        programs=programs,
        value_options=value_options,
        unless=unless,
        ignore_case=ignore_case,
        example_fires=example_fires,
        example_clean=example_clean,
        origin=origin,
        regex=regex,
        unless_regex=unless_regex,
    )


def parse_rules(text: str, origin: str) -> tuple[Rule, ...]:
    """Parse the text of a rule file.

    Args:
        text: the TOML source.
        origin: a label for error messages, usually the file name.

    Raises:
        RuleError: the text is not valid TOML, uses another schema version, or a
            rule fails validation.
    """
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise RuleError(f"{origin}: not valid TOML: {error}") from None
    except RecursionError:
        raise RuleError(f"{origin}: not valid TOML: nested too deeply") from None
    version = document.get("schema_version")
    if version != SCHEMA_VERSION:
        raise RuleError(f"{origin}: schema_version must be {SCHEMA_VERSION}")
    unknown = sorted(set(document) - {"schema_version", "rule"})
    if unknown:
        raise RuleError(f"{origin}: unknown top level key(s): {', '.join(unknown)}")
    tables = document.get("rule", [])
    if not isinstance(tables, list):
        raise RuleError(f"{origin}: rule must be an array of tables")
    rules: list[Rule] = []
    seen: set[str] = set()
    for table in tables:
        rule = _build_rule(table, origin)
        if rule.id in seen:
            raise _fail(origin, rule.id, "duplicate id in the same file")
        seen.add(rule.id)
        rules.append(rule)
    return tuple(rules)


def load_rule_file(path: str | Path) -> tuple[Rule, ...]:
    """Load a rule file from disk.

    Raises:
        RuleError: the file cannot be read or is invalid.
    """
    file = Path(path)
    try:
        text = read_small_file(file).decode("utf-8")
    except FileRefused as refusal:
        raise RuleError(f"{file}: cannot read rule file: {refusal}") from None
    except (OSError, UnicodeDecodeError) as error:
        raise RuleError(f"{file}: cannot read rule file: {error.__class__.__name__}") from None
    return parse_rules(text, str(file))


@functools.cache
def builtin_rules() -> tuple[Rule, ...]:
    """Return every rule shipped in the package, ordered by file name then position."""
    directory = resources.files("guardline").joinpath("data", "rules")
    rules: list[Rule] = []
    for entry in sorted(directory.iterdir(), key=lambda item: item.name):
        if entry.name.endswith(".toml"):
            rules.extend(parse_rules(entry.read_text(encoding="utf-8"), entry.name))
    return tuple(rules)


def merge_rules(base: Sequence[Rule], extra: Sequence[Rule]) -> tuple[Rule, ...]:
    """Return ``base`` followed by ``extra``.

    Raises:
        RuleError: an id in ``extra`` is already taken.
    """
    taken = {rule.id for rule in base}
    for rule in extra:
        if rule.id in taken:
            raise _fail(rule.origin, rule.id, "id is already used by another rule")
        taken.add(rule.id)
    return (*base, *extra)


def verify_rule_examples(rule: Rule, ruleset: Sequence[Rule] | None = None) -> list[str]:
    """Check that a rule fires on its fire example and not on its clean example.

    Args:
        rule: the rule to check.
        ruleset: the rules to scan with. Defaults to the built-in rules plus ``rule``.

    Returns:
        A list of problems, empty when the rule behaves. Problems never quote an example.
    """
    from guardline.engine import Scanner

    rules = tuple(ruleset) if ruleset is not None else builtin_rules()
    if rule not in rules:
        rules = (*rules, rule)
    scanner = Scanner(rules)
    run = scanner.scan_text if rule.scope == "text" else scanner.scan_command
    problems: list[str] = []
    if rule.id not in {finding.rule_id for finding in run(rule.example_fires)}:
        problems.append(f"rule {rule.id}: example_fires does not fire the rule")
    if rule.id in {finding.rule_id for finding in run(rule.example_clean)}:
        problems.append(f"rule {rule.id}: example_clean fires the rule, so it is not a look-alike")
    return problems
