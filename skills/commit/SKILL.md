---
name: commit
description: Create a single git commit from current staged and unstaged changes with an appropriate message. Use when the user asks to commit current work.
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git commit:*), Bash(git diff:*), Bash(git branch:*), Bash(git log:*)
---

# Commit

Create one commit for the current work.

- Inspect `git status`, `git diff HEAD`, the current branch, and recent commits.
- If there is nothing to commit, report that and stop.
- Stage only changes relevant to the requested work; preserve unrelated user changes.
- Follow the repository's recent commit style and use a concise message describing the change.

Do not run unrelated cleanup or tests, change branches, push, or create a PR unless requested separately.
