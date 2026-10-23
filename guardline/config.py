"""Read guardline configuration and assemble the rule set.

Configuration comes from ``guardline.toml`` (top level keys) or from the
``[tool.guardline]`` table of ``pyproject.toml``. The nearest file found walking up
from the starting directory wins, and ``guardline.toml`` wins over ``pyproject.toml``
in the same directory. The walk stops at the first directory that holds a ``.git``
entry. There is deliberately no configuration key that turns on the fenced
attribution exception: it is a per run switch only.
"""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from guardline.engine import DEFAULT_MAX_COMMAND_CHARS, DEFAULT_MAX_TEXT_CHARS, Scanner
from guardline.errors import ConfigError
from guardline.fileio import FileRefused, read_small_file
from guardline.model import Rule
from guardline.rules import builtin_rules, load_rule_file, merge_rules

MODES = ("report", "block")
CONFIG_NAMES = ("guardline.toml", "pyproject.toml")
MAX_TEXT_CHARS_CAP = 16 * 1024 * 1024
"""Largest ``max_text_chars`` a configuration may set: 16 MiB of characters."""
MAX_COMMAND_CHARS_CAP = 1024 * 1024
"""Largest ``max_command_chars`` a configuration may set: 1 MiB of characters."""
_KEYS = frozenset(
    {"mode", "disable", "rule_files", "families", "exclude", "max_text_chars", "max_command_chars"}
)


@dataclass(frozen=True)
class Config:
    """Resolved configuration.

    Attributes:
        mode: ``report``, ``block`` or None when the file does not say.
        disable: rule ids to turn off.
        rule_files: extra rule files, already resolved against the config file's directory.
        families: when set, only these families run.
        exclude: glob patterns of paths the file scan skips.
        max_text_chars: text size limit, or None for the default.
        max_command_chars: shell command size limit, or None for the default.
        origin: the file the values came from, or None for defaults.
    """

    mode: str | None = None
    disable: tuple[str, ...] = ()
    rule_files: tuple[Path, ...] = ()
    families: tuple[str, ...] | None = None
    exclude: tuple[str, ...] = ()
    max_text_chars: int | None = None
    max_command_chars: int | None = None
    origin: Path | None = None


def _string_list(table: dict[str, Any], key: str, origin: Path) -> tuple[str, ...]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"{origin}: {key} must be a list of non-empty strings")
    return tuple(value)


def _limit(table: dict[str, Any], key: str, origin: Path, cap: int) -> int | None:
    value = table.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"{origin}: {key} must be a positive integer")
    if value > cap:
        raise ConfigError(f"{origin}: {key} must be a positive integer of at most {cap}")
    return value


def _confined(items: tuple[str, ...], origin: Path) -> tuple[Path, ...]:
    """Resolve rule file paths against the config directory and keep them inside it."""
    root = origin.parent.resolve()
    resolved: list[Path] = []
    for item in items:
        path = (root / item).resolve()
        if not path.is_relative_to(root):
            raise ConfigError(f"{origin}: a rule_files entry leaves the configuration directory")
        resolved.append(path)
    return tuple(resolved)


def config_from_table(table: dict[str, Any], origin: Path) -> Config:
    """Validate a configuration table and resolve it.

    Raises:
        ConfigError: the table has an unknown key, a value of the wrong type, or an
            empty ``families`` list, which would leave no rule to run.
    """
    unknown = sorted(set(table) - _KEYS)
    if unknown:
        raise ConfigError(f"{origin}: unknown key(s): {', '.join(unknown)}")
    mode = table.get("mode")
    if mode is not None and mode not in MODES:
        raise ConfigError(f"{origin}: mode must be one of {', '.join(MODES)}")
    families = _string_list(table, "families", origin) if "families" in table else None
    if families == ():
        raise ConfigError(f"{origin}: families must name at least one family")
    return Config(
        mode=mode,
        disable=_string_list(table, "disable", origin),
        rule_files=_confined(_string_list(table, "rule_files", origin), origin),
        families=families,
        exclude=_string_list(table, "exclude", origin),
        max_text_chars=_limit(table, "max_text_chars", origin, MAX_TEXT_CHARS_CAP),
        max_command_chars=_limit(table, "max_command_chars", origin, MAX_COMMAND_CHARS_CAP),
        origin=origin,
    )


def _read(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(read_small_file(path).decode("utf-8"))
    except FileRefused as refusal:
        raise ConfigError(f"{path}: cannot read configuration: {refusal}") from None
    except (OSError, UnicodeDecodeError, RecursionError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(
            f"{path}: cannot read configuration: {error.__class__.__name__}"
        ) from None


def load_config_file(path: Path) -> Config:
    """Load one configuration file explicitly named by the user.

    A file named ``pyproject.toml`` is read from its ``[tool.guardline]`` table, and any
    other file is read from its top level keys.

    Raises:
        ConfigError: the file cannot be read or is invalid.
    """
    document = _read(path)
    if path.name == "pyproject.toml":
        tool = document.get("tool", {})
        table = tool.get("guardline") if isinstance(tool, dict) else None
        if not isinstance(table, dict):
            raise ConfigError(f"{path}: no [tool.guardline] table")
        return config_from_table(table, path)
    return config_from_table(document, path)


def discover_config(start: Path) -> Config:
    """Find the nearest configuration walking up from ``start``.

    Returns:
        The configuration, or defaults when none is found.
    """
    directory = start.resolve()
    while True:
        guardline_toml = directory / "guardline.toml"
        if guardline_toml.is_file():
            return load_config_file(guardline_toml)
        pyproject = directory / "pyproject.toml"
        if pyproject.is_file():
            tool = _read(pyproject).get("tool", {})
            table = tool.get("guardline") if isinstance(tool, dict) else None
            if isinstance(table, dict):
                return config_from_table(table, pyproject)
        if (directory / ".git").exists() or directory.parent == directory:
            return Config()
        directory = directory.parent


def build_ruleset(
    config: Config,
    extra_rule_files: Sequence[Path] = (),
    extra_disable: Sequence[str] = (),
) -> tuple[Rule, ...]:
    """Combine built-in rules, custom rule files and disables into the active rules.

    Raises:
        RuleError: a rule file is invalid or reuses an id.
        ConfigError: a disabled id names no rule.
    """
    rules = builtin_rules()
    for path in (*config.rule_files, *extra_rule_files):
        rules = merge_rules(rules, load_rule_file(path))
    known = {rule.id for rule in rules}
    disabled = {*config.disable, *extra_disable}
    unknown = sorted(disabled - known)
    if unknown:
        raise ConfigError(f"unknown rule id(s) in disable: {', '.join(unknown)}")
    return tuple(rule for rule in rules if rule.id not in disabled)


def build_scanner(
    config: Config,
    *,
    extra_rule_files: Sequence[Path] = (),
    extra_disable: Sequence[str] = (),
    families: Sequence[str] | None = None,
    allow_fenced_attribution: bool = False,
    allow_config_edit: bool = False,
    protected_paths: Sequence[str] = (),
) -> Scanner:
    """Build a ``Scanner`` from a configuration and command line overrides.

    Raises:
        ConfigError: a chosen family matches no active rule, or the configuration leaves
            no active rule at all. Either would give the scanner no rules, so block mode
            would pass everything.
    """
    rules = build_ruleset(config, extra_rule_files, extra_disable)
    if not rules:
        raise ConfigError("the configuration leaves no active rules")
    chosen = families if families else config.families
    if chosen is not None:
        if not chosen:
            raise ConfigError("the configuration leaves no active rules")
        present = {rule.family for rule in rules}
        unknown = sorted(set(chosen) - present)
        if unknown:
            raise ConfigError(
                f"unknown family(s): {', '.join(unknown)} "
                f"(active families: {', '.join(sorted(present))})"
            )
    return Scanner(
        rules,
        allow_fenced_attribution=allow_fenced_attribution,
        allow_config_edit=allow_config_edit,
        protected_paths=protected_paths,
        max_text_chars=config.max_text_chars or DEFAULT_MAX_TEXT_CHARS,
        max_command_chars=config.max_command_chars or DEFAULT_MAX_COMMAND_CHARS,
        families=chosen,
    )
