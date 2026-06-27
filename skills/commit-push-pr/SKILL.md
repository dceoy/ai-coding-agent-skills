---
name: commit-push-pr
description: Commit staged and unstaged changes, push the branch to origin, and open a pull request using the GitHub CLI. Use when the user asks to commit, push, and create a PR in one workflow.
allowed-tools: Bash(git checkout --branch:*), Bash(git add:*), Bash(git status:*), Bash(git push:*), Bash(git commit:*), Bash(gh pr create:*)
---

# Commit, Push, and PR Skill

Create a commit from current changes, push to a remote branch, and open a pull request in a single workflow.

## When to Use

- After completing a feature or fix and wanting to open a PR in one step.
- When all changes are ready to commit, push, and submit for review.

## Agent Compatibility

This skill is tool-agnostic and can be executed by Claude Code, Codex CLI, or Cursor CLI.

## Inputs

- Current repository with uncommitted changes (staged or unstaged).

If there are no changes to commit, report that and stop.

Do not include unrelated user changes unless the user explicitly asked to include them.

## Workflow

1. **Gather context** by running these commands in parallel:

   ```bash
   git status
   git diff HEAD
   git branch --show-current
   ```

2. **Create a new branch** if currently on `main` (or the repository's default branch). Use an appropriate prefixed branch name based on the changes, following repository guidance such as `feature/...`, `bugfix/...`, `refactor/...`, `docs/...`, or `chore/...`.

3. **Stage and commit** all relevant changes with a concise, descriptive commit message summarizing the changes. Prefer explicit paths over `git add .` when unrelated changes are present.

4. **Push the branch** to origin:

   ```bash
   git push -u origin <branch-name>
   ```

5. **Create a pull request** using the GitHub CLI:

   ```bash
   gh pr create --title "<title>" --body "<description>"
   ```

   Include a clear title and summary of changes in the PR body. If repository guidelines request draft PRs or labels, apply them by default.

All steps should be executed efficiently once scope is clear. Do not perform unrelated cleanup or broad refactors while preparing the PR.

## Outputs

- A new git commit on the current or newly created branch.
- The branch pushed to origin.
- A pull request created on GitHub (URL printed to console).
