"""The ``guardline init`` command: choose a mode and rule families, then write the config.

The flow asks four questions: where to write the configuration, which mode to use,
which rule families to enable and which setup snippets to print. Every answer can come
from a command line flag instead, and ``--yes`` accepts the default for the rest. The
file is only written after the person has seen a diff of the change and confirmed it.
Existing configuration is never overwritten without ``--force``.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shlex
import shutil
import stat
import sys
import tempfile
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TypeVar

from guardline.config import MODES
from guardline.errors import ConfigError
from guardline.rules import builtin_rules

T = TypeVar("T")
TARGETS = ("guardline.toml", "pyproject.toml")
HOOKS = ("claude-code", "pre-commit", "none")
DEFAULT_MODE = "block"
MODE_HELP = {
    "block": "stops the action: a scan exits 1 and the agent hook denies the tool call",
    "report": "only prints findings: a scan exits 0 and the agent hook allows the tool call",
}
FAMILY_HELP = {
    "attribution": "credit to a coding agent or model in authored text",
    "env-dump": "shell commands that print the environment or a secret store",
    "token": "token-shaped values such as keys, tokens and private key blocks",
}
_TABLE_HEADER = re.compile(r"\s*\[\[?\s*[A-Za-z0-9_-]+(?:\s*\.\s*[A-Za-z0-9_-]+)*\s*\]\]?\s*(#.*)?")
_OWN_HEADER = re.compile(r"\s*\[\s*tool\s*\.\s*guardline\s*\]\s*(#.*)?")


def known_families() -> tuple[str, ...]:
    """Return the family names of the built-in rules, sorted."""
    return tuple(sorted({rule.family for rule in builtin_rules()}))


def parse_families(text: str) -> tuple[str, ...]:
    """Parse a comma separated family list, or ``all``, into canonical order.

    Raises:
        ConfigError: the list is empty or names an unknown family.
    """
    names = [part for part in re.split(r"[,\s]+", text.strip().lower()) if part]
    if not names:
        raise ConfigError("choose at least one family, or all")
    known = known_families()
    if names == ["all"]:
        return known
    unknown = sorted(set(names) - set(known))
    if unknown:
        raise ConfigError(
            f"unknown family: {', '.join(unknown)} (known: {', '.join(known)}, or all)"
        )
    return tuple(family for family in known if family in names)


def render_body(mode: str, families: tuple[str, ...]) -> str:
    """Return the configuration keys as TOML text.

    ``families`` is left out when every family is chosen, so a family added in a later
    release is not silently excluded.
    """
    lines = [f"mode = {json.dumps(mode)}"]
    if families != known_families():
        lines.append(f"families = {json.dumps(list(families))}")
    return "\n".join(lines) + "\n"


def expected_table(mode: str, families: tuple[str, ...]) -> dict[str, object]:
    """Return what the loader should read back from ``render_body(mode, families)``."""
    table: dict[str, object] = {"mode": mode}
    if families != known_families():
        table["families"] = list(families)
    return table


def _remove_own_table(text: str) -> str:
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if _OWN_HEADER.fullmatch(line.rstrip())), None)
    if start is None:
        return text
    end = next(
        (i for i in range(start + 1, len(lines)) if _TABLE_HEADER.fullmatch(lines[i].rstrip())),
        len(lines),
    )
    return "".join(lines[:start] + lines[end:])


@dataclass(frozen=True)
class Plan:
    """A file change ready to show and write.

    Attributes:
        path: the file to write.
        old: its current text, or None when the file does not exist.
        new: the text to write.
    """

    path: Path
    old: str | None
    new: str

    def diff(self) -> str:
        """Return a unified diff of the change."""
        old_lines = (self.old or "").splitlines(keepends=True)
        lines = difflib.unified_diff(
            old_lines,
            self.new.splitlines(keepends=True),
            fromfile="/dev/null" if self.old is None else str(self.path),
            tofile=str(self.path),
            n=1,
        )
        return "".join(line if line.endswith("\n") else line + "\n" for line in lines)


def write_plan(plan: Plan) -> None:
    """Write a planned change without following a link or losing a change made meanwhile.

    A new file is created exclusively and without following a link, so a file or link
    that appeared since the check makes the write fail. An existing file is read again
    and compared with the text the plan was built from, then replaced through a
    temporary file in the same directory, so a reader never sees a half written file and
    the mode of the original is kept.

    Raises:
        ConfigError: the target is now a link, appeared, or changed while the person was
            looking at the diff. Nothing is written.
    """
    path = plan.path
    if plan.old is None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags, 0o644)
        except FileExistsError:
            raise ConfigError(f"{path} appeared while init was running; nothing written") from None
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(plan.new)
        return
    try:
        current = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(current, "r", encoding="utf-8") as handle:
            now = handle.read()
            mode = stat.S_IMODE(os.fstat(handle.fileno()).st_mode)
    except (OSError, UnicodeDecodeError):
        raise ConfigError(f"{path} changed while init was running; nothing written") from None
    if now != plan.old:
        raise ConfigError(f"{path} changed while init was running; nothing written")
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".guardline-init-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(plan.new)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def inspect_target(directory: Path, target: str, *, force: bool) -> tuple[Path, str | None]:
    """Check that ``target`` can be written and return its path and current text.

    Raises:
        ConfigError: the target is a symbolic link, the target already holds
            configuration and ``force`` is off, a ``pyproject.toml`` target is missing or
            unreadable, or a ``guardline.toml`` beside it would override it.
    """
    path = directory / target
    if path.is_symlink():
        raise ConfigError(f"{path} is a symbolic link; refusing to write through it")
    if target == "guardline.toml":
        if path.exists() and not force:
            raise ConfigError(f"{path} already exists; use --force to replace it")
        return path, path.read_text(encoding="utf-8") if path.is_file() else None
    if (directory / "guardline.toml").exists():
        raise ConfigError(
            f"{directory / 'guardline.toml'} exists and takes precedence over pyproject.toml; "
            "choose --target guardline.toml"
        )
    if not path.is_file():
        raise ConfigError(f"{path} does not exist; choose --target guardline.toml")
    try:
        text = path.read_text(encoding="utf-8")
        document = tomllib.loads(text)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise ConfigError(f"{path}: cannot read as TOML; fix it first") from None
    tool = document.get("tool", {})
    if isinstance(tool, dict) and "guardline" in tool and not force:
        raise ConfigError(f"{path} already has a [tool.guardline] table; use --force to replace it")
    return path, text


def compose(path: Path, old: str | None, mode: str, families: tuple[str, ...], target: str) -> Plan:
    """Build the new file text for the chosen answers.

    Raises:
        ConfigError: the existing ``pyproject.toml`` cannot be edited safely.
    """
    body = render_body(mode, families)
    if target == "guardline.toml":
        return Plan(path, old, body)
    if old is None:
        raise ConfigError(f"{path}: the existing file was not read")
    kept = _remove_own_table(old).rstrip("\n")
    new = (kept + "\n\n" if kept else "") + "[tool.guardline]\n" + body
    try:
        parsed = tomllib.loads(new)
    except tomllib.TOMLDecodeError:
        parsed = {}
    tool = parsed.get("tool", {})
    if not isinstance(tool, dict) or tool.get("guardline") != expected_table(mode, families):
        raise ConfigError(
            f"{path}: cannot add [tool.guardline] safely (is it defined another way?); "
            "edit the file by hand or use --target guardline.toml"
        )
    return Plan(path, old, new)


def guardline_executable() -> tuple[str, bool]:
    """Find the absolute path of the ``guardline`` command that is running.

    Returns:
        The path and True, or the bare name and False when no absolute path was found.
    """
    sibling = Path(sys.executable).parent / "guardline"
    if sibling.is_file():
        return str(sibling), True
    found = shutil.which("guardline")
    if found:
        return str(Path(found).absolute()), True
    return "guardline", False


def hook_command(config_path: Path) -> tuple[str, bool]:
    """Return the agent hook command line that applies ``config_path``, and whether the
    command path is absolute."""
    executable, found = guardline_executable()
    return shlex.join([executable, "hook", "--config", str(config_path.resolve())]), found


def claude_code_snippet(command: str) -> str:
    """Return the Claude Code ``settings.json`` snippet for a hook command."""
    settings = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": command}]},
            ]
        }
    }
    return json.dumps(settings, indent=2) + "\n"


def pre_commit_snippet(mode: str) -> str:
    """Return the ``.pre-commit-config.yaml`` snippet for a mode."""
    args = "" if mode == "block" else "\n        args: [--mode, report, --]"
    return (
        "repos:\n"
        "  - repo: https://github.com/klappe-pm/guardline\n"
        "    rev: main\n"
        "    hooks:\n"
        f"      - id: guardline{args}\n"
        f"      - id: guardline-commit-msg{args}\n"
    )


def _ask(prompt: str, default: str, shown: str | None = None) -> str:
    try:
        answer = input(f"{prompt} [{shown or default}]: ")
    except EOFError:
        raise ConfigError("no input available; answer with flags or pass --yes") from None
    return answer.strip() or default


def _ask_valid(prompt: str, default: str, parse: Callable[[str], T], out: IO[str]) -> T:
    """Ask until ``parse`` accepts the answer; ``parse`` raises ConfigError to refuse."""
    while True:
        answer = _ask(prompt, default)
        try:
            return parse(answer)
        except ConfigError as error:
            out.write(f"  {error}\n")


def _parse_mode(text: str) -> str:
    mode = text.strip().lower()
    if mode not in MODES:
        raise ConfigError(f"choose one of: {', '.join(MODES)}")
    return mode


def _parse_target(text: str) -> str:
    target = text.strip().lower()
    if target not in TARGETS:
        raise ConfigError(f"choose one of: {', '.join(TARGETS)}")
    return target


def parse_hooks(values: list[str]) -> tuple[str, ...]:
    """Normalise hook choices: a list of snippet names, where ``none`` stands alone.

    Raises:
        ConfigError: ``none`` is mixed with another choice.
    """
    names = tuple(dict.fromkeys(values))
    if "none" in names and len(names) > 1:
        raise ConfigError("--hook none cannot be combined with another --hook")
    return tuple(name for name in names if name != "none")


def _parse_hook_answer(text: str) -> tuple[str, ...]:
    words = [w for w in re.split(r"[,\s]+", text.strip().lower()) if w]
    if words == ["both"]:
        words = ["claude-code", "pre-commit"]
    bad = sorted(set(words) - set(HOOKS))
    if bad or not words:
        raise ConfigError("choose claude-code, pre-commit, both or none")
    return parse_hooks(words)


def _explain_modes(out: IO[str]) -> None:
    out.write("Mode decides what happens when guardline finds something:\n")
    for mode in MODES[::-1]:
        out.write(f"  {mode}: {MODE_HELP[mode]}\n")


def _explain_families(out: IO[str]) -> None:
    counts = {f: sum(1 for r in builtin_rules() if r.family == f) for f in known_families()}
    out.write("Rule families:\n")
    for family in known_families():
        out.write(f"  {family} ({counts[family]} rules): {FAMILY_HELP.get(family, '')}\n")


def run_init(args: argparse.Namespace, out: IO[str], cwd: Path | None = None) -> int:
    """Run ``guardline init``. Returns the exit code.

    Raises:
        ConfigError: the answers are invalid, the target cannot be written, or input
            ran out in an interactive run.
    """
    directory = (cwd or Path.cwd()).resolve()
    yes: bool = args.yes
    has_pyproject = (directory / "pyproject.toml").is_file()
    hooks_given = parse_hooks(args.hook) if args.hook else None

    if args.target:
        target = args.target
    elif yes or not has_pyproject:
        target = "pyproject.toml" if has_pyproject else "guardline.toml"
    else:
        out.write("Where to write the configuration: guardline.toml or [tool.guardline].\n")
        target = _ask_valid("Target file", "pyproject.toml", _parse_target, out)
    path, old = inspect_target(directory, target, force=args.force)

    if args.mode:
        mode = args.mode
    elif yes:
        mode = DEFAULT_MODE
    else:
        _explain_modes(out)
        mode = _ask_valid("Mode", DEFAULT_MODE, _parse_mode, out)

    if args.families:
        families = parse_families(args.families)
    elif yes:
        families = known_families()
    else:
        _explain_families(out)
        families = _ask_valid(
            "Families to enable (comma separated, or all)", "all", parse_families, out
        )

    if hooks_given is not None:
        hooks = hooks_given
    elif yes:
        hooks = ()
    else:
        out.write("Setup snippets: claude-code, pre-commit, both or none.\n")
        hooks = _ask_valid("Print snippets for", "none", _parse_hook_answer, out)

    plan = compose(path, old, mode, families, target)
    out.write("\nThis change will be made:\n")
    out.write(plan.diff())
    if not yes and _ask("Write this?", "n", "y/N").lower() not in ("y", "yes"):
        out.write("Nothing written.\n")
        return 1
    write_plan(plan)
    out.write(f"\nWrote {path}\n")
    _print_snippets(out, hooks, path, mode, families)
    out.write("\nCheck what is active with: guardline config show\n")
    return 0


def has_text_rule(families: tuple[str, ...]) -> bool:
    """Whether a built-in rule of one of ``families`` judges file text."""
    return any(rule.scope == "text" and rule.family in families for rule in builtin_rules())


def _print_snippets(
    out: IO[str], hooks: tuple[str, ...], config: Path, mode: str, families: tuple[str, ...]
) -> None:
    if "claude-code" in hooks:
        command, found = hook_command(config)
        out.write(
            "\nClaude Code hook. Add this to ~/.claude/settings.json, or to .claude/settings.json "
            "in one project:\n\n"
        )
        out.write(claude_code_snippet(command))
        out.write(
            "\nThe hook never searches for configuration. An agent that can write files could "
            "otherwise create a guardline.toml that switches its own guard off. So the command "
            f"names your file with --config and an absolute path, and the hook takes mode {mode} "
            "and the families from it. Keep the file where the agent cannot write it, ideally "
            "outside the project; the hook denies edits made through the agent's edit tools, "
            "but not a shell command that writes the file.\n"
        )
        if not found:
            out.write(
                "The guardline command was not found on PATH, so replace the word guardline in "
                "the command with its absolute path.\n"
            )
    if "pre-commit" in hooks:
        out.write("\npre-commit. Add this to .pre-commit-config.yaml:\n\n")
        out.write(pre_commit_snippet(mode))
        if not has_text_rule(families):
            out.write(
                "\nWarning: the families you chose have no rule that judges text, and the "
                "pre-commit hooks scan file text, so they will stop with a configuration "
                "error. Add the attribution or token family to run them.\n"
            )
        if mode == "report":
            out.write(
                "\nThe hook entries already pass --mode block, and the last --mode on the "
                "command line wins, so report mode is set here with args. Keep the -- at the "
                "end: args replaces the hook's own, and the -- is what makes a staged file "
                "named like an option a file name.\n"
            )
        out.write(
            "\nThe scan hooks find your configuration by searching up from the repository, so "
            "the families you chose apply to them.\n"
        )
