---
name: clean-gone-branches
description: Remove local git branches whose configured upstream is marked [gone], including associated worktrees.
---

# Clean Gone Branches

Run the bundled `scripts/clean.sh` from this skill in the current repository.

Only branches explicitly marked `[gone]` may be deleted. Never delete the current branch or the repository's main worktree.

Report removed and skipped branches or worktrees. If none are `[gone]`, report that no cleanup was needed.
