# Global Codex instructions

This file is the user-wide installation template. Project-local Codex sessions read the same routing policy from the repository-root `AGENTS.md`.

## Native named-agent dispatch

`planner` and `advisor` must be invoked through Codex's native multi-agent tools. Do not invoke them through `codex exec`, nested Codex CLI processes, shell wrappers, copied prompts, generic agents, or simulations.

Implementation is owned by the top-level main agent. Do not delegate implementation to named or generic worker subagents. If native dispatch or a required runtime guarantee is unavailable, report `unsupported` rather than silently omitting, downgrading, or simulating a phase.

## Model routing

This section applies only to the top-level main agent. The named `planner` and `advisor` agents follow their own definitions and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and narrow, deterministic edits when planning overhead is not justified.

For non-trivial implementation tasks:

1. Invoke `planner` before editing and obtain a decision-complete contract covering objective, scope, interfaces, constraints, and verification.
2. Resolve material architectural, product, security, compatibility, or data-model decisions before implementation. Do not invent requirements.
3. Before editing, ensure the top-level implementation session is configured with `model_reasoning_effort = "xhigh"`; otherwise restart with `xhigh` or report `unsupported`. Implement the approved contract directly in that session. Do not delegate implementation to a worker subagent.
4. Inspect the actual changes, preserve unrelated work, and run the relevant verification from the planner contract.
5. Invoke `advisor` in a fresh context with effective read-only permission and no inherited implementation history (`fork_turns: "none"`). Provide the planner contract, actual changed files or diff, implementation decisions, and verification results. If either runtime guarantee cannot be established, report `unsupported` and do not accept a verdict.
6. Handle the verdict: apply bounded `fix-first` findings in the main agent; for `rethink`, return to `planner` and approve a revised contract before reimplementation; `unsupported` blocks completion. Rerun verification and fresh review after changes. Report completion only after `VERDICT: ship`.

The planner and advisor TOML files configure `model_reasoning_effort = "xhigh"` and read-only defaults. Runtime overrides must not weaken the final-review requirements above.

For architecture, design evaluation, or technical advice without implementation, invoke `advisor` and keep the work read-only.

Do not invoke a subagent when the main agent can complete a non-implementation task safely and efficiently without delegation.
