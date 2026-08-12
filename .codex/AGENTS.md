# Global Codex instructions

This file is the user-wide installation template. Project-local Codex sessions read the same routing policy from the repository-root `AGENTS.md`.

## Native named-agent dispatch

This is Codex's default routing for non-trivial implementation work when no portable skill defines its own orchestration. A portable skill such as `pr-loop` follows its own `SKILL.md` contract instead and may use whichever native independent-subagent mechanism the active runtime provides, without requiring `.codex/agents` or a fixed named agent; see the repository-root `AGENTS.md`'s "Portable native-subagent contract" section for the full contract.

`planner` and `advisor` must be invoked through Codex's native multi-agent tools. Do not invoke them through `codex exec`, nested Codex CLI processes, shell wrappers, copied prompts, generic agents, or simulations.

Invoke each role with `fork_turns: "none"` and pass its task-specific context explicitly; do not rely on inherited conversation history.

Treat the installed agent TOML as the source of truth for the named role, model, and requested sandbox default. Reasoning effort is deliberately selected per native dispatch rather than pinned in the agent definition. A successful native dispatch to the requested named role is sufficient; the runtime does not need to echo those configuration values back to the parent. A broader effective sandbox such as `workspace-write` does not by itself invalidate the invocation when the named-agent mutation guard below can be established: `planner` and `advisor` remain behaviorally read-only and must not modify files. Treat the invocation as `unsupported` only when available runtime evidence explicitly shows that native dispatch is unavailable, a generic or different agent was used, the configured model was overridden, an explicitly requested per-dispatch reasoning effort was overridden incompatibly, context was inherited contrary to `fork_turns: "none"`, or a writable invocation cannot be guarded because the workspace is not a Git worktree. Missing runtime telemetry, an adaptively selected reasoning effort, or a writable effective sandbox alone is not evidence of a mismatch.

Reasoning effort for `planner` and `advisor` is adaptive by dispatch policy. Their TOML files intentionally omit `model_reasoning_effort`. Before each spawn, explicitly select and pass the lowest adequate supported effort for the task instead of relying on `[agents]` defaults or parent-effort inheritance: use `medium` for routine non-trivial planning or review, `high` for complex or cross-cutting work, and `xhigh` only for unusually demanding work.

Implementation is owned by the top-level main agent. Do not delegate implementation to named or generic worker subagents. If native dispatch is explicitly unavailable or incompatible with the configured role, report `unsupported` rather than silently omitting, downgrading, or simulating a phase.

### Planner context handoff

Because `planner` runs with `fork_turns: "none"`, every planner dispatch must include a context packet that preserves the user's intent instead of relying on an implementation-oriented summary. Include:

- `USER REQUEST`: the user's actual request with minimal paraphrasing; prefer verbatim wording when practical.
- `PRIOR DECISIONS`: decisions already settled with the user. Do not reopen them without a concrete conflict or new evidence.
- `TASK CONTEXT`: relevant repository state, existing implementation, architecture, and other facts needed to plan.
- `NON-NEGOTIABLE CONSTRAINTS`: user and project constraints, compatibility, security, migration, operational requirements, and explicit exclusions.
- `OPEN QUESTIONS`: only genuinely unresolved material decisions.

Keep settled decisions separate from open questions. The planner must not have to reconstruct or guess user intent from a lossy parent-agent summary.

### Named-agent mutation guard

For every `planner` or `advisor` invocation in a Git worktree, immediately before dispatch record a Git-visible baseline: `HEAD` when it exists (otherwise an explicit unborn-`HEAD` sentinel), index diff, tracked worktree diff, and every non-ignored untracked path with a content digest. Compare the same state immediately after return. Any persistent Git-visible mutation introduced during the invocation invalidates the result; preserve changes that already existed in the baseline. If available runtime output or telemetry explicitly shows a mutating action, including a transient edit that was restored before return, invalidate the result even when the post-dispatch baseline matches. Ignored and generated files are intentionally outside the persistent-state comparison. If the workspace is not a Git worktree, require an effective read-only sandbox; do not accept a writable effective sandbox without this guard. This guard establishes persistent Git-visible state integrity; it does not prove that a writable runtime performed no transient writes. The named agents remain behaviorally read-only and must not intentionally edit files. Do not describe this guard as runtime-enforced read-only or mutation-free execution.

## Model routing

This section applies only to the top-level main agent. The named `planner` and `advisor` agents follow their own definitions and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and narrow, deterministic edits when planning overhead is not justified.

For non-trivial implementation tasks:

1. Apply the named-agent mutation guard, select and pass the planner reasoning effort according to the adaptive policy above, then invoke `planner` in a separate context with read-only behavior. Supply the required planner context packet and obtain a decision-complete contract covering objective, scope, interfaces, constraints, and verification. Prefer the configured read-only sandbox, but accept the contract when native dispatch returns the requested planner result unless runtime evidence explicitly reports a fallback, incompatible model override, failure to honor the explicitly requested reasoning effort, inherited context contrary to `fork_turns: "none"`, or a writable invocation outside a Git worktree. A writable effective sandbox alone is not a failure condition when the guard can be established.
2. Route planner decisions before implementation. If the planner returns `STATUS: blocked`, obtain the smallest missing user decision and replan. If it returns `STATUS: ready`, preserve decisions already settled by the user. Require explicit user approval only when the contract introduces or changes a material user-facing or requirement-level decision that is not already settled, including observable product behavior, API or compatibility guarantees, architecture with meaningful trade-offs, destructive or irreversible migration, security posture, significant scope expansion, or a new requirement. The main agent may approve tactical and operational implementation details internally when they stay within the established contract. Do not invent requirements or reopen settled decisions without cause.
3. Pass the approved contract to a top-level implementation session configured with `model_reasoning_effort = "xhigh"`; otherwise restart with `xhigh` or report `unsupported`. Implement the approved contract directly in that session. Do not delegate implementation to a worker subagent.
4. Inspect the actual changes, preserve unrelated work, and run the relevant verification from the planner contract.
5. Apply the named-agent mutation guard, select and pass the advisor reasoning effort according to the adaptive policy above, then invoke `advisor` in a fresh context with read-only behavior. Provide the planner contract and primary review evidence: the actual changed files or diff, relevant source and test configuration, and the verification commands and results. Implementation decisions and summaries may be included for orientation, but treat them and reported verification outcomes as claims rather than authoritative evidence; the advisor must independently inspect the available primary evidence before issuing a verdict. Prefer the configured read-only sandbox, but accept its verdict unless runtime evidence explicitly reports a fallback, incompatible model override, failure to honor the explicitly requested reasoning effort, inherited context contrary to `fork_turns: "none"`, or a writable invocation outside a Git worktree. A writable effective sandbox alone is not a failure condition when the guard can be established.
6. Handle the verdict: apply bounded `fix-first` findings in the main agent; for `rethink`, return to `planner` and route any newly material user decision under the same approval rules before reimplementation; an explicitly justified `unsupported` verdict blocks completion. Rerun verification and fresh review after changes. Report completion only after `VERDICT: ship`.

The planner and advisor TOML files intentionally omit `model_reasoning_effort` and configure read-only sandbox defaults. Select their reasoning effort explicitly per dispatch using the adaptive policy above. Runtime sandbox broadening alone must not block execution when the mutation guard can be established. Every named-agent invocation must use the Git-visible mutation guard above before its result is accepted; outside a Git worktree, require an effective read-only sandbox instead.

For architecture, design evaluation, or technical advice without implementation, apply the same named-agent mutation guard, select the advisor effort adaptively, invoke `advisor`, and keep the work behaviorally read-only.

Do not invoke a subagent when the main agent can complete a non-implementation task safely and efficiently without delegation.
