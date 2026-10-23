"""Exception types raised by guardline."""

from __future__ import annotations


class GuardlineError(Exception):
    """Base class for every error guardline raises on purpose."""


class RuleError(GuardlineError):
    """A rule file or a rule in it is invalid.

    Messages name the file and the rule id. They never contain an example or a
    matched value.
    """


class ConfigError(GuardlineError):
    """A guardline.toml or [tool.guardline] table is invalid."""
