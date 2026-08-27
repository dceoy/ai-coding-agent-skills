# Global Codex instructions

This file is the user-wide installation template for the named-agent routing policy. Install it as `$CODEX_HOME/AGENTS.md`.

## Named-agent dispatch

Use the configured `planner`, `advisor`, `reviewer`, and `feedback-analyst` only through Codex native multi-agent dispatch. Do not use nested `codex exec`, shell wrappers, copied prompts, generic-agent simulations, or child coding-agent CLI processes.

Invoke every named role in a fresh child context: use `fork_turns: "none"` with MultiAgentV2, or `fork_context: false`/omitted with MultiAgentV1. Pass task-specific context explicitly. Named agents are terminal read-only leaves and must not modify files or dispatch another subagent.

The agent TOML files define role behavior and sandbox defaults but intentionally omit `model` and `model_reasoning_effort`. Select both explicitly for every dispatch.

### Model and effort routing

Use these model defaults and escalate only when the stated work requires it:

- `planner`: `gpt-5.6-terra`; use `gpt-5.6-sol` for architecture, public interfaces, schemas, migrations, security boundaries, broad cross-cutting behavior, or unusually regression-prone planning.
- `advisor`: `gpt-5.6-sol`.
- `reviewer` / `correctness`: `gpt-5.6-terra`; use Sol for difficult state transitions, concurrency, large refactors, or cross-component invariants.
- `reviewer` / `tests/docs`: `gpt-5.6-luna`; use Terra when verification, compatibility, or documentation behavior requires substantial code reasoning.
- `reviewer` / `security/performance`: `gpt-5.6-terra`; use Sol for authentication, authorization, secrets, untrusted input, CI or privilege boundaries, concurrency, resource exhaustion, or similarly high-risk analysis.
- `reviewer` / other caller-defined lens or scope: `gpt-5.6-terra`; use Sol when the review is materially difficult, high-risk, cross-cutting, or otherwise quality-critical.
- `feedback-analyst`: `gpt-5.6-luna`; use Terra when feedback conflicts, root-cause grouping is ambiguous, or dispositions require non-trivial code reasoning. Use `advisor` instead for architecture-level or other consequential judgment.

After selecting the model, choose effort for cost/performance as follows:

- Luna: `max`.
- Terra: `xhigh` by default; `max` when materially useful.
- Sol: `high` by default; `xhigh` for unusually demanding work; `max` only for the hardest quality-first work.

Do not carry an effort choice across a model escalation; reselect it from the selected model's allowed set. If native dispatch cannot honor an explicit model or effort, do not silently inherit another value. Treat that named invocation as unsupported and follow the caller's permitted fallback contract.

Implementation remains owned by the top-level main agent. Do not delegate implementation to a worker subagent. The main agent keeps the user- or session-selected model and effort.

### Planner handoff

Every planner dispatch must include:

- `USER REQUEST`: the user's request with minimal paraphrasing.
- `PRIOR DECISIONS`: settled decisions that must not be reopened without new evidence.
- `TASK CONTEXT`: relevant repository state, architecture, and existing implementation.
- `NON-NEGOTIABLE CONSTRAINTS`: project/user constraints, compatibility, security, migration, operational requirements, and exclusions.
- `OPEN QUESTIONS`: only unresolved material decisions.

A ready plan must be decision-complete for objective, scope, interfaces, constraints, and verification. Ask the user only when a material user-facing or requirement-level decision remains unresolved; tactical implementation choices stay with the planner/main-agent path.

### Mutation guard

Before every named-agent invocation in a Git worktree, record `HEAD` (or an unborn-`HEAD` sentinel), index diff, tracked worktree diff, and every non-ignored untracked path with a content digest. Compare the same state after return. Reject a result if the invocation introduced persistent Git-visible mutation or runtime evidence shows a mutating action, including a transient edit later restored. Preserve pre-existing changes. Ignored/generated files are outside this comparison.

Outside a Git worktree, require an effective read-only sandbox. A broader sandbox such as `workspace-write` is acceptable only when the Git-visible mutation guard can be established; it does not make mutation permissible.

## Routing

Use the main agent directly for simple questions and narrow deterministic edits. For non-trivial implementation, invoke `planner` when planning overhead is justified, implement directly in the top-level main agent, run verification, and invoke `advisor` only when an independent second opinion materially improves decision quality or confidence.

Skill-specific routing follows each skill's own contract:

- `issue-plan` may map its required fresh planning subagent to the compatible `planner` role.
- `pr-review` owns its dynamic review and validation task selection. Map those tasks to compatible fresh `reviewer` invocations when useful; do not force a fixed lens set that the skill did not select.
- `pr-feedback-triage` is a top-level mutation workflow. Do not insert `feedback-analyst` as an extra required phase unless that skill explicitly delegates analysis.
- `pr-loop` only sequences `issue-plan`, `pr-review`, and `pr-feedback-triage`; it does not define additional subagent roles.

Fall back to another native independent subagent only when a skill requires delegation and the preferred named role is unavailable or incompatible with that skill's portable contract.

Treat advisor output as guidance, not an approval gate. Apply supported bounded fixes in the main agent, return material architecture/scope conflicts to `planner`, rerun affected verification, and do not loop merely to obtain `VERDICT: ship`.

Treat a named invocation as unsupported only when available runtime evidence shows unavailable native named-role dispatch, use of a different/generic agent, failure to honor the explicit model/effort or fresh-context isolation, or a writable non-Git invocation. Missing telemetry or a writable Git worktree sandbox alone is not a mismatch.
