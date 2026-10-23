"""Audit a regular expression for shapes that make matching super linear.

The rule loader runs every pattern through ``unsafe_pattern_reason`` before it compiles a
rule, because a pattern is run against text an attacker may choose. The audit works on the
parsed pattern, with the flags the rule will be compiled with, and tracks which characters
each node can match: the ASCII characters one by one, and every other character by its class
(digit, space, word or other). It is conservative about what it cannot see and does not
claim to prove a pattern linear. A single unbounded repeat that may start at every position,
such as ``[a-z]+;``, is still quadratic on a long run of its characters and is accepted;
``unbounded_repeat_warning`` names that case so ``guardline rules check`` can report it.
"""

from __future__ import annotations

import importlib
import re
from typing import Any

_parser: Any = importlib.import_module("re._parser")
_const: Any = importlib.import_module("re._constants")

WIDE_REPEAT = 16
"""A repeat allowing more than this many repetitions is wide."""

BIG_BOUND = 1024
"""A bound above this is counted as unbounded, because the work it allows is not small."""

MAX_UNBOUNDED_REPEATS = 3
"""Most unbounded repeats (``*``, ``+``, ``{n,}`` or a huge bound) one pattern may contain."""

_RANGE_LIMIT = 4096
"""Longest non ASCII range whose characters are classified one by one."""

NA_DIGIT, NA_SPACE, NA_WORD, NA_OTHER = "<digit>", "<space>", "<word>", "<other>"
"""Stand ins for the non ASCII characters of each class."""
_NA_ALL = frozenset({NA_DIGIT, NA_SPACE, NA_WORD, NA_OTHER})
_ASCII = frozenset(chr(code) for code in range(128))
_DIGITS = frozenset(c for c in _ASCII if c.isdigit())
_SPACES = frozenset(" \t\n\r\f\v")
_WORDS = frozenset(c for c in _ASCII if c.isalnum() or c == "_")
_CATEGORIES: dict[str, frozenset[str]] = {
    "CATEGORY_DIGIT": _DIGITS | {NA_DIGIT},
    "CATEGORY_NOT_DIGIT": (_ASCII - _DIGITS) | {NA_SPACE, NA_WORD, NA_OTHER},
    "CATEGORY_SPACE": _SPACES | {NA_SPACE},
    "CATEGORY_NOT_SPACE": (_ASCII - _SPACES) | {NA_DIGIT, NA_WORD, NA_OTHER},
    "CATEGORY_WORD": _WORDS | {NA_DIGIT, NA_WORD},
    "CATEGORY_NOT_WORD": (_ASCII - _WORDS) | {NA_SPACE, NA_OTHER},
}
_ANCHORS_AT_END = frozenset({"AT_END", "AT_END_STRING"})


def _repeat_ops() -> frozenset[Any]:
    names = ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT")
    return frozenset(getattr(_const, name) for name in names if hasattr(_const, name))


_REPEATS = _repeat_ops()
_GROUPREFS = frozenset(
    getattr(_const, name)
    for name in ("GROUPREF", "GROUPREF_EXISTS", "GROUPREF_IGNORE")
    if hasattr(_const, name)
)
_ATOMIC = getattr(_const, "ATOMIC_GROUP", None)


def _non_ascii_class(char: str) -> str:
    if char.isdecimal():
        return NA_DIGIT
    if char.isspace():
        return NA_SPACE
    if char.isalnum() or char == "_":
        return NA_WORD
    return NA_OTHER


def _literal(code: int) -> frozenset[str]:
    return frozenset({chr(code)}) if code < 128 else frozenset({_non_ascii_class(chr(code))})


def _fold(chars: frozenset[str]) -> frozenset[str]:
    """Add the other case of every ASCII letter, and the non ASCII letters that fold onto one."""
    folded = set(chars)
    for char in chars:
        if char in _NA_ALL:
            continue
        folded.update(variant for variant in (char.lower(), char.upper()) if variant in _ASCII)
        if char.lower() in "ksi":  # the Kelvin sign, the long s and the dotless i fold to these
            folded.add(NA_WORD)
    return frozenset(folded)


def _members(items: Any) -> frozenset[str]:
    """The characters a bracketed set lists, before negation."""
    members: set[str] = set()
    for op, item in items:
        if op == _const.LITERAL:
            members |= _literal(item)
        elif op == _const.RANGE:
            low, high = item
            members.update(chr(code) for code in range(low, min(high, 127) + 1))
            if high > 127:
                start = max(low, 128)
                if high - start >= _RANGE_LIMIT:
                    members |= _NA_ALL
                else:
                    members.update(_non_ascii_class(chr(code)) for code in range(start, high + 1))
        elif op == _const.CATEGORY:
            members |= _CATEGORIES.get(getattr(item, "name", str(item)), _ASCII | _NA_ALL)
    return frozenset(members)


def _node_chars(op: Any, argument: Any, ignore_case: bool) -> frozenset[str] | None:
    """The characters a one character node can match, or None when it is not one."""
    if op == _const.LITERAL:
        members, negate = _literal(argument), False
    elif op == _const.NOT_LITERAL:
        members, negate = _literal(argument), True
    elif op == _const.ANY:
        return (_ASCII - {"\n"}) | _NA_ALL
    elif op == _const.IN:
        negate = any(item_op == _const.NEGATE for item_op, _ in argument)
        members = _members(item for item in argument if item[0] != _const.NEGATE)
    else:
        return None
    if ignore_case:
        members = _fold(members)
    return (_ASCII - members) | _NA_ALL if negate else members


def _first(
    items: list[Any], ignore_case: bool, follow: frozenset[str] | None
) -> frozenset[str] | None:
    """The characters the first character of ``items`` can be, or of ``follow`` if they are empty.

    An empty set means the end of the text, so nothing can follow. None means unknown.
    """
    if not items:
        return follow
    op, argument = items[0]
    rest = items[1:]
    chars = _node_chars(op, argument, ignore_case)
    if chars is not None:
        return chars
    if op == _const.AT:
        if getattr(argument, "name", "") in _ANCHORS_AT_END:
            return frozenset()
        return _first(rest, ignore_case, follow)  # a zero width anchor consumes nothing
    if op == _const.SUBPATTERN:
        inner = _scoped_case(ignore_case, argument)
        return _first(list(argument[3].data), inner, _first(rest, ignore_case, follow))
    if _ATOMIC is not None and op == _ATOMIC:
        return _first(list(argument.data), ignore_case, _first(rest, ignore_case, follow))
    if op == _const.BRANCH:
        tail = _first(rest, ignore_case, follow)
        union: set[str] = set()
        for branch in argument[1]:
            part = _first(list(branch.data), ignore_case, tail)
            if part is None:
                return None
            union |= part
        return frozenset(union)
    if op in _REPEATS:
        low, _high, body = argument
        tail = _first(rest, ignore_case, follow)
        inside = _first(list(body.data), ignore_case, None if low == 0 else tail)
        if low >= 1:
            return inside
        if inside is None or tail is None:
            return None
        return inside | tail
    return None


def _scoped_case(ignore_case: bool, argument: Any) -> bool:
    """Whether a group ``(?i:...)`` or ``(?-i:...)`` changes case folding inside its body."""
    added, removed = argument[1], argument[2]
    if added & re.IGNORECASE:
        return True
    if removed & re.IGNORECASE:
        return False
    return ignore_case


def _is_unbounded(high: int) -> bool:
    return high == _const.MAXREPEAT or high > BIG_BOUND


def _is_wide(high: int) -> bool:
    return _is_unbounded(high) or high > WIDE_REPEAT


def _wide_repeat_next(data: list[Any], index: int) -> bool:
    """Whether the item after ``index`` is a wide repeat, so the item sits between two repeats."""
    if index + 1 >= len(data):
        return False
    op, argument = data[index + 1]
    return op in _REPEATS and _is_wide(argument[1])


class _Audit:
    """Walks a parsed pattern looking for shapes that make matching super linear."""

    def __init__(self, ignore_case: bool) -> None:
        self.ignore_case = ignore_case
        self.unbounded = 0

    def walk(
        self,
        items: Any,
        inside_wide: bool,
        inside_many: bool,
        follow: frozenset[str] | None,
        incoming: frozenset[str] | None = None,
    ) -> tuple[str | None, frozenset[str] | None]:
        """Audit a sequence.

        Args:
            items: the parsed sequence.
            inside_wide: it sits in a repeat that is unbounded or allows over 16 repetitions.
            inside_many: it sits in a repeat that allows more than one repetition.
            follow: the characters that can come right after the sequence, as ``_first``.
            incoming: the characters of a wide repeat that ends right before the sequence.

        Returns:
            The reason the sequence is unsafe, or None, and the characters of the wide
            repeat the sequence ends with, so that a group or an alternation does not hide
            an overlap with the repeat after it.
        """
        data = list(items.data)
        previous = incoming
        for index, (op, argument) in enumerate(data):
            after = _first(data[index + 1 :], self.ignore_case, follow)
            between = _wide_repeat_next(data, index)
            if op in _REPEATS:
                low, high, body = argument
                reason, previous = self._repeat(
                    low, high, body, previous, after, inside_wide, inside_many, between
                )
            else:
                reason, previous = self._other(
                    op, argument, inside_wide, inside_many, after, previous, between
                )
            if reason:
                return reason, previous
        return None, previous

    def _repeat(
        self,
        low: int,
        high: int,
        body: Any,
        previous: frozenset[str] | None,
        after: frozenset[str] | None,
        inside_wide: bool,
        inside_many: bool,
        between: bool = False,
    ) -> tuple[str | None, frozenset[str] | None]:
        unbounded = _is_unbounded(high)
        wide = _is_wide(high)
        if unbounded:
            self.unbounded += 1
            if self.unbounded > MAX_UNBOUNDED_REPEATS:
                return f"more than {MAX_UNBOUNDED_REPEATS} unbounded repeats", previous
        if inside_wide and (high > 1 or low == 0):
            return "nested quantifier", previous
        chars = None
        if len(body.data) == 1:
            node_op, node_argument = body.data[0]
            chars = _node_chars(node_op, node_argument, self.ignore_case)
        if inside_many and low != high and (after is None or chars is None or chars & after):
            return "nested quantifier without a delimiter", previous
        if wide and previous is not None and chars is not None and previous & chars:
            return "adjacent overlapping repeats", previous
        if wide:
            carried = chars
        elif low == 0 and previous is not None:
            # An optional item can be skipped, so the repeats on both sides can still touch.
            carried = previous | chars if chars is not None else previous
        elif between and chars is not None and previous is not None and previous & chars:
            # A fixed repeat of a character that the wide repeat before it can match does
            # not separate that repeat from the wide repeat after it.
            carried = previous
        else:
            carried = None
        inner_follow = after
        if high > 1:
            again = _first(list(body.data), self.ignore_case, None)
            inner_follow = None if again is None or after is None else again | after
        reason, _ = self.walk(body, inside_wide or wide, inside_many or high > 1, inner_follow)
        return reason, carried

    def _other(
        self,
        op: Any,
        argument: Any,
        inside_wide: bool,
        inside_many: bool,
        after: Any,
        previous: frozenset[str] | None,
        between: bool = False,
    ) -> tuple[str | None, frozenset[str] | None]:
        if op in _GROUPREFS:
            return "backreference", None
        if between and previous is not None:
            chars = _node_chars(op, argument, self.ignore_case)
            if chars is not None and previous & chars:
                # One character that the wide repeat before it can match is no delimiter, so
                # that repeat is carried forward to be compared with the one after it.
                return None, previous
        if op == _const.BRANCH:
            return self._branch(argument[1], inside_wide, inside_many, after, previous)
        if op == _const.SUBPATTERN:
            saved = self.ignore_case
            self.ignore_case = _scoped_case(saved, argument)
            try:
                return self.walk(argument[3], inside_wide, inside_many, after, previous)
            finally:
                self.ignore_case = saved
        if _ATOMIC is not None and op == _ATOMIC:
            return self.walk(argument, inside_wide, inside_many, after, previous)
        if op in (_const.ASSERT, _const.ASSERT_NOT):
            reason, _ = self.walk(argument[1], inside_wide, inside_many, None)
            return reason, None
        return None, None

    def _branch(
        self,
        branches: Any,
        inside_wide: bool,
        inside_many: bool,
        after: Any,
        previous: frozenset[str] | None,
    ) -> tuple[str | None, frozenset[str] | None]:
        if inside_wide:
            return "alternation inside a wide repeat", None
        if inside_many and self._overlap(branches, after):
            return "overlapping alternation inside a repeat", None
        trailing: set[str] = set()
        for branch in branches:
            reason, ends = self.walk(branch, inside_wide, inside_many, after, previous)
            if reason:
                return reason, None
            trailing |= ends or set()
        return None, frozenset(trailing) if trailing else None

    def _overlap(self, branches: Any, after: Any) -> bool:
        """Whether two branches can start with the same character, or both can be empty.

        A repeat of such an alternation can match the same text in many ways, so the work
        grows exponentially with the repetitions even when the repeat is narrow.
        """
        seen: frozenset[str] = frozenset()
        empty = False
        for branch in branches:
            if not branch.data:
                if empty:
                    return True
                empty = True
            start = _first(list(branch.data), self.ignore_case, after)
            if start is None or seen & start:
                return True
            seen |= start
        return False


def _parse(pattern: str, flags: int) -> Any:
    try:
        return _parser.parse(pattern, flags)
    except re.error:
        return None


def _ignores_case(parsed: Any, flags: int) -> bool:
    return bool((flags | parsed.state.flags) & re.IGNORECASE)


def unsafe_pattern_reason(pattern: str, flags: int = 0) -> str | None:
    """Return why ``pattern`` could be slow on hostile text, or None when it looks safe.

    A pattern is rejected for any of these shapes:

    - a nested quantifier: a repeat that is unbounded or allows more than 16 repetitions and
      contains an optional repeat or a repeat allowing more than one repetition, such as
      ``(a+)+``, ``(?:a?){28}`` or ``(?>(?:a+)+)``;
    - an alternation inside such a repeat;
    - an alternation inside any repeat that allows more than one repetition when two of its
      branches can start with the same character or both can be empty (``(?:a|a){0,16}``,
      ``(?:aa|a){0,16}``), because each repetition then has several ways to match;
    - a variable length repeat inside a repeat that allows more than one repetition, unless
      what can follow it cannot start with one of its own characters (``(?:a{1,2}){0,16}``
      is rejected, ``(?:[a-z]{1,63}\\.){0,8}`` is accepted);
    - more than 3 unbounded repeats, where a bound over 1024 counts as unbounded;
    - two adjacent wide repeats whose characters overlap (``a*a*``, ``.*.*``), also with
      optional items between them (``\\w*-?\\w*``), also when only case folding or a non
      ASCII character makes them overlap;
    - a backreference.

    ``flags`` are the flags the pattern will be compiled with, so that case folding is seen.
    A single unbounded repeat is accepted; see ``unbounded_repeat_warning``.
    """
    parsed = _parse(pattern, flags)
    if parsed is None:
        return None
    reason, _ = _Audit(_ignores_case(parsed, flags)).walk(parsed, False, False, frozenset())
    return reason


def _has_unbounded(items: Any) -> bool:
    for op, argument in items.data:
        if op in _REPEATS:
            if _is_unbounded(argument[1]) or _has_unbounded(argument[2]):
                return True
        elif op == _const.BRANCH:
            if any(_has_unbounded(branch) for branch in argument[1]):
                return True
        elif op == _const.SUBPATTERN:
            if _has_unbounded(argument[3]):
                return True
        elif op in (_const.ASSERT, _const.ASSERT_NOT):
            if _has_unbounded(argument[1]):
                return True
        elif _ATOMIC is not None and op == _ATOMIC and _has_unbounded(argument):
            return True
    return False


def unbounded_repeat_warning(pattern: str, flags: int = 0) -> str | None:
    """Return a warning when ``pattern`` holds an unbounded repeat, otherwise None.

    One unbounded repeat with free start positions (``[a-z]+;``), or one inside a lookahead
    (``(?=\\w*;)\\w``), is accepted by the audit but is quadratic on a long run of its own
    characters. It is reported so the author can bound it.
    """
    parsed = _parse(pattern, flags)
    if parsed is None or not _has_unbounded(parsed):
        return None
    return "has an unbounded repeat; on a long run of its characters it can take quadratic time"
