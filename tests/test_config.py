"""Configuration discovery, validation and the assembled rule set."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from guardline.config import (
    Config,
    build_ruleset,
    build_scanner,
    config_from_table,
    discover_config,
    load_config_file,
)
from guardline.errors import ConfigError, RuleError
from guardline.rules import builtin_rules
from tests.helpers import call_within
from tests.samples import TRAILER

RULE_FILE = (
    'schema_version = 1\n[[rule]]\nid = "style-no-todo"\nfamily = "style"\n'
    'description = "No TODO markers."\npattern = "TODO"\n'
    'example_fires = "TODO fix"\nexample_clean = "done"\n'
)


def test_guardline_toml_top_level_keys(tmp_path: Path) -> None:
    file = tmp_path / "guardline.toml"
    file.write_text(
        'mode = "report"\ndisable = ["token-jwt"]\nrule_files = ["mine.toml"]\n'
        'families = ["token"]\nexclude = ["*.lock"]\nmax_text_chars = 99\nmax_command_chars = 77\n',
        encoding="utf-8",
    )
    config = load_config_file(file)
    assert config.mode == "report"
    assert config.disable == ("token-jwt",)
    assert config.rule_files == ((tmp_path / "mine.toml").resolve(),)
    assert config.families == ("token",)
    assert config.exclude == ("*.lock",)
    assert (config.max_text_chars, config.max_command_chars) == (99, 77)
    assert config.origin == file


def test_pyproject_tool_table(tmp_path: Path) -> None:
    file = tmp_path / "pyproject.toml"
    file.write_text(
        '[tool.other]\nx = 1\n[tool.guardline]\ndisable = ["token-jwt"]\n', encoding="utf-8"
    )
    assert load_config_file(file).disable == ("token-jwt",)


def test_pyproject_without_a_table_is_an_error_when_named(tmp_path: Path) -> None:
    file = tmp_path / "pyproject.toml"
    file.write_text("[project]\nname = 'x'\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"no .tool.guardline. table"):
        load_config_file(file)


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ("bogus = 1", "unknown key"),
        ('mode = "loud"', "mode must be"),
        ("disable = 3", "disable must be"),
        ("disable = [1]", "disable must be"),
        ("max_text_chars = 0", "positive integer"),
        ("max_text_chars = true", "positive integer"),
        ("allow_fenced_attribution = true", "unknown key"),
    ],
)
def test_invalid_configuration(tmp_path: Path, body: str, fragment: str) -> None:
    file = tmp_path / "guardline.toml"
    file.write_text(body + "\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=fragment):
        load_config_file(file)


def test_unreadable_configuration(tmp_path: Path) -> None:
    broken = tmp_path / "guardline.toml"
    broken.write_text("= =", encoding="utf-8")
    with pytest.raises(ConfigError, match="cannot read"):
        load_config_file(broken)
    with pytest.raises(ConfigError, match="cannot read"):
        load_config_file(tmp_path / "absent.toml")


def test_discovery_walks_up_and_prefers_guardline_toml(tmp_path: Path) -> None:
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.guardline]\nmode = "report"\n', encoding="utf-8"
    )
    assert discover_config(tmp_path / "a" / "b").mode == "report"
    (tmp_path / "a" / "guardline.toml").write_text('mode = "block"\n', encoding="utf-8")
    assert discover_config(tmp_path / "a" / "b").mode == "block"


def test_discovery_skips_a_pyproject_without_a_table(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    assert discover_config(tmp_path) == Config()


def test_discovery_stops_at_the_repository_root(tmp_path: Path) -> None:
    (tmp_path / "guardline.toml").write_text('mode = "report"\n', encoding="utf-8")
    inner = tmp_path / "repo"
    (inner / ".git").mkdir(parents=True)
    assert discover_config(inner) == Config()


def test_from_table_defaults() -> None:
    assert config_from_table({}, Path("x.toml")).mode is None


def test_disabling_removes_a_rule() -> None:
    config = Config(disable=("token-jwt",))
    assert "token-jwt" not in {rule.id for rule in build_ruleset(config)}
    assert len(build_ruleset(config)) == len(builtin_rules()) - 1


def test_unknown_disable_id_is_an_error() -> None:
    with pytest.raises(ConfigError, match="no-such"):
        build_ruleset(Config(disable=("no-such",)))
    with pytest.raises(ConfigError, match="typo"):
        build_ruleset(Config(), extra_disable=("typo",))


def test_custom_rule_files_extend_the_rules(tmp_path: Path) -> None:
    file = tmp_path / "mine.toml"
    file.write_text(RULE_FILE, encoding="utf-8")
    rules = build_ruleset(Config(rule_files=(file,)))
    assert "style-no-todo" in {rule.id for rule in rules}
    scanner = build_scanner(Config(rule_files=(file,)))
    assert [f.rule_id for f in scanner.scan_text("TODO later")] == ["style-no-todo"]


def test_a_custom_rule_can_be_disabled_by_id(tmp_path: Path) -> None:
    file = tmp_path / "mine.toml"
    file.write_text(RULE_FILE, encoding="utf-8")
    config = Config(rule_files=(file,), disable=("style-no-todo",))
    assert build_scanner(config).scan_text("TODO later") == []


def test_a_custom_rule_cannot_reuse_a_builtin_id(tmp_path: Path) -> None:
    file = tmp_path / "mine.toml"
    file.write_text(RULE_FILE.replace("style-no-todo", "token-jwt"), encoding="utf-8")
    with pytest.raises(RuleError, match="already used"):
        build_ruleset(Config(rule_files=(file,)))


def test_scanner_limits_and_families_come_from_config() -> None:
    scanner = build_scanner(Config(max_text_chars=5, max_command_chars=6, families=("token",)))
    assert (scanner.max_text_chars, scanner.max_command_chars) == (5, 6)
    assert {rule.family for rule in scanner.rules} == {"token"}
    override = build_scanner(Config(families=("token",)), families=["attribution"])
    assert {rule.family for rule in override.rules} == {"attribution"}


def test_unknown_family_in_config_is_an_error_not_an_empty_scanner() -> None:
    with pytest.raises(ConfigError, match="unknown famil"):
        build_scanner(Config(families=("tokens",)))


def test_unknown_family_on_the_command_line_is_an_error() -> None:
    with pytest.raises(ConfigError, match="tokens"):
        build_scanner(Config(), families=["token", "tokens"])


def test_family_from_a_custom_rule_file_is_known(tmp_path: Path) -> None:
    file = tmp_path / "mine.toml"
    file.write_text(RULE_FILE, encoding="utf-8")
    scanner = build_scanner(Config(rule_files=(file,), families=("style",)))
    assert {rule.id for rule in scanner.rules} == {"style-no-todo"}


def test_disabling_the_trailer_rules_lets_the_trailer_through() -> None:
    config = Config(disable=("attribution-co-author-trailer", "attribution-vendor-noreply-address"))
    assert build_scanner(config).scan_text(TRAILER) == []


# a configuration must leave at least one active rule ---------------------------------------


def test_an_empty_families_list_is_refused_when_the_table_is_read(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="families"):
        config_from_table({"families": []}, tmp_path / "guardline.toml")


def test_an_empty_families_value_is_refused_when_the_scanner_is_built() -> None:
    with pytest.raises(ConfigError, match="no active rules"):
        build_scanner(Config(families=()))


def test_disabling_every_rule_is_refused() -> None:
    every_rule = tuple(rule.id for rule in builtin_rules())
    with pytest.raises(ConfigError, match="no active rules"):
        build_scanner(Config(disable=every_rule))
    with pytest.raises(ConfigError, match="no active rules"):
        build_scanner(Config(), extra_disable=every_rule)


def test_disabling_one_whole_family_leaves_the_others_active() -> None:
    token_rules = tuple(rule.id for rule in builtin_rules() if rule.family == "token")
    scanner = build_scanner(Config(disable=token_rules))
    assert scanner.rules
    assert "token" not in {rule.family for rule in scanner.rules}


def test_a_config_file_with_empty_families_is_a_config_error(tmp_path: Path) -> None:
    file = tmp_path / "guardline.toml"
    file.write_text("families = []\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="families"):
        load_config_file(file)


# reading the file safely ---------------------------------------------------------------------


def test_a_config_that_is_not_utf8_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_bytes(b'[tool.guardline]\nmode = "block"\n# \xff\n')
    with pytest.raises(ConfigError, match="UnicodeDecodeError"):
        load_config_file(path)


def test_a_config_nested_too_deeply_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "guardline.toml"
    path.write_text("x = " + "[" * 5000 + "]" * 5000 + "\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="RecursionError"):
        load_config_file(path)


def test_an_oversized_config_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "guardline.toml"
    path.write_text('mode = "block"\n#' + "a" * (1 << 20) + "\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="larger than"):
        load_config_file(path)


def test_a_config_at_the_size_limit_is_read(tmp_path: Path) -> None:
    path = tmp_path / "guardline.toml"
    body = 'mode = "block"\n#'
    path.write_text(body + "a" * ((1 << 20) - len(body) - 1) + "\n", encoding="utf-8")
    assert load_config_file(path).mode == "block"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a FIFO")
def test_a_fifo_config_is_refused_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "guardline.toml"
    os.mkfifo(fifo)
    with pytest.raises(ConfigError, match="not a regular file"):
        call_within(10, lambda: load_config_file(fifo))


def test_a_config_that_is_a_link_to_a_regular_file_is_still_read(tmp_path: Path) -> None:
    real = tmp_path / "real.toml"
    real.write_text('mode = "report"\n', encoding="utf-8")
    link = tmp_path / "guardline.toml"
    link.symlink_to(real)
    assert load_config_file(link).mode == "report"
