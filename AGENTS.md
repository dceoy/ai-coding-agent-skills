# Repository Guidelines

## Repository Purpose

This is a single-source skill library shared across AI coding runtimes. The `skills/` directory is the authoritative source of truth; runtime-specific directories reference it via symlinks.

## Model routing

This section applies only to the root or main agent that receives the user's task. Named custom agents (`planner_sol`, `advisor_sol`, `worker_terra`, and `worker_luna`) must ignore this section, follow their agent-specific instructions, and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and narrow, deterministic edits.

For non-trivial implementation tasks:

1. Spawn `planner_sol` before modifying files.
2. Wait for the complete plan and preserve its constraints and acceptance checks.
3. Start exactly one implementation agent:
   - Use `worker_luna` for localized, low-risk changes with explicit scope and mechanical validation.
   - Use `worker_terra` for diagnosis, cross-cutting changes, ambiguity, or non-trivial implementation.
4. If implementation encounters an architectural, security, compatibility, or data-model decision not covered by the plan, return control to `planner_sol` or `advisor_sol`.
5. Do not run write-capable workers concurrently. A sequential Luna-to-Terra handoff is allowed only after Luna has stopped and reported all partial edits.

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
