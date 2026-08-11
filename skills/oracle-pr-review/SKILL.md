---
name: oracle-pr-review
description: Review one GitHub pull request through Oracle browser mode and ChatGPT's connected GitHub app, prioritizing inline review comments. Use when the user explicitly wants ChatGPT-via-Oracle review; if no PR target is supplied, detect the pull request for the current branch.
allowed-tools: Bash(gh:*), Bash(oracle:*), Bash(which:*)
---

# Oracle PR Review

Review exactly one GitHub pull request through Oracle browser mode. Oracle owns browser/session and remote-host
routing; ChatGPT's connected GitHub app owns repository access and review context. Do not duplicate either
responsibility in the current agent.

## Prerequisites

Require:

- `oracle` in `PATH` and an authenticated ChatGPT browser session.
- The ChatGPT GitHub app authorized for the target repository.
- `GPT-5.6 Sol` available to Oracle browser mode.
- `gh` only when the PR target must be detected from the current branch.

Check Oracle with:

```bash
which oracle
```

Stop if a required prerequisite is unavailable.

## Target

Accept exactly one of:

1. `OWNER/REPO#NUMBER`.
2. `https://github.com/OWNER/REPO/pull/NUMBER`, normalized to the canonical form above.
3. No explicit target, in which case resolve the current branch PR with:

   ```bash
   gh pr view --json url --jq .url
   ```

Normalize the result and require:

```regex
^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*$
```

Reject ambiguous or non-matching input. Never put raw user text, raw `gh` output, query strings, whitespace,
newlines, shell metacharacters, or extra instructions into the Oracle prompt.

Use `gh` only for PR identity when the target is omitted. Do not use `gh`, GitHub APIs, the local checkout, or
attachments to gather review context; the ChatGPT GitHub app is the sole review-context source.

## Oracle routing

Keep Oracle's native browser routing intact. Do not add `--remote-host` or `--remote-token`, print remote
credentials, or reproduce Oracle's configuration-precedence logic in this skill. Oracle may resolve remote
browser settings from its supported user configuration or `ORACLE_REMOTE_HOST` / `ORACLE_REMOTE_TOKEN`; when
no remote host resolves, it uses the local browser path.

Treat Oracle routing or authentication failures as failures rather than switching review paths.

## Run

Substitute the validated canonical target into the `OWNER/REPO#NUMBER` occurrence and run exactly:

```bash
oracle \
  --engine browser \
  --model gpt-5.6-sol \
  --browser-thinking-time high \
  -p '# PR: OWNER/REPO#NUMBER
@GitHub Review this pull request, prioritizing inline review comments on the relevant changed lines whenever possible.'
```

Do not interpolate an unvalidated shell variable, use `eval`, or append repository context or user prose.

## Failure and output

Fail closed: do not substitute Oracle API mode, another model, another PR, local/GitHub-API review context,
or the current agent's own review. Do not retry with a modified prompt if ChatGPT cannot invoke `@GitHub` or
access the target repository.

If Oracle exits non-zero or its response shows that the GitHub app was not invoked or lacked repository
access, report the failure. Otherwise return Oracle's ChatGPT review without rewriting its findings.
