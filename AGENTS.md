# Repository Guidelines

## Repository Purpose

This is a single-source skill library shared across AI coding runtimes. The `skills/` directory is the authoritative source of truth; runtime-specific directories reference it via symlinks.

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
