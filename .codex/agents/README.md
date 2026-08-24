# Codex custom subagents

These project-scoped TOML files are an optional Codex-specific native-subagent setup for the named-agent routing policy in `.codex/AGENTS.md`. Portable skills remain usable without these files, but Codex may map compatible logical roles onto the configured named agents before falling back to generic native independent subagents.

The repository defines four generic native read-only Codex roles:

- `planner`: defaults to `gpt-5.6-terra`, with `gpt-5.6-sol` escalation for materially complex planning; read-only. Produces a decision-complete implementation plan.
- `advisor`: defaults to `gpt-5.6-sol`; read-only. Provides on-demand technical advice or implementation review when an independent high-quality second opinion is materially useful.
- `reviewer`: model selection depends on the caller-supplied review lens; read-only. Reviews one caller-defined lens against an exact revision and returns evidence-based findings.
- `feedback-analyst`: defaults to `gpt-5.6-luna`, with `gpt-5.6-terra` escalation for materially ambiguous or code-reasoning-heavy triage; read-only. Analyzes review feedback into source-preserving dispositions, fix plans, verification guidance, and source actions.

These roles are not owned by any one skill. A portable workflow such as `pr-loop` may map its logical roles onto them when the contracts are compatible; other workflows may reuse the same agents. Implementation remains owned by the top-level main agent. There are no separate model-specific role definitions or implementation-worker roles.

## Design rationale

The architecture keeps model selection at dispatch time while preserving one write-capable implementation authority:

```text
planner ────────────────┐
reviewer ───────────────┼─→ top-level main implementation
feedback-analyst ───────┤
advisor (when useful) ──┘
```

The steady-state authority split is:

```text
planning authority          → planner
implementation authority    → top-level main agent
review authority            → reviewer when invoked
feedback-analysis authority → feedback-analyst when invoked
advisory authority          → advisor when invoked
```

Keeping implementation ownership in the top-level main-agent path avoids an additional write-capable handoff and preserves a single implementation authority. The top-level implementation session keeps the reasoning effort selected by the user or current session; this routing policy does not override it.

All named roles use fresh child contexts so correctness does not depend on inherited parent history. With MultiAgentV2, set `fork_turns: "none"`; with MultiAgentV1, use `fork_context: false` or omit `fork_context`. Pass task-specific context explicitly.

Invoke named roles only through Codex native multi-agent tools. Do not use nested `codex exec`, shell wrappers, copied prompts, generic-agent simulations, or child coding-agent CLI processes. Treat each TOML definition as authoritative for the configured role and requested sandbox default; model and reasoning effort are selected per native dispatch.

## Role-specific model and reasoning effort

The custom agent files intentionally omit both `model` and `model_reasoning_effort`; routing policy is expressed at dispatch time rather than as literal TOML defaults. Before every named-agent spawn, explicitly choose and pass the role-appropriate supported model and reasoning effort instead of relying on `[agents]` defaults or parent inheritance.

Model selection:

- `planner`: use `gpt-5.6-terra` by default. Escalate to `gpt-5.6-sol` when planning materially depends on architecture, public interfaces, schemas, migrations, security boundaries, broad cross-cutting behavior, or unusually regression-prone reasoning.
- `advisor`: use `gpt-5.6-sol` by default. The advisor should be invoked only when an independent second opinion materially improves decision quality, so its dispatch is intentionally quality-first rather than cost-first.
- `reviewer` with `correctness`: use `gpt-5.6-terra` by default; escalate to `gpt-5.6-sol` for complex state transitions, concurrency, large refactors, cross-component invariants, or similarly difficult correctness analysis.
- `reviewer` with `tests/docs`: use `gpt-5.6-luna` by default; escalate to `gpt-5.6-terra` when the verification surface, compatibility implications, or documentation behavior requires substantial code reasoning.
- `reviewer` with `security/performance`: use `gpt-5.6-terra` by default; escalate to `gpt-5.6-sol` for authentication, authorization, secrets, untrusted input, CI trust boundaries, privilege boundaries, concurrency, resource exhaustion, or similarly high-risk analysis.
- `feedback-analyst`: use `gpt-5.6-luna` by default; escalate to `gpt-5.6-terra` when feedback conflicts, root-cause grouping is ambiguous, or dispositions require non-trivial source-code reasoning. If the unresolved question instead requires architecture-level or other consequential judgment, consult `advisor` rather than turning feedback analysis into a general advisory role.

Reasoning-effort selection:

- `medium`: default for Luna dispatches whose work is bounded and structurally well-defined.
- `high`: default for Terra and Sol dispatches, and for Luna work escalated because additional reasoning is materially useful.
- `xhigh`: unusually demanding Terra or Sol work where deeper reasoning is expected to improve the result materially.
- `max`: only the hardest quality-first Sol work where maximum reasoning is materially useful.

Do not flatten these defaults into one model for every named-agent role. The purpose of the policy is to spend capability where judgment risk is highest while keeping repeated bounded review and triage work inexpensive. If native dispatch cannot accept the selected model override or rejects the selected model, do not silently inherit a different parent model; treat that named invocation as unsupported and let the caller follow its permitted fallback contract. The top-level main agent is outside this subagent policy, and its model and reasoning effort remain user- or session-selected.

## Role contracts

### Planner

Every planner dispatch should include:

```text
USER REQUEST
PRIOR DECISIONS
TASK CONTEXT
NON-NEGOTIABLE CONSTRAINTS
OPEN QUESTIONS
```

The planner returns `STATUS: ready` with a decision-complete contract or `STATUS: blocked` with the smallest missing material decision. It does not implement.

### Advisor

Use `advisor` for on-demand architecture, design, technical advice, or independent implementation review when a second opinion materially improves decision quality. Its verdict is advisory, not an approval gate, and it does not implement its own findings.

### Reviewer

`reviewer` is a generic terminal review leaf. The caller supplies one exact target revision plus one review lens or scope. The agent returns actionable findings with:

```text
LENS
SEVERITY
CONFIDENCE
FILE
LINE
IMPACT
REMEDIATION
```

If there are no actionable findings it returns `FINDINGS: none`. A workflow may dispatch multiple fresh reviewer invocations with different lenses.

### Feedback analyst

`feedback-analyst` is a generic terminal feedback-triage leaf. The caller supplies an exact target revision, the current feedback snapshot, stable source IDs, source metadata, constraints, and any caller-arbitrated findings. It returns one root-cause record per feedback item with:

```text
SOURCE_IDS
DISPOSITION
RATIONALE
EDIT_PLAN
VERIFICATION
REPLY_GUIDANCE
SOURCE_ACTIONS
DECISION_TERMINAL
```

Platform-specific state transitions remain owned by the caller; the agent does not publish, reply, resolve, dismiss, or mutate reviewer state.

## Named-agent mutation guard

For every named-agent invocation in a Git worktree, immediately before dispatch record a Git-visible baseline: `HEAD` when it exists (otherwise an explicit unborn-`HEAD` sentinel), index diff, tracked worktree diff, and every non-ignored untracked path with a content digest. Compare the same state immediately after return.

Any persistent Git-visible mutation introduced during the invocation invalidates the result; preserve changes that already existed in the baseline. If available runtime output or telemetry explicitly shows a mutating action, including a transient edit restored before return, invalidate the result even when the post-dispatch baseline matches. Ignored and generated files are intentionally outside the persistent-state comparison.

If the workspace is not a Git worktree, require an effective read-only sandbox; do not accept a writable effective sandbox without this guard. A broader effective sandbox such as `workspace-write` is not by itself a failure when the Git-visible mutation guard can be established. Named agents remain behaviorally read-only and must not intentionally edit files.

## Routing

Use the main agent directly for simple questions and narrow deterministic edits.

For ordinary non-trivial implementation, use `planner` when planning overhead is justified, implement directly in the top-level main agent, and invoke `advisor`, `reviewer`, or `feedback-analyst` only when the task or workflow contract calls for those read-only phases.

For `pr-loop` on Codex, map the skill's logical roles as follows whenever the configured named agent is available and compatible:

```text
planning          → planner
review            → reviewer
feedback-analysis → feedback-analyst
```

For each `review` attempt, dispatch a separate fresh `reviewer` invocation for each `pr-loop` lens: `correctness`, `tests/docs`, and `security/performance`, applying the lens-specific model defaults above. Pass the skill's exact source metadata and terminal-state constraints to `feedback-analyst`. Fall back to another native independent subagent only when the required named role is unavailable or incompatible. `advisor` remains a separate on-demand role rather than a substitute for these contracts.

All named agents are terminal leaves for their assigned role and must not spawn or delegate to another subagent.

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

Use regular-file copies; agent-definition symlinks may not be discovered. Remove obsolete `planner-sol.toml`, `advisor-sol.toml`, `worker-luna.toml`, `worker-terra.toml`, `pr-loop-reviewer.toml`, and `pr-loop-feedback-analyst.toml` from existing user-wide installations.

Start a fresh Codex session after installation and verify that native `planner`, `advisor`, `reviewer`, and `feedback-analyst` resolve from the expected definitions.
