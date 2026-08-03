# Global Codex instructions

This file is the user-wide installation template. Project-local Codex sessions read the same routing policy from the repository-root `AGENTS.md`.

## Model routing

This section applies only to the root or main agent that receives the user's task. Named custom agents (`planner_sol`, `advisor_sol`, `worker_luna`, and `worker_terra`) must ignore this section, follow their agent-specific instructions, and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and narrow, deterministic edits when delegation overhead is not justified.

For non-trivial implementation tasks:

1. Spawn `planner_sol` before modifying files.
2. Require its five-part implementation contract: objective, files and ownership, interfaces, constraints, and verification.
3. Wait for the complete contract and preserve its scope, settled decisions, interfaces, acceptance checks, and recommended executor.
4. Start exactly one implementation agent:
   - Use `worker_luna` by default when the objective and file ownership are bounded, architecture and externally visible interfaces are settled, no material security or migration decision remains, and verification has concrete commands or inspectable acceptance evidence.
   - Use `worker_terra` only when the planner identifies an explicit Terra condition: unresolved architectural or product decisions; security, authentication, authorization, data-model, or migration design; broad diagnosis where affected components are not yet known; cross-cutting adaptation that cannot be expressed as bounded ownership; judgment-heavy validation without concrete acceptance criteria; or a documented Luna escalation.
   - Complexity, multiple files, or non-trivial implementation alone do not justify Terra.
5. Require `worker_luna` to perform its pre-edit suitability check. If it declines before editing, return control to the parent and start `worker_terra` only after reviewing the exact reason. If it escalates after partial edits, inspect and preserve its reported state, update the implementation contract when necessary, and then perform a sequential Terra handoff.
6. Do not run write-capable workers concurrently.
7. If implementation encounters a material architectural, security, compatibility, data-model, authentication, authorization, product, or migration decision not covered by the contract, return control to `planner_sol` or `advisor_sol` instead of silently expanding scope.
8. Treat every worker report as claims that the main agent must verify:
   - inspect the complete working-tree diff;
   - confirm that only approved files and behavior changed;
   - rerun the relevant verification commands in the main session; and
   - resolve any discrepancy between the report and the actual evidence.
9. Spawn a fresh `advisor_sol` context for final review. Provide the user goal, allowed change set, complete diff or explicit base and head revisions, interfaces and constraints, and the main session's verification evidence.
10. Do not report completion unless the reviewer returns `VERDICT: ship`. A subsequent code change invalidates the verdict; verify again and obtain a new fresh review. Route bounded `fix-first` findings to `worker_luna` by default. Use `worker_terra` only when the finding introduces an explicit Terra condition. Return `rethink` findings to `planner_sol` or the user.

For architecture, design evaluation, or technical advice without implementation, spawn `advisor_sol` and keep the work read-only.

Do not spawn a subagent when the main agent can complete the task safely and efficiently without delegation.
