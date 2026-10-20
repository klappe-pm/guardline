"""``guardline init`` and ``guardline config show``."""

from __future__ import annotations

import io
import itertools
import json
import shlex
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest

from guardline import initcmd
from guardline.cli import main
from guardline.config import MODES, discover_config, load_config_file
from guardline.errors import ConfigError
from guardline.initcmd import (
    claude_code_snippet,
    guardline_executable,
    known_families,
    parse_families,
    parse_hooks,
    pre_commit_snippet,
    render_body,
)
from tests.samples import COMMIT_WITH_TRAILER

Run = Callable[..., tuple[int, str, str]]


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> Run:
    def invoke(
        *argv: str, stdin: str = "", answers: list[str] | None = None
    ) -> tuple[int, str, str]:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        queue = iter(answers or [])

        def fake_input(prompt: str = "") -> str:
            print(prompt, end="")
            try:
                return next(queue)
            except StopIteration:
                raise EOFError from None

        monkeypatch.setattr("builtins.input", fake_input)
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return invoke


@pytest.fixture(autouse=True)
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def family_subsets() -> list[tuple[str, ...]]:
    names = known_families()
    return [c for n in range(1, len(names) + 1) for c in itertools.combinations(names, n)]


# the loader reads back every combination ------------------------------------------------


@pytest.mark.parametrize("target", ["guardline.toml", "pyproject.toml"])
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("subset", family_subsets(), ids=lambda s: "+".join(s))
def test_every_mode_and_family_combination_round_trips(
    run: Run, project: Path, target: str, mode: str, subset: tuple[str, ...]
) -> None:
    if target == "pyproject.toml":
        (project / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    code, _, err = run(
        "init", "--yes", "--mode", mode, "--families", ",".join(subset), "--target", target
    )
    assert (code, err) == (0, "")
    path = project / target
    loaded = load_config_file(path)
    assert loaded.mode == mode
    expected = None if subset == known_families() else subset
    assert loaded.families == expected
    assert discover_config(project) == loaded
    assert loaded.origin == path


def test_a_pyproject_target_keeps_the_rest_of_the_file(run: Run, project: Path) -> None:
    original = '[project]\nname = "demo"\n\n[tool.ruff]\nline-length = 100\n'
    (project / "pyproject.toml").write_text(original, encoding="utf-8")
    assert run("init", "--yes")[0] == 0
    text = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert text.startswith(original.rstrip("\n"))
    document = tomllib.loads(text)
    assert document["tool"]["ruff"] == {"line-length": 100}
    assert document["tool"]["guardline"] == {"mode": "block"}


# defaults and flags ---------------------------------------------------------------------


def test_yes_writes_block_mode_with_every_family_and_no_snippet(run: Run, project: Path) -> None:
    code, out, _ = run("init", "--yes")
    assert code == 0
    assert (project / "guardline.toml").read_text(encoding="utf-8") == 'mode = "block"\n'
    assert "claude" not in out.lower().replace("claude-code", "")
    assert '+mode = "block"' in out
    assert "--- /dev/null" in out


def test_yes_prefers_pyproject_when_one_exists(run: Run, project: Path) -> None:
    (project / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    assert run("init", "--yes")[0] == 0
    assert not (project / "guardline.toml").exists()
    assert "[tool.guardline]" in (project / "pyproject.toml").read_text(encoding="utf-8")


def test_families_all_is_accepted_and_case_does_not_matter() -> None:
    assert parse_families("ALL") == known_families()
    assert parse_families("token, Attribution") == ("attribution", "token")


@pytest.mark.parametrize("bad", ["", " , ", "tokens", "token,nope"])
def test_bad_family_lists_are_refused(bad: str) -> None:
    with pytest.raises(ConfigError):
        parse_families(bad)


def test_a_bad_family_flag_exits_2_and_writes_nothing(run: Run, project: Path) -> None:
    code, _, err = run("init", "--yes", "--families", "tokens")
    assert code == 2
    assert "unknown family: tokens" in err
    assert not (project / "guardline.toml").exists()


def test_hook_none_cannot_be_combined() -> None:
    with pytest.raises(ConfigError):
        parse_hooks(["none", "claude-code"])
    assert parse_hooks(["none"]) == ()
    assert parse_hooks(["pre-commit", "pre-commit"]) == ("pre-commit",)


def test_hook_none_flag_prints_no_snippet(run: Run) -> None:
    _, out, _ = run("init", "--yes", "--hook", "none")
    assert "hooks" not in out
    assert "pre-commit" not in out


# refusing to overwrite ------------------------------------------------------------------


def test_an_existing_guardline_toml_is_never_overwritten_without_force(
    run: Run, project: Path
) -> None:
    (project / "guardline.toml").write_text('mode = "report"\n', encoding="utf-8")
    code, _, err = run("init", "--yes")
    assert code == 2
    assert "--force" in err
    assert (project / "guardline.toml").read_text(encoding="utf-8") == 'mode = "report"\n'


def test_force_replaces_and_the_diff_shows_the_old_line(run: Run, project: Path) -> None:
    (project / "guardline.toml").write_text('mode = "report"\n', encoding="utf-8")
    code, out, _ = run("init", "--yes", "--force")
    assert code == 0
    assert '-mode = "report"' in out
    assert '+mode = "block"' in out
    assert (project / "guardline.toml").read_text(encoding="utf-8") == 'mode = "block"\n'


def test_an_existing_tool_table_is_refused_then_replaced_with_force(
    run: Run, project: Path
) -> None:
    original = (
        '[tool.guardline]\nmode = "report"\ndisable = ["a"]\n\n[tool.ruff]\nline-length = 90\n'
    )
    (project / "pyproject.toml").write_text(original, encoding="utf-8")
    code, _, err = run("init", "--yes")
    assert (code, "[tool.guardline]" in err) == (2, True)
    assert (project / "pyproject.toml").read_text(encoding="utf-8") == original

    assert run("init", "--yes", "--force", "--mode", "block")[0] == 0
    document = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    assert document["tool"]["guardline"] == {"mode": "block"}
    assert document["tool"]["ruff"] == {"line-length": 90}


def test_a_table_defined_by_dotted_keys_cannot_be_rewritten_safely(run: Run, project: Path) -> None:
    original = '[tool]\nguardline.mode = "report"\n'
    (project / "pyproject.toml").write_text(original, encoding="utf-8")
    assert run("init", "--yes")[0] == 2
    code, _, err = run("init", "--yes", "--force")
    assert code == 2
    assert "by hand" in err
    assert (project / "pyproject.toml").read_text(encoding="utf-8") == original


def test_pyproject_loses_to_a_guardline_toml_beside_it(run: Run, project: Path) -> None:
    (project / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    (project / "guardline.toml").write_text('mode = "report"\n', encoding="utf-8")
    code, _, err = run("init", "--yes", "--force", "--target", "pyproject.toml")
    assert code == 2
    assert "takes precedence" in err


def test_a_pyproject_target_needs_a_pyproject(run: Run) -> None:
    code, _, err = run("init", "--yes", "--target", "pyproject.toml")
    assert (code, "does not exist" in err) == (2, True)


def test_an_unreadable_pyproject_is_refused(run: Run, project: Path) -> None:
    (project / "pyproject.toml").write_text("[project\n", encoding="utf-8")
    code, _, err = run("init", "--yes")
    assert (code, "cannot read as TOML" in err) == (2, True)


# the interactive flow --------------------------------------------------------------------


def test_the_interactive_flow_asks_every_question_and_confirms(run: Run, project: Path) -> None:
    (project / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    code, out, _ = run(
        "init",
        answers=["guardline.toml", "report", "token, attribution", "pre-commit", "y"],
    )
    assert code == 0
    assert "block: stops the action" in out
    assert "report: only prints findings" in out
    assert "attribution (9 rules)" in out
    text = (project / "guardline.toml").read_text(encoding="utf-8")
    assert tomllib.loads(text) == {"mode": "report", "families": ["attribution", "token"]}
    assert "args: [--mode, report]" in out


def test_empty_answers_take_the_defaults(run: Run, project: Path) -> None:
    code, _, _ = run("init", answers=["", "", "", "y"])
    assert code == 0
    assert (project / "guardline.toml").read_text(encoding="utf-8") == 'mode = "block"\n'


def test_a_bad_answer_is_asked_again(run: Run, project: Path) -> None:
    code, out, _ = run("init", answers=["loud", "block", "nope", "all", "maybe", "none", "y"])
    assert code == 0
    assert "choose one of: report, block" in out
    assert "unknown family: nope" in out
    assert "choose claude-code, pre-commit, both or none" in out


def test_a_bad_target_answer_is_asked_again(run: Run, project: Path) -> None:
    (project / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    code, out, _ = run("init", answers=["setup.cfg", "pyproject.toml", "", "", "", "y"])
    assert code == 0
    assert "choose one of: guardline.toml, pyproject.toml" in out


def test_declining_the_confirmation_writes_nothing(run: Run, project: Path) -> None:
    code, out, _ = run(
        "init", "--mode", "block", "--families", "all", "--hook", "none", answers=[""]
    )
    assert code == 1
    assert "Nothing written." in out
    assert not (project / "guardline.toml").exists()


def test_running_out_of_input_is_an_error_not_a_hang(run: Run, project: Path) -> None:
    code, _, err = run("init", answers=[])
    assert code == 2
    assert "pass --yes" in err
    assert not (project / "guardline.toml").exists()


def test_both_snippets_can_be_chosen_in_one_answer(run: Run) -> None:
    _, out, _ = run("init", answers=["", "", "both", "y"])
    assert '"PreToolUse"' in out
    assert "guardline-commit-msg" in out


# the hook snippet --------------------------------------------------------------------------


def hook_command_from(out: str) -> list[str]:
    start = out.index('{\n  "hooks"')
    document, _ = json.JSONDecoder().raw_decode(out[start:])
    return shlex.split(document["hooks"]["PreToolUse"][0]["hooks"][0]["command"])


def test_the_claude_code_snippet_names_the_config_with_an_absolute_path(
    run: Run, project: Path
) -> None:
    code, out, _ = run("init", "--yes", "--hook", "claude-code")
    assert code == 0
    words = hook_command_from(out)
    assert words[1] == "hook"
    assert words[2] == "--config"
    assert Path(words[3]).is_absolute()
    assert Path(words[3]) == (project / "guardline.toml").resolve()
    assert "never searches for configuration" in out
    assert "outside the project" in out


@pytest.mark.parametrize(("mode", "denied"), [("block", True), ("report", False)])
def test_the_printed_hook_command_applies_the_chosen_mode(
    run: Run, project: Path, mode: str, denied: bool
) -> None:
    _, out, _ = run("init", "--yes", "--mode", mode, "--hook", "claude-code")
    config = hook_command_from(out)[3]
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "printenv"}})
    code, hook_out, _ = run("hook", "--config", config, stdin=payload)
    assert code == 0
    assert ('"permissionDecision": "deny"' in hook_out) is denied


def test_the_hook_command_names_a_pyproject_config_too(run: Run, project: Path) -> None:
    (project / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    _, out, _ = run("init", "--yes", "--hook", "claude-code")
    assert hook_command_from(out)[3] == str((project / "pyproject.toml").resolve())


def test_a_path_with_spaces_survives_quoting(tmp_path: Path) -> None:
    spaced = tmp_path / "a b" / "guardline.toml"
    spaced.parent.mkdir()
    command, _ = initcmd.hook_command(spaced)
    assert shlex.split(command)[-1] == str(spaced.resolve())
    json.loads(claude_code_snippet(command))


def test_executable_lookup_prefers_the_running_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "python").write_text("", encoding="utf-8")
    (tmp_path / "bin" / "guardline").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "bin" / "python"))
    assert guardline_executable() == (str(tmp_path / "bin" / "guardline"), True)


def test_executable_lookup_falls_back_to_path_then_to_the_bare_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    monkeypatch.setattr(sys, "executable", str(tmp_path / "nowhere" / "python"))
    monkeypatch.setattr("shutil.which", lambda name: str(tmp_path / "found" / name))
    assert guardline_executable() == (str(tmp_path / "found" / "guardline"), True)
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert guardline_executable() == ("guardline", False)
    _, out, _ = run("init", "--yes", "--hook", "claude-code")
    assert "replace the word guardline" in out


# the pre-commit snippet ---------------------------------------------------------------------


def test_the_pre_commit_snippet_sets_report_mode_through_args() -> None:
    assert "args:" not in pre_commit_snippet("block")
    snippet = pre_commit_snippet("report")
    assert snippet.count("args: [--mode, report]") == 2
    assert "id: guardline-commit-msg" in snippet


def test_a_later_mode_flag_beats_the_hook_entry(run: Run, project: Path) -> None:
    """The hook entry passes --mode block, so report mode has to arrive after it."""
    file = project / "msg.txt"
    file.write_text(COMMIT_WITH_TRAILER, encoding="utf-8")
    assert run("scan", "--mode", "block", "--mode", "report", str(file))[0] == 0
    assert run("scan", "--mode", "report", "--mode", "block", str(file))[0] == 1


def test_the_pre_commit_note_explains_report_mode(run: Run) -> None:
    _, out, _ = run("init", "--yes", "--mode", "report", "--hook", "pre-commit")
    assert "args: [--mode, report]" in out
    assert "last --mode" in out
    _, out, _ = run("init", "--yes", "--force", "--hook", "pre-commit")
    assert "last --mode" not in out


def test_render_body_omits_families_only_when_all_are_chosen() -> None:
    assert render_body("block", known_families()) == 'mode = "block"\n'
    assert 'families = ["token"]' in render_body("report", ("token",))


# config show -----------------------------------------------------------------------------------


def test_config_show_with_no_file_reports_the_defaults(run: Run) -> None:
    code, out, _ = run("config", "show")
    assert code == 0
    assert "source: none (built-in defaults)" in out
    assert "mode: block (default)" in out
    assert "families: attribution, env-dump, token" in out
    assert "disabled rules: none" in out
    assert "active rules: 43" in out
    assert "guardline hook reads only the file named by its --config" in out


def test_config_show_reads_the_discovered_file(run: Run, project: Path) -> None:
    (project / "guardline.toml").write_text(
        'mode = "report"\nfamilies = ["token"]\ndisable = ["token-hex-run-near-keyword"]\n'
        'exclude = ["*.lock"]\n',
        encoding="utf-8",
    )
    code, out, _ = run("config", "show")
    assert code == 0
    assert f"source: {project / 'guardline.toml'}" in out
    assert "mode: report (config file)" in out
    assert "families: token\n" in out
    assert "disabled rules: token-hex-run-near-keyword" in out
    assert "exclude: *.lock" in out
    assert "active rules: 19" in out


def test_config_show_applies_command_line_overrides(run: Run, project: Path) -> None:
    (project / "guardline.toml").write_text('mode = "report"\n', encoding="utf-8")
    _, out, _ = run(
        "config",
        "--mode",
        "block",
        "--family",
        "env-dump",
        "--disable",
        "env-dump-printenv",
        "show",
    )
    assert "mode: block (--mode)" in out
    assert "families: env-dump\n" in out
    assert "disabled rules: env-dump-printenv" in out


def test_config_show_no_config_ignores_the_file(run: Run, project: Path) -> None:
    (project / "guardline.toml").write_text('mode = "report"\n', encoding="utf-8")
    _, out, _ = run("config", "--no-config", "show")
    assert "source: none (--no-config)" in out
    assert "mode: block (default)" in out


def test_config_show_json(run: Run, project: Path) -> None:
    (project / "pyproject.toml").write_text('[tool.guardline]\nmode = "report"\n', encoding="utf-8")
    code, out, _ = run("config", "show", "--format", "json")
    document = json.loads(out)
    assert code == 0
    assert document["source"] == str(project / "pyproject.toml")
    assert document["mode"] == "report"
    assert document["families"] == ["attribution", "env-dump", "token"]
    assert document["disabled_rules"] == []


def test_config_show_warns_about_a_family_that_matches_nothing(run: Run, project: Path) -> None:
    (project / "guardline.toml").write_text('families = ["tokens"]\n', encoding="utf-8")
    _, out, _ = run("config", "show")
    assert "warning, families that match no rule: tokens" in out
    assert "active rules: 0" in out


def test_config_show_reports_a_broken_file_as_an_error(run: Run, project: Path) -> None:
    (project / "guardline.toml").write_text("mode = 3\n", encoding="utf-8")
    code, _, err = run("config", "show")
    assert (code, "mode must be one of" in err) == (2, True)


def test_config_show_lists_extra_rule_files(run: Run, project: Path) -> None:
    rules = project / "extra.toml"
    rules.write_text(
        'schema_version = 1\n\n[[rule]]\nid = "x-demo"\nfamily = "custom"\nscope = "text"\n'
        'description = "Demo."\npattern = "zzdemozz"\nexample_fires = "a zzdemozz b"\n'
        'example_clean = "nothing"\n',
        encoding="utf-8",
    )
    code, out, _ = run("config", "--rules", str(rules), "show")
    assert code == 0
    assert str(rules) in out
    assert "custom" in out
