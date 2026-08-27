#!/usr/bin/env bash
set -euo pipefail

current_branch="$(git branch --show-current)"
main_worktree="$(
  git worktree list --porcelain |
    awk '$1 == "worktree" && main == "" { main = substr($0, 10) } END { print main }'
)"
found=false

while IFS=$'\t' read -r branch tracking; do
  [[ "$tracking" == "[gone]" ]] || continue
  found=true
  echo "Processing branch: $branch"

  if [[ "$branch" == "$current_branch" ]]; then
    echo "  Skipping current branch"
    continue
  fi

  worktree="$(
    git worktree list --porcelain |
      awk -v ref="refs/heads/$branch" '
        $1 == "worktree" { path = substr($0, 10) }
        $1 == "branch" && $2 == ref { found_path = path }
        END { if (found_path != "") print found_path }
      '
  )"

  if [[ -n "$worktree" ]]; then
    if [[ "$worktree" == "$main_worktree" ]]; then
      echo "  Skipping branch checked out in main worktree"
      continue
    fi
    echo "  Removing worktree: $worktree"
    git worktree remove --force "$worktree"
  fi

  echo "  Deleting branch: $branch"
  git branch -D -- "$branch"
done < <(git for-each-ref --format='%(refname:short)%09%(upstream:track)' refs/heads/)

if [[ "$found" == false ]]; then
  echo "No [gone] branches found."
fi
