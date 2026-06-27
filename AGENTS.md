# Repository Guidelines

## Repository Purpose

This is a single-source skill library shared across AI coding runtimes. The `skills/` directory is the authoritative source of truth; runtime-specific directories reference it via symlinks.

## Architecture

```
skills/                        # Source of truth for all skills
├── <skill-name>/SKILL.md      # Each skill is a directory with a SKILL.md
.claude/agents/                # Claude Code agent definitions
.claude/skills -> ../skills    # Symlink: exposes skills/ to Claude Code runtime
.agents/skills/                # Standalone skill definitions for other runtimes
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

### Agent definitions (`.claude/agents/*.md`)

Agent files use frontmatter including `skills:` to restrict which skills the agent may invoke:

```yaml
---
name: <agent-name>
description: <trigger description>
tools: Read, Write, Edit, Grep, Glob, Bash, LSP, WebFetch, WebSearch
model: inherit
skills: <skill-name>
---
```

## Adding or Modifying Skills

1. Create or edit `skills/<skill-name>/SKILL.md` — this is the only file needed per skill.
2. Runtime symlinks pick up the change automatically; no additional wiring required.
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
