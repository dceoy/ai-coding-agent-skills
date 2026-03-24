# ai-coding-agent-skills

Agent skills for AI coders

## Overview

Single-source, reusable skills and agent prompts shared across AI coding runtimes. The `skills/` directory is the source of truth and is referenced by runtime-specific integrations:

- **Claude Code** — Agents in `.claude/agents/`; skills via `.claude/skills -> ../skills`
- **GitHub Copilot CLI** — Skills via `.github/skills -> ../skills`
- **OpenAI Codex CLI** — Skills via `.codex/skills -> ../skills`
- **Gemini CLI** — Unified `gemini-cli` skill in `skills/gemini-cli/`, used by `.claude/agents/gemini.md`

Each skill directory contains a `SKILL.md` that documents prerequisites and invocation.

## Quick start

1. Clone the repo:

   ```bash
   git clone git@github.com:dceoy/ai-coding-agent-skills.git
   ```

2. Pick a runtime and explore the skills in `skills/` and the relevant runtime integration:
   - **Claude Code:** `.claude/agents/` (agent definitions), `.claude/skills -> ../skills`
   - **Codex CLI:** `.codex/skills -> ../skills`
   - **GitHub Copilot CLI:** `.github/skills -> ../skills`
   - **Gemini CLI:** `skills/gemini-cli/` (unified skill), `.claude/agents/gemini.md` (agent definition)

3. Open a skill directory and read the `SKILL.md` to learn how to invoke it.

## Skills

All skills are located in `skills/` and symlinked into runtime-specific directories.

### Claude Code Integration

- `claude-ask` - Ask questions about code (read-only)
- `claude-exec` - Execute development tasks with code modifications
- `claude-review` - Perform code reviews (read-only)
- `claude-search` - Search the web for current information (read-only)

### OpenAI Codex CLI Integration

- `codex-ask` - Ask questions about code (read-only)
- `codex-exec` - Execute development tasks with code modifications
- `codex-review` - Perform code reviews (read-only)
- `codex-search` - Search the web for current information (read-only)

### GitHub Copilot CLI Integration

- `copilot-cli` - Unified GitHub Copilot CLI skill for ask, exec, review, and search workflows

### Gemini CLI Integration

- `gemini-cli` - Unified Gemini CLI skill for ask, exec, review, and Google Search-grounded workflows

### Git Workflows

- `clean-gone-branches` - Clean up local branches marked as [gone] and their worktrees
- `commit` - Create a git commit with an appropriate message
- `commit-push-pr` - Commit, push, and open a pull request

### Code Quality

- `code-review` - Comprehensive multi-agent code review for pull requests
- `code-simplifier` - Simplify and refine code for clarity and maintainability

### Skill Management

- `claude-agent-converter` - Convert Claude Code agents to portable skills
- `claude-command-converter` - Convert Claude Code commands to portable skills

## Agents

Agents are located in `.claude/agents/` and provide unified interfaces for each CLI tool.

| Agent        | Description                                                 |
| ------------ | ----------------------------------------------------------- |
| `codex.md`   | Unified Codex CLI agent (ask, exec, review, search modes)   |
| `copilot.md` | Unified Copilot CLI agent (ask, exec, review, search modes) |
| `gemini.md`  | Unified Gemini CLI agent (ask, exec, review, search modes)  |

See [AGENTS.md](./AGENTS.md) for detailed agent documentation.

## Structure

```
.
├── skills/                  # Shared skill directories (source of truth)
│   ├── claude-*/            # Claude Code integration skills
│   ├── codex-*/             # Codex CLI integration skills
│   ├── copilot-cli/         # Unified Copilot CLI skill
│   └── gemini-cli/          # Unified Gemini CLI skill
├── .claude/
│   ├── agents/              # Agent definitions (codex.md, copilot.md, gemini.md)
│   └── skills -> ../skills
├── .codex/
│   └── skills -> ../skills
├── .github/
│   ├── skills -> ../skills
│   └── workflows/           # CI workflows (ci.yml)
├── AGENTS.md                # Agent repository guidelines
├── CLAUDE.md -> AGENTS.md   # Symlink for Claude Code
├── README.md                # This file
└── LICENSE
```

## Prerequisites

Install and authenticate the required CLI tools before running skills:

- **Claude Code** - For `claude-*` skills and `.claude/` agents
  - Install: <https://docs.anthropic.com/en/docs/claude-code>
  - Auth: Follow CLI onboarding flow

- **GitHub Copilot CLI** - For the `copilot-cli` skill
  - Install: <https://docs.github.com/en/copilot/github-copilot-in-the-cli>
  - Auth: start `copilot` and run `/login` (requires GitHub Copilot subscription)

- **OpenAI Codex CLI** - For `codex-*` skills
  - Install: <https://github.com/openai/codex>
  - Auth: ChatGPT subscription or API key in `~/.codex/config.toml`

- **Gemini CLI** - For the `gemini-cli` skill and `.claude/agents/gemini.md`
  - Install: <https://github.com/google-gemini/gemini-cli>
  - Auth: Google account or API key

## Usage notes

- Skills do not always auto-run; use your agent's skill invocation flow or ask for the skill explicitly.
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
  - Copilot CLI: `copilot` then `/login`
  - Codex CLI: `codex` (follow auth flow) or configure `~/.codex/config.toml`
  - Gemini CLI: `gemini` (follow auth flow)
- Verify active subscription (Copilot, ChatGPT) or API key

**Symlink issues**

- Skill directories are shared from `skills/` via symlinks (`.claude/skills`, `.codex/skills`, `.github/skills`)
- If broken, recreate the symlink or ensure `skills/` exists
- On Windows, ensure symlink support is enabled

## Contributing

See [AGENTS.md](./AGENTS.md) for repository guidelines and agent-specific rules.

## License

See [LICENSE](./LICENSE) for details.
