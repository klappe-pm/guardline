# Rules

This page lists all 43 built-in rules, grouped by family: 9 attribution rules, 14 environment dump rules and 20 token-shaped value rules. Each row gives the rule id, which you use to disable it, the scope that says how it is applied, and what it catches. The authoritative definition of a rule is its entry in the rule files under `guardline/data/rules/`, and each entry carries the two examples that the tests run. Fields are explained in the [rule file format](rule-file-format.md).

A finding carries the rule id and a position and never the matched text. All patterns are heuristics; the [security model](../explanation/security-model.md) lists what they miss.

## Attribution

Attribution rules judge authored text: commit messages, pull request bodies, files and message fields. The agent and vendor names the trailer and footer rules recognise are Claude, Anthropic, Codex, OpenAI, ChatGPT, GPT followed by a digit, Copilot, Cursor, Devin, Gemini, Aider, Windsurf, Grok, Kiro, Cline, Google Jules, "Jules agent", "Jules bot", "Jules AI", "AI assistant", "AI agent" and LLM, matched as whole words. A bare first name such as Jules is not matched, so a person with that name is not a finding. White space is allowed between a trailer keyword and its colon. A trailer names an agent only in its name part, so a person's address at a vendor domain is not a trailer naming the vendor. A footer must open its line or follow the end of a sentence, so a technical mention inside a sentence ("files created by a tool") is not attribution.

| rule id | scope | what it catches |
| --- | --- | --- |
| `attribution-co-author-trailer` | text | A Co-Authored-By trailer whose name part names a coding agent or its vendor. |
| `attribution-assisted-by-trailer` | text | An Assisted-By or Generated-By trailer whose name part names a coding agent or its vendor. |
| `attribution-generated-with-footer` | text | A generated with, created by or written by footer or byline that names a coding agent. |
| `attribution-vendor-noreply-address` | text | A vendor noreply address, as used for an agent author identity. |
| `attribution-vendor-bot-noreply-address` | text | A GitHub bot noreply address for a coding agent account. |
| `attribution-session-permalink` | text | A link back to an agent chat or session transcript. |
| `attribution-session-trailer` | text | A session trailer line that carries an agent session reference. |
| `attribution-product-link` | text | A link whose text names an agent product and whose host is the vendor or the vendor's own repository landing page. |
| `attribution-robot-byline` | text | A robot emoji used as an authorship mark. |

The product link rule decides by host. A link to an issue, pull request, release or documentation path in a vendor's repository, and a link to a third party's page that merely names the product, are citations and pass. The `--allow-fenced-attribution` switch affects only this family.

## Env-Dump

Environment dump rules judge shell commands, one simple command at a time, after the splitter has looked through pipes, `&&`, `;`, newlines, subshells, `$(...)`, backticks, heredocs, here-strings and wrappers: `bash -c` and the other shells, `eval`, `env VAR=val cmd`, `env -S`, `sudo`, `doas`, `command`, `exec`, `nohup`, `time`, `nice`, `timeout`, `stdbuf`, `unbuffer`, `caffeinate`, `script`, `watch`, `xargs`, `find -exec`, `ssh host cmd`, `docker` and `podman` `exec` and `run`, `docker compose exec`, `kubectl exec --` and `op run --`.

| rule id | scope | what it catches |
| --- | --- | --- |
| `env-dump-env-no-command` | args | env with no command to run prints the whole environment. |
| `env-dump-printenv` | args | printenv prints environment values, with or without a name. |
| `env-dump-set-bare` | args | set with no arguments prints every shell variable. |
| `env-dump-export-listing` | args | export with no name, or export -p, lists every exported variable. |
| `env-dump-declare-print` | args | declare, typeset, readonly or local with -p prints variable definitions. |
| `env-dump-declare-no-name` | args | declare or typeset with only attribute flags lists variables. |
| `env-dump-readonly-no-name` | args | readonly or local with no name lists variables. |
| `env-dump-launchctl-print` | args | launchctl print, getenv, export, procinfo and dumpstate print launchd state and environment. |
| `env-dump-ps-environment-flag` | args | ps with -E in an option cluster prints each process environment. |
| `env-dump-ps-bsd-environment-word` | args | ps with a BSD style option word containing e (ps e, ps eww, ps aux e) prints each process environment. |
| `env-dump-proc-environ` | word | A reference to /proc/PID/environ, as an argument or a redirect target. |
| `env-dump-docker-inspect` | args | docker or podman inspect prints Env, unless a narrow format template selects neither Env, Config nor the whole object. |
| `env-dump-security-print-secret` | args | security find-generic-password or find-internet-password with -w or -g prints the secret. |
| `env-dump-security-dump-keychain` | args | security dump-keychain with -d prints secrets. |

On macOS `ps -e` is the same as `-A` (every process) and does not print environments, so `ps -e` and `ps -eo pid,command` pass, while `ps -E`, `ps e` and `ps eww` are findings. A command whose quotes are unbalanced is split leniently so that a broken quote cannot hide a command.

## Token

Token-shaped rules judge text, and also the whole text of a shell command, so a secret passed as an argument is found. A finding names the rule, which is the kind of value, and the position.

| rule id | scope | what it catches |
| --- | --- | --- |
| `token-private-key-block` | text | The header line of a PEM or PGP private key block. |
| `token-aws-access-key-id` | text | An AWS access key id (AKIA, ASIA or ABIA prefix). |
| `token-github-fine-grained-pat` | text | A GitHub fine-grained personal access token. |
| `token-github-token` | text | A GitHub personal, OAuth, user, server or refresh token. |
| `token-slack-token` | text | A Slack bot, app, user or refresh token. |
| `token-sk-style-key` | text | An sk- style API key (several providers use this prefix). |
| `token-google-api-key` | text | A Google API key. |
| `token-stripe-live-key` | text | A Stripe live secret or restricted key. |
| `token-gitlab-pat` | text | A GitLab personal access token. |
| `token-npm-token` | text | An npm access token. |
| `token-pypi-token` | text | A PyPI upload token. |
| `token-azure-storage-account-key` | text | An Azure storage connection string account key. |
| `token-huggingface-token` | text | A Hugging Face user access token. |
| `token-slack-app-token` | text | A Slack app level token. |
| `token-sendgrid-api-key` | text | A SendGrid API key. |
| `token-jwt` | text | A JSON web token: three dot separated base64url segments, the first starting with eyJ. |
| `token-bearer-token` | text | A Bearer credential of twenty or more token characters. |
| `token-generic-assignment` | text | A key, token, secret or password name assigned a literal of sixteen or more token characters. |
| `token-hex-run-near-keyword` | text | A hexadecimal run of thirty-two or more characters directly after the word key, token, secret or password. |
| `token-base64-run-near-keyword` | text | A mixed case base64 run of forty or more characters assigned to a name ending in key, token or secret. |

Prefix rules start at a token boundary and cap the length of the run they read, which keeps scan time linear. The generic assignment rule ignores a value that is a dotted chain of identifiers (`settings.env.api_key`) and a `secret://` reference, and does not fire when the value is followed by an opening parenthesis, which is a function call.

## Engine Findings

These findings come from the engine, not from a rule file, and cannot be disabled. They carry the family `engine`.

| id | meaning |
| --- | --- |
| `guardline-input-too-large` | the input is longer than the configured limit and was not scanned. The hook's deny reason repeats the finding's description, so it says which limit was hit. In the hook it is also raised when the string values of one tool input together, or its command values together, exceed the limit |
| `guardline-findings-truncated` | more than 1000 findings; the rest are not listed |
| `guardline-command-too-complex` | a shell command hit a parser limit (more than 100000 words across everything nested in it, nesting deeper than 8, or more than 5000 commands), or a tool input nests deeper than 16 levels or holds more than 2000 strings, so what was found is incomplete |
| `guardline-config-edit` | the hook saw a Write, Edit or MultiEdit to `guardline.toml`, to a pyproject.toml that holds or receives a `[tool.guardline]` table, or to the hook's own `--config` file, a `--rules` file or a rule file named by that config's `rule_files`; allowed only by `--allow-config-edit` |
| `guardline-file-skipped` | a directory scan met a symbolic link or special file and did not read it |
