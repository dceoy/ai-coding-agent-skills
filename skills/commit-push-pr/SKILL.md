---
name: commit-push-pr
description: Commit staged and unstaged changes, push the branch to origin, and open a pull request using the GitHub CLI. Use when the user asks to commit, push, and create a PR in one workflow.
allowed-tools: "Bash(git checkout -b:\u002A), Bash(git switch -c:\u002A), Bash(git add:\u002A), Bash(git status:\u002A), Bash(git push -u origin HEAD), Bash(git commit:\u002A), Bash(gh pr create:\u002A), Bash(gh repo view:\u002A), Bash(gh pr view:\u002A), Bash(git diff:\u002A), Bash(git branch:\u002A), Bash(git log:\u002A)"
---

# Commit, Push, and PR

Turn the current relevant work into a pull request.

1. Inspect status, diff, the current branch, recent commits, and the repository's default branch.
2. If there is nothing to commit, report that and stop.
3. If on the default branch, create an appropriately named branch following repository guidance.
4. Stage only relevant changes and create one concise commit in the repository's existing style. Do not stage secrets, credentials, or large generated artifacts.
5. Push with exactly `git push -u origin HEAD`. Never force-push.
6. If the branch already has an open PR (`gh pr view`), report its URL instead of creating another. Otherwise open a pull request with `gh pr create`, following repository-specific PR guidance when present.

If a commit hook or push fails, fix the cause or report it; do not bypass hooks (for example with `--no-verify`). The `git commit` pre-approval is a broad wildcard, so this is behavioral guidance rather than a permission-level guarantee; enforce it with a `PreToolUse` hook where it is a hard requirement. Preserve unrelated user changes and avoid unrelated cleanup or refactors. Report the resulting PR URL.
