# Repository Guidelines

## Repository Purpose

This is a single-source skill library shared across AI coding runtimes. The `skills/` directory is the authoritative source of truth; runtime-specific directories reference it via symlinks.

## Model routing

This section applies only to the root or main agent that receives the user's task. Named custom agents (`planner_sol`, `advisor_sol`, `worker_luna`, and `worker_terra`) must ignore this section, follow their agent-specific instructions, and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and narrow, deterministic edits when delegation overhead is not justified.

For non-trivial implementation tasks:

1. Spawn `planner_sol` before modifying files.
2. Require its five-part implementation contract: objective, files and ownership, interfaces, constraints, and verification.
3. Do not start implementation while a material architectural, product, security, authentication, authorization, data-model, migration, compatibility, or externally visible interface decision remains unresolved. Return the smallest blocking question to `planner_sol`, `advisor_sol`, or the user.
4. Preserve the approved contract's scope, settled decisions, interfaces, acceptance checks, ownership boundary, and recommended executor.
5. Before starting a write-capable worker, establish an attribution boundary. Prefer a dedicated clean git worktree rooted at the captured `HEAD`. If the current worktree must be used, require exclusive write access to every approved ownership and verification-relevant path until parent verification and final evidence capture finish. Then capture the current `HEAD`, status, staged and unstaged diffs, and untracked-file inventory. For every relevant pre-existing untracked file, also capture its content or a cryptographic hash. A baseline records pre-existing state but does not by itself attribute later concurrent writes.
6. Preflight whether the runtime can resolve the selected named worker, load its definition, and spawn its configured model. Retain parent-visible evidence of the resolved role and model or the concrete runtime/backend failure.
7. Start exactly one implementation agent:
   - Use `worker_luna` by default when the objective and exact file ownership are bounded, architecture and externally visible interfaces are settled, and verification has concrete commands or inspectable acceptance evidence.
   - Use `worker_terra` in `terra-escalation` mode only after all material decisions are settled and the contract defines a bounded ownership zone plus an explicit Terra condition: broad diagnosis where the exact affected files inside that zone are not yet known; cross-cutting adaptation whose exact file set must be discovered inside that zone; or a documented Luna suitability failure or escalation identifying the concrete adaptive judgment Luna could not complete within exact ownership.
   - If `worker_luna` or its configured model cannot be spawned because of a runtime, backend, model-catalog, or named-agent limitation, runtime unavailability is not a Terra condition. Prefer the parent agent when it can safely execute the exact contract; otherwise use `worker_terra` in explicit `luna-compatibility` mode with the same exact ownership, suitability checks, interfaces, constraints, and verification as Luna. Compatibility mode grants no discovery, adaptive-judgment, or scope-expansion authority. If no compliant executor is available, report the runtime limitation and stop.
   - Complexity, multiple files, non-trivial implementation, or apparent need for engineering judgment alone do not justify Terra escalation. When exact ownership is known, route to Luna or its constrained compatibility executor first.
8. Require `worker_luna` to perform its pre-edit suitability check. If Luna is unavailable and compatibility mode is used, require `worker_terra` to verify the same suitability conditions and the parent-provided Luna spawn-failure evidence before editing. If Luna declines before editing, review whether the reason is a valid Terra condition or an unresolved decision that requires replanning. If it escalates after partial edits, inspect and preserve its reported state, update the contract when necessary, and then perform a sequential Terra handoff.
9. Do not run write-capable workers concurrently. Do not allow another process or user to write approved ownership or verification-relevant paths while the worker is active or while final review evidence is being frozen.
10. If implementation encounters a material decision not covered by the contract or must cross the approved ownership boundary, return control to `planner_sol` or `advisor_sol` instead of silently expanding scope.
11. Treat every worker report as claims that the main agent must verify:
    - compare the post-worker repository state against the captured pre-worker baseline, including relevant pre-existing untracked-file content or hashes, rather than relying only on the current working-tree diff;
    - if an unexpected mutation appears in an owned or verification-relevant path, or attribution is uncertain because concurrent writes occurred, stop and reconcile or restart from an isolated worktree instead of classifying the mutation as worker-introduced;
    - inspect every attributable worker-introduced file and behavior change while preserving and excluding pre-existing edits;
    - confirm that Luna or a Luna-compatibility executor stayed within exact ownership, or that Terra escalation stayed within its approved ownership zone;
    - rerun the relevant verification commands in the main session; and
    - resolve any discrepancy between the report and the actual evidence.
12. After parent verification, freeze the reviewed repository state and capture a second baseline, including content or cryptographic hashes for every relevant pre-existing untracked file. End the workspace-write implementation turn. Start a separate parent session in read-only mode for final review, invoke `advisor_sol` with no inherited implementation history (`fork_turns: "none"`), and provide the user goal, allowed change set, complete pre-worker-baseline-relative tracked diff, complete relevant untracked-file evidence, interfaces and constraints, and parent verification evidence. Explicit immutable base and head revisions may replace the baseline-relative evidence only when they fully encode the entire reviewed change set and the relevant worktree is clean. Require visible evidence that the named `advisor_sol` definition resolved with `gpt-5.6-sol`, `fork_turns: "none"`, and effective read-only permission; if named-agent attestation is unavailable, use the separate read-only parent session with the final-review instructions supplied explicitly and retain visible model, permission, and session-isolation evidence. If neither path can be attested, do not accept any verdict.
13. Keep the attribution boundary in force through final review. After the reviewer returns, compare the repository state with the frozen pre-review baseline, including relevant untracked-file content or hashes. Any mutation during or between review handoff and completion invalidates the verdict and requires investigation without overwriting unrelated changes.
14. Do not report completion unless an attested reviewer returns `VERDICT: ship`. Any subsequent change to the reviewed change set or verification-relevant repository state invalidates the verdict. For `REMEDIATION: parent-evidence`, the parent must repair the review path or evidence packet and rerun review without delegating to an implementation worker. For `REMEDIATION: repository-change` or the repository-change portion of `mixed`, route bounded edits to `worker_luna` by default or to the constrained Luna-compatibility executor only when Luna remains unavailable; use `worker_terra` escalation only when the finding introduces a valid Terra condition. Return `replan` or `rethink` findings to `planner_sol` or the user. Every repository change requires new parent verification and a fresh separate read-only review.

For architecture, design evaluation, or technical advice without implementation, spawn `advisor_sol` and keep the work read-only.

Do not spawn a subagent when the main agent can complete the task safely and efficiently without delegation.

## SKILL.md Frontmatter

Each `SKILL.md` uses YAML frontmatter:

```yaml
---
name: <skill-name>
description: <one-line description used for skill triggering>
allowed-tools: Bash, Read, Write, ... # tools the skill may use
---
```

## Adding or Modifying Skills

1. Create or edit `skills/<skill-name>/SKILL.md` — this is the canonical skill definition.
2. Claude Code picks up the skill automatically via `.claude/skills -> ../skills`. For non-Claude runtimes,
   add a per-skill symlink: `ln -s ../../skills/<skill-name> .agents/skills/<skill-name>`.
3. Keep `description` in the frontmatter precise — it controls when the skill auto-triggers in Claude Code.

## Autonomous and Scheduled Use

Do not duplicate skill instructions into separate routine files unless a runtime truly requires a self-contained prompt. Prefer invoking the canonical skill under `skills/` and passing schedule, PR, branch, or CI context from the runtime configuration.

For autonomous PR review, `skills/pr-review/SKILL.md` is the source of truth. It defines the GitHub posting contract used by CI, GitHub Actions, Claude Code Routines, and other automated review contexts.

## Local QA

Before committing, run the following checks:

| Check             | Command                          |
| ----------------- | -------------------------------- |
| Format Markdown   | `npx -y prettier -w './**/*.md'` |
| Lint Python       | `uv run ruff check`              |
| Type-check Python | `uv run pyright`                 |
| Run tests         | `uv run pytest`                  |

## Commit & Pull Request Guidelines

- Format Markdown files using `npx -y prettier -w './**/*.md'` before committing.
- Keep PRs focused and include: concise summary, affected workflow paths, linked issue/context, and regenerated `README.md` when workflow inventory changes.
- Branch names use appropriate prefixes on creation (e.g., `feature/...`, `bugfix/...`, `refactor/...`, `docs/...`, `chore/...`).
- When instructed to create a PR, create it as a draft with appropriate labels by default.
