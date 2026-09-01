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

- `parameterized-tests` - Prefer native parameterized or table-driven tests for repeated unit-test cases that share the same test logic
- `pr-feedback-triage` - Triage and resolve pull request review feedback
- `pr-loop` - Issue-to-PR and iterative PR review/fix loop using native independent subagents
- `pr-review` - Autonomous CI/GitHub PR review that posts concise, high-confidence findings by default
- `simplify-codebase` - Reduce maintenance surface under KISS/DRY/YAGNI, explicitly or proactively when worthwhile

### AI Tools

- `oracle-chatgpt` - Send one arbitrary prompt to ChatGPT through Oracle browser mode and return the captured response without reinterpretation
- `x-timeline` - Read authenticated X timelines through agent-browser without engagement actions

### Skill Management

- `claude-agent-converter` - Convert Claude Code agents to portable skills
- `claude-command-converter` - Convert Claude Code commands to portable skills

## Codex Custom Subagents

Project-scoped definitions under `.codex/agents/` provide four native read-only roles:

- `planner` - Produce a decision-complete implementation plan
- `advisor` - Provide on-demand technical advice or implementation review
- `reviewer` - Review one caller-defined lens against an exact revision
- `feedback-analyst` - Analyze review feedback into source-preserving dispositions and fix guidance

Models and reasoning effort are intentionally unpinned in the TOML files and selected at dispatch time. Role defaults are planner=Terra, advisor=Sol, reviewer correctness=Terra, tests/docs=Luna, security/performance=Terra, other scopes=Terra, and feedback-analyst=Luna, with escalation defined in `.codex/AGENTS.md`. Effort is model-specific: Luna=`max`, Terra=`xhigh|max`, Sol=`high|xhigh|max`. Implementation remains in the top-level main agent.

See [.codex/AGENTS.md](./.codex/AGENTS.md) for the authoritative routing policy and [.codex/agents/README.md](./.codex/agents/README.md) for installation.

## Structure

```text
.
├── skills/                  # Shared skill directories (source of truth)
├── .agents/
│   └── skills/              # Per-skill symlinks into skills/ (other runtimes)
├── .claude/
│   └── skills -> ../skills  # Symlink exposing skills/ to Claude Code runtime
├── .codex/
│   ├── AGENTS.md            # Codex user-wide routing template
│   └── agents/              # Project-scoped Codex custom subagents
├── .github/
│   └── workflows/           # CI workflows (ci.yml)
├── README.md
└── LICENSE
```

## Prerequisites

Install and authenticate the required CLI tools before running skills:

- **Claude Code** - For `.claude/` agents and skills
  - Install: <https://docs.anthropic.com/en/docs/claude-code>
  - Auth: Follow CLI onboarding flow
- **Codex CLI** - For `.agents/skills/` and `.codex/agents/`
  - Install: `npm install -g @openai/codex`
  - Auth: run `codex login`
- **Oracle CLI** - For `oracle-chatgpt`
  - Install: `npm install -g @steipete/oracle`
  - ChatGPT: sign in for Oracle browser mode
  - Remote browser routing is optional and uses Oracle's native configuration
- **agent-browser** - For `x-timeline`
  - Install: `npm install -g agent-browser` (or the package manager your environment uses), so `agent-browser` is on
    `PATH`
  - No custom wrapper, browser service, or MCP server is required or bundled; `x-timeline` invokes `agent-browser`
    directly and fails closed if the installed workflow cannot enforce its documented safeguards.
  - `x-timeline` prefers a reusable dedicated X session already on `https://x.com/home`, so routine reads need no
    navigation or tab-selection action. Initial setup and tab changes use guarded actions and capability-check the
    installed `agent-browser` workflow instead of pinning behavior to a specific upstream release number.

## Usage notes

- Skills do not always auto-run; use your agent's skill invocation flow or ask for the skill explicitly.
- For Claude Code Routines, CI, and other autonomous workflows, invoke the canonical skill under `skills/` and pass runtime-specific context externally.
- `pr-review` is the source of truth for autonomous PR review behavior, including GitHub posting and verification.
- If a skill fails, open its `SKILL.md` and verify prerequisites and command syntax.

## Troubleshooting

### Skill not found

- Confirm the skill directory exists in the expected runtime location
- Check that skill name matches exactly (case-sensitive)
- Verify the `SKILL.md` documentation is present

### CLI not in PATH

- Ensure the tool is installed and accessible: `which <tool-name>`
- Add the tool's bin directory to your shell PATH
- Restart your terminal after installation

### Authentication errors

- Re-run the tool's auth command:
  - Claude Code: Follow onboarding flow
  - Codex CLI: run `codex login`
- Verify active subscription or API key

### Symlink issues

- Skill directories are shared from `skills/` via `.agents/skills` and `.claude/skills`
- If broken, recreate the symlink or ensure `skills/` exists

## License

See [LICENSE](./LICENSE) for details.
