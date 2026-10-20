# Security Model

This page states what Guardline protects against, what it assumes, and what it does not stop, and every claim on it is one the code and the tests back. It is written to be read before you rely on the tool. The short version: Guardline is a set of heuristics that catches accidents and lazy bypasses. It is not a sandbox, it does not contain a hostile agent, and a person or program that wants to get past it can. Read the list of open gaps below before you decide what else you need.

## What Guardline Is for

Guardline helps in three situations that share one property: the content is produced by a cooperative but fallible author, usually a coding agent working from instructions, and a mistake is more likely than an attack.

- Authored text carries agent attribution that a policy forbids: a co-author trailer, a generated with footer, a session link, a robot byline.
- A shell command would print the whole environment, a process environment or a keychain secret into a transcript, where every live key then sits in a log.
- Text, or a command line, contains something shaped like a credential, about to be written to a file, a commit, a message or a shell history.

The goal in each case is to stop the accident before it lands, to say which rule fired and where, and to cost the author a retry rather than an incident.

## Threat Model

In scope:

- **Accidents.** The author did not notice the trailer, the dump command or the pasted token. Guardline catches the common forms.
- **Lazy bypasses.** The author reaches for a wrapper, a quoting trick or a substitution to get the same dump or footer past a plain string match. The shell lexer decodes quotes, backslashes, backslash-newline, `$'...'` escapes (hex, octal, unicode, concatenation) and `$"..."` before any word is judged, and the splitter looks through pipes, substitutions, heredocs, here-strings, function bodies and the wrappers in its table (`sudo`, `doas`, `env`, `nice`, `nohup`, `time`, `timeout`, `stdbuf`, `setsid`, `flock`, `strace`, `taskset`, `ionice`, `chrt`, `chroot`, `unshare`, `su -c`, `script -c`, `xargs`, `find -exec`, `watch`, `ssh`, `docker`, `podman`, `nerdctl` and the compose tools, `kubectl`, `op`, `busybox`, and the shells with `-c`), including their long options. Program names are matched in lower case.
- **The guarded agent editing its own guard.** The hook never discovers configuration, and it denies edits to Guardline configuration files made with the edit tools (see below).
- **Hostile input to the detector.** The text being scanned may be crafted to make the scanner slow or to crash it. Guardline bounds input size and work, uses linear patterns, audits rule file patterns, and fails closed in the hook.
- **Hostile paths and files named on the command line.** The hook's `--config` and `--rules` paths, and the rule files a configuration names, are read only if they are regular files of at most 1 MiB, opened without blocking, so a FIFO that never produces data cannot hang the hook past its timeout. Bytes that are not UTF-8 and deeply nested TOML become a configuration or rule file error, which the hook turns into a deny.
- **Leaking through the guard.** Findings, deny reasons, exception reports and logs carry rule ids and positions, never matched text, and never the key names of a rule file or of a tool input.

Out of scope:

- **A determined adversary.** Anyone who knows the rules can write around them. The open gaps below are examples, not a complete list.
- **Containment.** Guardline judges a tool call before it runs. It does not confine the tool, limit what the process can read, or inspect what a program does once it runs. Use an operating system sandbox, scoped credentials and network policy for that.
- **Secrets that do not look like secrets.** A password in prose, an internal hostname, a credential with no recognisable prefix or label, or a value that has been encoded, split or encrypted.
- **Reading secrets.** Reading a `.env` file or a credentials file is not an environment dump and is not detected.
- **Policy outside the three families.** Anything not covered by a rule is allowed.

## Trust Assumptions

- **The rule files are trusted code.** A rule is a regular expression run against untrusted text. The loader audits every pattern and `unless` expression and rejects nested quantifiers, optional repeats inside wide repeats, alternation inside wide repeats, more than 3 unbounded repeats, adjacent wide repeats whose characters overlap, and backreferences. It cannot prove an arbitrary expression is linear, so only load rule files you trust, and run `guardline rules check` on them.
- **The hook trusts only its command line.** `guardline hook` reads configuration only from an explicit `--config PATH`, and `rule_files` in that file must stay inside the file's directory. Put that file where the agent cannot write. The hook's command and the runtime settings that name it are trusted too: whoever can edit them can remove the hook.
- **`scan` and `diff` trust the tree they scan.** They discover `guardline.toml` or `[tool.guardline]` by walking up from the current directory, because a person runs them. A pull request that adds a configuration file can switch checks off for a scan run on its own checkout. In CI use `--config` with a file from the base branch, or `--no-config` with explicit flags.
- **The runtime delivers the payload.** The hook judges the payload it is given. If a runtime does not send a tool call through the hook, the call is not judged.
- **Guardline never executes the input.** The shell lexer reads a command; it never runs it and never expands a variable. It runs `git` only in `guardline diff`, with an argument list, no shell and no remote, with external diff programs and `textconv` filters switched off so that no configured filter can change the text being judged, and decodes the output with invalid bytes replaced.

## Protecting the Configuration

The hook ignores any configuration file it discovers, so an agent that writes `guardline.toml` or a `[tool.guardline]` table with `mode = "report"` or a long `disable` list changes nothing for the hook. As a second layer it denies a Write, Edit or MultiEdit (and NotebookEdit) whose target is any file named `guardline.toml`, a `pyproject.toml` whose new text or existing content mentions `tool.guardline`, the hook's own `--config` file or one of its `--rules` files, or a rule file that the `--config` file names in `rule_files`. The finding is `guardline-config-edit` and a person lifts it with `--allow-config-edit`. A shell command that writes such a file is not covered by this second layer, which is why the hook does not read discovered files at all.

## What Init Writes

`guardline init` writes into a directory that may be shared with an agent, so it does not trust the path it checked. It refuses a target that is a symbolic link, creates a new file with an exclusive, no-follow open, and replaces an existing file through a temporary file in the same directory after reading it again and comparing it with the text it showed in the diff. A file that appeared or changed while the person was deciding makes the command stop with exit 2 and write nothing. Between the second read and the rename there is still a small window that no portable call closes; the check narrows it, it does not remove it.

## Pre-Commit and File Names

A pre-commit hook receives file names the author chose, and a name can look like an option. The hook entries therefore end their options with `--` (the manifest's `args`) and pass `--no-stdin`, so a staged file called `--mode=report`, `--help`, `--family=env-dump` or `-` is a file to scan and cannot switch the scan to report mode, narrow its families, print help and exit 0, or turn into a read of standard input. A user's own `args` replace the manifest's, so the snippet from `guardline init` ends its `args` with `--` too. Every parser also refuses abbreviated option names, so a name that happens to start an option cannot be completed into one. The file hook matches `types: [file]` rather than `types: [text]`, because pre-commit's text tag leaves out a file with a NUL byte or a name like `.pdf`, and Guardline strips NUL and decodes with replacement precisely so that such a file is judged.

## How the Hook Fails

In block mode the hook denies when it cannot judge: no payload, a payload that is not JSON, a configuration or rule file error (a file that is not a regular file, is over 1 MiB, is not UTF-8 or is nested too deeply, and a configuration that leaves no active rule, such as `families = []` or a `disable` list that names every rule), a scanner exception, input over the size limit, a command that hit a parser limit, and a tool input that nests deeper than 16 levels or holds more than 2000 strings. Invalid bytes on standard input are replaced and the payload is still judged. It never uses exit status 1 for a block, because Claude Code treats that as a non-blocking error. In report mode every one of those only prints. Deny messages name rule ids, positions and exception class names; they never contain the input, a matched value, an exception message, or a key from a rule file.

## Regular Expression Denial of Service

A guard that can be made slow can be made to time out, and a hook that times out may let the call through. The mitigations are layered, and none is the only one:

- input over 1 MiB of text or 64 KiB of shell command is not scanned and is reported as a finding (the limits are configurable);
- the shell lexer shares a budget of 100000 tokens across a command and everything nested in it, stops at nesting depth 8 and at 5000 commands, and each of those limits yields a `guardline-command-too-complex` finding rather than silence;
- no built-in pattern fails the loader audit; prefix patterns start at a token boundary, repeats are bounded wherever the text can be hostile, and possessive repeats avoid backtracking;
- a tool input is walked to depth 16 and 2000 strings;
- a test feeds each rule inputs built from its own example in shapes meant to be slow, and feeds the whole scanner large adversarial text and commands, and requires each to finish within a fixed budget.

What this does not prove: the budget in the tests is generous so that it does not flake, and a slow machine with a 1 MiB input still takes seconds. Lower the limits in the configuration if the hook has a short timeout.

## What a Publishing Command Means

Attribution rules run on prose that gets published, not on every string in a command. For a shell command they judge the text of a publishing command only: `git commit`, `tag`, `notes`, `merge`, `commit-tree`, `revert` and `cherry-pick` (also as `git-commit` and the like), `gh pr`, `issue`, `release` and `gist` verbs that write, a `gh api` call with a body flag or a non-GET method, and `glab mr`, `issue` and `release`. The text is the decoded arguments, the value after `=` in an argument (so `--message=...` and `--body=...` count), text fed to the command by a here-string or by a piped `echo` or `printf` (escapes decoded), `echo` and `printf` output inside a substitution, and heredoc bodies. Token rules, by contrast, run over the whole command text and over the decoded words, because a credential anywhere on a command line is a leak.

## Known Open Gaps

These are cases a person would call a violation and Guardline does not flag. Each is pinned by a test, so this list and the behavior cannot drift apart. If you need one closed, it needs a control that Guardline is not, such as a sandbox or a review step.

### Environment Dumps

- **Another program prints the environment.** `python3 -c 'import os; print(os.environ)'`, `perl -e 'print %ENV'`, `awk 'BEGIN{for (k in ENVIRON) print k}'`, `ruby -e 'puts ENV.to_a'` and `node -p 'process.env'` are not detected. There are too many interpreters to list.
- **The command is built at run time.** A program name assembled from variables (`p=pri; q=ntenv; $p$q`), taken from a substitution (`$(echo env)` or backticks), from a default expansion (`${x:-env}`), or from a brace expansion (`{env,-0}`, `{printenv,HOME}`) is not seen, because the lexer does not expand anything. An encoded command piped to a shell (`echo cHJpbnRlbnY= | base64 -d | sh`) is the same case, and so is a path assembled in pieces.
- **Commands read from somewhere the lexer cannot see.** `bash <(echo env)` runs a process substitution whose output is a script, `echo env | xargs sh -c` and `echo printenv | xargs -I{} sh -c {}` feed commands to a shell through arguments or standard input at run time, and `sh ./dump-env.sh` runs a script Guardline did not read.
- **The dump is in a file.** A file written by one tool call and run by the next is judged only as text when it is written. Environment rules do not run on file content unless you scan it with `--shell`.
- **A name defined elsewhere.** An alias, a function or a shell startup file can define a command that dumps the environment.
- **Reading, not dumping.** Printing a single variable by name (`echo "$API_KEY"`) is not a dump. A `.env` or a credentials file read with `cat` is not detected.

### Attribution

- **Disguised vendor names.** A zero width character or a look-alike letter inside a name defeats the whole-word match.
- **Wording the rules do not know.** A footer without a known verb ("made using ..."), a vendor or agent name that is not in the list, or a trailer in another language.
- **Mid-sentence footers.** A footer must open its line or follow the end of a sentence. "This change was generated by a named agent" and "Note: generated with a named agent" are not footers to the rule, on purpose, because the same shape is an ordinary technical sentence.
- **Names that are also names.** A bare first name such as Jules is not in the list; only "Google Jules" and "Jules agent", "Jules bot" and "Jules AI" are. A person with that name is never a finding, and an agent that signs only "Jules" is not caught.
- **Publishing paths that are not listed.** `gh repo edit --description ...`, `gh label create --description ...`, `curl -X POST ... -d '...'` and every other tool that publishes text are not publishing commands to guardline. Only the list above is.
- **Git aliases and option forms.** `git -c alias.ci=commit ci -m ...` and `git --config-env a=B commit -m ...` hide the subcommand, so the command is not recognised as a commit.
- **Text that is not in the call.** `git commit -F message.txt` and `gh pr create --body-file body.md` publish text from a file, and Guardline does not open the file. A message held in a shell variable (`M='...'; git commit -m "$M"`) is not decoded either. Scan the file with `guardline scan` or the commit message hook.
- **Text written by a shell redirect.** `echo '...' >> notes.md` writes authored text, but it is not a publishing command. A file write tool is judged; a redirect is not.
- **Edits judged alone.** An edit is judged by its replacement text, not in the file it lands in, so attribution completed around existing text is not seen.
- **Fields it does not treat as text.** Attribution is judged in the authored text keys (`content`, `new_string`, `new_source`, `body`, `commit_message`, `message`, `title`, `description`, `text`) at any depth and in shell commands. A tool that carries authored text under another key is judged for tokens only.
- **The fenced switch.** With `--allow-fenced-attribution`, a closed fenced code block is exempt on purpose, and anything can be wrapped in a fence. The switch is per run for that reason and has no configuration key.

### Token-Shaped Values

- **Values split, encoded or separated.** A token split across lines, with a separator inserted, or base64 encoded is not matched. Shell quoting is decoded for commands, so `gh''p_...` is matched; this does not extend to text.
- **Formats not in the list.** A credential with no known prefix, label or shape is not found. The generic rules look for a key, token, secret or password name (optionally quoted) next to a long literal, or a long hex or base64 run next to such a word. A bare flag value such as `--token VALUE` is not matched unless the value has a known shape.
- **Headerless private keys.** The key rule matches the PEM or PGP header line. A body pasted without it is not matched.
- **False positives.** The generic rules fire on non-secrets that look the same: a long identifier assigned to a name that contains `key`, or a hash next to the word `token`. Disable the rule for a path or in the configuration when that happens.

### Structure

- **Positions are approximate for commands.** A command found inside `bash -c '...'` or a substitution is reported at the position of the enclosing command, and line continuations shift later offsets.
- **The lexer is not a shell.** Unusual syntax (some zsh and fish forms, aliases, options that change parsing) can be read differently from the way your shell reads it. On unbalanced quotes a lenient split is used, which can both miss and over-report.
- **Staged symbolic links are not handed to the pre-commit hook.** pre-commit tags a link `symlink` and not `file`, so the file hook skips it. `guardline diff --staged` reads the link's target text as an added line and covers it.
- **Nothing inside `.git` is scanned.** It is the one directory a scan never enters. Use `guardline diff` for history you are about to publish.
- **The hook cannot stop its own removal**, and does not cover a shell command that writes a configuration file; it ignores discovered configuration instead.

## Reporting

A bypass is not a vulnerability by default; a pull request with a rule and a test is the best report. A way to make Guardline print a matched value, run unbounded, change the hook's behavior from inside the project tree, or allow a call it should have blocked on its own failure is a vulnerability. See [SECURITY.md](../../SECURITY.md) for private reporting.
