# Global Codex instructions

This file is the user-wide installation template. Project-local Codex sessions read the same routing policy from the repository-root `AGENTS.md`.

## Native named-agent dispatch

`planner` and `advisor` must be invoked through Codex's native multi-agent tools. Do not invoke them through `codex exec`, nested Codex CLI processes, shell wrappers, copied prompts, generic agents, or simulations.

Invoke each role with `fork_turns: "none"` and pass its task-specific context explicitly; do not rely on inherited conversation history.

Treat the installed agent TOML as the source of truth for the named role, model, reasoning effort, and sandbox defaults. A successful native dispatch to the requested named role is sufficient; the runtime does not need to echo those configuration values back to the parent. Treat the invocation as `unsupported` only when available runtime evidence explicitly shows that native dispatch is unavailable, a generic or different agent was used, or a configured guarantee was overridden incompatibly. Missing runtime telemetry is not evidence of a mismatch.

Implementation is owned by the top-level main agent. Do not delegate implementation to named or generic worker subagents. If native dispatch is explicitly unavailable or incompatible with the configured role, report `unsupported` rather than silently omitting, downgrading, or simulating a phase.

## Model routing

This section applies only to the top-level main agent. The named `planner` and `advisor` agents follow their own definitions and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and narrow, deterministic edits when planning overhead is not justified.

For non-trivial implementation tasks:

1. Invoke `planner` in a separate context with effective read-only permission and obtain a decision-complete contract covering objective, scope, interfaces, constraints, and verification. Accept the contract when native dispatch returns the requested planner result unless runtime evidence explicitly reports a fallback, incompatible override, or writable permission.
2. Resolve material architectural, product, security, compatibility, or data-model decisions before implementation. Do not invent requirements.
3. Pass the approved contract to a top-level implementation session configured with `model_reasoning_effort = "xhigh"`; otherwise restart with `xhigh` or report `unsupported`. Implement the approved contract directly in that session. Do not delegate implementation to a worker subagent.
4. Inspect the actual changes, preserve unrelated work, and run the relevant verification from the planner contract.
5. Invoke `advisor` in a fresh context with effective read-only permission. Provide the planner contract, actual changed files or diff, implementation decisions, and verification results. Accept its verdict unless runtime evidence explicitly reports a fallback, incompatible override, writable permission, or inherited context contrary to `fork_turns: "none"`.
6. Handle the verdict: apply bounded `fix-first` findings in the main agent; for `rethink`, return to `planner` and approve a revised contract before reimplementation; an explicitly justified `unsupported` verdict blocks completion. Rerun verification and fresh review after changes. Report completion only after `VERDICT: ship`.

The planner and advisor TOML files configure `model_reasoning_effort = "xhigh"` and read-only defaults. Runtime overrides must not weaken the final-review requirements above, but absence of parent-visible runtime metadata alone must not block execution.

For architecture, design evaluation, or technical advice without implementation, invoke `advisor` and keep the work read-only.

Do not invoke a subagent when the main agent can complete a non-implementation task safely and efficiently without delegation.
