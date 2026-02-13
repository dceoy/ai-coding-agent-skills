---
name: commit-push-pr
description: Commit staged and unstaged changes, push the branch to origin, and open a pull request using the GitHub CLI.
---

# Commit, Push, and PR Skill

Create a commit from current changes, push to a remote branch, and open a pull request in a single workflow.

## When to Use

- After completing a feature or fix and wanting to open a PR in one step.
- When all changes are ready to commit, push, and submit for review.

## Agent Compatibility

This skill is tool-agnostic and can be executed by Claude Code, OpenAI Codex CLI, GitHub Copilot CLI, or Gemini CLI.

## Inputs

- Current repository with uncommitted changes (staged or unstaged).

If there are no changes to commit, report that and stop.

## Workflow

1. **Gather context** by running these commands in parallel:

   ```bash
   git status
   git diff HEAD
   git branch --show-current
   ```

2. **Create a new branch** if currently on `main` (or the repository's default branch). Use an appropriate branch name based on the changes.

3. **Stage and commit** all relevant changes with a concise, descriptive commit message summarizing the changes.

4. **Push the branch** to origin:

   ```bash
   git push -u origin <branch-name>
   ```

5. **Create a pull request** using the GitHub CLI:

   ```bash
   gh pr create --title "<title>" --body "<description>"
   ```

   Include a clear title and summary of changes in the PR body.

All steps should be executed as efficiently as possible, combining independent operations.

## Outputs

- A new git commit on the current or newly created branch.
- The branch pushed to origin.
- A pull request created on GitHub (URL printed to console).
