"""Data types shared by the rule loader, the engine and the entry points."""

from __future__ import annotations

import re
from dataclasses import dataclass

SCOPES = ("text", "args", "word")
"""How a rule is applied: to whole text, to a command's arguments, or to its words."""

BUILTIN_FAMILIES = ("attribution", "env-dump", "token")
"""The rule families that ship with the package."""

ENGINE_FAMILY = "engine"
"""The family of findings the engine itself reports, such as an input over the size limit."""


@dataclass(frozen=True)
class Rule:
    """One detection rule, loaded from a rule file.

    Attributes:
        id: unique kebab-case identifier, used to disable the rule.
        family: kebab-case group name, such as ``attribution``.
        description: one sentence saying what the rule catches.
        pattern: the regular expression source.
        scope: ``text``, ``args`` or ``word``.
        programs: for scope ``args``, the base names of the programs it applies to.
        value_options: for scope ``args``, options whose next word is a value and
            is dropped before matching.
        unless: an optional regular expression; when it matches, the rule does not fire.
        ignore_case: whether matching ignores case.
        example_fires: an input the rule must fire on.
        example_clean: a look-alike input the rule must not fire on.
        origin: where the rule came from, for messages.
    """

    id: str
    family: str
    description: str
    pattern: str
    scope: str
    programs: frozenset[str]
    value_options: frozenset[str]
    unless: str | None
    ignore_case: bool
    example_fires: str
    example_clean: str
    origin: str
    regex: re.Pattern[str]
    unless_regex: re.Pattern[str] | None


@dataclass(frozen=True)
class Finding:
    """One rule firing at one position. It never carries the matched text."""

    rule_id: str
    family: str
    description: str
    source: str
    offset: int
    line: int
    column: int

    def to_dict(self) -> dict[str, object]:
        """Return a JSON ready mapping of the finding."""
        return {
            "rule": self.rule_id,
            "family": self.family,
            "description": self.description,
            "source": self.source,
            "offset": self.offset,
            "line": self.line,
            "column": self.column,
        }

    def format_text(self) -> str:
        """Return the one line text form: ``source:line:column: rule [family] description``."""
        return (
            f"{self.source}:{self.line}:{self.column}: {self.rule_id} "
            f"[{self.family}] {self.description}"
        )
