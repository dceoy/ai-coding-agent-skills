# Repository Guidelines

## Repository Purpose

This is a single-source skill library shared across AI coding runtimes. The `skills/` directory is the authoritative source of truth; runtime-specific directories reference it via symlinks.

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
