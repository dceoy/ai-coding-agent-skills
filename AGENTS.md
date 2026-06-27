# Repository Guidelines

## Repository Purpose

This is a single-source skill library shared across AI coding runtimes. The `skills/` directory is the authoritative source of truth; runtime-specific directories reference it via symlinks.

## Architecture

```
skills/                        # Source of truth for all skills
├── <skill-name>/SKILL.md      # Each skill is a directory with a SKILL.md
.claude/skills -> ../skills    # Symlink: exposes skills/ to Claude Code runtime
.agents/skills/                # Per-skill symlinks into skills/ (other runtimes)
routines/                      # Claude Code Routines (scheduled cloud agents)
tests/                         # Python tests for QA validation
pyproject.toml                 # Local QA tooling: ruff, pyright, pytest
```

### SKILL.md Frontmatter

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

## Routines

The `routines/` directory contains instruction files for [Claude Code Routines](https://code.claude.com/docs/en/routines) — scheduled cloud agents that run autonomously on a cron schedule. Unlike skills (which are invoked interactively), routines run unattended and are self-contained.

Each routine is a plain Markdown file with no frontmatter. The file body is the instruction set the agent executes on each scheduled run.

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
