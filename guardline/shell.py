"""Split a shell command string into the simple commands a shell would run.

The parser reads far enough to find each simple command: pipes, ``&&``, ``;``,
newlines, subshells, ``$(...)`` and backticks, heredocs, here-strings, function
bodies, and the wrappers that run another command (``bash -c``, ``eval``,
``env VAR=val cmd``, ``sudo``, ``ssh host cmd``, ``xargs``, ``find -exec``,
``docker exec`` and the like). It decodes quoting the way a shell does: single and
double quotes, backslashes, backslash-newline, ``$'...'`` with its escapes and
``$"..."``. It is not a full shell. It never runs anything and never expands a
variable.

When the text cannot be tokenised (an unbalanced quote), a lenient split is used
instead, so a broken quote cannot hide a command. The result is flagged with
``fallback``. When a limit is hit (nesting depth, command count, token budget) the
result is flagged ``exhausted`` and the caller must treat the input as unjudged.
"""

from __future__ import annotations

import os
import posixpath
import re
import shlex
from dataclasses import dataclass, field

MAX_DEPTH = 8
"""How deep wrappers and substitutions are followed."""

MAX_COMMANDS = 5000
"""Most simple commands collected from one input."""

MAX_TOKENS = 100_000
"""Most shell tokens read across one input and everything nested in it."""

_PUNCTUATION = ";&|()<>\n"
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "fish", "ash", "csh", "tcsh", "mksh"})
_STDIN_SCRIPTS = frozenset({"/dev/stdin", "/dev/fd/0", "/proc/self/fd/0"})
_HEREDOC_RECEIVERS = _SHELLS | {
    "ssh",
    "kubectl",
    "docker",
    "podman",
    "eval",
    "xargs",
    ".",
    "source",
    "busybox",
}
_SHELL_VALUE_OPTIONS = frozenset({"-o", "+o", "-O", "+O", "--rcfile", "--init-file"})
_LEADING_KEYWORDS = frozenset(
    {"{", "}", "!", "if", "then", "elif", "else", "while", "until", "do", "done", "fi"}
)
_DOCKER_PROGRAMS = frozenset({"docker", "podman", "nerdctl", "docker-compose", "podman-compose"})
_DOCKER_GLOBAL_VALUE_OPTIONS = frozenset(
    {"--context", "-c", "-H", "--host", "--config", "-l", "--log-level", "-f", "--file"}
    | {"-p", "--project-name", "--profile", "--env-file", "--project-directory"}
)
_DOCKER_VALUE_OPTIONS = frozenset(
    {"-e", "--env", "--env-file", "-u", "--user", "-w", "--workdir", "--detach-keys"}
    | {"-v", "--volume", "-p", "--publish", "--name", "--entrypoint", "--network"}
    | {"--platform", "-l", "--label", "--mount", "-h", "--hostname", "--add-host"}
    | {"--cpus", "-m", "--memory", "--restart", "--pull", "--log-driver", "--index"}
)
_SSH_VALUE_OPTIONS = frozenset("-" + letter for letter in "bcDEeFIiJLlmOoPpQRSWw")
_EXEC_FLAGS = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
_ECHO_FLAGS = frozenset({"-n", "-e", "-E"})


@dataclass(frozen=True)
class SimpleCommand:
    """One simple command.

    Attributes:
        program: the lower case base name of the program word.
        args: the arguments after the program, redirections removed.
        words: every word of the command, redirect targets included.
        offset: best effort character offset of the command in the input.
        depth: 0 for a command written at the top level, more for one found inside a
            substitution, a ``-c`` string or a wrapper.
        stdin: text fed to the command by a here-string or by a piped ``echo`` or ``printf``.
    """

    program: str
    args: tuple[str, ...]
    words: tuple[str, ...]
    offset: int
    depth: int = 0
    stdin: tuple[str, ...] = ()


@dataclass
class ShellParse:
    """The result of parsing one command string."""

    commands: list[SimpleCommand] = field(default_factory=list)
    heredocs: list[tuple[int, str]] = field(default_factory=list)
    fallback: bool = False
    exhausted: bool = False


# decoding ----------------------------------------------------------------------

_ANSI_SIMPLE = {
    "a": "\a",
    "b": "\b",
    "e": "\x1b",
    "E": "\x1b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "?": "?",
}
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_HEX_WIDTH = {"x": 2, "u": 4, "U": 8}


def _ansi(text: str, i: int) -> tuple[str, int]:
    """Decode the body of a ``$'...'`` string starting at ``i`` (after the opening quote).

    Returns the decoded text and the index after the closing quote. Raises ValueError
    when the string is not closed.
    """
    out: list[str] = []
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "'":
            return "".join(out).replace("\x00", ""), i + 1
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        i += 1
        if i >= n:
            break
        c = text[i]
        i += 1
        if c in _ANSI_SIMPLE:
            out.append(_ANSI_SIMPLE[c])
        elif c in _HEX_WIDTH:
            j = i
            while j < n and j - i < _HEX_WIDTH[c] and text[j] in _HEX_DIGITS:
                j += 1
            if j > i:
                code = int(text[i:j], 16)
                out.append(chr(code) if code <= 0x10FFFF else chr(0xFFFD))
                i = j
            else:
                out.append("\\" + c)
        elif c in "01234567":
            j = i
            while j < n and j - i < 2 and text[j] in "01234567":
                j += 1
            out.append(chr(int(text[i - 1 : j], 8) & 0xFF))
            i = j
        elif c == "c" and i < n:
            out.append(chr(ord(text[i]) & 31))
            i += 1
        else:
            out.append("\\" + c)
    raise ValueError("a $' string is not closed")


def decode_escapes(text: str) -> str:
    """Decode the backslash escapes ``printf`` and ``echo -e`` understand."""
    try:
        return _ansi(text.replace("'", "\\'") + "'", 0)[0]
    except ValueError:
        return text


def _skip_ansi(text: str, i: int) -> int:
    """Return the index after the ``$'...'`` string whose body starts at ``i``."""
    n = len(text)
    while i < n:
        if text[i] == "\\":
            i += 2
        elif text[i] == "'":
            return i + 1
        else:
            i += 1
    return n


def _strip_comments(text: str) -> str:
    """Blank out shell comments, keeping the text length and every newline."""
    out: list[str] = []
    quote = ""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote:
            out.append(ch)
            if quote in ('"', "$'") and ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if (quote == "$'" and ch == "'") or (quote != "$'" and ch == quote):
                quote = ""
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            out.append(ch)
            out.append(text[i + 1])
            i += 2
            continue
        if ch == "$" and text.startswith("'", i + 1):
            out.append("$'")
            quote = "$'"
            i += 2
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "#" and (i == 0 or text[i - 1] in " \t\n;&|()"):
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


class _TooComplex(Exception):
    """The input has more tokens than the budget allows."""


def _lex(text: str, budget: list[int] | None = None) -> list[str]:
    """Return shell words and operators.

    Quotes, backslashes, backslash-newline, ``$'...'`` and ``$"..."`` are decoded.
    Operators are runs of ``;&|()<>`` and newlines, each its own token. Raises
    ValueError on an unbalanced quote and _TooComplex when the shared token
    ``budget`` (a one item list) runs out.
    """
    tokens: list[str] = []
    word: list[str] = []
    has_word = False
    quoted = False  # part of the current word was escaped or quoted
    i = 0
    n = len(text)

    def push(token: str) -> None:
        if budget is not None:
            budget[0] -= 1
            if budget[0] < 0:
                raise _TooComplex
        tokens.append(token)

    def push_word() -> None:
        text_ = "".join(word).replace("\x00", "")
        # An escaped or quoted ``;`` or ``|`` is a word, not an operator, as in a shell.
        push(_Literal(text_) if quoted and _is_operator(text_) else text_)

    while i < n:
        ch = text[i]
        if ch in " \t\r":
            if has_word:
                push_word()
                word, has_word, quoted = [], False, False
            i += 1
        elif ch == "\\":
            if text.startswith("\n", i + 1):
                i += 2
            else:
                word.append(text[i + 1] if i + 1 < n else "\\")
                has_word = quoted = True
                i += 2
        elif ch in _PUNCTUATION:
            if has_word:
                push_word()
                word, has_word, quoted = [], False, False
            j = i
            while j < n and text[j] in _PUNCTUATION:
                j += 1
            push(text[i:j])
            i = j
        elif ch == "'":
            end = text.find("'", i + 1)
            if end < 0:
                raise ValueError("a single quote is not closed")
            word.append(text[i + 1 : end])
            has_word = quoted = True
            i = end + 1
        elif ch == '"' or (ch == "$" and text.startswith('"', i + 1)):
            i += 1 if ch == '"' else 2
            while True:
                if i >= n:
                    raise ValueError("a double quote is not closed")
                c = text[i]
                if c == '"':
                    i += 1
                    break
                if c == "\\" and i + 1 < n:
                    following = text[i + 1]
                    if following == "\n":
                        i += 2
                        continue
                    if following in '$`"\\':
                        word.append(following)
                        i += 2
                        continue
                word.append(c)
                i += 1
            has_word = quoted = True
        elif ch == "$" and text.startswith("'", i + 1):
            decoded, i = _ansi(text, i + 2)
            word.append(decoded)
            has_word = quoted = True
        elif ch == "#" and not has_word:
            end = text.find("\n", i)
            i = n if end < 0 else end
        else:
            word.append(ch)
            has_word = True
            i += 1
    if has_word:
        push_word()
    return tokens


class _Literal(str):
    """A word made only of operator characters that was escaped or quoted, so it is data."""

    __slots__ = ()


def _is_operator(token: str) -> bool:
    return (
        not isinstance(token, _Literal) and bool(token) and all(ch in _PUNCTUATION for ch in token)
    )


# heredocs, segments, substitutions ----------------------------------------------


def _heredocs(line: str) -> list[tuple[str, bool]]:
    """Return (delimiter, body_is_commands) for each heredoc operator on one line."""
    if "((" in line:
        return []
    try:
        tokens = _lex(line)
    except ValueError:
        return []
    receives = any(
        os.path.basename(token).lower() in _HEREDOC_RECEIVERS
        for token in tokens
        if not _is_operator(token)
    )
    found: list[tuple[str, bool]] = []
    for i, token in enumerate(tokens[:-1]):
        if token == "<<" and not _is_operator(tokens[i + 1]):  # noqa: S105 (a shell operator)
            delimiter = tokens[i + 1].lstrip("-")
            if delimiter:
                found.append((delimiter, receives))
    return found


def _blank_heredoc_bodies(text: str, bodies: list[tuple[int, str]]) -> str:
    """Blank heredoc bodies that are data, keep the ones that run as commands.

    A data body is recorded in ``bodies`` as (offset, text). A heredoc whose
    delimiter never arrives was a misreading, so the text is kept whole.
    """
    if "<<" not in text:
        return text
    out: list[str] = []
    pending: list[tuple[str, bool]] = []
    found: list[tuple[int, str]] = []
    position = 0
    current_start = 0
    current: list[str] = []
    for line in text.split("\n"):
        if pending:
            delimiter, keep = pending[0]
            if line.strip() == delimiter:
                pending.pop(0)
                if current:
                    found.append((current_start, "\n".join(current)))
                    current = []
                out.append(" " * len(line))
            else:
                if not keep:
                    if not current:
                        current_start = position
                    current.append(line)
                out.append(line if keep else " " * len(line))
        else:
            out.append(line)
            pending.extend(_heredocs(line))
        position += len(line) + 1
    if pending:
        return text
    bodies.extend(found)
    return "\n".join(out)


def _preprocess(command: str, bodies: list[tuple[int, str]]) -> str:
    """Return length preserving text ready for lexing: comments and data heredocs blanked."""
    return _blank_heredoc_bodies(_strip_comments(command), bodies)


def _segments(
    tokens: list[str],
) -> list[tuple[list[str], list[str], list[str], bool]]:
    """Split tokens into simple commands.

    Each segment is (argv, every_word, herestrings, piped). ``argv`` has
    redirections and their targets removed, ``every_word`` keeps the targets,
    ``herestrings`` holds each ``<<<`` word, ``piped`` is True when a pipe feeds
    the segment.
    """
    segments: list[tuple[list[str], list[str], list[str], bool]] = []
    argv: list[str] = []
    words: list[str] = []
    herestrings: list[str] = []
    piped = False
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if _is_operator(token):
            redirect = ("<" in token or ">" in token) and "(" not in token and ")" not in token
            if redirect:
                if argv and argv[-1].isdigit():
                    argv.pop()
                if i + 1 < len(tokens) and not _is_operator(tokens[i + 1]):
                    words.append(tokens[i + 1])
                    if token == "<<<":  # noqa: S105 (a shell operator)
                        herestrings.append(tokens[i + 1])
                    i += 1
                i += 1
                continue
            if argv or words:
                segments.append((argv, words, herestrings, piped))
            argv, words, herestrings = [], [], []
            piped = token in ("|", "|&")
            i += 1
            continue
        argv.append(token)
        words.append(token)
        i += 1
    if argv or words:
        segments.append((argv, words, herestrings, piped))
    return segments


def _substitutions(text: str) -> list[tuple[int, str]]:
    """Return (offset, text) for each ``$(...)`` and backtick body a shell would run.

    Single quotes and ``$'...'`` suppress expansion, so a mention of a command inside
    them is inert data. The scan tracks quotes itself on the raw text for that reason.
    """
    found: list[tuple[int, str]] = []
    quote = ""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote == "'":
            if ch == "'":
                quote = ""
            i += 1
            continue
        if quote == '"':
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == '"':
                quote = ""
                i += 1
                continue
        elif ch == "\\" and i + 1 < n:
            i += 2
            continue
        elif ch == "$" and text.startswith("'", i + 1):
            i = _skip_ansi(text, i + 2)
            continue
        elif ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        if text.startswith("$(", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if text[j] == "(":
                    depth += 1
                elif text[j] == ")":
                    depth -= 1
                j += 1
            end = j - 1 if depth == 0 else n
            found.append((i + 2, text[i + 2 : end]))
            i = j
            continue
        if ch == "`":
            j = text.find("`", i + 1)
            if j < 0:
                found.append((i + 1, text[i + 1 :]))
                break
            found.append((i + 1, text[i + 1 : j]))
            i = j + 1
            continue
        i += 1
    return found


# option handling ---------------------------------------------------------------


def _skip_options(args: list[str], with_value: frozenset[str] | set[str] = frozenset()) -> int:
    """Return the index of the first operand after leading options.

    ``with_value`` names options that consume the next word, alone (``-u root``)
    or ending a cluster (``-Eu root``). A ``--`` ends the options and is skipped. A
    long option written ``--name=value`` is one word.
    """
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            return i + 1
        if not arg.startswith("-") or arg == "-":
            return i
        clustered = len(arg) > 2 and not arg.startswith("--") and ("-" + arg[-1]) in with_value
        if arg in with_value or clustered:
            i += 2
            continue
        i += 1
    return i


def _after_double_dash(args: list[str]) -> list[str] | None:
    return args[args.index("--") + 1 :] if "--" in args else None


def _shell_script(args: list[str]) -> tuple[str, str | None]:
    """For a shell's arguments return ("c", text), ("stdin", None) or ("file", None)."""
    i = 0
    reads_stdin_flag = False
    while i < len(args):
        arg = args[i]
        if arg == "--":
            return ("file", None) if i + 1 < len(args) and not reads_stdin_flag else ("stdin", None)
        if arg in _SHELL_VALUE_OPTIONS:
            i += 2
            continue
        if arg[:1] in ("-", "+") and len(arg) > 1 and not arg.startswith("--"):
            if "c" in arg[1:]:
                return ("c", args[i + 1] if i + 1 < len(args) else "")
            if "s" in arg[1:]:
                reads_stdin_flag = True
            i += 1
            continue
        if arg.startswith("--"):
            i += 1
            continue
        return ("stdin", None) if reads_stdin_flag else ("file", None)
    return ("stdin", None)


def _strip_leading(argv: list[str]) -> list[str]:
    """Drop leading keywords, assignments and a ``function name {`` header in one pass."""
    i = 0
    while i < len(argv):
        word = argv[i]
        if word in _LEADING_KEYWORDS or _ASSIGNMENT.match(word):
            i += 1
        elif word == "function" and "{" in argv[i:]:
            i = argv.index("{", i) + 1
        else:
            break
    return argv[i:]


def _reads_stdin_shell(argv: list[str]) -> bool:
    argv = _strip_leading(argv)
    if not argv:
        return False
    program = os.path.basename(argv[0]).lower()
    if program in _SHELLS:
        return _shell_script(argv[1:])[0] == "stdin" or any(a in _STDIN_SCRIPTS for a in argv[1:])
    return program in (".", "source") and any(a in _STDIN_SCRIPTS for a in argv[1:])


# wrappers ----------------------------------------------------------------------


@dataclass(frozen=True)
class _Wrap:
    """How a wrapper program is skipped to reach the command it runs.

    values: options whose next word is a value. operands: positional words before
    the command (a duration, a lock file). cancel_operand: options that remove that
    positional word. command_flags: options whose value is itself a command string.
    """

    values: frozenset[str] = frozenset()
    operands: int = 0
    cancel_operand: frozenset[str] = frozenset()
    command_flags: frozenset[str] = frozenset()


def _w(
    values: str = "",
    operands: int = 0,
    cancel: str = "",
    command: str = "",
) -> _Wrap:
    return _Wrap(
        frozenset(values.split()), operands, frozenset(cancel.split()), frozenset(command.split())
    )


_SUDO = (
    "-u -g -h -p -C -D -R -T -U -r -t --user --group --host --prompt --close-from --chdir "
    "--chroot --command-timeout --role --type --other-user"
)
_XARGS = (
    "-n -I -J -L -P -s -E -d -R -S -a --max-args --max-lines --max-procs --max-chars "
    "--delimiter --arg-file --replace --eof --process-slot-var --max-replace"
)
_STRACE = (
    "-o -e -p -s -u -E -O -S -a -b -I -P -X -U -C --output --trace --attach --string-limit "
    "--user --env --signal --abbrev --absolute-timestamps --decode-fds --inject --fault"
)
_UNSHARE = (
    "--propagation -S -G --setuid --setgid --map-user --map-group --map-users --map-groups "
    "--root -R --wd -w --setgroups --keep-caps --monotonic --boottime"
)
_WRAPPERS: dict[str, _Wrap] = {
    "sudo": _w(_SUDO),
    "doas": _w(_SUDO),
    "nice": _w("-n --adjustment"),
    "nohup": _w(),
    "command": _w(),
    "builtin": _w(),
    "noglob": _w(),
    "caffeinate": _w("-t -w"),
    "exec": _w("-a"),
    "time": _w("-f -o --format --output"),
    "stdbuf": _w("-i -o -e --input --output --error"),
    "unbuffer": _w(),
    "setsid": _w(),
    "busybox": _w(),
    "strace": _w(_STRACE),
    "ltrace": _w("-o -e -p -s -u -n --output"),
    "taskset": _w("-c --cpu-list", operands=1, cancel="-p --pid -c --cpu-list"),
    "ionice": _w("-c -n -p -P -u --class --classdata --pid --pgid --uid"),
    "chrt": _w(operands=1, cancel="-p --pid"),
    "chroot": _w("--userspec --groups", operands=1),
    "unshare": _w(_UNSHARE),
    "flock": _w("-w -E --timeout --conflict-exit-code", operands=1, command="-c --command"),
    "su": _w("-g -G -s --group --supp-group --shell", command="-c --command"),
    "script": _w(
        "-t -T -I -O -B -m -E -o", operands=1, cancel="-c --command", command="-c --command"
    ),
    "timeout": _w("-s -k --signal --kill-after", operands=1),
    "gtimeout": _w("-s -k --signal --kill-after", operands=1),
    "xargs": _w(_XARGS),
}


class _Walker:
    """Collects simple commands from a command string and everything it runs."""

    def __init__(self) -> None:
        self.result = ShellParse()
        self.budget = [MAX_TOKENS]
        self._stdin: tuple[str, ...] = ()

    def _emit(
        self, program: str, args: list[str], words: list[str], offset: int, depth: int
    ) -> None:
        if len(self.result.commands) >= MAX_COMMANDS:
            self.result.exhausted = True
            return
        self.result.commands.append(
            SimpleCommand(program, tuple(args), tuple(words), offset, depth, self._stdin)
        )

    def command(self, text: str, depth: int, base: int, exact: bool) -> None:
        """Walk a command string. ``exact`` says offsets in ``text`` map onto the input."""
        if depth > MAX_DEPTH:
            self.result.exhausted = True
            return
        if not text.strip():
            return
        local: list[tuple[int, str]] = []
        processed = _preprocess(text, local)
        self.result.heredocs.extend(
            (base + offset if exact else base, body) for offset, body in local
        )
        for start, inner in _substitutions(processed):
            self.command(inner, depth + 1, base + start if exact else base, exact)
        try:
            tokens = _lex(processed, self.budget)
        except ValueError:
            self.result.fallback = True
            self._lenient(processed, depth, base)
            return
        cursor = 0
        previous: list[str] = []
        for argv, words, herestrings, piped in _segments(tokens):
            offset = base
            if exact and argv:
                found = processed.find(argv[0], cursor)
                if found >= 0:
                    offset = base + found
                    cursor = found + len(argv[0])
            fed = list(herestrings)
            source = _strip_leading(previous)
            if piped and source and os.path.basename(source[0]).lower() in ("echo", "printf"):
                fed.append(self._echoed(source))
            self._stdin = tuple(fed)
            self.argv(argv, depth, offset, words)
            self._stdin = ()
            if _reads_stdin_shell(argv):
                for fed_text in fed:
                    self.command(fed_text.replace("\\n", "\n"), depth + 1, offset, False)
            previous = argv

    @staticmethod
    def _echoed(source: list[str]) -> str:
        words = [a for a in source[1:] if a not in _ECHO_FLAGS]
        return decode_escapes(" ".join(words))

    def _lenient(self, processed: str, depth: int, base: int) -> None:
        for chunk in re.split(r"[;&|()<>\n]+", processed):
            argv = [word.strip("'\"") for word in chunk.split()]
            argv = [word for word in argv if word]
            if argv:
                self.argv(argv, depth, base, argv)

    def argv(
        self, argv: list[str], depth: int, offset: int, words: list[str] | None = None
    ) -> None:
        """Judge one simple command given as its words, following wrappers."""
        if depth > MAX_DEPTH:
            self.result.exhausted = True
            return
        argv = _strip_leading(argv)
        if not argv:
            return
        program = os.path.basename(argv[0]).lower()
        args = argv[1:]
        every = words if words is not None else argv
        if program == "env":
            self._env(args, depth, offset, every)
            return
        if program == "command" and args[:1] in (["-v"], ["-V"]):
            return
        self._emit(program, args, every, offset, depth)
        self._wrapper(program, args, depth, offset)

    def _env(self, args: list[str], depth: int, offset: int, words: list[str]) -> None:
        if args and args[0] in ("--version", "--help"):
            return
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--":
                i += 1
                break
            cluster = len(arg) > 2 and not arg.startswith("--")
            if arg in ("-S", "--split-string") or (cluster and arg[-1] == "S"):
                if i + 1 < len(args):
                    joined = args[i + 1] + " " + " ".join(shlex.quote(a) for a in args[i + 2 :])
                    self.command(joined, depth + 1, offset, False)
                return
            if arg.startswith("--split-string="):
                self.command(arg.split("=", 1)[1], depth + 1, offset, False)
                return
            if arg in ("-u", "-C", "-P", "--unset", "--chdir") or (cluster and arg[-1] in "uCP"):
                i += 2
                continue
            if arg.startswith("-"):
                i += 1
                continue
            break
        while i < len(args) and _ASSIGNMENT.match(args[i]):
            i += 1
        rest = args[i:]
        if not rest:
            self._emit("env", [], words, offset, depth)
            return
        self.argv(rest, depth + 1, offset)

    def _wrapper(self, program: str, args: list[str], depth: int, offset: int) -> None:
        nxt = depth + 1
        if program in _SHELLS:
            kind, text = _shell_script(args)
            if kind == "c" and text:
                self.command(text, nxt, offset, False)
        elif program == "eval":
            self.command(" ".join(args), nxt, offset, False)
        elif program == "ssh":
            remote = args[_skip_options(args, _SSH_VALUE_OPTIONS) + 1 :]
            remote = remote[_skip_options(remote, _SSH_VALUE_OPTIONS) :]
            if remote:
                self.command(" ".join(remote), nxt, offset, False)
        elif program == "find":
            self._find(args, nxt, offset)
        elif program == "watch":
            rest = args[_skip_options(args, {"-n", "--interval", "-d", "--differences"}) :]
            self.command(" ".join(rest), nxt, offset, False)
        elif program in _DOCKER_PROGRAMS:
            self._docker(program, args, nxt, offset)
        elif program in ("op", "kubectl"):
            tail = _after_double_dash(args)
            if tail:
                self.argv(tail, nxt, offset)
        elif program in _WRAPPERS:
            self._table(_WRAPPERS[program], args, nxt, offset)
        elif program in ("function",):
            return

    def _table(self, spec: _Wrap, args: list[str], depth: int, offset: int) -> None:
        for i, arg in enumerate(args):
            if arg == "--":
                break
            if self._is_command_flag(arg, spec):
                value = arg.split("=", 1)[1] if "=" in arg and arg.startswith("--") else None
                if value is None and i + 1 < len(args):
                    value = args[i + 1]
                if value:
                    self.command(value, depth, offset, False)
                return
        index = _skip_options(args, spec.values)
        if spec.operands and not any(a in spec.cancel_operand for a in args[:index]):
            index += spec.operands
        self.argv(args[index:], depth, offset)

    @staticmethod
    def _is_command_flag(arg: str, spec: _Wrap) -> bool:
        if not spec.command_flags or not arg.startswith("-"):
            return False
        if arg in spec.command_flags:
            return True
        if arg.startswith("--"):
            return arg.split("=", 1)[0] in spec.command_flags and "=" in arg
        return len(arg) > 2 and ("-" + arg[-1]) in spec.command_flags

    def _find(self, args: list[str], depth: int, offset: int) -> None:
        k = 0
        while k < len(args):
            if args[k] in _EXEC_FLAGS:
                end = k + 1
                while end < len(args) and args[end] not in (";", "+"):
                    end += 1
                self.argv(args[k + 1 : end], depth, offset)
                k = end + 1
            else:
                k += 1

    def _docker(self, program: str, args: list[str], depth: int, offset: int) -> None:
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in _DOCKER_GLOBAL_VALUE_OPTIONS else 1
        if i >= len(args):
            return
        sub, rest = args[i], args[i + 1 :]
        if sub in ("container", "compose", "image", "service") and rest:
            index = _skip_options(rest, _DOCKER_GLOBAL_VALUE_OPTIONS)
            if index >= len(rest):
                return
            sub, rest = rest[index], rest[index + 1 :]
        if sub not in ("exec", "run"):
            return
        j = _skip_options(rest, _DOCKER_VALUE_OPTIONS)
        entry = self._entrypoint(rest[:j])
        tail = rest[j + 1 :]
        self.argv(([entry] if entry else []) + tail, depth, offset)

    @staticmethod
    def _entrypoint(options: list[str]) -> str | None:
        for k, option in enumerate(options):
            if option == "--entrypoint" and k + 1 < len(options):
                return options[k + 1]
            if option.startswith("--entrypoint="):
                return option.split("=", 1)[1]
        return None


def normalise_path(word: str) -> str:
    """Collapse repeated slashes, ``.`` and ``..`` in a path-like word."""
    return posixpath.normpath(word) if "/" in word else word


def parse_shell(command: str) -> ShellParse:
    """Parse a shell command string into simple commands.

    Args:
        command: the command text. The caller bounds its length.

    Returns:
        A ``ShellParse``. Commands are listed in order of appearance, with the
        commands a wrapper, substitution or ``-c`` string runs following the
        command that runs them. ``exhausted`` is set when a limit ran out (token
        budget, nesting depth or command count), in which case the commands found so
        far are incomplete.
    """
    walker = _Walker()
    command = command.replace("\x00", "")
    try:
        walker.command(command, 0, 0, True)
    except _TooComplex:
        walker.result.exhausted = True
    return walker.result
