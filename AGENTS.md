# Repository Guidelines

## Repository Purpose

This is a single-source skill library shared across AI coding runtimes. The `skills/` directory is the authoritative source of truth; runtime-specific directories reference it via symlinks.

## Native named-agent dispatch

`planner_sol`, `worker_luna`, `worker_terra`, and `advisor_sol` must be dispatched only through Codex's native multi-agent tools. Do not invoke `codex exec`, nested Codex CLI processes, shell wrappers, equivalent subprocess dispatch, or agent simulations. If native named-agent dispatch is unavailable, stop and report `unsupported`; do not fall back to direct parent execution, generic children, or compatibility modes.

## Model routing

This section applies only to the root or main agent that receives the user's task. Named custom agents (`planner_sol`, `advisor_sol`, `worker_luna`, and `worker_terra`) must ignore this section, follow their agent-specific instructions, and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and narrow, deterministic edits when delegation overhead is not justified.

For non-trivial implementation tasks:

1. Spawn `planner_sol` before modifying files.
2. Require its five-part implementation contract: objective, files and ownership, interfaces, constraints, and verification.
3. Do not start implementation while a material architectural, product, security, authentication, authorization, data-model, migration, compatibility, or externally visible interface decision remains unresolved. Return the smallest blocking question to `planner_sol`, `advisor_sol`, or the user.
4. Preserve the approved contract's scope, settled decisions, interfaces, acceptance checks, ownership boundary, and recommended executor.
5. Before starting a write-capable worker, capture the approved full baseline: current `HEAD`, status, staged and unstaged diffs, untracked-file inventory, and content or a cryptographic hash for every relevant untracked file. Establish an attribution boundary from that state. Use a dedicated clean git worktree rooted at the captured `HEAD` only when the relevant approved workspace is clean. When the approved task depends on relevant staged, unstaged, or untracked state, either seed an isolated worktree from an immutable snapshot that exactly reproduces that full baseline and retain evidence linking the snapshot to the source state, or use the current worktree with exclusive write access to every approved ownership and verification-relevant path until parent verification and final evidence capture finish. Never delegate in a `HEAD`-only worktree that omits relevant approved uncommitted state. A baseline records pre-existing state but does not by itself attribute later concurrent writes.
6. Preflight whether the runtime can resolve the selected named worker, load its definition, and spawn its configured model. Retain parent-visible evidence of the resolved role, loaded definition source, configured model and reasoning effort, and the concrete runtime/backend result.

For every planning, implementation, Terra-escalation, and final-review phase, the parent must retain a runtime-metadata execution attestation. The attestation must record the phase and execution path, resolved named role and loaded definition source, configured and effective model, configured and effective reasoning effort, configured sandbox, and effective permission mode. Runtime metadata, not TOML contents or a child self-report, establishes effective values. Require effective `reasoning_effort=max` for `planner_sol`, the implementation executor (`worker_luna` or `worker_terra`), and `advisor_sol`. For final review, also attest a fresh separate session with no inherited implementation history, `fork_turns: "none"`, and effective read-only permission. Missing or lower effective reasoning is a fail-closed runtime result: stop and report unsupported or repair the parent evidence; it is never a Terra condition.

7. Start exactly one implementation agent:

- Use `worker_luna` by default when the objective is bounded, every modifiable repository file and generated-artifact path is enumerated exactly, architecture and externally visible interfaces are settled, and verification has concrete commands or inspectable acceptance evidence.
- Use `worker_terra` in `terra-escalation` mode only after all material decisions are settled and the contract defines a bounded ownership zone plus an explicit Terra condition: broad diagnosis where the exact affected files inside that zone are not yet known; cross-cutting adaptation whose exact file set must be discovered inside that zone; or a documented Luna suitability failure or escalation identifying the concrete adaptive judgment Luna could not complete within exact ownership.
- If native dispatch cannot resolve `worker_luna`, `worker_terra`, or its configured model, runtime unavailability is not a Terra condition; stop and report unsupported. Do not substitute direct parent execution, generic children, or compatibility modes.
- Complexity, multiple files, non-trivial implementation, or apparent need for engineering judgment alone do not justify Terra escalation. When exact file and artifact ownership is known, route to Luna first.

8. Require `worker_luna` to perform its pre-edit suitability check. If Luna declines before editing, review whether the reason is a valid Terra condition or an unresolved decision that requires replanning. If it escalates after partial edits, inspect and preserve its reported state, update the contract when necessary, and then perform a sequential native `worker_terra` handoff.
9. Do not run write-capable workers concurrently. Do not allow another process or user to write approved ownership or verification-relevant paths while the worker is active or while final review evidence is being frozen.
10. If implementation encounters a material decision not covered by the contract or must cross the approved ownership boundary, return control to `planner_sol` or `advisor_sol` instead of silently expanding scope.
11. Treat every worker report as claims that the main agent must verify:
    - treat worker `CHANGES` and `SCOPE` fields as claims about intentional edits, not as an authoritative repository delta; the parent must compute the complete baseline-relative tracked and relevant untracked delta from its captured approved baseline;
    - compare the post-worker repository state against the captured pre-worker baseline, including relevant pre-existing untracked-file content or hashes, rather than relying only on the current working-tree diff;
    - if an unexpected mutation appears in an owned or verification-relevant path, or attribution is uncertain because concurrent writes occurred, stop and reconcile or restart from an isolated full-baseline snapshot instead of classifying the mutation as worker-introduced;
    - inspect every attributable worker-introduced file and behavior change while preserving and excluding pre-existing edits;
    - confirm that `worker_luna` stayed within exact file and artifact ownership, or that Terra escalation stayed within its approved ownership zone;
    - rerun the relevant verification commands in the main session; and
    - resolve any discrepancy between the report and the actual evidence.
12. After parent verification, freeze the reviewed repository state and capture a second baseline, including content or cryptographic hashes for every relevant pre-existing untracked file. End the workspace-write implementation turn. Start a separate parent session in read-only mode and invoke the native named `advisor_sol` agent with no inherited implementation history (`fork_turns: "none"`). Provide the user goal, allowed change set, complete pre-worker-baseline-relative tracked diff, complete relevant untracked-file evidence, interfaces and constraints, and parent verification evidence. The frozen-review evidence packet must bind that review to one exact target: the canonical absolute worktree root with symlinks resolved, canonical absolute Git common-dir, canonical Git dir/worktree administrative identity, frozen `HEAD`, complete porcelain-v2 status including untracked files, and a SHA-256 manifest for every reviewed and verification-relevant path. If the target is an immutable materialization, also include its canonical location, immutable identifier or digest, source-worktree identity, and proof that it reproduces the frozen `HEAD`, status, and content manifest. The separate reviewer must verify this identity before inspection and use the same canonical worktree or materialization for review commands and the parent’s post-review comparison. Explicit immutable base and head revisions may replace the baseline-relative evidence only when they fully encode the entire reviewed change set and the relevant worktree is clean. Require visible runtime-metadata evidence that the native named `advisor_sol` definition resolved from its loaded source with configured and effective `gpt-5.6-sol`, configured and effective reasoning `max`, `fork_turns: "none"`, a fresh session with no inherited implementation history, and effective read-only permission. If native named-agent dispatch is unavailable, stop and report unsupported; if the target identity mismatches or any required attestation is missing or lower than required, return `fix-first` with `REMEDIATION: parent-evidence`; never accept `ship`.
13. Keep the attribution boundary in force through final review. After the reviewer returns, compare the repository state against the frozen pre-review baseline, including relevant untracked-file content or hashes, using the same canonical worktree or materialization and rechecking its identity. Any mutation during or between review handoff and completion, or any target identity mismatch, invalidates the verdict and requires investigation without overwriting unrelated changes.
14. Do not report completion unless an attested native `advisor_sol` reviewer returns `VERDICT: ship`. Any subsequent change to the reviewed change set or verification-relevant repository state invalidates the verdict. For `REMEDIATION: parent-evidence`, the parent must repair the review path or evidence packet and rerun review without delegating to an implementation worker. For `REMEDIATION: repository-change` or the repository-change portion of `mixed`, route bounded edits to native `worker_luna` by default; use native `worker_terra` escalation only when the finding introduces a valid Terra condition. Return `replan` or `rethink` findings to `planner_sol` or the user. Every repository change requires new parent verification and a fresh separate read-only review.

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
