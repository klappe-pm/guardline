"""The shell command splitter."""

from __future__ import annotations

import time
import tracemalloc

import pytest

from guardline import Scanner
from guardline.engine import DEFAULT_MAX_COMMAND_CHARS
from guardline.shell import MAX_DEPTH, parse_shell


def programs(command: str) -> list[str]:
    return [simple.program for simple in parse_shell(command).commands]


def test_pipes_and_lists_split_into_simple_commands() -> None:
    assert programs("a | b && c; d\ne") == ["a", "b", "c", "d", "e"]


def test_redirect_targets_are_words_but_not_arguments() -> None:
    simple = parse_shell("cat < /proc/1/environ 2>&1").commands[0]
    assert simple.args == ()
    assert "/proc/1/environ" in simple.words


def test_command_substitutions_are_followed() -> None:
    assert "printenv" in programs('echo "$(printenv)" `env`')


def test_single_quoted_substitution_is_inert() -> None:
    assert programs("echo '$(printenv)'") == ["echo"]


def test_wrappers_are_unwrapped() -> None:
    assert "launchctl" in programs("sudo -u root nohup timeout 5 launchctl print x")
    assert "printenv" in programs("ssh -p 22 host printenv")
    assert "printenv" in programs("bash -c 'echo hi; printenv'")
    assert "printenv" in programs("docker run --rm -e A=b image printenv")
    assert "printenv" in programs("find . -name x -exec printenv ;")


def test_env_with_nothing_to_run_is_reported_bare() -> None:
    simple = parse_shell("env -i FOO=1").commands[0]
    assert (simple.program, simple.args) == ("env", ())


def test_env_with_a_command_is_not_bare() -> None:
    assert programs("env FOO=1 ls") == ["ls"]


def test_command_lookup_runs_nothing() -> None:
    assert programs("command -v env") == []


def test_data_heredoc_bodies_are_not_commands_but_are_recorded() -> None:
    parse = parse_shell("cat <<EOF\nset\nEOF\n")
    assert programs("cat <<EOF\nset\nEOF\n") == ["cat"]
    assert [body for _, body in parse.heredocs] == ["set"]


def test_command_heredoc_bodies_are_commands() -> None:
    assert "printenv" in programs("bash <<EOF\nprintenv\nEOF\n")


def test_comments_are_ignored() -> None:
    assert programs("ls # env\nenv #x") == ["ls", "env"]


def test_unbalanced_quotes_fall_back_to_a_lenient_split() -> None:
    parse = parse_shell("echo 'oops ; printenv")
    assert parse.fallback
    assert "printenv" in [simple.program for simple in parse.commands]


def test_offsets_point_at_the_command() -> None:
    commands = parse_shell("ls\n  echo hi\nenv").commands
    assert [command.offset for command in commands] == [0, 5, 13]


def test_nesting_is_bounded() -> None:
    deep = "bash -c '" * (MAX_DEPTH + 4) + "printenv" + "'" * (MAX_DEPTH + 4)
    assert isinstance(programs(deep), list)


def test_empty_and_blank_commands_have_no_commands() -> None:
    assert programs("") == []
    assert programs("   \n") == []


def test_here_string_and_pipe_into_a_shell_are_followed() -> None:
    assert "printenv" in programs("bash <<< printenv")
    assert "printenv" in programs("echo printenv | sh")


def test_a_command_over_the_token_budget_is_flagged_exhausted() -> None:
    parse = parse_shell("$(" * 30000)
    assert parse.exhausted


def test_a_normal_command_is_not_exhausted() -> None:
    assert not parse_shell("bash -c 'ls | wc -l'").exhausted


# work grows linearly with the command ------------------------------------------------------


def test_find_with_many_exec_flags_is_linear_in_time() -> None:
    command = ("find . " + "-exec " * 6000)[: DEFAULT_MAX_COMMAND_CHARS // 2]
    started = time.perf_counter()
    Scanner().scan_command(command)
    assert time.perf_counter() - started < 1.0


def test_find_with_many_exec_flags_is_linear_in_memory() -> None:
    command = ("find . " + "-exec " * 3000)[: DEFAULT_MAX_COMMAND_CHARS // 4]
    tracemalloc.start()
    try:
        Scanner().scan_command(command)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 20_000_000, f"peak {peak / 1e6:.0f} MB for {len(command)} characters"


def test_find_still_finds_every_exec_body() -> None:
    assert "printenv" in programs("find . -exec printenv + -exec ls {} \\;")


@pytest.mark.parametrize("piece", ["{ ", "! "])
def test_many_leading_keywords_are_linear(piece: str) -> None:
    command = (piece * DEFAULT_MAX_COMMAND_CHARS)[: DEFAULT_MAX_COMMAND_CHARS - 1] + "x"
    started = time.perf_counter()
    Scanner().scan_command(command)
    assert time.perf_counter() - started < 1.0
