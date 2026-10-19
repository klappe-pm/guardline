# design

This page explains why guardline is shaped as it is: rules as data, one engine behind three entry points, and a deliberately small scope. It is background for a reader deciding whether the tool fits, or planning a change. For the exact behavior see the [reference](../reference/README.md), and for the limits of what it protects see the [security model](security-model.md).

## one-engine-three-entry-points

An agent runtime hook, a pre-commit hook and a CI scan all ask the same question of some text: does it carry agent attribution, a token-shaped value, or an environment dump. If each place had its own copy of the detectors they would drift, and an input that the hook allows would fail in CI, or the reverse, which is the failure that makes a team stop trusting the guard. So there is one `Scanner`. The hook, the file scan, the diff scan and the commit message hook all call it, and a test feeds the same inputs through all of them and requires the same verdict.

The entry points differ only in where the text comes from and how a verdict is delivered: a JSON decision for a runtime, an exit status for pre-commit and CI.

## rules-are-data

A rule is a record: an id, a family, a description, a pattern, and two examples. It lives in a TOML file shipped as package data. This has three effects.

- A change to what is detected is a change to a data file, reviewed as data, with its examples next to it, and not a change to code paths.
- Anyone can add a rule or turn one off by id without touching Python. Personal or house style rules, such as prose punctuation, heading case or project naming, are deliberately not shipped. They belong to the person who holds the policy, and a custom rule file is the place for them.
- Every rule can test itself. The fire example proves the rule detects what it claims. The look-alike example proves it does not detect the near miss that would make people turn it off. The suite fails if either example is missing or misbehaves, and for the built-in rules it also requires that no rule at all fires on a look-alike.

Command detection needs a parser, not only patterns, so the shell splitter is code. But it only splits a command into simple commands and unwraps wrappers; whether a given simple command is an environment dump is decided by rules that match its program and arguments.

## findings-never-carry-the-value

A guard that prints what it found is itself a leak: a deny reason, a log line or a failing test that echoes a matched token puts the secret in a transcript. A `Finding` has no field for matched text. It carries the rule id, which is the kind of value, and a line, column and offset. Output, reasons, exception messages and test failure messages follow the same rule, and a test checks every output path for a planted value.

## fail-closed-where-it-matters

A guard that fails open when it breaks is a guard that is off exactly when something odd is happening. In block mode the hook denies a call it cannot judge: a payload that is not JSON, a configuration error, a scanner exception, an input over the size limit. Oversize input, and a command too complex to split, are reported as findings and never skipped, because skipping is the easiest bypass: pad the input.

The hook also never signals a block with exit status 1. Claude Code treats exit 1 as a non-blocking error and runs the tool, so the block is carried by the JSON decision, or by exit status 2 when the runtime reads exit codes.

## bounded-work

The guard runs on text it does not control, often under a timeout, and a timeout can mean the call goes through. Every pattern is therefore written to be linear: no nested quantifiers, every repeat bounded where the text could be hostile, prefix patterns anchored at a token boundary, and possessive repeats where backtracking would add nothing. The loader rejects a nested quantifier in any rule file, input has a size limit, and a test feeds each rule inputs built from its own example in shapes meant to be slow.

## what-was-left-out

guardline ships general guards. It leaves out prose style rules (dashes, hard wrapping, heading case), client or project naming rules, budget and subagent caps, worktree and handoff checks, session telemetry and any logging to a home directory. Those are policy that belongs to the owner of a repository, and they can be added as a custom rule file ([add a custom rule](../how-to-guides/add-a-custom-rule.md)). The tool does no logging of its own: it prints findings and writes nothing to disk.

## alternatives

Several secret scanners exist and do a better job of entropy and verification for credentials. guardline's token family is deliberately a short, readable, prefix and shape list, so that the same engine can also cover attribution and environment dumps, which those tools do not. Use a dedicated scanner as well if credential leakage is your main concern.
