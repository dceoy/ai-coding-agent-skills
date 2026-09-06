# Codex custom subagents

These optional project-scoped TOML files define four reusable native read-only Codex roles. `.codex/AGENTS.md` is the authoritative routing policy; portable skills remain usable without these definitions.

- `planner`: decision-complete implementation planning.
- `advisor`: on-demand technical advice or implementation review.
- `reviewer`: one caller-defined review lens against an exact revision.
- `feedback-analyst`: source-preserving feedback disposition and fix guidance.

Implementation remains owned by the top-level main agent. Named agents are fresh-context terminal leaves and must not modify files or dispatch another subagent.

## Model routing

The TOML files intentionally omit `model` and `model_reasoning_effort`; both are selected per native dispatch.

- `planner`: Terra by default → Sol for architecture, public interfaces, schemas, migrations, security boundaries, broad cross-cutting behavior, or unusually regression-prone planning → Astra only for the hardest plans when several such concerns interact, uncertainty remains, or design-error cost is unusually high.
- `advisor`: Sol by default → Astra for consequential architecture, security, cross-system, or similarly high-impact judgment.
- `reviewer`: correctness=Terra, tests/docs=Luna, security/performance=Terra, other lenses/scopes=Terra; escalate to Sol per `.codex/AGENTS.md`, and to Astra only for the hardest or highest-risk cases covered by the authoritative routing policy.
- `feedback-analyst`: Luna → Terra for ambiguous or code-reasoning-heavy triage; escalate consequential architecture-level judgment to `advisor`.

Astra is capability-gated: use it only when the native Codex model catalog or dispatch surface confirms `gpt-6-astra` support in the current environment. Otherwise remain on Sol with an appropriate Sol effort.

Effort is selected for the chosen model: Luna=`max`; Terra=`xhigh` or `max`; Sol=`high`, `xhigh`, or `max`; Astra=`high`, `xhigh`, or `max`. See `.codex/AGENTS.md` for the default effort within each model and escalation criteria.

Invoke named roles only through Codex native multi-agent tools. With MultiAgentV2 use `fork_turns: "none"`; with MultiAgentV1 use `fork_context: false` or omit it. Pass task-specific context explicitly and apply the mutation guard defined in `.codex/AGENTS.md`.

## User-wide installation

Codex uses `$CODEX_HOME` when set and otherwise defaults to `$HOME/.codex`.

```bash
codex_home="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$codex_home/agents"

for file in .codex/agents/*.toml; do
  destination="$codex_home/agents/$(basename "$file")"
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    printf 'Preserve and merge or remove %s before installation.\n' "$destination" >&2
    exit 1
  fi
done

for file in .codex/agents/*.toml; do
  cp "$file" "$codex_home/agents/$(basename "$file")"
done

if [ -e "$codex_home/AGENTS.override.md" ] || [ -L "$codex_home/AGENTS.override.md" ]; then
  printf 'Merge .codex/AGENTS.md into the active AGENTS.override.md manually.\n'
elif [ -e "$codex_home/AGENTS.md" ] || [ -L "$codex_home/AGENTS.md" ]; then
  printf 'Merge .codex/AGENTS.md into the existing AGENTS.md manually.\n'
else
  cp .codex/AGENTS.md "$codex_home/AGENTS.md"
fi
```

Use regular-file copies; agent-definition symlinks may not be discovered.

Start a fresh Codex session after installation and verify that `planner`, `advisor`, `reviewer`, and `feedback-analyst` resolve from the expected definitions.
