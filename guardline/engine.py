"""The scanner: one place where text, shell commands and tool payloads are judged.

Every entry point (the agent hook, the pre-commit hook, the command line scan)
goes through ``Scanner``, so the same input gets the same verdict from all of them.
A finding carries the rule id, the family and a position. It never carries the
matched text.
"""

from __future__ import annotations

import bisect
import os
import re
import shlex
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from guardline.model import ENGINE_FAMILY, Finding, Rule
from guardline.rules import builtin_rules
from guardline.shell import (
    ShellParse,
    SimpleCommand,
    decode_escapes,
    normalise_path,
    parse_shell,
)

DEFAULT_MAX_TEXT_CHARS = 1024 * 1024
"""Longest text one scan accepts, in characters."""

DEFAULT_MAX_COMMAND_CHARS = 64 * 1024
"""Longest shell command one scan accepts, in characters."""

MAX_FINDINGS = 1000
"""Most findings one scan returns before it reports truncation."""

TOO_LARGE_RULE = "guardline-input-too-large"
TRUNCATED_RULE = "guardline-findings-truncated"
TOO_COMPLEX_RULE = "guardline-command-too-complex"
CONFIG_EDIT_RULE = "guardline-config-edit"
FILE_SKIPPED_RULE = "guardline-file-skipped"

ATTRIBUTION_FAMILY = "attribution"

_FENCE_OPEN = re.compile(r" {0,3}(`{3,}|~{3,})[^\n]*")
_FENCE_CLOSE = re.compile(r" {0,3}(`{3,}|~{3,})[ \t]*")

_GIT_AUTHORING = frozenset(
    {"commit", "tag", "notes", "merge", "commit-tree", "revert", "cherry-pick"}
)
_GIT_GLOBAL_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
_GH_READ_VERBS = frozenset(
    {"list", "ls", "view", "status", "diff", "checks", "checkout", "download"}
)
_GH_TEXT_COMMANDS = frozenset({"pr", "issue", "release", "gist"})
_GH_API_BODY_FLAGS = frozenset({"-f", "-F", "--field", "--raw-field", "--input"})
_GLAB_COMMANDS = frozenset({"mr", "issue", "release"})

_MESSAGE_FIELDS = (
    "content",
    "new_string",
    "new_source",
    "body",
    "commit_message",
    "message",
    "title",
    "description",
    "text",
)
_COMMAND_FIELDS = ("command", "cmd")
_LOCAL_TOOLS = frozenset({"TodoWrite"})
_EDIT_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_COMMAND_KEYS = frozenset(_COMMAND_FIELDS)
_MESSAGE_KEYS = frozenset(_MESSAGE_FIELDS)
_KNOWN_KEYS = _COMMAND_KEYS | _MESSAGE_KEYS | {"edits", "file_path", "old_string"}
MAX_PAYLOAD_DEPTH = 16
"""Deepest nesting of a tool input that is walked."""
MAX_PAYLOAD_LEAVES = 2000
"""Most string values of a tool input that are judged."""
_GIT_BINARY = "git-"


class _Lines:
    """Map a character offset to a one based line and column."""

    def __init__(self, text: str) -> None:
        self._starts = [0]
        for match in re.finditer("\n", text):
            self._starts.append(match.end())

    def locate(self, offset: int) -> tuple[int, int]:
        index = bisect.bisect_right(self._starts, offset) - 1
        return index + 1, offset - self._starts[index] + 1


def fenced_ranges(text: str) -> list[tuple[int, int]]:
    """Return the character ranges of the content inside closed fenced code blocks.

    A fence is three or more backticks or tildes at the start of a line, indented
    at most three spaces. A block closes on a fence of the same character that is
    at least as long and has no info string. A block that never closes is not
    fenced, so an unterminated fence exempts nothing.
    """
    ranges: list[tuple[int, int]] = []
    position = 0
    opened: tuple[str, int, int] | None = None
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if opened is None:
            match = _FENCE_OPEN.fullmatch(body)
            if match and not (match.group(1)[0] == "`" and "`" in body[match.end(1) :]):
                opened = (match.group(1)[0], len(match.group(1)), position + len(line))
        else:
            close = _FENCE_CLOSE.fullmatch(body)
            if close and close.group(1)[0] == opened[0] and len(close.group(1)) >= opened[1]:
                ranges.append((opened[2], position))
                opened = None
        position += len(line)
    return ranges


def _in_ranges(offset: int, ranges: Sequence[tuple[int, int]]) -> bool:
    return any(start <= offset < end for start, end in ranges)


def strip_value_options(args: Sequence[str], value_options: frozenset[str]) -> list[str]:
    """Drop the value word that follows each value taking option.

    The option word itself is kept, so a cluster such as ``-Eo`` is still seen.
    """
    kept: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        kept.append(arg)
        if arg.startswith("-") and len(arg) > 1:
            ends_with_value = not arg.startswith("--") and ("-" + arg[-1]) in value_options
            if arg in value_options or ends_with_value:
                i += 2
                continue
        i += 1
    return kept


def _git_subcommand(args: Sequence[str]) -> str:
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in _GIT_GLOBAL_VALUE:
            i += 2
        elif arg.startswith("-"):
            i += 1
        else:
            return arg
    return ""


def is_authoring_command(command: SimpleCommand) -> bool:
    """Return True when a command publishes a message, such as a commit or a pull request body."""
    program, args = command.program, command.args
    if program == "git":
        return _git_subcommand(args) in _GIT_AUTHORING
    if program.startswith(_GIT_BINARY):
        return program[len(_GIT_BINARY) :] in _GIT_AUTHORING
    if program == "gh" and args:
        if args[0] in _GH_TEXT_COMMANDS:
            return len(args) > 1 and args[1] not in _GH_READ_VERBS
        if args[0] == "api":
            method = ""
            for i, arg in enumerate(args):
                if arg in ("-X", "--method") and i + 1 < len(args):
                    method = args[i + 1].upper()
            return any(arg in _GH_API_BODY_FLAGS for arg in args) or method not in ("", "GET")
    if program == "glab" and args and args[0] in _GLAB_COMMANDS:
        return len(args) > 1 and args[1] not in _GH_READ_VERBS
    return False


class _TooBig(Exception):
    """A tool input has more nesting or values than the walker allows."""


def _all(_rule: Rule) -> bool:
    return True


def _not_attribution(rule: Rule) -> bool:
    return rule.family != ATTRIBUTION_FAMILY


def _only_attribution(rule: Rule) -> bool:
    return rule.family == ATTRIBUTION_FAMILY


def _word_candidates(word: str) -> Iterable[str]:
    """Yield a word, its normalised path, and the value of a ``name=value`` word likewise."""
    yield word
    normal = normalise_path(word)
    if normal != word:
        yield normal
    if "=" in word:
        value = word.split("=", 1)[1]
        yield value
        yield normalise_path(value)


class Scanner:
    """Apply a set of rules to text, shell commands and tool payloads.

    Args:
        rules: the rules to apply. Defaults to the built-in rules.
        allow_fenced_attribution: when True, attribution findings inside a closed
            fenced code block are dropped. This is an explicit switch for quoting a
            third party's text. It is off by default and has no configuration key.
        max_text_chars: longest text accepted. Longer text yields a single
            ``guardline-input-too-large`` finding instead of being scanned.
        max_command_chars: longest shell command accepted, with the same result.
        families: when given, only rules of these families run.
        allow_config_edit: when False (the default), ``scan_payload`` reports a
            Write, Edit or MultiEdit that targets a guardline configuration file.
        protected_paths: extra files (the hook's own ``--config`` and rule files)
            that ``scan_payload`` also protects from edits.
    """

    def __init__(
        self,
        rules: Sequence[Rule] | None = None,
        *,
        allow_fenced_attribution: bool = False,
        max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
        max_command_chars: int = DEFAULT_MAX_COMMAND_CHARS,
        families: Iterable[str] | None = None,
        allow_config_edit: bool = False,
        protected_paths: Iterable[str] = (),
    ) -> None:
        chosen = tuple(rules) if rules is not None else builtin_rules()
        wanted = frozenset(families) if families is not None else None
        self.rules = tuple(rule for rule in chosen if wanted is None or rule.family in wanted)
        self.allow_fenced_attribution = allow_fenced_attribution
        self.max_text_chars = max_text_chars
        self.max_command_chars = max_command_chars
        self.allow_config_edit = allow_config_edit
        self._protected = frozenset(os.path.realpath(path) for path in protected_paths)
        self._text_rules = tuple(rule for rule in self.rules if rule.scope == "text")
        self._command_rules = tuple(rule for rule in self.rules if rule.scope != "text")

    # text -------------------------------------------------------------

    def _text_matches(self, text: str, include: Callable[[Rule], bool]) -> list[tuple[Rule, int]]:
        fenced = (
            fenced_ranges(text)
            if self.allow_fenced_attribution
            and any(rule.family == ATTRIBUTION_FAMILY for rule in self._text_rules)
            else []
        )
        found: list[tuple[Rule, int]] = []
        for rule in self._text_rules:
            if not include(rule):
                continue
            for match in rule.regex.finditer(text):
                if rule.unless_regex is not None and rule.unless_regex.search(match.group(0)):
                    continue
                if rule.family == ATTRIBUTION_FAMILY and _in_ranges(match.start(), fenced):
                    continue
                found.append((rule, match.start()))
                if len(found) > MAX_FINDINGS:
                    return found
        return found

    def _finding(self, rule: Rule, source: str, lines: _Lines, offset: int) -> Finding:
        line, column = lines.locate(offset)
        return Finding(rule.id, rule.family, rule.description, source, offset, line, column)

    def _engine_finding(self, rule_id: str, description: str, source: str) -> Finding:
        return Finding(rule_id, ENGINE_FAMILY, description, source, 0, 1, 1)

    def oversize_finding(self, source: str) -> Finding:
        """Return the finding that stands for an input too large to scan."""
        return self._too_large(source, self.max_text_chars)

    def skipped_finding(self, source: str) -> Finding:
        """Return the finding that stands for a file that could not be scanned."""
        return self._engine_finding(
            FILE_SKIPPED_RULE,
            "The file was not scanned: it is a symbolic link or not a regular file.",
            source,
        )

    def _too_large(self, source: str, limit: int) -> Finding:
        return self._engine_finding(
            TOO_LARGE_RULE,
            f"The input is longer than {limit} characters and was not scanned.",
            source,
        )

    def _finish(self, findings: list[Finding], source: str) -> list[Finding]:
        unique = {(f.rule_id, f.offset, f.source): f for f in findings}
        ordered = sorted(unique.values(), key=lambda f: (f.source, f.offset, f.rule_id))
        if len(ordered) > MAX_FINDINGS:
            ordered = ordered[:MAX_FINDINGS]
            ordered.append(
                self._engine_finding(
                    TRUNCATED_RULE,
                    f"More than {MAX_FINDINGS} findings; the rest are not listed.",
                    source,
                )
            )
        return ordered

    def scan_text(
        self, text: str, source: str = "<text>", *, include_attribution: bool = True
    ) -> list[Finding]:
        """Scan authored text with every text scope rule.

        NUL characters are removed first, so they cannot split a match.

        Args:
            text: the text to judge.
            source: a label for findings, usually a file path.
            include_attribution: when False the attribution family is skipped.

        Returns:
            Findings ordered by position. Empty means clean.
        """
        if len(text) > self.max_text_chars:
            return [self._too_large(source, self.max_text_chars)]
        text = text.replace("\x00", "")
        lines = _Lines(text)
        include = _all if include_attribution else _not_attribution
        return self._finish(
            [
                self._finding(rule, source, lines, at)
                for rule, at in self._text_matches(text, include)
            ],
            source,
        )

    # commands ---------------------------------------------------------

    def _command_matches(self, command: SimpleCommand, rule: Rule) -> bool:
        if rule.scope == "word":
            return any(
                rule.regex.fullmatch(candidate)
                for word in command.words
                for candidate in _word_candidates(word)
            )
        if command.program not in rule.programs:
            return False
        args = " ".join(strip_value_options(command.args, rule.value_options))
        if not rule.regex.search(args):
            return False
        return not (rule.unless_regex is not None and rule.unless_regex.search(args))

    @staticmethod
    def _authored(parse: ShellParse) -> list[tuple[int, str]]:
        """Return (offset, text) pairs a publishing command carries, when there is one."""
        authoring = [simple for simple in parse.commands if is_authoring_command(simple)]
        if not authoring:
            return []
        texts: list[tuple[int, str]] = []
        for simple in authoring:
            lines: list[str] = []
            for arg in simple.args:
                lines.append(arg)
                if "=" in arg:
                    lines.append(arg.partition("=")[2])
            texts.append((simple.offset, "\n".join(lines)))
            texts.extend((simple.offset, fed) for fed in simple.stdin)
        for simple in parse.commands:
            if simple.program in ("echo", "printf") and simple.depth > 0:
                words = [a for a in simple.args if a not in ("-n", "-e", "-E")]
                texts.append((simple.offset, decode_escapes(" ".join(words))))
        texts.extend(parse.heredocs)
        return texts

    def scan_command(self, command: str, source: str = "<command>") -> list[Finding]:
        """Scan a shell command string.

        Command rules (scope ``args`` and ``word``) judge each simple command the
        shell would run, looking through pipes, substitutions and wrappers. Text
        rules of every family except attribution judge the whole command text and
        also the decoded shell words, so a secret passed as an argument is found even
        when quoting hides it. Attribution rules judge only the text a publishing
        command (a git commit, a gh pull request body and the like) carries, including
        text fed to it on standard input by a here-string or a piped echo or printf,
        plus heredoc bodies when such a command is present.

        Args:
            command: the command text.
            source: a label for findings.

        Returns:
            Findings ordered by position. Empty means clean. A command that hit a
            parser limit yields a ``guardline-command-too-complex`` finding.
        """
        if len(command) > self.max_command_chars:
            return [self._too_large(source, self.max_command_chars)]
        command = command.replace("\x00", "")
        lines = _Lines(command)
        parse: ShellParse = parse_shell(command)
        findings: list[Finding] = []
        if parse.exhausted:
            findings.append(
                self._engine_finding(
                    TOO_COMPLEX_RULE,
                    "The command has too many words or nests too deeply to judge.",
                    source,
                )
            )
        for simple in parse.commands:
            for rule in self._command_rules:
                if self._command_matches(simple, rule):
                    findings.append(self._finding(rule, source, lines, simple.offset))
        raw = self._text_matches(command, _not_attribution)
        found = {rule.id for rule, _ in raw}
        for rule, at in raw:
            findings.append(self._finding(rule, source, lines, at))
        for simple in parse.commands:
            if all(word in command for word in simple.words):
                continue
            for rule, _ in self._text_matches("\n".join(simple.words), _not_attribution):
                if rule.id not in found:
                    found.add(rule.id)
                    findings.append(self._finding(rule, source, lines, simple.offset))
        for offset, text in self._authored(parse):
            for rule, _ in self._text_matches(text, _only_attribution):
                findings.append(self._finding(rule, source, lines, offset))
        return self._finish(findings, source)

    # payloads ---------------------------------------------------------

    def _collect(
        self,
        value: Any,
        path: str,
        key: str | None,
        depth: int,
        out: list[tuple[str, str | None, str]],
    ) -> None:
        if depth > MAX_PAYLOAD_DEPTH or len(out) > MAX_PAYLOAD_LEAVES:
            raise _TooBig
        if isinstance(value, str):
            out.append((path, key, value))
        elif isinstance(value, dict):
            for name, item in value.items():
                label = name if name in _KNOWN_KEYS else "*"
                self._collect(item, f"{path}.{label}", name, depth + 1, out)
        elif isinstance(value, list):
            if key in _COMMAND_KEYS and value and all(isinstance(part, str) for part in value):
                out.append((path, key, " ".join(shlex.quote(part) for part in value)))
                return
            for index, item in enumerate(value):
                self._collect(item, f"{path}[{index}]", key, depth + 1, out)

    def _config_edit(self, tool: Any, tool_input: Any) -> Finding | None:
        if self.allow_config_edit or tool not in _EDIT_TOOLS or not isinstance(tool_input, dict):
            return None
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not isinstance(path, str) or not path:
            return None
        base = os.path.basename(path).lower()
        protected = base == "guardline.toml" or os.path.realpath(path) in self._protected
        if not protected and base == "pyproject.toml":
            protected = self._touches_guardline_table(path, tool_input)
        if not protected:
            return None
        return self._engine_finding(
            CONFIG_EDIT_RULE,
            "A write to a guardline configuration file could switch the guard off.",
            "tool_input.file_path",
        )

    @staticmethod
    def _touches_guardline_table(path: str, tool_input: dict[str, Any]) -> bool:
        pieces: list[str] = []
        for holder in [
            tool_input,
            *[e for e in tool_input.get("edits", []) if isinstance(e, dict)],
        ]:
            for key in ("content", "new_string", "old_string"):
                if isinstance(holder.get(key), str):
                    pieces.append(holder[key])
        if "tool.guardline" in "\n".join(pieces).lower():
            return True
        try:
            with open(path, "rb") as handle:
                existing = handle.read(DEFAULT_MAX_TEXT_CHARS).decode("utf-8", errors="replace")
        except OSError:
            return False
        return "tool.guardline" in existing.lower()

    def scan_payload(self, payload: Any) -> list[Finding]:
        """Scan a PreToolUse style tool call payload.

        The payload is a mapping with ``tool_name`` and ``tool_input``. Every string
        value of ``tool_input`` is judged, at any depth. A value under a key named
        ``command`` or ``cmd`` is a shell command and goes through ``scan_command``
        (a list of strings under such a key is joined as shell words). A value under
        an authored text key (``content``, ``new_string``, ``body``, ``message`` and
        the like) goes through ``scan_text`` with every family. Any other string goes
        through ``scan_text`` without the attribution family, so a credential in any
        field of any tool, including an MCP tool, is found. A Write, Edit or MultiEdit
        to a guardline configuration file is reported unless ``allow_config_edit``.

        Returns:
            Findings, each with a source such as ``tool_input.command``. Values under
            keys guardline does not know are labelled ``*``.
        """
        if not isinstance(payload, dict) or payload.get("tool_name") in _LOCAL_TOOLS:
            return []
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict | list):
            return []
        findings: list[Finding] = []
        guard = self._config_edit(payload.get("tool_name"), tool_input)
        if guard is not None:
            findings.append(guard)
        leaves: list[tuple[str, str | None, str]] = []
        try:
            self._collect(tool_input, "tool_input", None, 0, leaves)
        except _TooBig:
            findings.append(
                self._engine_finding(
                    TOO_COMPLEX_RULE,
                    "The tool input nests too deeply or has too many values to judge.",
                    "tool_input",
                )
            )
        for path, key, value in leaves:
            if key in _COMMAND_KEYS:
                findings.extend(self.scan_command(value, path))
            elif key in _MESSAGE_KEYS:
                findings.extend(self.scan_text(value, path))
            else:
                findings.extend(self.scan_text(value, path, include_attribution=False))
        return findings


def scan_text(text: str, **options: Any) -> list[Finding]:
    """Scan text with the built-in rules. Keyword options are those of ``Scanner``."""
    return Scanner(**options).scan_text(text)


def scan_command(command: str, **options: Any) -> list[Finding]:
    """Scan a shell command with the built-in rules. Keyword options are those of ``Scanner``."""
    return Scanner(**options).scan_command(command)


def scan_payload(payload: Any, **options: Any) -> list[Finding]:
    """Scan a tool call payload with the built-in rules. Options are those of ``Scanner``."""
    return Scanner(**options).scan_payload(payload)


__all__ = [
    "CONFIG_EDIT_RULE",
    "DEFAULT_MAX_COMMAND_CHARS",
    "DEFAULT_MAX_TEXT_CHARS",
    "FILE_SKIPPED_RULE",
    "MAX_FINDINGS",
    "TOO_COMPLEX_RULE",
    "TOO_LARGE_RULE",
    "TRUNCATED_RULE",
    "Scanner",
    "fenced_ranges",
    "is_authoring_command",
    "scan_command",
    "scan_payload",
    "scan_text",
    "strip_value_options",
]
