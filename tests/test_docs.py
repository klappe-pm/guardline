"""The documentation rules, the rules reference and the repository's own hygiene."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from guardline import Scanner, builtin_rules, verify_rule_examples
from guardline.rules import parse_rules

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
KEBAB = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
RESERVED = {"README.md", "LICENSE"}


def markdown_files() -> list[Path]:
    found = [p for p in ROOT.rglob("*.md") if not SKIP_DIRS & set(p.relative_to(ROOT).parts)]
    return sorted(found)


MD = markdown_files()


def ids(paths: list[Path]) -> list[str]:
    return [str(p.relative_to(ROOT)) for p in paths]


def prose_lines(text: str) -> list[tuple[int, str]]:
    """Return (line number, line) for lines outside fenced code blocks."""
    lines: list[tuple[int, str]] = []
    opened: tuple[str, int] | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r" {0,3}(`{3,}|~{3,})(.*)", line)
        if opened is None:
            if match:
                opened = (match.group(1)[0], len(match.group(1)))
                continue
            lines.append((number, line))
        elif match and match.group(1)[0] == opened[0] and len(match.group(1)) >= opened[1]:
            if not match.group(2).strip():
                opened = None
    return lines


def fence_openings(text: str) -> list[tuple[int, str]]:
    """Return (line number, info string) for each opening fence."""
    found: list[tuple[int, str]] = []
    opened: tuple[str, int] | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r" {0,3}(`{3,}|~{3,})(.*)", line)
        if match is None:
            continue
        if opened is None:
            opened = (match.group(1)[0], len(match.group(1)))
            found.append((number, match.group(2).strip()))
        elif match.group(1)[0] == opened[0] and len(match.group(1)) >= opened[1]:
            if not match.group(2).strip():
                opened = None
    return found


def strip_code(line: str) -> str:
    line = re.sub(r"`[^`]*`", "", line)
    line = re.sub(r"\]\([^)]*\)", "]", line)
    return re.sub(r"<https?://[^>]*>", "", line)


@pytest.mark.parametrize("path", MD, ids=ids(MD))
def test_no_dash_punctuation(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "\u2014" not in text
    assert "\u2013" not in text
    for number, line in prose_lines(text):
        if re.fullmatch(r"\|[ :|-]+\|", line.strip()):
            continue
        plain = strip_code(line)
        if re.search(r"(?<=\S) - (?=\S)", plain) or "--" in plain:
            pytest.fail(f"{path.name}:{number}: dash used as punctuation")


@pytest.mark.parametrize("path", MD, ids=ids(MD))
def test_headings_are_kebab_case_and_h1_matches_the_name(path: Path) -> None:
    h1_seen = 0
    for number, line in prose_lines(path.read_text(encoding="utf-8")):
        match = re.match(r"(#{1,6}) (.*)", line)
        if not match:
            continue
        level, title = len(match.group(1)), match.group(2).strip()
        if not KEBAB.fullmatch(title):
            pytest.fail(f"{path.name}:{number}: heading is not lowercase kebab-case")
        if level == 1:
            h1_seen += 1
            expected = path.parent.name if path.name == "README.md" else path.stem
            if path == ROOT / "README.md":
                expected = "guardline"
            if title != expected:
                pytest.fail(f"{path.name}:{number}: H1 should be {expected}")
    assert h1_seen == 1


@pytest.mark.parametrize("path", MD, ids=ids(MD))
def test_filenames_are_kebab_case(path: Path) -> None:
    for part in path.relative_to(ROOT).parts:
        stem = part[:-3] if part.endswith(".md") else part
        assert part in RESERVED or KEBAB.fullmatch(stem), part


@pytest.mark.parametrize("path", MD, ids=ids(MD))
def test_every_code_fence_has_a_language(path: Path) -> None:
    for number, info in fence_openings(path.read_text(encoding="utf-8")):
        if not info:
            pytest.fail(f"{path.name}:{number}: code fence has no language tag")


@pytest.mark.parametrize("path", MD, ids=ids(MD))
def test_paragraphs_are_not_hard_wrapped(path: Path) -> None:
    previous: tuple[int, str] | None = None
    for number, line in prose_lines(path.read_text(encoding="utf-8")):
        plain = bool(line.strip()) and not re.match(r"\s*([#>|*+-]|\d+\.|<)", line)
        if plain and previous is not None and previous[0] == number - 1:
            pytest.fail(f"{path.name}:{number}: paragraph continues onto a second line")
        previous = (number, line) if plain else None


@pytest.mark.parametrize("path", MD, ids=ids(MD))
def test_no_provenance_frontmatter_and_no_agent_credit(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        header = text.split("---", 2)[1]
        for key in ("models", "providers", "session-link"):
            assert not re.search(rf"^{key}:", header, re.MULTILINE)
    assert "\U0001f916" not in text


@pytest.mark.parametrize("path", MD, ids=ids(MD))
def test_relative_links_resolve(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for number, line in prose_lines(text):
        for target in re.findall(r"\]\(([^)\s]+)\)", line):
            if re.match(r"(https?:|mailto:|#)", target):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            if not resolved.exists():
                pytest.fail(f"{path.name}:{number}: broken link {target}")


def test_every_folder_readme_lists_its_pages() -> None:
    for tree in ("docs", "developer-docs"):
        for readme in (ROOT / tree).rglob("README.md"):
            text = readme.read_text(encoding="utf-8")
            for page in readme.parent.glob("*.md"):
                if page.name != "README.md":
                    assert f"({page.name})" in text, f"{readme} does not list {page.name}"


def test_top_level_readmes_name_every_page() -> None:
    for tree in ("docs", "developer-docs"):
        readme = (ROOT / tree / "README.md").read_text(encoding="utf-8")
        for page in (ROOT / tree).rglob("*.md"):
            relative = page.relative_to(ROOT / tree).as_posix()
            if page.name != "README.md":
                assert f"({relative})" in readme, f"{tree}/README.md does not name {relative}"


def test_both_trees_have_the_four_quadrants() -> None:
    quadrants = {"tutorials", "how-to-guides", "reference", "explanation"}
    for tree in ("docs", "developer-docs"):
        folders = {p.name for p in (ROOT / tree).iterdir() if p.is_dir()}
        assert quadrants <= folders
        for quadrant in quadrants:
            assert (ROOT / tree / quadrant / "README.md").is_file()


def test_minimum_documentation_exists() -> None:
    pages = [
        "docs/tutorials/getting-started.md",
        "docs/how-to-guides/install.md",
        "docs/how-to-guides/troubleshooting.md",
        "docs/reference/cli.md",
        "docs/reference/configuration.md",
        "docs/reference/python-api.md",
        "docs/explanation/design.md",
        "docs/explanation/security-model.md",
        "developer-docs/tutorials/first-contribution.md",
        "developer-docs/how-to-guides/run-the-tests.md",
        "developer-docs/explanation/architecture.md",
    ]
    for page in pages:
        assert (ROOT / page).is_file(), page


def test_every_page_opens_with_a_purpose_paragraph() -> None:
    for path in MD:
        if path.parent == ROOT and path.name != "README.md":
            continue
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert lines[0].startswith("# "), path
        assert len(lines) > 1 and not lines[1].startswith("#"), f"{path} has no opening paragraph"


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


@pytest.mark.parametrize("path", MD, ids=ids(MD))
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


# the repository holds no complete credential and no agent credit ---------------------


def repository_text_files() -> list[Path]:
    suffixes = {".md", ".py", ".toml", ".yaml", ".yml", ".cfg", ".txt", ".gitignore", ""}
    found = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or SKIP_DIRS & set(path.relative_to(ROOT).parts):
            continue
        if path.suffix in suffixes and path.stat().st_size < 1_000_000:
            found.append(path)
    return found


@pytest.mark.parametrize("path", repository_text_files(), ids=ids(repository_text_files()))
def test_guardline_finds_nothing_in_its_own_repository(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    scanner = Scanner(allow_fenced_attribution=True, families=["attribution", "token"])
    findings = scanner.scan_text(text, str(path.relative_to(ROOT)))
    if findings:
        pytest.fail(f"{path.relative_to(ROOT)} holds {sorted({f.rule_id for f in findings})}")
