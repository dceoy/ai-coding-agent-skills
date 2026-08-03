# Global Codex instructions

This file is the user-wide installation template. Project-local Codex sessions read the same routing policy from the repository-root `AGENTS.md`.

## Model routing

This section applies only to the root or main agent that receives the user's task. Named custom agents (`planner_sol`, `advisor_sol`, `worker_terra`, and `worker_luna`) must ignore this section, follow their agent-specific instructions, and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and narrow, deterministic edits when delegation overhead is not justified.

For non-trivial implementation tasks:

1. Spawn `planner_sol` before modifying files.
2. Require its five-part implementation contract: objective, files and ownership, interfaces, constraints, and verification.
3. Wait for the complete contract and preserve its scope, settled decisions, interfaces, acceptance checks, and recommended executor.
4. Start exactly one implementation agent:
   - Use `worker_luna` only for localized, deterministic, low-risk work with explicit file ownership and mechanical validation.
   - Use `worker_terra` for diagnosis, ambiguity, cross-cutting changes, adaptation to repository state, or any other non-trivial implementation.
5. Require `worker_luna` to perform its pre-edit suitability check. If it declines before editing, return control to the parent and start `worker_terra` only after reviewing the reason. If it escalates after partial edits, inspect and preserve its reported state before a sequential Terra handoff.
6. Do not run write-capable workers concurrently.
7. If implementation encounters a material architectural, security, compatibility, data-model, authentication, authorization, or migration decision not covered by the contract, return control to `planner_sol` or `advisor_sol` instead of silently expanding scope.
8. Treat every worker report as claims that the main agent must verify:
   - inspect the complete working-tree diff;
   - confirm that only approved files and behavior changed;
   - rerun the relevant verification commands in the main session; and
   - resolve any discrepancy between the report and the actual evidence.
9. Spawn a fresh `advisor_sol` context for final review. Provide the user goal, allowed change set, complete diff or explicit base and head revisions, interfaces and constraints, and the main session's verification evidence.
10. Do not report completion unless the reviewer returns `VERDICT: ship`. A subsequent code change invalidates the verdict; verify again and obtain a new fresh review. Route bounded `fix-first` findings to the current worker when it remains suitable, otherwise use `worker_terra`. Return `rethink` findings to `planner_sol` or the user.

For architecture, design evaluation, or technical advice without implementation, spawn `advisor_sol` and keep the work read-only.

Do not spawn a subagent when the main agent can complete the task safely and efficiently without delegation.
