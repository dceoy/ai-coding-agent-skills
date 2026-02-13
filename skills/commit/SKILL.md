---
name: commit
description: Create a git commit from current staged and unstaged changes with an appropriate commit message.
---

# Commit Skill

Stage and commit current changes with a concise, well-formed commit message based on the diff and recent commit history.

## When to Use

- After completing a change and wanting to commit it.
- When all modifications are ready to be captured in a single commit.

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
   git log --oneline -10
   ```

2. **Analyze changes** from the diff output to understand what was modified and why.

3. **Stage relevant files** using `git add` for the appropriate files.

4. **Create a commit** with a concise, descriptive message that:
   - Follows the repository's existing commit message style (based on recent commits).
   - Summarizes the nature of the change (new feature, bug fix, refactor, etc.).
   - Uses imperative mood and sentence case.

Stage and commit should be executed as efficiently as possible in a single step.

## Outputs

- A new git commit on the current branch.
- Console output confirming the commit was created.
