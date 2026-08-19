# Codex custom subagents

These project-scoped TOML files are an optional, Codex-specific native-subagent routing setup for the default `planner`/`advisor` workflow described in the repository-root `AGENTS.md`. Portable skills such as `pr-loop` (`skills/pr-loop/SKILL.md`) do not require them and instead dispatch their own logical subagent roles through whichever native independent-subagent mechanism the active runtime provides.

These project-scoped TOML files define two native read-only Codex roles:

- `planner`: `gpt-5.6-sol`, adaptive reasoning effort, read-only. Produces a decision-complete implementation plan.
- `advisor`: `gpt-5.6-sol`, adaptive reasoning effort, read-only. Provides on-demand technical advice or implementation review.

Implementation is performed directly by the top-level main agent. There are no dedicated Luna or Terra worker roles.

## Design rationale

This layout is intentionally OpusPlan-inspired: high-capability read-only subagents provide planning and optional advisory boundaries around implementation, not generic implementation workers.

```text
Claude Code
Opus planning → Sonnet implementation
                   ↕ when useful
                Opus advisor

Codex
Sol planning → top-level main implementation (Terra-class, not a worker role)
                   ↕ when useful
                Sol advisor
```

The steady-state authority split is:

```text
planning authority        → Sol planner
implementation authority  → top-level main agent
advisory authority        → Sol advisor when invoked
```

Keeping implementation ownership in the top-level main-agent path avoids an additional write-capable subagent handoff and preserves a single implementation authority. The top-level implementation session keeps the reasoning effort selected by the user or current session; this routing policy does not override it. The approved planner contract remains the implementation contract. The former `worker_luna` and `worker_terra` roles were therefore removed intentionally and should not be restored by default.

Both named roles use fresh child contexts so the routing has one semantic isolation contract across native runtimes. With MultiAgentV2, set `fork_turns: "none"`; with MultiAgentV1, use `fork_context: false` or omit `fork_context`. Planner correctness comes from an explicit context packet rather than inherited parent history. Advisor independence comes from a fresh context that reviews task-specific primary evidence instead of inheriting the parent agent's conclusions.

If future measurements justify parallelism, prefer bounded read-only investigation roles such as dependency, test, security, or compatibility scouts. Do not introduce write-capable implementation workers into the default architecture unless empirical results show that the added orchestration and context-transfer cost is worthwhile.

Invoke `planner` and `advisor` only through Codex native multi-agent tools. Do not use nested `codex exec`, shell wrappers, copied prompts, generic agents, or simulations. Invoke both roles with a fresh child context using the active native runtime's isolation parameter and pass each role the task-specific context it needs explicitly. Treat these TOML definitions as authoritative for the configured role, model, and requested sandbox default. Their reasoning effort is intentionally unpinned and must be selected explicitly per native dispatch using the adaptive policy below. A successful native dispatch to the requested named role is enough to proceed; do not require the runtime to echo configuration metadata that it may not expose. A broader effective sandbox such as `workspace-write` does not by itself invalidate the invocation when the named-agent mutation guard below can be established: the named agents must remain behaviorally read-only and must not modify files. Report `unsupported` only when available runtime evidence explicitly shows a generic/different-agent fallback, incompatible model override, failure to honor an explicitly requested per-dispatch reasoning effort or fresh-context isolation, unavailable native named-role dispatch, or a writable invocation outside a Git worktree.

### Adaptive reasoning effort

The custom agent files intentionally omit `model_reasoning_effort`; `adaptive` is a routing policy, not a literal TOML effort value. Before every `planner` or `advisor` spawn, explicitly choose and pass the lowest adequate supported effort instead of relying on `[agents]` defaults or parent-effort inheritance:

- `medium`: routine non-trivial planning or review.
- `high`: complex, cross-cutting, security-sensitive, or regression-prone work.
- `xhigh`: unusually demanding work where additional reasoning is materially useful.

Do not default every named-agent dispatch to `xhigh`. The top-level main agent is outside this adaptive subagent policy, and its reasoning effort remains user- or session-selected.

### Planner context handoff

Every planner dispatch must include this minimum context packet so planning does not depend on inherited conversation history:

```text
USER REQUEST
- Preserve the user's actual request with minimal paraphrasing.
- Prefer verbatim wording when practical.

PRIOR DECISIONS
- Decisions already settled with the user.
- Do not reopen them without a concrete conflict or new evidence.

TASK CONTEXT
- Relevant repository state, existing implementation, and architecture.

NON-NEGOTIABLE CONSTRAINTS
- User/project constraints, compatibility, security, migration, operational requirements, and explicit exclusions.

OPEN QUESTIONS
- Only genuinely unresolved material decisions.
```

The planner should not need to reconstruct or guess user intent from an implementation-oriented summary. Keep settled decisions in `PRIOR DECISIONS` and genuinely unresolved decisions in `OPEN QUESTIONS`. Treat the explicit packet as authoritative; the fresh child context ensures the planner does not depend on parent-history inheritance.

### Named-agent mutation guard

For every `planner` or `advisor` invocation in a Git worktree, immediately before dispatch record a Git-visible baseline: `HEAD` when it exists (otherwise an explicit unborn-`HEAD` sentinel), index diff, tracked worktree diff, and every non-ignored untracked path with a content digest. Compare the same state immediately after return. Any persistent Git-visible mutation introduced during the invocation invalidates the result; preserve changes that already existed in the baseline. If available runtime output or telemetry explicitly shows a mutating action, including a transient edit that was restored before return, invalidate the result even when the post-dispatch baseline matches. Ignored and generated files are intentionally outside the persistent-state comparison. If the workspace is not a Git worktree, require an effective read-only sandbox; do not accept a writable effective sandbox without this guard. This guard establishes persistent Git-visible state integrity; it does not prove that a writable runtime performed no transient writes. The named agents remain behaviorally read-only and must not intentionally edit files. Do not describe this guard as runtime-enforced read-only or mutation-free execution.

## Routing

Use the main agent directly for simple questions and narrow, deterministic edits.

For non-trivial implementation:

1. Apply the named-agent mutation guard, select and pass the planner reasoning effort according to the adaptive policy above, then invoke the configured `planner` in a fresh behaviorally read-only child context: use `fork_turns: "none"` with MultiAgentV2, or `fork_context: false`/omitted with MultiAgentV1. Supply `USER REQUEST`, `PRIOR DECISIONS`, `TASK CONTEXT`, `NON-NEGOTIABLE CONSTRAINTS`, and `OPEN QUESTIONS`. Prefer its configured read-only sandbox, but accept its contract unless runtime evidence explicitly reports a generic/different-agent fallback, incompatible model override, failure to honor the explicitly requested reasoning effort or fresh-context isolation, or a writable invocation outside a Git worktree; missing runtime telemetry, an adaptively selected reasoning effort, or a writable effective sandbox alone is not a failure when the guard can be established.
2. Route the planner result. For `STATUS: blocked`, obtain the smallest missing user decision and replan. For `STATUS: ready`, preserve already-settled decisions. Ask the user only when the contract introduces or changes an unresolved material decision about observable product behavior, API/compatibility guarantees, meaningful architectural trade-offs, destructive migration, security posture, significant scope, or new requirements. The main agent may approve tactical implementation details internally when they remain within the established contract.
3. Pass the approved contract to the top-level main agent and implement the plan directly without changing the reasoning effort selected by the user or current session.
4. Inspect the actual changes and run the planned verification.
5. Invoke `advisor` only when an independent second opinion materially improves decision quality or confidence. Appropriate triggers include an explicit user request; unresolved architecture, security, API, compatibility, migration, or other cross-cutting trade-offs; multiple plausible approaches with meaningful consequences; uncertain diagnosis after verification failures; or a high-risk/regression-prone implementation where independent review is warranted. Skip advisor for routine, low-risk changes when the main agent can validate the result directly.
6. When `advisor` is invoked, apply the named-agent mutation guard, select and pass its reasoning effort according to the adaptive policy above, then invoke the configured `advisor` in a fresh behaviorally read-only child context: use `fork_turns: "none"` with MultiAgentV2, or `fork_context: false`/omitted with MultiAgentV1. Provide only the task-specific contract and primary evidence needed for independent review. For implementation review, pass the planner contract and primary evidence: actual changed files or diff, relevant source/test configuration, and verification commands/results. Treat implementation summaries, decisions, and reported verification outcomes as orientation and claims, not sufficient evidence; the advisor must independently inspect available primary evidence. Treat its result as guidance rather than independent approval: apply supported `fix-first` findings in the main agent, return material `rethink` findings to `planner`, and surface conflicts where verified primary evidence contradicts the advice instead of following it mechanically. Rerun relevant verification after changes. Re-invoke advisor only when another independent opinion remains materially useful or the user explicitly requests it; do not loop solely to obtain `VERDICT: ship`. The verdict is an advisory classification, not a completion gate. An `unsupported` advisor result blocks completion only when the user explicitly required the consultation or a material risk remains unresolved and cannot be validated independently.

The planner and advisor TOML files intentionally omit `model_reasoning_effort` and configure read-only sandbox defaults. Select their reasoning effort explicitly whenever they are dispatched. The top-level main agent's reasoning effort is not prescribed by this routing policy; preserve the user-selected or current-session setting. Runtime sandbox broadening alone must not block a named-agent invocation when the mutation guard can be established; every named-agent invocation in a Git worktree must use the guard before its result is accepted, and invocations outside a Git worktree require an effective read-only sandbox.

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
Apply the Git-visible mutation guard described above. Select and explicitly pass the planner reasoning effort using the adaptive policy: medium for routine non-trivial planning, high for complex or cross-cutting work, and xhigh only for unusually demanding work. Use the native planner in a fresh behaviorally read-only child context: set fork_turns to none with MultiAgentV2, or use fork_context false/omitted with MultiAgentV1. Supply a planner context packet with USER REQUEST, PRIOR DECISIONS, TASK CONTEXT, NON-NEGOTIABLE CONSTRAINTS, and OPEN QUESTIONS; preserve settled user decisions and put only genuinely unresolved material decisions in OPEN QUESTIONS. Produce a decision-complete plan for this task. Treat the installed planner definition as authoritative for gpt-5.6-sol and the requested read-only sandbox default; reasoning effort is a per-dispatch input and is intentionally not pinned in the TOML. Do not require parent-visible configuration attestation, and do not treat an effective workspace-write or other writable sandbox as unsupported by itself when the mutation guard can be established. In an unborn Git repository, record a no-HEAD sentinel instead of failing the guard; outside a Git worktree, require an effective read-only sandbox. Accept the planner result only if the post-dispatch Git-visible state still matches the recorded baseline and reject it if available runtime evidence shows a generic/different-agent fallback, an incompatible model or reasoning-effort override, failure to honor the requested fresh-context isolation, or any mutating action, including a transient edit restored before return. Resolve any blocking questions. If STATUS is ready, obtain user approval only for an unresolved material user-facing or requirement-level decision; otherwise the main agent may approve tactical implementation details internally. Then pass the approved contract to the top-level main agent without changing the reasoning effort selected by the user or current session. Do not delegate implementation to worker subagents. Run the planned verification. Invoke advisor only when an independent second opinion materially improves decision quality or confidence, or when the user explicitly requests it; routine low-risk changes may complete after direct verification without advisor review.
```

### On-demand advisor

```text
When advisor use is warranted, apply the Git-visible mutation guard described above. Select and explicitly pass the advisor reasoning effort using the adaptive policy: medium for routine non-trivial review, high for complex or cross-cutting work, and xhigh only for unusually demanding work. Use the native advisor in a fresh behaviorally read-only child context: set fork_turns to none with MultiAgentV2, or use fork_context false/omitted with MultiAgentV1. Provide the task-specific contract and primary workspace evidence, including the actual changes, relevant source/test configuration, and verification surface. Treat the installed advisor definition as authoritative for gpt-5.6-sol and the requested read-only sandbox default; reasoning effort is a per-dispatch input and is intentionally not pinned in the TOML. Do not require parent-visible configuration attestation, and do not treat an effective workspace-write or other writable sandbox as unsupported by itself when the mutation guard can be established. In an unborn Git repository, record a no-HEAD sentinel instead of failing the guard; outside a Git worktree, require an effective read-only sandbox. Treat implementation decisions, summaries, and reported verification results as claims and orientation rather than sufficient evidence; independently inspect the available primary evidence before returning guidance. Accept the result only if the post-dispatch Git-visible state still matches the recorded baseline and reject it if available runtime evidence shows a generic/different-agent fallback, an incompatible model or reasoning-effort override, failure to honor the requested fresh-context isolation, or any mutating action, including a transient edit restored before return. Treat verdict labels as advisory classifications rather than approval gates. Apply supported findings, rerun relevant verification, and adapt when verified primary evidence contradicts a recommendation. Re-consult advisor only when another independent opinion remains materially useful or the user explicitly requests it; do not loop solely to obtain VERDICT: ship. An unsupported advisor result blocks completion only when the user explicitly required the consultation or a material risk remains unresolved and cannot be validated independently.
```

### Advice only

```text
Apply the Git-visible mutation guard described above. Select and explicitly pass the advisor reasoning effort using the adaptive policy, then use native advisor in a fresh child context using the active native runtime's isolation parameter to evaluate this design. Return advice only and do not modify files. In an unborn Git repository, record a no-HEAD sentinel instead of failing the guard; outside a Git worktree, require an effective read-only sandbox if the runtime would otherwise be writable. Accept the result only if the post-dispatch Git-visible state still matches the recorded baseline and reject it if available runtime evidence shows failure to honor the requested fresh-context isolation or any mutating action, including a transient edit restored before return.
```
