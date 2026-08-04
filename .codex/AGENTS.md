# Global Codex instructions

This file is the user-wide installation template. Project-local Codex sessions read the same routing policy from the repository-root `AGENTS.md`.

## Native named-agent dispatch

`planner` and `advisor` must be invoked through Codex's native multi-agent tools. Do not invoke them through `codex exec`, nested Codex CLI processes, shell wrappers, copied prompts, generic agents, or simulations.

Implementation is owned by the top-level main agent. Do not delegate implementation to named or generic worker subagents. If native dispatch is unavailable for a required planning or review phase, report `unsupported` rather than silently omitting or simulating that phase.

## Model routing

This section applies only to the top-level main agent. The named `planner` and `advisor` agents follow their own definitions and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and narrow, deterministic edits when planning overhead is not justified.

For non-trivial implementation tasks:

1. Invoke `planner` before editing and obtain a decision-complete contract covering objective, scope, interfaces, constraints, and verification.
2. Resolve material architectural, product, security, compatibility, or data-model decisions before implementation. Do not invent requirements.
3. Implement the approved contract directly in the top-level main agent with `reasoning_effort=xhigh`. Do not delegate implementation to a worker subagent.
4. Inspect the actual changes, preserve unrelated work, and run the relevant verification from the planner contract.
5. Start a fresh read-only review context and invoke `advisor` with no inherited implementation history (`fork_turns: "none"`). Provide the planner contract, actual changed files or diff, implementation decisions, and verification results.
6. If the advisor returns `fix-first`, apply the bounded fixes in the main agent, rerun verification, and request a fresh review. Report completion only after `VERDICT: ship`.

Use `reasoning_effort=xhigh` for `planner`, the main implementation phase, and `advisor`. The planner and advisor TOML files are read-only defaults; start planning, advice, and final-review contexts with effective read-only permission when the runtime supports it.

For architecture, design evaluation, or technical advice without implementation, invoke `advisor` and keep the work read-only.

Do not invoke a subagent when the main agent can complete a non-implementation task safely and efficiently without delegation.
