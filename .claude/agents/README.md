# Claude Code custom subagent

`haiker.md` defines one low-cost Claude Code subagent for repository exploration and routine implementation work. It pins `model: haiku` while leaving architecture, ambiguous decisions, high-risk reasoning, and final validation with the parent model.

The companion `.claude/CLAUDE.md` routing policy tells the parent Claude Code session to prefer `haiker` over the built-in `Explore` agent for repository exploration when Haiku is adequate. The built-in agent remains available as a fallback; this setup does not deny `Agent(Explore)` globally.

## User-wide installation

Claude Code discovers personal subagents from `~/.claude/agents/` and personal instructions from `~/.claude/CLAUDE.md`.

Installing user-wide applies `haiker`'s `acceptEdits` permission mode and the CLAUDE.md routing preference to every repository you open afterward, including ones you have not vetted. If you want manual approval on edits, remove or change `permissionMode: acceptEdits` in your copy of `haiker.md`. If you want the routing preference scoped to specific repositories, install `.claude/agents/haiker.md` and `.claude/CLAUDE.md` per-project instead of user-wide. Note that `acceptEdits` is honored except when the parent session is in `auto` mode (ignored; the classifier reviews instead) or already in `bypassPermissions`/`acceptEdits` (the parent's mode takes precedence).

Because this worker can edit and write files with `acceptEdits`, remember that Claude Code's `/rewind` checkpoints do not restore edits made by subagents (see <https://code.claude.com/docs/en/checkpointing#subagent-edits-not-restored>) — revert unwanted `haiker` changes with your version control system (e.g. `git checkout` / `git restore`), not `/rewind`. This applies whether you install `haiker` user-wide or per-project.

From this repository, install the worker as a regular file (user-wide, shown below), or per-project with `cp .claude/agents/haiker.md <target-repo>/.claude/agents/haiker.md` and `cp .claude/CLAUDE.md <target-repo>/.claude/CLAUDE.md`:

```bash
mkdir -p "$HOME/.claude/agents"

if [ -e "$HOME/.claude/agents/haiker.md" ] || [ -L "$HOME/.claude/agents/haiker.md" ]; then
  printf 'Preserve and merge or remove %s before installation.\n' "$HOME/.claude/agents/haiker.md" >&2
else
  cp .claude/agents/haiker.md "$HOME/.claude/agents/haiker.md"
fi
```

Then install the routing policy without overwriting existing personal instructions:

```bash
if [ -e "$HOME/.claude/CLAUDE.md" ] || [ -L "$HOME/.claude/CLAUDE.md" ]; then
  printf 'Merge .claude/CLAUDE.md into the existing %s manually.\n' "$HOME/.claude/CLAUDE.md"
else
  cp .claude/CLAUDE.md "$HOME/.claude/CLAUDE.md"
fi
```

Start a new Claude Code session after installation so it picks up the newly installed `haiker` subagent and routing policy.

## Routing model

```text
main model
├── architecture / planning / ambiguous decisions / security-sensitive or high-risk trade-offs / difficult cross-cutting debugging / final validation
└── haiker
    ├── repository exploration and code search
    ├── routine decision-complete implementation
    ├── mechanical refactoring and focused debugging
    └── tests / lint / formatting / verification
```

The worker intentionally has no `Agent` tool, so delegated work remains a leaf rather than spawning additional subagents.
