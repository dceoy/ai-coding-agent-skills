---
name: commit-push-pr
description: Commit staged and unstaged changes, push the branch to origin, and open a pull request using the GitHub CLI. Use when the user asks to commit, push, and create a PR in one workflow.
allowed-tools: Bash(git checkout --branch:*), Bash(git add:*), Bash(git status:*), Bash(git push:*), Bash(git commit:*), Bash(gh pr create:*), Bash(gh repo view:*), Bash(git diff:*), Bash(git branch:*), Bash(git log:*)
---

# Commit, Push, and PR

Turn the current relevant work into a pull request.

1. Inspect status, diff, the current branch, recent commits, and the repository's default branch.
2. If there is nothing to commit, report that and stop.
3. If on the default branch, create an appropriately named branch following repository guidance.
4. Stage only relevant changes and create one concise commit in the repository's existing style.
5. Push the branch to `origin` with upstream tracking.
6. Open a pull request with `gh pr create`, following repository-specific PR guidance when present.

Preserve unrelated user changes and avoid unrelated cleanup or refactors. Report the resulting PR URL.
