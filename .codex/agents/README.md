# Codex custom subagents

These project-scoped agents separate high-quality planning and advice from implementation.

| Agent | Model | Access | Purpose |
| --- | --- | --- | --- |
| `planner_sol` | `gpt-5.6-sol` | Read-only | Produce a decision-complete implementation plan and select an executor |
| `advisor_sol` | `gpt-5.6-sol` | Read-only | Provide architectural or technical advice without implementation |
| `worker_terra` | `gpt-5.6-terra` | Workspace write | Implement non-trivial approved plans |
| `worker_luna` | `gpt-5.6-luna` | Workspace write | Implement narrow, deterministic, mechanically verifiable plans |

## Usage

Ask Codex to delegate explicitly by agent name.

### Plan and implement

```text
Use planner_sol to plan this task. After the plan is complete, delegate implementation to the recommended worker_terra or worker_luna agent. Use only one write-capable worker.
```

For a human approval gate, split the workflow into two turns:

```text
Use planner_sol to produce the implementation plan only. Do not modify files.
```

After reviewing the plan:

```text
Implement the approved plan with worker_terra.
```

### Advice only

```text
Use advisor_sol to evaluate this design. Return advice only and do not modify files.
```

## Routing policy

Use `worker_luna` only for localized, low-risk changes with explicit scope and mechanical validation. Use `worker_terra` when the change requires diagnosis, non-trivial reasoning, cross-cutting edits, or adaptation to repository state.

If an implementation agent encounters an unplanned architectural, security, compatibility, or data-model decision, return control to `planner_sol` or `advisor_sol` instead of silently expanding the plan.
