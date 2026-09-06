# Global Codex instructions

This file is the user-wide installation template for the named-agent routing policy. Install it as `$CODEX_HOME/AGENTS.md`.

## Named-agent dispatch

Use the configured `planner`, `advisor`, `reviewer`, and `feedback-analyst` only through Codex native multi-agent dispatch. Do not use nested `codex exec`, shell wrappers, copied prompts, generic-agent simulations, or child coding-agent CLI processes.

Invoke every named role in a fresh child context: use `fork_turns: "none"` with MultiAgentV2, or `fork_context: false`/omitted with MultiAgentV1. Pass task-specific context explicitly. Named agents are terminal read-only leaves and must not modify files or dispatch another subagent.

The agent TOML files define role behavior and sandbox defaults but intentionally omit `model` and `model_reasoning_effort`. Select both explicitly for every dispatch.

### Model and effort routing

Use these model defaults and escalate only when the stated work requires it:

- `planner`: `gpt-5.6-terra` by default; use `gpt-5.6-sol` for architecture, public interfaces, schemas, migrations, security boundaries, broad cross-cutting behavior, or unusually regression-prone planning; use `gpt-6-astra` only for the hardest plans when several such concerns interact, uncertainty remains after inspection, or the cost of a design error is unusually high and the strongest end-to-end reasoning is materially useful.
- `advisor`: `gpt-5.6-sol` by default; use `gpt-6-astra` for consequential architecture, security, cross-system, or similarly high-impact judgment when the strongest independent analysis materially improves decision quality.
- `reviewer`: choose the model from the task's hardest selected lens and concrete risk, not from a fixed review slot:
  - use `gpt-5.6-luna` for documentation, comments, or narrowly scoped test-coverage tasks that need little implementation reasoning;
  - use `gpt-5.6-terra` by default for correctness, errors, types, compatibility, simplification, ordinary performance, and code-reasoning-heavy test or documentation tasks;
  - use `gpt-5.6-sol` for authentication, authorization, secrets, untrusted-input or privilege boundaries, migrations, concurrency, difficult state transitions, cross-component invariants, resource exhaustion, broad scalability analysis, or similarly high-risk review work;
  - use `gpt-6-astra` only for the highest-risk or most cross-cutting reviews, especially when several of the preceding high-risk domains interact, uncertainty remains after inspection, or the cost of a missed defect is unusually high.
  - when a task combines lenses, select the highest tier justified by any material risk in that task.
- `feedback-analyst`: `gpt-5.6-luna`; use Terra when feedback conflicts, root-cause grouping is ambiguous, or dispositions require non-trivial code reasoning. Use `advisor` instead for architecture-level or other consequential judgment, with Astra available there under the advisor escalation criteria.

Treat Astra as a capability-gated escalation. Select it only when the native Codex model catalog or dispatch surface confirms `gpt-6-astra` is supported in the current environment. If Astra support is unavailable or cannot be confirmed, retain Sol and select an appropriate Sol effort rather than attempting Astra and relying on an implicit downgrade.

After selecting the model, choose effort for cost/performance as follows:

- Luna: `max`.
- Terra: `xhigh` by default; `max` when materially useful.
- Sol: `high` by default; `xhigh` for unusually demanding work; `max` only for the hardest quality-first work.
- Astra: `high` by default; `xhigh` for the hardest cross-cutting work; `max` only when quality is the dominant constraint and the additional reasoning cost is justified.

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

Treat advisor output as guidance, not an approval gate. Apply supported bounded fixes in the main agent, return material architecture/scope conflicts to `planner`, rerun affected verification, and do not loop merely to obtain `VERDICT: ship`.

Treat a named invocation as unsupported only when available runtime evidence shows unavailable native named-role dispatch, use of a different/generic agent, failure to honor the explicit model/effort or fresh-context isolation, or a writable non-Git invocation. Missing telemetry or a writable Git worktree sandbox alone is not a mismatch.
