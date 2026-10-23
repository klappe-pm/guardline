"""guardline: one detector library for coding agent guardrails.

The same rules run from an agent runtime hook, a pre-commit hook and a command
line scan, so a given input gets the same verdict from all three.
"""

from guardline.engine import Scanner, scan_command, scan_payload, scan_text
from guardline.errors import ConfigError, GuardlineError, RuleError
from guardline.model import Finding, Rule
from guardline.rules import builtin_rules, load_rule_file, verify_rule_examples

__version__ = "0.1.0"

__all__ = [
    "ConfigError",
    "Finding",
    "GuardlineError",
    "Rule",
    "RuleError",
    "Scanner",
    "__version__",
    "builtin_rules",
    "load_rule_file",
    "scan_command",
    "scan_payload",
    "scan_text",
    "verify_rule_examples",
]
