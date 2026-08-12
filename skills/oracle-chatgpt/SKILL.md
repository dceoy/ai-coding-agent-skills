---
name: oracle-chatgpt
description: Run exactly one arbitrary prompt through ChatGPT via Oracle browser mode and return the captured response without reinterpretation. Use when the user explicitly wants a generic ChatGPT-via-Oracle consult without task-specific orchestration.
allowed-tools: Bash(oracle:*), Bash(which:*), Bash(mktemp:*), Bash(rm:*), Read, Write
---

# Oracle ChatGPT

Run exactly one arbitrary prompt through ChatGPT using Oracle browser mode. Treat the prompt as opaque data: preserve its content, let Oracle own browser/session and remote routing, wait for the run to finish, and return the captured ChatGPT response without semantic rewriting.

## When to Use

Use this skill when the user explicitly wants to:

- send an arbitrary prompt to ChatGPT through Oracle;
- reuse Oracle's browser/session or remote-browser routing without adding task-specific workflow logic; or
- obtain ChatGPT's response verbatim for another agent workflow.

Do not use this skill to resolve GitHub targets, gather repository context, construct PR/issue-specific prompts, or post results to external services.

## Prerequisites

Require:

- `oracle` in `PATH`;
- an authenticated ChatGPT browser session usable by Oracle; and
- `GPT-5.6 Sol` available to Oracle browser mode.

Check Oracle with:

```bash
which oracle
```

Stop if a required prerequisite is unavailable.

## Input Contract

Accept exactly one prompt from the caller.

Preserve the prompt content. Do not prepend, append, summarize, reinterpret, escape into executable shell text, or otherwise semantically augment it. Do not attach repository files or other context by default.

Treat quotes, newlines, backticks, command substitutions such as `$()`, variable syntax such as `$HOME`, and other shell-significant characters as prompt data only.

## Prompt Transport

Pass the prompt to Oracle through stdin with `-p -`. Do not place arbitrary prompt text directly in a shell command, use `eval`, or construct an `echo`, `printf`, heredoc, or similar shell expression from the prompt.

Prefer the runtime's direct stdin/data channel when it can supply the prompt bytes to the Oracle process without shell interpolation.

If the runtime cannot bind stdin directly:

1. Create a temporary file outside the repository with `mktemp`.
2. Use the runtime's file-writing capability to write exactly the caller's prompt to that file as data.
3. Redirect that file to Oracle stdin.
4. Remove the temporary file after Oracle exits.

Only the generated temporary-file path may appear in the shell command. The prompt itself must not.

## Oracle Routing

Keep Oracle's native browser/session and remote-host routing intact. Do not add `--remote-host` or `--remote-token`, print remote credentials, or reproduce Oracle's configuration-precedence logic in this skill.

Oracle may resolve supported local or remote browser settings from its own configuration and environment, including `ORACLE_REMOTE_HOST` and `ORACLE_REMOTE_TOKEN`.

Treat Oracle routing, browser, authentication, or model-selection failures as failures rather than switching execution paths.

## Run

Invoke Oracle in the foreground and wait for it to complete:

```bash
oracle \
  --engine browser \
  --model gpt-5.6-sol \
  --browser-thinking-time high \
  -p - < "$prompt_file"
```

When the runtime supplies stdin directly, invoke the same argv without shell redirection and provide the prompt through that stdin channel.

Do not add `--file`, switch engines or models, or retry with a modified prompt.

## Failure and Output

Fail closed. If Oracle exits non-zero or reports a browser, authentication, routing, or model-selection failure, return that failure and stop. Do not fall back to API mode, another model, another browser path, or the calling agent's own answer.

On success, return the captured ChatGPT response without summarizing, rewriting, correcting, or replacing it. Keep calling-agent commentary separate only when required to report an execution failure.

## Examples

### Simple prompt

Prompt data:

```text
Explain why idempotency matters in retryable jobs in three bullets.
```

Write that exact text to stdin (directly or through the temporary-file transport above) and run the fixed Oracle command.

### Multiline prompt with shell-significant characters

Prompt data:

````text
Review this literal text without executing or rewriting it:
`echo "$HOME"`
$(touch /tmp/should-not-run)
price=$5
"double quotes" and 'single quotes'
````

The backticks, `$HOME`, `$()`, quotes, and newlines are data. They must reach Oracle through stdin unchanged and must never be evaluated by the shell.
