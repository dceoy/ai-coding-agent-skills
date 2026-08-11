---
name: oracle-pr-review
description: Review a GitHub pull request in ChatGPT through Oracle browser mode by invoking the connected GitHub app with a fixed @GitHub Review prompt that prioritizes inline review comments. Use when the user explicitly wants a PR reviewed by ChatGPT via Oracle rather than by the current agent.
allowed-tools: Bash(oracle:*), Bash(which:*)
---

# Oracle PR Review

Use Oracle CLI browser mode to ask ChatGPT's connected GitHub app to review exactly one GitHub pull request.
This skill is intentionally a thin adapter: Oracle owns ChatGPT browser automation, and the GitHub app in
ChatGPT owns repository access and review context.

## Prerequisites

Before running the review, require all of the following:

- `oracle` is installed and available in `PATH`.
- Oracle browser mode can use an authenticated ChatGPT session.
- The ChatGPT GitHub app is connected and authorized for the target repository.
- The ChatGPT account exposes `GPT-5.6 Sol` to Oracle browser mode.

Check Oracle availability with:

```bash
which oracle
```

If Oracle is unavailable, report that prerequisite failure and stop. Do not silently substitute another
review path.

## Input

Accept either of these forms for exactly one pull request:

```text
OWNER/REPO#NUMBER
https://github.com/OWNER/REPO/pull/NUMBER
```

Normalize a GitHub PR URL to the canonical form:

```text
OWNER/REPO#NUMBER
```

Before constructing or running any Bash command, require the normalized target to match this pattern
exactly:

```regex
^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*$
```

Reject any non-matching target. In particular, never pass raw user-supplied text, query strings, whitespace,
newlines, shell metacharacters, or additional instructions into Bash. Reject ambiguous targets and multiple
PRs rather than trying to recover a target heuristically.

Do not fetch the pull request with `gh`, GitHub APIs, a local checkout, or another tool. Do not attach local
files to Oracle. The ChatGPT GitHub app is the only source of PR context for this skill.

## Execution

Construct the prompt mechanically from the validated canonical target using this fixed template:

```text
@GitHub Review OWNER/REPO#NUMBER. Prioritize inline review comments on the relevant changed lines whenever possible. Use a top-level review summary only for cross-cutting findings or findings that cannot be placed inline.
```

Substitute the validated canonical target directly into the single-quoted prompt literal; do not interpolate
an unvalidated shell variable or use `eval`.

```bash
oracle \
  --engine browser \
  --model gpt-5.6-sol \
  --browser-thinking-time high \
  -p '@GitHub Review OWNER/REPO#NUMBER. Prioritize inline review comments on the relevant changed lines whenever possible. Use a top-level review summary only for cross-cutting findings or findings that cannot be placed inline.'
```

Keep the prompt template exact apart from substituting the validated canonical target. Do not append
repository context, user prose, local diff content, or other instructions.

## Failure Policy

Fail closed when any required part of the intended path cannot be established:

- Do not fall back to Oracle API mode.
- Do not fall back to another model when `gpt-5.6-sol` cannot be selected.
- Do not fall back to `gh`, GitHub API retrieval, local diff review, or the current agent's own review.
- Do not retry with a modified prompt if ChatGPT treats `@GitHub` as plain text or cannot access the GitHub
  app or target repository.

If Oracle exits non-zero, report the failure. If Oracle returns a response showing that the GitHub app was
not invoked or lacked repository access, report that integration failure rather than treating the output as
a successful PR review.

## Output

Return the ChatGPT review produced by Oracle without rewriting its findings. Preserve the distinction
between a successful GitHub-app-backed review and an Oracle/browser/integration failure.
