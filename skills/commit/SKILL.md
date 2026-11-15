---
name: commit
description: Create a single git commit from current staged and unstaged changes with an appropriate message. Use when the user asks to commit current work.
allowed-tools: "Bash(git add:\u002A), Bash(git status:\u002A), Bash(git commit:\u002A), Bash(git diff:\u002A), Bash(git branch:\u002A), Bash(git log:\u002A)"
---

# Commit

Create one commit for the current work.

- Inspect `git status`, `git diff HEAD`, the current branch, and recent commits.
- If there is nothing to commit, report that and stop.
- Stage only changes relevant to the requested work; preserve unrelated user changes.
- Do not commit secrets, credentials, or large generated artifacts; warn about them instead.
- Follow the repository's recent commit style and use a concise message describing the change.

If a commit hook fails, fix the cause or report it; do not bypass hooks (for example with `--no-verify`). The `git commit` pre-approval is a broad wildcard, so this is behavioral guidance rather than a permission-level guarantee; enforce it with a `PreToolUse` hook where it is a hard requirement. Do not run unrelated cleanup or tests, change branches, push, or create a PR unless requested separately.
