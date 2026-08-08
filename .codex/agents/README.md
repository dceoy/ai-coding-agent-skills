# Codex custom subagents

These project-scoped TOML files define two native read-only Codex roles:

- `planner`: `gpt-5.6-sol`, `xhigh`, read-only. Produces a decision-complete implementation plan.
- `advisor`: `gpt-5.6-sol`, `xhigh`, read-only. Provides technical advice or final implementation review.

Implementation is performed directly by the top-level main agent. There are no dedicated Luna or Terra worker roles.

Invoke `planner` and `advisor` only through Codex native multi-agent tools. Do not use nested `codex exec`, shell wrappers, copied prompts, generic agents, or simulations. Invoke each role with `fork_turns: "none"` and pass its task-specific context explicitly. Treat these TOML definitions as authoritative for the configured role, model, reasoning effort, and sandbox defaults. A successful native dispatch to the requested named role is enough to proceed; do not require the runtime to echo configuration metadata that it may not expose. Report `unsupported` only when available runtime evidence explicitly shows a fallback, incompatible override, writable permission, inherited context contrary to the requested isolation, or unavailable native dispatch.

## Routing

Use the main agent directly for simple questions and narrow, deterministic edits.

For non-trivial implementation:

1. Invoke `planner` in a separate context with effective read-only permission. Accept its contract unless runtime evidence explicitly reports a fallback, incompatible override, writable permission, or inherited context contrary to `fork_turns: "none"`; missing runtime telemetry alone is not a failure.
2. Resolve material open decisions and approve the plan.
3. Pass the approved contract to a top-level implementation session configured with `model_reasoning_effort = "xhigh"`; otherwise restart with `xhigh` or report `unsupported`. Implement the plan directly in that session.
4. Inspect the actual changes and run the planned verification.
5. Invoke `advisor` in a fresh context with effective read-only permission, passing the planner contract, changed files or diff, implementation decisions, and verification results. Accept its verdict unless runtime evidence explicitly contradicts the configured role, model, reasoning effort, read-only permission, or fresh-context request.
6. Apply bounded `fix-first` findings in the main agent. For `rethink`, return to `planner` and approve a revised contract before reimplementation. An explicitly justified `unsupported` verdict blocks completion. Repeat verification and fresh review until `VERDICT: ship`.

The planner and advisor TOML files configure `model_reasoning_effort = "xhigh"` and read-only defaults. The top-level implementation session must be configured with `model_reasoning_effort = "xhigh"` separately, and runtime overrides must not weaken final-review isolation. Absence of parent-visible runtime attestation by itself must not stop the workflow.

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

Use regular-file copies; agent-definition symlinks may not be discovered. Remove obsolete `planner-sol.toml`, `advisor-sol.toml`, `worker-luna.toml`, and `worker-terra.toml` from existing user-wide installations.

Start a fresh Codex session after installation and verify that native `planner` and `advisor` resolve from the expected definitions.

## Usage

### Planning and implementation phase

```text
Use native planner with fork_turns set to none in a separate effectively read-only context, and supply the task-specific context explicitly. Produce a decision-complete plan for this task. Treat the installed planner definition as authoritative for gpt-5.6-sol, xhigh, and read-only defaults unless the runtime explicitly reports a fallback, incompatible override, writable permission, or inherited context contrary to fork_turns set to none. Do not require parent-visible configuration attestation. Resolve any blocking questions, then pass the approved contract to a top-level main-agent session configured with model_reasoning_effort = "xhigh". Do not delegate implementation to worker subagents. Run the planned verification and prepare the planner contract, actual changed files or diff, implementation decisions, and verification results for the mandatory final-review phase below. Do not report completion yet.
```

### Mandatory final review

```text
Use native advisor with fork_turns set to none in a fresh effectively read-only context. Treat the installed advisor definition as authoritative for gpt-5.6-sol, xhigh, and read-only defaults unless the runtime explicitly reports a fallback, incompatible override, writable permission, or inherited context. Do not require parent-visible configuration attestation. Review the planner contract, actual changes, implementation decisions, and verification results. Do not modify files. Return VERDICT: ship, fix-first, rethink, or unsupported. Report completion only after VERDICT: ship; apply fix-first findings and rerun verification and review, return rethink findings to planner for a revised approved contract, and treat explicitly justified unsupported as blocking.
```

### Advice only

```text
Use native advisor to evaluate this design. Return advice only and do not modify files.
```
