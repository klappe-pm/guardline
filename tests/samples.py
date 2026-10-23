"""Synthetic sample inputs, assembled from fragments.

The fragments are joined at run time so that no test file contains a complete
token-shaped value or a complete attribution line. Every value here is made up.
"""

from __future__ import annotations

AGENT = "Cl" + "aude"
VENDOR_HOST = "cl" + "aude.ai"
NOREPLY = "noreply@" + "anthropic" + ".com"

# A made up GitHub style token: prefix plus 36 filler characters.
FAKE_TOKEN = "gh" + "p_" + "Zq9Xk2" * 6
FAKE_AWS = "AK" + "IA" + "ABCDEFGHIJKLMNOP"
FAKE_JWT = "ey" + "Jhbgc" + "ioIx.ey" + "Jzdwii" + "OiIx.c2ln" + "bmF0dXJl"
FAKE_PEM = "-----BEGIN " + "RSA PRIVATE KEY" + "-----"

TRAILER = f"Co-Authored-By: {AGENT} <{NOREPLY}>"
FOOTER = f"Generated with {AGENT} Code"
PERMALINK = f"https://{VENDOR_HOST}/code/session_01AbCd"

COMMIT_WITH_TRAILER = f"fix: parser\n\nBody line.\n\n{TRAILER}\n"
CLEAN_COMMIT = "fix: parser\n\nBody line.\n\nCo-Authored-By: Dana Lee <dana@example.com>\n"

ENV_DUMP_COMMANDS = (
    "env",
    "env -i",
    "env -u HOME",
    "FOO=1 env",
    "/usr/bin/env",
    "printenv",
    "printenv API_KEY",
    "set",
    "export",
    "export -p",
    "declare -p",
    "declare -x",
    "typeset -p",
    "readonly",
    "git status && env",
    "echo a | printenv",
    "ls; set",
    "(env)",
    "{ env; }",
    'echo "$(printenv)"',
    "echo `env`",
    "x=$(env)",
    "diff <(env) /dev/null",
    'bash -c "env"',
    "bash -lc 'launchctl print system'",
    "sh -c 'ps eww'",
    'eval "set"',
    "ssh host env",
    "ssh -p 22 host -- printenv",
    "sudo -u root env",
    "sudo printenv",
    "env FOO=1 env",
    "env bash -c env",
    "env -S 'printenv'",
    "timeout 5 env",
    "nohup env",
    "xargs env",
    "find . -exec env ;",
    "docker exec web env",
    "docker compose exec web printenv",
    "kubectl exec pod -- env",
    "op run -- env",
    "cat /proc/1/environ",
    "tr '\\0' '\\n' < /proc/self/environ",
    "ps e",
    "ps aux e",
    "ps -E",
    "ps -axE",
    "docker inspect web",
    "docker container inspect web",
    "podman inspect web",
    "docker inspect --format '{{json .Config}}' web",
    "security find-generic-password -gs svc",
    "security find-internet-password -s host -w",
    "echo env | sh",
    "bash <<< printenv",
    "cat <<EOF | bash\nenv\nEOF",
    '"env"',
    "e''nv",
    "$'env'",
    "launchctl getenv PATH",
    "unterminated 'quote ; env",
)

ENV_SAFE_COMMANDS = (
    "env FOO=1 ls",
    "ls -la",
    "echo env",
    "grep set file.txt",
    "set -e",
    "export PATH=/usr/bin",
    "ps -e",
    "ps -ef",
    "ps -eo pid,command",
    "ps -u deploy",
    "docker ps",
    "docker inspect --format '{{.State.Status}}' web",
    "command -v env",
    "cat <<EOF\nset\nEOF",
    "git commit -m 'run env to check'",
    "echo 'x $(env)'",
    "launchctl list",
    "declare -a items",
    "readonly FOO=1",
    "cat /proc/1/status",
    "security find-generic-password -s svc",
    "env --version",
)
