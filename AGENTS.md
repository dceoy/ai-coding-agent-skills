# Repository Guidelines

## Repository Purpose

This is a single-source skill library shared across AI coding runtimes. The `skills/` directory is the authoritative source of truth; runtime-specific directories reference it via symlinks.

## Native named-agent dispatch

This section is Codex's default routing for non-trivial implementation work when no portable skill defines its own orchestration. A portable skill such as `pr-loop` follows its own `SKILL.md` contract instead; see [Portable native-subagent contract](#portable-native-subagent-contract) below.

`planner` and `advisor` must be invoked through Codex's native multi-agent tools. Do not invoke them through `codex exec`, nested Codex CLI processes, shell wrappers, copied prompts, generic agents, or simulations.

Invoke `planner` with `fork_turns: "all"` so planning inherits the full parent conversation, preserving user intent and prior decisions without a lossy context-packet reconstruction. Invoke `advisor` with `fork_turns: "none"` so advisory work starts from a fresh context; pass only the task-specific contract and primary evidence it needs.

Treat the installed agent TOML as the source of truth for the named role, model, and requested sandbox default. Reasoning effort is deliberately selected per native dispatch rather than pinned in the agent definition. A successful native dispatch to the requested named role is sufficient; the runtime does not need to echo those configuration values back to the parent. A broader effective sandbox such as `workspace-write` does not by itself invalidate the invocation when the named-agent mutation guard below can be established: `planner` and `advisor` remain behaviorally read-only and must not modify files. Treat the invocation as `unsupported` only when available runtime evidence explicitly shows that native dispatch is unavailable, a generic or different agent was used, the configured model was overridden, an explicitly requested per-dispatch reasoning effort was overridden incompatibly, `planner` failed to inherit the requested full parent turns, `advisor` inherited parent turns contrary to `fork_turns: "none"`, or a writable invocation cannot be guarded because the workspace is not a Git worktree. Missing runtime telemetry, an adaptively selected reasoning effort, or a writable effective sandbox alone is not evidence of a mismatch.

Reasoning effort for `planner` and `advisor` is adaptive by dispatch policy. Their TOML files intentionally omit `model_reasoning_effort`. Before each spawn, explicitly select and pass the lowest adequate supported effort for the task instead of relying on `[agents]` defaults or parent-effort inheritance: use `medium` for routine non-trivial planning or review, `high` for complex or cross-cutting work, and `xhigh` only for unusually demanding work.

Implementation is owned by the top-level main agent. Do not delegate implementation to named or generic worker subagents. If native dispatch is explicitly unavailable or incompatible with the configured role, report `unsupported` rather than silently omitting, downgrading, or simulating a phase.

### Planner context handoff

Because `planner` runs with `fork_turns: "all"`, preserve the parent conversation as the authoritative source for the user's request, prior decisions, constraints, and unresolved questions. Do not reconstruct those items into a separate mandatory context packet or replace inherited history with an implementation-oriented summary.

The planner dispatch should state the planning task and add only task-specific context that is not already available in the inherited conversation, such as newly inspected repository state or relevant implementation evidence. If the parent context contains stale or superseded information, explicitly identify the newer evidence instead of silently rewriting prior decisions.

### Named-agent mutation guard

For every `planner` or `advisor` invocation in a Git worktree, immediately before dispatch record a Git-visible baseline: `HEAD` when it exists (otherwise an explicit unborn-`HEAD` sentinel), index diff, tracked worktree diff, and every non-ignored untracked path with a content digest. Compare the same state immediately after return. Any persistent Git-visible mutation introduced during the invocation invalidates the result; preserve changes that already existed in the baseline. If available runtime output or telemetry explicitly shows a mutating action, including a transient edit that was restored before return, invalidate the result even when the post-dispatch baseline matches. Ignored and generated files are intentionally outside the persistent-state comparison. If the workspace is not a Git worktree, require an effective read-only sandbox; do not accept a writable effective sandbox without this guard. This guard establishes persistent Git-visible state integrity; it does not prove that a writable runtime performed no transient writes. The named agents remain behaviorally read-only and must not intentionally edit files. Do not describe this guard as runtime-enforced read-only or mutation-free execution.

## Portable native-subagent contract

A portable skill such as `skills/pr-loop/SKILL.md` may use whichever native mechanism the active coding-agent runtime provides for launching a fresh, independent, read-only subagent (for example Claude Code's subagent/Task launch mechanism, a native Codex multi-agent dispatch with no inherited turns, or Cursor's equivalent independent-agent mechanism). Such a skill must not require `.codex/agents`, `planner.toml`, `advisor.toml`, a fixed agent name, a fixed model, or a fixed provider; it expresses planning, review, and feedback-analysis as logical roles, not named agents. Do not launch `codex`, `claude`, `cursor-agent`, or another coding-agent CLI as a subprocess to emulate an unavailable native subagent, and do not perform an advisory phase directly in the main agent's own context in place of a real independent subagent. When the active runtime exposes no suitable native mechanism for a required phase, the skill must report that phase as `unsupported` rather than silently downgrading it. Implementation, QA, and all Git/GitHub mutations remain owned by the top-level main agent in every case.

The Codex-specific `planner`/`advisor` routing above, and the project-scoped definitions under `.codex/agents/`, are one optional, Codex-specific implementation of a native-subagent mechanism. They are not required by, and must stay separate from, any portable skill's own execution contract.

## Model routing

This section applies only to the top-level main agent when no portable skill defines its own orchestration. A portable skill such as `pr-loop` follows its own `SKILL.md` contract instead; its planning, review, and feedback-analysis roles must not be routed through the named `planner` and `advisor` agents below. The named `planner` and `advisor` agents follow their own definitions and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and narrow, deterministic edits when planning overhead is not justified.

For non-trivial implementation tasks:

1. Apply the named-agent mutation guard, select and pass the planner reasoning effort according to the adaptive policy above, then invoke `planner` with `fork_turns: "all"` in a behaviorally read-only child context. Let the inherited parent conversation carry the user's request, settled decisions, constraints, and open questions; add only newly inspected repository state or task-specific evidence needed for planning. Obtain a decision-complete contract covering objective, scope, interfaces, constraints, and verification. Prefer the configured read-only sandbox, but accept the contract when native dispatch returns the requested planner result unless runtime evidence explicitly reports a fallback, incompatible model override, failure to honor the explicitly requested reasoning effort, failure to inherit the requested parent turns, or a writable invocation outside a Git worktree. A writable effective sandbox alone is not a failure condition when the guard can be established.
2. Route planner decisions before implementation. If the planner returns `STATUS: blocked`, obtain the smallest missing user decision and replan. If it returns `STATUS: ready`, preserve decisions already settled by the user. Require explicit user approval only when the contract introduces or changes a material user-facing or requirement-level decision that is not already settled, including observable product behavior, API or compatibility guarantees, architecture with meaningful trade-offs, destructive or irreversible migration, security posture, significant scope expansion, or a new requirement. The main agent may approve tactical and operational implementation details internally when they stay within the established contract. Do not invent requirements or reopen settled decisions without cause.
3. Pass the approved contract to the top-level main agent and implement it directly. Keep the main agent's reasoning effort at the user-selected or current-session setting; this routing policy must not set, override, or require a particular reasoning effort. Do not delegate implementation to a worker subagent.
4. Inspect the actual changes, preserve unrelated work, and run the relevant verification from the planner contract.
5. Invoke `advisor` only when an independent second opinion materially improves decision quality or confidence. Appropriate triggers include an explicit user request; unresolved architecture, security, API, compatibility, migration, or other cross-cutting trade-offs; multiple plausible approaches with meaningful consequences; verification failures whose diagnosis remains uncertain; or a high-risk/regression-prone implementation where independent review is warranted. Skip advisor for routine, low-risk changes when the main agent can validate the result directly.
6. When `advisor` is invoked, apply the named-agent mutation guard, select and pass its reasoning effort according to the adaptive policy above, and use a fresh read-only context with `fork_turns: "none"`. For implementation review, provide the planner contract and primary evidence: the actual changed files or diff, relevant source and test configuration, and verification commands and results. Treat implementation decisions, summaries, and reported verification outcomes as claims rather than authoritative evidence; the advisor must independently inspect available primary evidence. Treat the advisor result as guidance rather than independent approval: apply supported `fix-first` findings in the main agent, return material `rethink` findings to `planner`, and surface any conflict where verified primary evidence contradicts the advice instead of following it mechanically. Rerun relevant verification after changes. Re-invoke `advisor` only when another independent opinion remains materially useful or the user explicitly requests it; do not loop solely to obtain `VERDICT: ship`. The verdict is an advisory classification, not a completion gate. An `unsupported` advisor result blocks completion only when the user explicitly required the consultation or a material risk remains unresolved and cannot be validated independently.

The planner and advisor TOML files intentionally omit `model_reasoning_effort` and configure read-only sandbox defaults. Select reasoning effort explicitly whenever either named agent is dispatched. Runtime sandbox broadening alone must not block execution when the mutation guard can be established. Every named-agent invocation must use the Git-visible mutation guard above before its result is accepted; outside a Git worktree, require an effective read-only sandbox instead.

For architecture, design evaluation, or technical advice without implementation, invoke `advisor` when its independent judgment is useful or when the user explicitly requests it. Apply the same named-agent mutation guard, select advisor effort adaptively, and keep the work behaviorally read-only.

Do not invoke a subagent when the main agent can complete a non-implementation task safely and efficiently without delegation.

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
