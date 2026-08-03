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
5. Before starting a write-capable worker, capture a repository baseline in the parent session: current `HEAD`, status, staged and unstaged diffs, and the untracked-file inventory. For every relevant pre-existing untracked file inside the approved ownership boundary or used by verification, also capture its content or a cryptographic hash so same-path content mutations are detectable. Retain enough evidence to distinguish pre-existing or concurrent changes from worker-introduced changes.
6. Start exactly one implementation agent:
   - Use `worker_luna` by default when the objective and exact file ownership are bounded, architecture and externally visible interfaces are settled, and verification has concrete commands or inspectable acceptance evidence.
   - Use `worker_terra` only after all material decisions are settled and the contract defines a bounded ownership zone plus an explicit Terra condition: broad diagnosis where the exact affected files inside that zone are not yet known; cross-cutting adaptation whose exact file set must be discovered inside that zone; or a documented Luna suitability failure or escalation identifying the concrete adaptive judgment Luna could not complete within exact ownership.
   - Complexity, multiple files, non-trivial implementation, or apparent need for engineering judgment alone do not justify Terra. When exact ownership is known, route to Luna first.
7. Require `worker_luna` to perform its pre-edit suitability check. If it declines before editing, review whether the reason is a valid Terra condition or an unresolved decision that requires replanning. If it escalates after partial edits, inspect and preserve its reported state, update the contract when necessary, and then perform a sequential Terra handoff.
8. Do not run write-capable workers concurrently.
9. If implementation encounters a material decision not covered by the contract or must cross the approved ownership boundary, return control to `planner_sol` or `advisor_sol` instead of silently expanding scope.
10. Treat every worker report as claims that the main agent must verify:
    - compare the post-worker repository state against the captured pre-worker baseline, including relevant pre-existing untracked-file content or hashes, rather than relying only on the current working-tree diff;
    - inspect every worker-introduced file and behavior change while preserving and excluding pre-existing or concurrent edits;
    - confirm that Luna stayed within exact ownership or Terra stayed within its approved ownership zone;
    - rerun the relevant verification commands in the main session; and
    - resolve any discrepancy between the report and the actual evidence.
11. After parent verification, capture a second repository baseline immediately before final review, including content or cryptographic hashes for every relevant pre-existing untracked file. Spawn `advisor_sol` with no inherited implementation history (`fork_turns: "none"` when invoking the named agent) and provide the user goal, allowed change set, the complete pre-worker-baseline-relative tracked diff, complete relevant untracked-file evidence, interfaces and constraints, and the main session's verification evidence. Explicit immutable base and head revisions may replace the baseline-relative evidence only when they fully encode the entire reviewed change set and the relevant worktree is clean.
12. After `advisor_sol` returns, compare the repository state with the pre-review baseline, including relevant untracked-file content or hashes. Any mutation during review invalidates the verdict and must be investigated without overwriting unrelated changes.
13. Do not report completion unless the reviewer returns `VERDICT: ship`. Any subsequent change to the reviewed change set or verification-relevant repository state invalidates the verdict; verify again and obtain a new fresh review. Route bounded `fix-first` findings to `worker_luna` by default. Use `worker_terra` only when the finding introduces a valid Terra condition. Return `rethink` findings to `planner_sol` or the user.

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
