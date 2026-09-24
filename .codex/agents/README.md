# Codex custom subagents

These optional project-scoped TOML files define four reusable native read-only Codex roles. `.codex/AGENTS.md` is the authoritative routing policy; portable skills remain usable without these definitions.

- `planner`: decision-complete implementation planning.
- `advisor`: on-demand technical advice or implementation review.
- `reviewer`: one caller-defined PR-review discovery or validation task against an exact revision.
- `feedback-analyst`: source-preserving feedback disposition and fix guidance.

Implementation remains owned by the top-level main agent. Named agents are fresh-context terminal leaves and must not modify files or dispatch another subagent.

## Model routing

The TOML files intentionally omit `model` and `model_reasoning_effort`; both are selected per native dispatch.

- `planner`: GPT-6 Sol by default → GPT-6 Astra only for the hardest plans when several architecture, public-interface, schema, migration, security-boundary, broad cross-cutting, or unusually regression-prone concerns interact, uncertainty remains, or design-error cost is unusually high.
- `advisor`: GPT-6 Sol by default → GPT-6 Astra for consequential architecture, security, cross-system, or similarly high-impact judgment.
- `reviewer`: GPT-6 Luna for lightweight docs/comments/narrow coverage; GPT-6 Sol for substantive correctness/errors/types/compatibility/simplification/performance reasoning and high-risk security, migration, concurrency, state, invariant, exhaustion, or scalability analysis; GPT-6 Astra only for the highest-risk or most cross-cutting reviews.
- `feedback-analyst`: GPT-6 Luna → GPT-6 Sol for ambiguous or code-reasoning-heavy triage; escalate consequential architecture-level judgment to `advisor`.

Astra is capability-gated: use it only when the native Codex model catalog or dispatch surface confirms `gpt-6-astra` support in the current environment. Otherwise remain on Sol with an appropriate Sol effort.

Effort is selected for the chosen model: Luna=`max`; Sol uses `xhigh` for routine planning, ordinary correctness/code-reasoning review, and ambiguous/code-heavy feedback triage, while `high` remains the default for advisor work and architecture/security/high-risk review bands; `max` is reserved for the hardest quality-first Sol work. Astra=`medium` by default with `high`, `xhigh`, or `max` available when stronger reasoning is justified. See `.codex/AGENTS.md` for the full criteria.

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
