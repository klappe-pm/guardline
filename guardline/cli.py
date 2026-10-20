"""The ``guardline`` command: hook, scan, diff, rules, init and config.

Exit codes: 0 means clean, or report mode; 1 means block mode found something;
2 means a usage, configuration or rule file error. The ``hook`` command is the one
exception to "1 blocks": it signals a deny with JSON on standard output and exit 0,
or with exit 2 under ``--deny-with exit-code``, because a runtime treats exit 1 as a
non blocking error.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import IO

from guardline import __version__
from guardline.config import (
    MODES,
    Config,
    build_scanner,
    discover_config,
    load_config_file,
)
from guardline.diffscan import git_diff, parse_added_lines, scan_added
from guardline.engine import Scanner
from guardline.errors import GuardlineError
from guardline.hook import run_hook, startup_failure
from guardline.initcmd import HOOKS, TARGETS, run_init
from guardline.model import Finding, Rule
from guardline.rules import builtin_rules, load_rule_file, merge_rules, verify_rule_examples

SKIP_DIRECTORIES = frozenset({".git"})
"""Directories a directory scan never enters. Every other exclusion is the user's choice."""
SCISSORS = re.compile(r"# -+ >8 -+[ \t]*")


def _common_parser() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parent.add_argument("--config", type=Path, help="read this guardline.toml or pyproject.toml")
    parent.add_argument("--no-config", action="store_true", help="ignore every configuration file")
    parent.add_argument("--mode", choices=("report", "block"), help="report exits 0, block exits 1")
    parent.add_argument("--disable", action="append", default=[], metavar="RULE_ID")
    parent.add_argument("--rules", action="append", default=[], type=Path, metavar="FILE")
    parent.add_argument("--family", action="append", default=[], metavar="NAME")
    parent.add_argument(
        "--allow-fenced-attribution",
        action="store_true",
        help="do not report attribution inside a closed fenced code block",
    )
    return parent


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``guardline`` command."""
    parser = argparse.ArgumentParser(
        prog="guardline", allow_abbrev=False, description=__doc__.split("\n")[0]
    )
    parser.add_argument("--version", action="version", version=f"guardline {__version__}")
    common = _common_parser()
    sub = parser.add_subparsers(dest="command", required=True)

    hook = sub.add_parser(
        "hook", parents=[common], allow_abbrev=False, help="judge a tool call payload on stdin"
    )
    hook.add_argument("--deny-with", choices=("json", "exit-code"), default="json")
    hook.add_argument(
        "--allow-config-edit",
        action="store_true",
        help="let the agent write guardline configuration files (a person's decision)",
    )

    scan = sub.add_parser(
        "scan", parents=[common], allow_abbrev=False, help="scan files, directories or stdin"
    )
    scan.add_argument("paths", nargs="*", type=str, help="files or directories; - reads stdin")
    scan.add_argument("--format", choices=("text", "json"), default="text")
    scan.add_argument("--shell", action="store_true", help="treat the input as shell commands")
    scan.add_argument(
        "--no-stdin",
        action="store_true",
        help="treat - as a file name and read standard input only when asked",
    )
    scan.add_argument(
        "--commit-msg",
        action="store_true",
        help="ignore the diff git appends after the scissors line of a commit message file",
    )

    diff = sub.add_parser(
        "diff", parents=[common], allow_abbrev=False, help="scan the lines a git diff adds"
    )
    diff.add_argument("--staged", action="store_true", help="scan the index, not the work tree")
    diff.add_argument("--base", help="compare against this revision")
    diff.add_argument("--repo", type=Path, default=Path("."), help="the repository directory")
    diff.add_argument("--format", choices=("text", "json"), default="text")
    diff.add_argument("paths", nargs="*", type=str)

    rules = sub.add_parser(
        "rules", parents=[common], allow_abbrev=False, help="list or check rules"
    )
    actions = rules.add_subparsers(dest="action", required=True)
    listing = actions.add_parser("list", allow_abbrev=False, help="list the active rules")
    listing.add_argument("--format", choices=("text", "json"), default="text")
    check = actions.add_parser(
        "check", allow_abbrev=False, help="validate rule files and run their examples"
    )
    check.add_argument(
        "files", nargs="*", type=Path, help="rule files; default is the built-in rules"
    )

    init = sub.add_parser(
        "init", allow_abbrev=False, help="choose a mode and rule families and write the config"
    )
    init.add_argument("--mode", choices=MODES, help="block stops the action, report only prints")
    init.add_argument("--families", help="comma separated families to enable, or all")
    init.add_argument("--target", choices=TARGETS, help="the file to write the configuration to")
    init.add_argument(
        "--hook",
        action="append",
        default=[],
        choices=HOOKS,
        help="print a setup snippet: claude-code or pre-commit; repeatable, or none",
    )
    init.add_argument("--yes", action="store_true", help="accept the default for every question")
    init.add_argument("--force", action="store_true", help="replace an existing configuration")

    config = sub.add_parser(
        "config", parents=[common], allow_abbrev=False, help="show the effective configuration"
    )
    config_actions = config.add_subparsers(dest="action", required=True)
    show = config_actions.add_parser(
        "show", allow_abbrev=False, help="print what is active and where it came from"
    )
    show.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _load_config(args: argparse.Namespace, start: Path, *, discover: bool) -> Config:
    if args.no_config:
        return Config()
    if args.config is not None:
        return load_config_file(args.config)
    return discover_config(start) if discover else Config()


def _setup(
    args: argparse.Namespace, start: Path | None = None, *, hook: bool = False
) -> tuple[Scanner, str, Config]:
    """Build the scanner. The hook never discovers configuration: only ``--config`` counts."""
    config = _load_config(args, start or Path.cwd(), discover=not hook)
    scanner = build_scanner(
        config,
        extra_rule_files=args.rules,
        extra_disable=args.disable,
        families=args.family,
        allow_fenced_attribution=args.allow_fenced_attribution,
        allow_config_edit=hook and args.allow_config_edit,
        protected_paths=(
            [str(path) for path in (args.config, *args.rules, *config.rule_files) if path]
            if hook
            else ()
        ),
    )
    mode = args.mode or config.mode or "block"
    return scanner, mode, config


def _emit(findings: Sequence[Finding], fmt: str, mode: str, out: IO[str]) -> None:
    if fmt == "json":
        document = {
            "version": 1,
            "mode": mode,
            "blocked": bool(findings) and mode == "block",
            "findings": [finding.to_dict() for finding in findings],
        }
        out.write(json.dumps(document, indent=2) + "\n")
        return
    for finding in findings:
        out.write(finding.format_text() + "\n")


def _exit_for(findings: Sequence[Finding], mode: str) -> int:
    return 1 if findings and mode == "block" else 0


def _walk(paths: Sequence[str], exclude: Sequence[str]) -> Iterator[tuple[Path, bool]]:
    """Yield (path, skipped). A skipped path is a symbolic link or special file in a directory."""
    for raw in paths:
        root = Path(raw)
        if root.is_dir() and not root.is_symlink():
            for current, directories, files in os.walk(root, followlinks=False):
                directories[:] = sorted(d for d in directories if d not in SKIP_DIRECTORIES)
                for name in sorted(files):
                    candidate = Path(current) / name
                    if _excluded(candidate, exclude):
                        continue
                    yield candidate, candidate.is_symlink() or not candidate.is_file()
        elif not _excluded(root, exclude):
            yield root, False


def _excluded(path: Path, patterns: Sequence[str]) -> bool:
    posix = path.as_posix()
    return any(fnmatch.fnmatch(posix, p) or fnmatch.fnmatch(path.name, p) for p in patterns)


def _read_text(path: Path, limit: int) -> tuple[str, bool]:
    """Return (text, too_large). Binary files are read too; NUL characters are dropped later."""
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        return "", True
    return data.decode("utf-8", errors="replace"), False


def _blank_after_scissors(text: str) -> str:
    """Blank the diff git appends after the scissors line, keeping offsets and line numbers.

    Comment lines above the scissors line are kept: git keeps them for ``-m`` and
    ``-F`` messages, so they are part of what is published.
    """
    out: list[str] = []
    cut = False
    for line in text.splitlines(keepends=True):
        cut = cut or bool(SCISSORS.fullmatch(line.rstrip("\r\n")))
        out.append(re.sub(r"[^\r\n]", " ", line) if cut else line)
    return "".join(out)


def _cmd_scan(args: argparse.Namespace, out: IO[str], err: IO[str]) -> int:
    scanner, mode, config = _setup(args)
    targets = list(args.paths) or ([] if args.no_stdin else ["-"])
    findings: list[Finding] = []

    def judge(text: str, source: str) -> list[Finding]:
        if args.commit_msg:
            text = _blank_after_scissors(text)
        return scanner.scan_command(text, source) if args.shell else scanner.scan_text(text, source)

    for target in targets:
        if target == "-" and not args.no_stdin:
            findings.extend(judge(_read_stdin(), "<stdin>"))
    files = [t for t in targets if t != "-" or args.no_stdin]
    for path, skipped in _walk(files, config.exclude):
        if skipped:
            findings.append(scanner.skipped_finding(str(path)))
            continue
        try:
            text, too_large = _read_text(path, scanner.max_text_chars)
        except OSError as error:
            err.write(f"guardline: cannot read {path}: {error.__class__.__name__}\n")
            return 2
        if too_large:
            findings.append(scanner.oversize_finding(str(path)))
        else:
            findings.extend(judge(text, str(path)))
    _emit(findings, args.format, mode, out)
    return _exit_for(findings, mode)


def _cmd_diff(args: argparse.Namespace, out: IO[str], err: IO[str]) -> int:
    scanner, mode, _ = _setup(args, args.repo)
    added = parse_added_lines(
        git_diff(args.repo, staged=args.staged, base=args.base, paths=args.paths)
    )
    findings = scan_added(scanner, added)
    _emit(findings, args.format, mode, out)
    return _exit_for(findings, mode)


def _read_stdin() -> str:
    """Read standard input as UTF-8, replacing bytes that are not valid, never raising on them."""
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is not None:
        return str(buffer.read().decode("utf-8", errors="replace"))
    return sys.stdin.read()


def _cmd_hook(args: argparse.Namespace, out: IO[str], err: IO[str]) -> int:
    try:
        scanner, mode, _ = _setup(args, hook=True)
        result = run_hook(_read_stdin(), scanner, mode=mode, deny_with=args.deny_with)
    except GuardlineError as error:
        message = f"configuration or rule file error ({error.__class__.__name__})"
        result = startup_failure(message, args.mode or "block", args.deny_with)
    except Exception as error:  # noqa: BLE001 - a hook that crashes must not fail open
        message = f"unexpected {error.__class__.__name__}"
        result = startup_failure(message, args.mode or "block", args.deny_with)
    out.write(result.stdout)
    err.write(result.stderr)
    return result.exit_code


def _cmd_rules(args: argparse.Namespace, out: IO[str], err: IO[str]) -> int:
    if args.action == "list":
        scanner, _, _ = _setup(args)
        rows = [r for r in scanner.rules]
        if args.format == "json":
            data = [_rule_dict(r) for r in rows]
            out.write(json.dumps(data, indent=2) + "\n")
        else:
            for rule in rows:
                out.write(f"{rule.id}\t{rule.family}\t{rule.scope}\t{rule.description}\n")
        return 0
    rules: tuple[Rule, ...] = builtin_rules()
    to_check: tuple[Rule, ...] = rules
    if args.files:
        loaded: list[Rule] = []
        for file in args.files:
            loaded.extend(load_rule_file(file))
        rules = merge_rules(rules, loaded)
        to_check = tuple(loaded)
    problems: list[str] = []
    for rule in to_check:
        problems.extend(verify_rule_examples(rule, rules))
    for problem in problems:
        err.write(problem + "\n")
    if problems:
        return 1
    out.write(f"ok: {len(to_check)} rule(s) validated\n")
    return 0


def _cmd_init(args: argparse.Namespace, out: IO[str], err: IO[str]) -> int:
    return run_init(args, out)


def effective_config(args: argparse.Namespace) -> dict[str, object]:
    """Describe the configuration the command line would use, and where each part came from."""
    scanner, mode, config = _setup(args)
    if args.no_config:
        source = "none (--no-config)"
    elif config.origin is not None:
        source = str(config.origin)
    else:
        source = "none (built-in defaults)"
    mode_source = "--mode" if args.mode else "config file" if config.mode else "default"
    return {
        "source": source,
        "mode": mode,
        "mode_source": mode_source,
        "families": sorted({rule.family for rule in scanner.rules}),
        "disabled_rules": sorted({*config.disable, *args.disable}),
        "rule_files": [str(path) for path in (*config.rule_files, *args.rules)],
        "exclude": list(config.exclude),
        "active_rules": len(scanner.rules),
    }


def _cmd_config(args: argparse.Namespace, out: IO[str], err: IO[str]) -> int:
    info = effective_config(args)
    if args.format == "json":
        out.write(json.dumps(info, indent=2) + "\n")
        return 0

    def line(label: str, value: object) -> None:
        shown = ", ".join(value) if isinstance(value, list) else value
        out.write(f"{label}: {shown or 'none'}\n")

    line("source", info["source"])
    out.write(f"mode: {info['mode']} ({info['mode_source']})\n")
    line("families", info["families"])
    line("disabled rules", info["disabled_rules"])
    line("rule files", info["rule_files"])
    line("exclude", info["exclude"])
    out.write(f"active rules: {info['active_rules']}\n")
    out.write("note: guardline hook reads only the file named by its --config option.\n")
    return 0


def _rule_dict(rule: Rule) -> dict[str, object]:
    return {
        "id": rule.id,
        "family": rule.family,
        "scope": rule.scope,
        "description": rule.description,
        "builtin": rule in builtin_rules(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    out, err = sys.stdout, sys.stderr
    handlers = {
        "hook": _cmd_hook,
        "scan": _cmd_scan,
        "diff": _cmd_diff,
        "rules": _cmd_rules,
        "init": _cmd_init,
        "config": _cmd_config,
    }
    try:
        return handlers[args.command](args, out, err)
    except GuardlineError as error:
        err.write(f"guardline: error: {error}\n")
        return 2
    except Exception as error:  # noqa: BLE001 - report, never traceback with input in it
        err.write(f"guardline: internal error ({error.__class__.__name__})\n")
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
