# Codex custom subagents

These project-scoped TOML files define two native read-only Codex roles:

- `planner`: `gpt-5.6-sol`, adaptive reasoning effort, read-only. Produces a decision-complete implementation plan.
- `advisor`: `gpt-5.6-sol`, adaptive reasoning effort, read-only. Provides technical advice or final implementation review.

Implementation is performed directly by the top-level main agent. There are no dedicated Luna or Terra worker roles.

## Design rationale

This layout is intentionally OpusPlan-inspired: high-capability read-only subagents are independent decision boundaries around implementation, not generic implementation workers.

```text
Claude Code
Opus planning → Sonnet implementation → Opus advisor/review

Codex
Sol planning → top-level main implementation (Terra-class, not a worker role) → Sol advisor
```

The steady-state authority split is:

```text
planning authority        → Sol planner
implementation authority  → top-level main agent
review authority          → Sol advisor
```

Keeping implementation ownership in the top-level main-agent path avoids an additional write-capable subagent handoff and preserves a single implementation authority. The top-level implementation session may still be restarted or reconfigured to satisfy the required `xhigh` reasoning effort; when that happens, the approved planner contract remains the implementation contract. The former `worker_luna` and `worker_terra` roles were therefore removed intentionally and should not be restored by default.

If future measurements justify parallelism, prefer bounded read-only investigation roles such as dependency, test, security, or compatibility scouts. Do not introduce write-capable implementation workers into the default architecture unless empirical results show that the added orchestration and context-transfer cost is worthwhile.

Invoke `planner` and `advisor` only through Codex native multi-agent tools. Do not use nested `codex exec`, shell wrappers, copied prompts, generic agents, or simulations. Invoke each role with `fork_turns: "none"` and pass its task-specific context explicitly. Treat these TOML definitions as authoritative for the configured role, model, and requested sandbox default. Their reasoning effort is intentionally unpinned and must be selected explicitly per native dispatch using the adaptive policy below. A successful native dispatch to the requested named role is enough to proceed; do not require the runtime to echo configuration metadata that it may not expose. A broader effective sandbox such as `workspace-write` does not by itself invalidate the invocation when the named-agent mutation guard below can be established: the named agents must remain behaviorally read-only and must not modify files. Report `unsupported` only when available runtime evidence explicitly shows a fallback, incompatible model override, failure to honor an explicitly requested per-dispatch reasoning effort, inherited context contrary to the requested isolation, unavailable native dispatch, or a writable invocation outside a Git worktree.

### Adaptive reasoning effort

The custom agent files intentionally omit `model_reasoning_effort`; `adaptive` is a routing policy, not a literal TOML effort value. Before every `planner` or `advisor` spawn, explicitly choose and pass the lowest adequate supported effort instead of relying on `[agents]` defaults or parent-effort inheritance:

- `medium`: routine non-trivial planning or review.
- `high`: complex, cross-cutting, security-sensitive, or regression-prone work.
- `xhigh`: unusually demanding work where additional reasoning is materially useful.

Do not default every named-agent dispatch to `xhigh`. The top-level implementation session remains a separate contract and still requires `xhigh`.

### Planner context handoff

`planner` receives no inherited conversation when invoked with `fork_turns: "none"`. Every planner dispatch must therefore include this minimum context packet:

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

The planner should not need to reconstruct or guess user intent from an implementation-oriented summary. Keep settled decisions in `PRIOR DECISIONS` and genuinely unresolved decisions in `OPEN QUESTIONS`.

### Named-agent mutation guard

For every `planner` or `advisor` invocation in a Git worktree, immediately before dispatch record a Git-visible baseline: `HEAD` when it exists (otherwise an explicit unborn-`HEAD` sentinel), index diff, tracked worktree diff, and every non-ignored untracked path with a content digest. Compare the same state immediately after return. Any persistent Git-visible mutation introduced during the invocation invalidates the result; preserve changes that already existed in the baseline. If available runtime output or telemetry explicitly shows a mutating action, including a transient edit that was restored before return, invalidate the result even when the post-dispatch baseline matches. Ignored and generated files are intentionally outside the persistent-state comparison. If the workspace is not a Git worktree, require an effective read-only sandbox; do not accept a writable effective sandbox without this guard. This guard establishes persistent Git-visible state integrity; it does not prove that a writable runtime performed no transient writes. The named agents remain behaviorally read-only and must not intentionally edit files. Do not describe this guard as runtime-enforced read-only or mutation-free execution.

## Routing

Use the main agent directly for simple questions and narrow, deterministic edits.

For non-trivial implementation:

1. Apply the named-agent mutation guard, select and pass the planner reasoning effort according to the adaptive policy above, then invoke `planner` in a separate context with read-only behavior. Supply `USER REQUEST`, `PRIOR DECISIONS`, `TASK CONTEXT`, `NON-NEGOTIABLE CONSTRAINTS`, and `OPEN QUESTIONS`. Prefer its configured read-only sandbox, but accept its contract unless runtime evidence explicitly reports a fallback, incompatible model override, failure to honor the explicitly requested reasoning effort, inherited context contrary to `fork_turns: "none"`, or a writable invocation outside a Git worktree; missing runtime telemetry, an adaptively selected reasoning effort, or a writable effective sandbox alone is not a failure when the guard can be established.
2. Route the planner result. For `STATUS: blocked`, obtain the smallest missing user decision and replan. For `STATUS: ready`, preserve already-settled decisions. Ask the user only when the contract introduces or changes an unresolved material decision about observable product behavior, API/compatibility guarantees, meaningful architectural trade-offs, destructive migration, security posture, significant scope, or new requirements. The main agent may approve tactical implementation details internally when they remain within the established contract.
3. Pass the approved contract to a top-level implementation session configured with `model_reasoning_effort = "xhigh"`; otherwise restart with `xhigh` or report `unsupported`. Implement the plan directly in that session.
4. Inspect the actual changes and run the planned verification.
5. Apply the named-agent mutation guard, select and pass the advisor reasoning effort according to the adaptive policy above, then invoke `advisor` in a fresh context with read-only behavior. Pass the planner contract and primary evidence: actual changed files or diff, relevant source/test configuration, and verification commands/results. Treat implementation summaries, decisions, and reported verification outcomes as orientation and claims, not sufficient evidence; the advisor must independently inspect available primary evidence before its verdict. Prefer its configured read-only sandbox, but accept its verdict unless runtime evidence explicitly contradicts the configured role or model, fails to honor the explicitly requested reasoning effort, contradicts the fresh-context request, or the invocation is writable outside a Git worktree. A writable effective sandbox alone is not a failure when the guard can be established.
6. Apply bounded `fix-first` findings in the main agent. For `rethink`, return to `planner` and route any newly material user decision under the same approval rules before reimplementation. An explicitly justified `unsupported` verdict blocks completion. Repeat verification and fresh review until `VERDICT: ship`.

The planner and advisor TOML files intentionally omit `model_reasoning_effort` and configure read-only sandbox defaults. Select their reasoning effort explicitly per dispatch using the adaptive policy above. The top-level implementation session must be configured with `model_reasoning_effort = "xhigh"` separately. Runtime sandbox broadening alone must not block planning or review when the mutation guard can be established; every named-agent invocation in a Git worktree must use the guard before its result is accepted, and invocations outside a Git worktree require an effective read-only sandbox.

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
Apply the Git-visible mutation guard described above. Select and explicitly pass the planner reasoning effort using the adaptive policy: medium for routine non-trivial planning, high for complex or cross-cutting work, and xhigh only for unusually demanding work. Use native planner with fork_turns set to none in a separate behaviorally read-only context. Supply a planner context packet with USER REQUEST, PRIOR DECISIONS, TASK CONTEXT, NON-NEGOTIABLE CONSTRAINTS, and OPEN QUESTIONS; preserve settled user decisions and put only genuinely unresolved material decisions in OPEN QUESTIONS. Produce a decision-complete plan for this task. Treat the installed planner definition as authoritative for gpt-5.6-sol and the requested read-only sandbox default; reasoning effort is a per-dispatch input and is intentionally not pinned in the TOML. Do not require parent-visible configuration attestation, and do not treat an effective workspace-write or other writable sandbox as unsupported by itself when the mutation guard can be established. In an unborn Git repository, record a no-HEAD sentinel instead of failing the guard; outside a Git worktree, require an effective read-only sandbox. Accept the planner result only if the post-dispatch Git-visible state still matches the recorded baseline and reject it if available runtime evidence shows any mutating action, including a transient edit restored before return. Resolve any blocking questions. If STATUS is ready, obtain user approval only for an unresolved material user-facing or requirement-level decision; otherwise the main agent may approve tactical implementation details internally. Then pass the approved contract to a top-level main-agent session configured with model_reasoning_effort = "xhigh". Do not delegate implementation to worker subagents. Run the planned verification and prepare the planner contract, actual changed files or diff, implementation decisions, and verification results for the mandatory final-review phase below. Do not report completion yet.
```

### Mandatory final review

```text
Apply the Git-visible mutation guard described above. Select and explicitly pass the advisor reasoning effort using the adaptive policy: medium for routine non-trivial review, high for complex or cross-cutting work, and xhigh only for unusually demanding work. Use native advisor with fork_turns set to none in a fresh behaviorally read-only context. Treat the installed advisor definition as authoritative for gpt-5.6-sol and the requested read-only sandbox default; reasoning effort is a per-dispatch input and is intentionally not pinned in the TOML. Do not require parent-visible configuration attestation, and do not treat an effective workspace-write or other writable sandbox as unsupported by itself when the mutation guard can be established. In an unborn Git repository, record a no-HEAD sentinel instead of failing the guard; outside a Git worktree, require an effective read-only sandbox. Review the planner contract and primary workspace evidence, including the actual changes, relevant source/test configuration, and verification surface. Treat implementation decisions, summaries, and reported verification results as claims and orientation rather than sufficient evidence; independently inspect the available primary evidence before issuing the verdict. Accept the verdict only if the post-dispatch Git-visible state still matches the recorded baseline and reject it if available runtime evidence shows any mutating action, including a transient edit restored before return. Return VERDICT: ship, fix-first, rethink, or unsupported. Report completion only after VERDICT: ship; apply fix-first findings and rerun verification and review, return rethink findings to planner for a revised approved contract, and treat explicitly justified unsupported as blocking.
```

### Advice only

```text
Apply the Git-visible mutation guard described above. Select and explicitly pass the advisor reasoning effort using the adaptive policy, then use native advisor to evaluate this design. Return advice only and do not modify files. In an unborn Git repository, record a no-HEAD sentinel instead of failing the guard; outside a Git worktree, require an effective read-only sandbox if the runtime would otherwise be writable. Accept the result only if the post-dispatch Git-visible state still matches the recorded baseline and reject it if available runtime evidence shows any mutating action, including a transient edit restored before return.
```
