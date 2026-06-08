---
name: clean-gone-branches
description: Clean up all git branches marked as [gone] (branches deleted on the remote but still existing locally), including removing associated worktrees.
---

# Clean Gone Branches Skill

Remove stale local branches that have been deleted from the remote repository, along with any associated worktrees.

## When to Use

- After merging and deleting remote branches, to clean up local tracking branches.
- When `git branch -v` shows branches marked as `[gone]`.
- Periodic local repository maintenance.

## Agent Compatibility

This skill is tool-agnostic and can be executed by Claude Code, OpenAI Codex CLI, GitHub Copilot CLI, or Gemini CLI.

## Inputs

- None required. The skill operates on the current git repository.

Before deleting anything, inspect the branch list and worktree list so the user can understand what will be removed.

## Workflow

1. **List branches** to identify any with `[gone]` status:

   ```bash
   git branch -v
   ```

   Branches with a `+` prefix have associated worktrees and must have their worktrees removed before deletion.

2. **List worktrees** that may need removal for `[gone]` branches:

   ```bash
   git worktree list
   ```

3. **Remove worktrees and delete `[gone]` branches**. Strip leading `+`, `*`, or spaces from `git branch -v` output before extracting branch names:

   ```bash
   git branch -v | grep '\[gone\]' | sed 's/^[+* ]//' | awk '{print $1}' | while read branch; do
     echo "Processing branch: $branch"
     worktree=$(git worktree list | grep "\\[$branch\\]" | awk '{print $1}')
     if [ -n "$worktree" ] && [ "$worktree" != "$(git rev-parse --show-toplevel)" ]; then
       echo "  Removing worktree: $worktree"
       git worktree remove --force "$worktree"
     fi
     echo "  Deleting branch: $branch"
     git branch -D "$branch"
   done
   ```

4. **Report results**: List which worktrees and branches were removed. If no branches are marked as `[gone]`, report that no cleanup was needed.

## Safety Notes

- Do not delete the current branch.
- Do not remove the repository's main worktree.
- Only delete branches shown by `git branch -v` as `[gone]`; do not infer stale branches by name.

## Outputs

- Console output listing removed worktrees and deleted branches.
- If no `[gone]` branches exist, a message indicating no cleanup was needed.
