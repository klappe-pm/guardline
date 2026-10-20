"""What the documentation says about guardline stays true: counts, tables, examples and output."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from guardline import Scanner, builtin_rules, verify_rule_examples
from guardline.rules import parse_rules
from tests.conftest import ROOT
from tests.test_docs import label, markdown_files

pytestmark = pytest.mark.repo_only

MD = markdown_files()


# the rules reference ---------------------------------------------------------------


def test_rules_reference_lists_every_builtin_rule_once() -> None:
    text = (ROOT / "docs/reference/rules.md").read_text(encoding="utf-8")
    for rule in builtin_rules():
        assert len(re.findall(rf"\| `{re.escape(rule.id)}` \|", text)) == 1, rule.id
        assert rule.description in text, rule.id


def test_rule_counts_in_the_documents_match_the_rules() -> None:
    rules = builtin_rules()
    per_family = {
        f: sum(1 for r in rules if r.family == f) for f in ("attribution", "env-dump", "token")
    }
    assert (per_family["attribution"], per_family["env-dump"], per_family["token"]) == (9, 14, 20)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{len(rules)} rules ship" in readme
    reference = (ROOT / "docs/reference/rules.md").read_text(encoding="utf-8")
    assert f"all {len(rules)} built-in rules" in reference
    assert (
        "9 attribution rules, 14 environment dump rules and 20 token-shaped value rules"
        in reference
    )


AGENT_NAMES = (
    "Claude",
    "Anthropic",
    "Codex",
    "OpenAI",
    "ChatGPT",
    "Copilot",
    "Cursor",
    "Devin",
    "Gemini",
    "Aider",
    "Windsurf",
    "Grok",
    "Kiro",
    "Cline",
    "Google Jules",
    "AI assistant",
    "AI agent",
    "LLM",
)


def test_the_agent_names_in_the_docs_match_the_rule() -> None:
    text = (ROOT / "docs/reference/rules.md").read_text(encoding="utf-8")
    patterns = [
        r.pattern
        for r in builtin_rules()
        if r.id
        in (
            "attribution-co-author-trailer",
            "attribution-assisted-by-trailer",
            "attribution-generated-with-footer",
        )
    ]
    for name in AGENT_NAMES:
        assert name in text, name
        assert all(name in pattern for pattern in patterns), name


# examples in the documentation run -----------------------------------------------------


def toml_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r"```toml\n(.*?)```", text, re.DOTALL)


@pytest.mark.parametrize("path", MD, ids=label)
def test_toml_blocks_in_the_documents_parse(path: Path) -> None:
    for block in toml_blocks(path):
        tomllib.loads(block)


def test_rule_files_in_the_documents_pass_their_own_examples() -> None:
    checked = 0
    for path in MD:
        for block in toml_blocks(path):
            if "schema_version" not in block or "[[rule]]" not in block:
                continue
            if "'regular expression'" in block:
                continue
            for rule in parse_rules(block, path.name):
                assert verify_rule_examples(rule) == [], rule.id
                checked += 1
    assert checked >= 3


def test_documented_getting_started_output_is_real() -> None:
    text = (ROOT / "docs/tutorials/getting-started.md").read_text(encoding="utf-8")
    finding = Scanner().scan_text(
        "fix: parser\n\nCo-Authored-By: Codex <dev@example.com>\n", "m.txt"
    )
    assert len(finding) == 1
    assert finding[0].format_text().replace("m.txt", "/tmp/guardline-tour/message.txt") in text


def test_documented_config_show_output_is_real(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from guardline.cli import main

    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "guardline.toml").write_text(
        'mode = "block"\nfamilies = ["attribution", "token"]\n', encoding="utf-8"
    )
    assert main(["config", "show"]) == 0
    real = capsys.readouterr().out.replace(str(tmp_path), "/tmp/guardline-tour/project")
    text = (ROOT / "docs/tutorials/getting-started.md").read_text(encoding="utf-8")
    assert real in text
