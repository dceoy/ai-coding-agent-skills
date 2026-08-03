# ai-coding-agent-skills

Agent skills for AI coders

## Overview

Single-source, reusable skills and agent prompts shared across AI coding runtimes. The `skills/` directory is the source of truth and is referenced by runtime-specific integrations via `.claude/skills -> ../skills` and per-skill symlinks under `.agents/skills/` (e.g. `.agents/skills/<skill> -> ../../skills/<skill>`). Autonomous or scheduled workflows should invoke these canonical skills instead of maintaining duplicate routine prompts.

Each skill directory contains a `SKILL.md` that documents prerequisites and invocation.

## Quick start

1. Clone the repo:

   ```bash
   git clone git@github.com:dceoy/ai-coding-agent-skills.git
   ```

2. Pick a runtime and explore the relevant integration:
   - **Claude Code / Claude Code Routines:** `.claude/skills -> ../skills` (symlink exposing all skills)
   - **Codex CLI skills:** `.agents/skills/` (per-skill symlinks into `skills/`)
   - **Codex CLI custom subagents:** `.codex/agents/` (project-scoped definitions discovered automatically by current Codex releases)

3. Open a skill directory or `.codex/agents/README.md` to learn how to invoke it.

## Skills

All skills are located in `skills/` and surfaced through shared discovery or runtime-specific symlinks.

### Git Workflows

- `clean-gone-branches` - Clean up local branches marked as [gone] and their worktrees
- `commit` - Create a git commit with an appropriate message
- `commit-push-pr` - Commit, push, and open a pull request

### Code Quality

- `code-review` - Comprehensive multi-agent code review for pull requests
- `code-simplifier` - Simplify and refine code for clarity and maintainability
- `pr-feedback-triage` - Triage and resolve pull request review feedback
- `pr-review` - Autonomous CI/GitHub PR review that posts concise, high-confidence findings by default
- `security-guidance` - Security-focused review of code changes, diffs, commits, and pull requests

### AI Tools

- `codex` - Use OpenAI Codex from AI coding agents for code reviews, adversarial reviews, and task delegation

### Skill Management

- `claude-agent-converter` - Convert Claude Code agents to portable skills
- `claude-command-converter` - Convert Claude Code commands to portable skills

## Codex Custom Subagents

Project-scoped agent definitions under `.codex/agents/` use a plan, Luna-first implement, parent verify, and fresh-review workflow. Codex discovers each standalone TOML file automatically; no per-agent registration in `.codex/config.toml` is required. All four agents use maximum reasoning effort.

- `planner_sol` - Produce a five-part implementation contract and Luna-first executor recommendation with `gpt-5.6-sol`
- `advisor_sol` - Provide read-only technical advice or fresh final review with `gpt-5.6-sol`
- `worker_luna` - Default implementation worker for bounded, settled, and verifiable contracts with `gpt-5.6-luna`
- `worker_terra` - Escalation worker for bounded ownership-zone discovery or adaptive decisions with `gpt-5.6-terra`

Use Luna by default whenever exact scope, interfaces, constraints, and acceptance evidence are settled. Use Terra only after material decisions are settled and an explicit bounded-discovery or adaptive-judgment condition remains; complexity or multiple files alone do not justify Terra. The main agent captures a pre-worker repository baseline, verifies only the worker-introduced delta, reruns validation, guards against reviewer mutation, and obtains a fresh Sol verdict before completion.

See [.codex/agents/README.md](./.codex/agents/README.md) for routing rules, permission behavior, and invocation examples.

## Structure

```
.
├── skills/                  # Shared skill directories (source of truth)
├── .agents/
│   └── skills/              # Per-skill symlinks into skills/ (other runtimes)
├── .claude/
│   └── skills -> ../skills  # Symlink exposing skills/ to Claude Code runtime
├── .codex/
│   └── agents/              # Project-scoped Codex custom subagents
├── .github/
│   └── workflows/           # CI workflows (ci.yml)
├── AGENTS.md                # Repository guidelines (source of truth)
├── CLAUDE.md -> AGENTS.md   # Symlink for Claude Code
├── README.md                # This file
└── LICENSE
```

## Prerequisites

Install and authenticate the required CLI tools before running skills:

- **Claude Code** - For `.claude/` agents and skills
  - Install: <https://docs.anthropic.com/en/docs/claude-code>
  - Auth: Follow CLI onboarding flow
- **Codex CLI / Codex plugin** - For the `codex` skill
  - Full Claude Code integration: install `openai/codex-plugin-cc` and run `/codex:setup`
  - Standalone / generic agent usage: install `@openai/codex` and run `codex login`
  - Plugin-managed operations (status/result/cancel/transfer) require the Claude Code plugin context

## Usage notes

- Skills do not always auto-run; use your agent's skill invocation flow or ask for the skill explicitly.
- For Claude Code Routines, CI, and other autonomous workflows, invoke the canonical skill under `skills/` and pass runtime-specific context externally.
- `pr-review` is the source of truth for autonomous PR review behavior, including GitHub posting and verification.
- If a skill fails, open its `SKILL.md` and verify prerequisites and command syntax.

## Troubleshooting

**Skill not found**

- Confirm the skill directory exists in the expected runtime location
- Check that skill name matches exactly (case-sensitive)
- Verify the `SKILL.md` documentation is present

**CLI not in PATH**

- Ensure the tool is installed and accessible: `which <tool-name>`
- Add the tool's bin directory to your shell PATH
- Restart your terminal after installation

**Authentication errors**

- Re-run the tool's auth command:
  - Claude Code: Follow onboarding flow
  - Codex CLI: run `codex login`
  - Codex Claude Code plugin: run `/codex:setup`
- Verify active subscription or API key

**Symlink issues**

- Skill directories are shared from `skills/` via `.agents/skills` and `.claude/skills`
- If broken, recreate the symlink or ensure `skills/` exists
- On Windows, ensure symlink support is enabled

## Contributing

See [AGENTS.md](./AGENTS.md) for repository guidelines and agent-specific rules.

## License

See [LICENSE](./LICENSE) for details.
