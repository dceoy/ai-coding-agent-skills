# Claude Code custom subagent

`haiker.md` defines one low-cost Claude Code subagent for repository exploration and routine implementation work. It pins `model: haiku` while leaving architecture, ambiguous decisions, high-risk reasoning, and final validation with the parent model.

The companion `.claude/CLAUDE.md` routing policy tells the parent Claude Code session to prefer `haiker` over the built-in `Explore` agent for repository exploration when Haiku is adequate. The built-in agent remains available as a fallback; this setup does not deny `Agent(Explore)` globally.

## User-wide installation

Claude Code discovers personal subagents from `~/.claude/agents/` and personal instructions from `~/.claude/CLAUDE.md`.

From this repository, install the worker as a regular file:

```bash
mkdir -p "$HOME/.claude/agents"

if [ -e "$HOME/.claude/agents/haiker.md" ] || [ -L "$HOME/.claude/agents/haiker.md" ]; then
  printf 'Preserve and merge or remove %s before installation.\n' "$HOME/.claude/agents/haiker.md" >&2
  exit 1
fi

cp .claude/agents/haiker.md "$HOME/.claude/agents/haiker.md"
```

Then install the routing policy without overwriting existing personal instructions:

```bash
if [ -e "$HOME/.claude/CLAUDE.md" ] || [ -L "$HOME/.claude/CLAUDE.md" ]; then
  printf 'Merge .claude/CLAUDE.md into the existing %s manually.\n' "$HOME/.claude/CLAUDE.md"
else
  cp .claude/CLAUDE.md "$HOME/.claude/CLAUDE.md"
fi
```

A running Claude Code session watches existing `~/.claude/agents/` directories for changes. If the directory did not exist when the session started, start a fresh session after installation.

## Routing model

```text
main model
├── architecture / planning / ambiguous decisions / final validation
└── haiker
    ├── repository exploration and code search
    ├── routine decision-complete implementation
    ├── mechanical refactoring and focused debugging
    └── tests / lint / formatting / verification
```

The worker intentionally has no `Agent` tool, so delegated work remains a leaf rather than spawning additional subagents.
