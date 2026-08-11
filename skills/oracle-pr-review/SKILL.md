---
name: oracle-pr-review
description: Review a GitHub pull request in ChatGPT through Oracle browser mode by invoking the connected GitHub app with a fixed, title-prefixed @GitHub Review prompt that prioritizes inline review comments. Use when the user explicitly wants a PR reviewed by ChatGPT via Oracle rather than by the current agent; if no PR target is supplied, detect the pull request for the current branch automatically.
allowed-tools: Bash(gh:*), Bash(oracle:*), Bash(which:*)
---

# Oracle PR Review

Use Oracle CLI browser mode to ask ChatGPT's connected GitHub app to review exactly one GitHub pull request.
This skill is intentionally a thin adapter: Oracle owns ChatGPT browser automation and remote-host routing,
and the GitHub app in ChatGPT owns repository access and review context.

## Prerequisites

Before running the review, require all of the following:

- `oracle` is installed and available in `PATH`.
- Oracle browser mode can reach an authenticated ChatGPT session, either locally or through a configured
  Oracle remote browser service.
- The ChatGPT GitHub app is connected and authorized for the target repository in the ChatGPT session used
  by the browser host.
- The ChatGPT account exposes `GPT-5.6 Sol` to Oracle browser mode.
- When the user does not supply a PR target, `gh` is installed, authenticated, and running in a repository
  context whose current branch has an associated pull request.

Check Oracle availability with:

```bash
which oracle
```

If Oracle is unavailable, report that prerequisite failure and stop. Do not silently substitute another
review path.

## Remote Browser Service

Oracle natively reads `ORACLE_REMOTE_HOST` and `ORACLE_REMOTE_TOKEN` for browser remote-service routing.
Use the remote browser service only when both variables are configured. Keep the normal Oracle invocation
unchanged and let Oracle route it to the remote `oracle serve` host. Do not copy the token into
`--remote-token`, print it, or include it in the review prompt or logs.

```bash
export ORACLE_REMOTE_HOST='oracle-host.example:9473'
export ORACLE_REMOTE_TOKEN='<secret>'
```

Before invoking Oracle, inspect only whether these variables are set, without printing their values:

- If both are unset, use Oracle's normal local browser path.
- If both are set, use Oracle's native remote-service routing.
- If exactly one is set, report the partial remote configuration and stop rather than invoking Oracle.

Treat an invalid, unreachable, or unauthorized configured remote service as an Oracle failure; do not
silently fall back to the local browser path or another review path.

## Target Resolution

Resolve exactly one pull request using this precedence:

1. If the user supplies `OWNER/REPO#NUMBER`, use it.
2. If the user supplies `https://github.com/OWNER/REPO/pull/NUMBER`, normalize it to
   `OWNER/REPO#NUMBER`.
3. If the user supplies no owner, repository, or pull request number, detect all three from the pull request
   associated with the current branch:

   ```bash
   gh pr view --json url --jq .url
   ```

   Treat the command output only as PR identity metadata. Normalize the returned GitHub PR URL to
   `OWNER/REPO#NUMBER`.

Do not guess from issue text, branch names, commit messages, recent pull requests, or repository history. If
`gh pr view` cannot resolve exactly one pull request for the current branch, report that target detection
failed and stop rather than reviewing a different PR.

Before constructing or running any Oracle command, require the resolved canonical target to match this
pattern exactly:

```regex
^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*$
```

Reject any non-matching target. In particular, never pass raw user-supplied text, raw `gh` output, query
strings, whitespace, newlines, shell metacharacters, or additional instructions into the Oracle prompt.
Reject ambiguous targets and multiple PRs rather than trying to recover a target heuristically.

`gh` is permitted only for resolving PR identity when the user omitted owner, repository, and PR number. Do
not use `gh` to fetch or inspect the pull request diff, changed files, comments, reviews, checks, or repository
contents. Do not use GitHub APIs, a local checkout, or another tool to gather review context. Do not attach
local files to Oracle. The ChatGPT GitHub app is the only source of PR review context for this skill.

## Execution

Construct the prompt mechanically from the validated canonical target using this fixed template. Keep the
`PR Review:` title hint as the first line so the ChatGPT thread can be named from the PR identity:

```text
PR Review: OWNER/REPO#NUMBER
@GitHub Review OWNER/REPO#NUMBER. Prioritize inline review comments on the relevant changed lines whenever possible.
```

Substitute the same validated canonical target into both occurrences. Do not interpolate an unvalidated shell
variable or use `eval`.

```bash
oracle \
  --engine browser \
  --model gpt-5.6-sol \
  --browser-thinking-time high \
  -p 'PR Review: OWNER/REPO#NUMBER
@GitHub Review OWNER/REPO#NUMBER. Prioritize inline review comments on the relevant changed lines whenever possible.'
```

Do not add `--remote-host` or `--remote-token` when the corresponding environment variables are configured;
Oracle resolves them natively. Keep the prompt template exact apart from substituting the validated canonical
target. Do not append repository context, user prose, local diff content, or other instructions.

## Failure Policy

Fail closed when any required part of the intended path cannot be established:

- Do not fall back to Oracle API mode.
- Do not fall back to another model when `gpt-5.6-sol` cannot be selected.
- Do not invoke Oracle when exactly one of `ORACLE_REMOTE_HOST` or `ORACLE_REMOTE_TOKEN` is configured.
- Do not fall back from a configured but failing remote browser service to the local browser path or another
  review path.
- Do not choose another PR when automatic current-branch target detection fails.
- Do not fall back to `gh`/GitHub API review-context retrieval, local diff review, or the current agent's own
  review.
- Do not retry with a modified prompt if ChatGPT treats `@GitHub` as plain text or cannot access the GitHub
  app or target repository.

If Oracle exits non-zero, report the failure. If Oracle returns a response showing that the GitHub app was
not invoked or lacked repository access, report that integration failure rather than treating the output as
a successful PR review.

## Output

Return the ChatGPT review produced by Oracle without rewriting its findings. Preserve the distinction
between a successful GitHub-app-backed review and an Oracle/browser/integration failure.
