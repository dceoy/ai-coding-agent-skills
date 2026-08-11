---
name: oracle-issue-plan
description: Generate a decision-complete pull request implementation plan for one GitHub issue through Oracle browser mode and ChatGPT's connected GitHub app.
allowed-tools: Bash(oracle:*), Bash(which:*)
---

# Oracle Issue Plan

Generate a decision-complete implementation plan for exactly one GitHub issue through Oracle browser mode. Oracle
owns browser/session and remote-host routing; ChatGPT's connected GitHub app owns issue and repository context. Do
not duplicate either responsibility in the current agent.

## Prerequisites

Require:

- `oracle` in `PATH` and an authenticated ChatGPT browser session.
- The ChatGPT GitHub app authorized for the target repository.
- `GPT-5.6 Sol` available to Oracle browser mode.

Check Oracle with:

```bash
which oracle
```

Stop if a required prerequisite is unavailable.

## Target

Accept exactly one of:

1. `OWNER/REPO#NUMBER`.
2. `https://github.com/OWNER/REPO/issues/NUMBER`, normalized to the canonical form above.

Normalize the result and require:

```regex
^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*$
```

Reject missing, ambiguous, or non-matching input. Never put raw user text, query strings, whitespace, newlines, shell
metacharacters, or extra instructions into the Oracle prompt.

Do not use `gh`, GitHub APIs, the local checkout, or attachments to gather issue or repository context; the ChatGPT
GitHub app is the sole context source.

## Oracle routing

Keep Oracle's native browser routing intact. Do not add `--remote-host` or `--remote-token`, print remote credentials,
or reproduce Oracle's configuration-precedence logic in this skill. Oracle may resolve remote browser settings from
its supported user configuration or `ORACLE_REMOTE_HOST` / `ORACLE_REMOTE_TOKEN`; when no remote host resolves, it
uses the local browser path.

Treat Oracle routing or authentication failures as failures rather than switching planning paths.

## Run

Substitute the validated canonical target into the `OWNER/REPO#NUMBER` occurrence and run exactly:

```bash
oracle \
  --engine browser \
  --model gpt-5.6-sol \
  --browser-thinking-time high \
  -p '# Issue: OWNER/REPO#NUMBER
@GitHub Analyze this issue, then produce a decision-complete implementation plan for a coding agent to resolve it in one pull request.'
```

Do not interpolate an unvalidated shell variable, use `eval`, or append repository context or user prose.

## Failure and output

Fail closed: do not substitute Oracle API mode, another model, another issue, local/GitHub-API context, or the current
agent's own analysis. Do not retry with a modified prompt if ChatGPT cannot invoke `@GitHub` or access the target
repository.

If Oracle exits non-zero or its response shows that the GitHub app was not invoked or lacked repository access, report
the failure. Otherwise return Oracle's implementation plan without rewriting it.
