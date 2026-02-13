# Agent Repository Guidelines

Guidelines for editing agent definitions, skills, and prompts in this repository.

## Project Structure

### Shared Skills (`skills/`)

- `skills/` - Source of truth for all skill directories (claude-_, copilot-_, codex-\_, gemini-\_)

### Claude Code Runtime (`.claude/`)

- `.claude/agents/` - Agent definitions for autonomous task execution (codex-_, copilot-_, gemini-\*)
- `.claude/skills/` - Symlink to `../skills/`

### Codex CLI Runtime (`.codex/`)

- `.codex/skills/` - Symlink to `../skills/`

### GitHub Copilot CLI Runtime (`.github/`)

- `.github/skills/` - Symlink to `../skills/`
- `.github/workflows/` - CI workflow definitions (ci.yml)

### Repository Layout

```
.
├── skills/                  # Shared skill directories (source of truth)
├── .claude/
│   ├── agents/              # Agent definitions (codex.md, copilot.md, gemini.md)
│   └── skills -> ../skills
├── .codex/
│   └── skills -> ../skills
├── .github/
│   ├── skills -> ../skills
│   └── workflows/           # CI workflows (ci.yml)
├── AGENTS.md                # Agent repository guidelines (canonical; edit this file)
├── CLAUDE.md -> AGENTS.md   # Symlink for Claude Code
├── README.md                # Repository overview
└── LICENSE
```

### Root Documentation

- `README.md` - Repository overview and quick start
- `AGENTS.md` - This file (agent guidelines)
- `CLAUDE.md` - Symlink to AGENTS.md (do not edit directly)
- `LICENSE` - Repository license

## Canonical Files

- `CLAUDE.md` is a symlink to `AGENTS.md`. Edit `AGENTS.md` only.

## Prerequisites

Install and authenticate the required CLI tools before running skills:

- **Claude Code** - <https://docs.anthropic.com/en/docs/claude-code>
- **GitHub Copilot CLI** - <https://docs.github.com/en/copilot/github-copilot-in-the-cli>
- **OpenAI Codex CLI** - <https://github.com/openai/codex>
- **Gemini CLI** - <https://github.com/google-gemini/gemini-cli>

## Coding Style & Naming

**Markdown Files**

- Use Markdown for docs, prompts, and agent definitions
- Keep headings short and descriptive
- Prefer fenced code blocks for examples
- Keep instructions concise and task-focused

**File Naming**

- Skills: `<tool>-<action>` directories (e.g., `codex-ask/`, `copilot-review/`)
- Agents: `<tool>-<action>.md` (e.g., `codex-ask.md`, `gemini-exec.md`)
- Use kebab-case for multi-word names

**YAML Files**

- 2-space indentation (see `.github/workflows/ci.yml`)
- If present, skill configs use `skill.yaml` in each skill directory
- Boolean values: `true`/`false` (lowercase)

**Skill Structure**
Each skill directory must contain:

- `SKILL.md` - Documentation and usage instructions
- `skill.yaml` (optional) - Skill configuration and metadata

## Symlink Strategy

This repository uses symlinks to share skills across runtimes:

**Source Skills** (`skills/`)

- Primary location for all skills with `SKILL.md`

**Symlinked Skills**

- `.claude/skills/`, `.codex/skills/`, `.github/skills/` - Symlink to `../skills/`

**Benefits**

- Single source of truth for shared skills
- Easy maintenance (edit once, works everywhere)
- Reduced duplication

**When Adding/Modifying Skills**

1. Create/edit skills in `skills/` (source of truth)
2. Ensure runtime directories remain symlinked to `../skills/` (e.g., `ls -la .claude/skills`)

## Skills Overview

Shared `skills/` directory (symlinked into `.claude/skills`, `.codex/skills`, `.github/skills`):

- **Claude Code**: `claude-ask`, `claude-exec`, `claude-review`, `claude-search`
- **OpenAI Codex CLI**: `codex-ask`, `codex-exec`, `codex-review`, `codex-search`
- **GitHub Copilot CLI**: `copilot-ask`, `copilot-exec`, `copilot-review`, `copilot-search`
- **Gemini CLI**: `gemini-ask`, `gemini-exec`, `gemini-review`, `gemini-search`
- **Git Workflows**: `clean-gone-branches`, `commit`, `commit-push-pr`
- **Code Quality**: `code-review`, `code-simplifier`
- **Skill Management**: `claude-agent-converter`, `claude-command-converter`

## Validation

- Review diffs with `git diff` before committing
- Check that Markdown renders cleanly in GitHub preview
- Verify symlinks are not broken: `find . -xtype l` (should return nothing)
- When adding/renaming agents or skills, update indexes:
  - `README.md` - Skills and structure sections
  - `AGENTS.md` - Project structure and CLI Agents sections

## Commit & Pull Request Guidelines

- Commit messages are short, imperative, sentence-case.
- Branch names use appropriate prefixes on creation (e.g., `feature/short-description`, `bugfix/short-description`).
- PRs should include: a clear summary, relevant context or linked issue.
- When instructed to create a PR, create it as a draft with appropriate labels by default.

## Agent-Specific Notes

- Agent and prompt files are the product of this repo—treat them as source of truth.
- Prefer small, focused edits per file for reviewability.

## Codex CLI Agents

Specialized Claude Code agents that integrate OpenAI Codex CLI capabilities for autonomous development tasks.

### Available Agents

**codex-ask** - Answer questions about code (read-only)

- Uses Codex to analyze code and provide detailed answers
- Includes file references and line numbers
- Shows code examples
- Never modifies code

Use for: Understanding existing code, exploring architecture, finding implementations, learning patterns, debugging assistance

**codex-exec** - Execute development tasks with code modifications

- Generates new code and refactors existing code
- Adds features and fixes bugs
- Creates tests
- Modifies code files

Use for: Code generation, refactoring, feature implementation, bug fixes, test creation

**codex-review** - Perform comprehensive code reviews (read-only)

- Identifies bugs and security vulnerabilities
- Detects performance problems
- Suggests improvements
- Provides actionable feedback
- Never modifies code

Use for: Pre-commit checks, pull request reviews, security audits, performance analysis, code quality assessment

**codex-search** - Search the web for current information (read-only)

- Searches documentation, best practices, and solutions
- Finds API references and tutorials
- Researches library comparisons and approaches
- Provides sourced, verified information
- Never modifies code

Use for: Finding documentation, researching solutions, comparing libraries, learning new technologies, troubleshooting errors

### Usage Patterns

Simply describe your task to Claude Code, and it will launch the appropriate agent:

```
"Can you help me understand how authentication works?"
→ Launches codex-ask agent

"Add input validation to the registration form"
→ Launches codex-exec agent

"Review my changes for security issues"
→ Launches codex-review agent

"What's the best library for JWT authentication in 2026?"
→ Launches codex-search agent
```

### Workflow Patterns

**Understand → Execute → Review**

1. Launch codex-ask: Understand current implementation
2. Launch codex-exec: Make improvements
3. Launch codex-review: Verify changes

**Pre-Commit Workflow**

1. Make changes to code
2. Launch codex-review: Review uncommitted changes
3. Launch codex-exec: Fix identified issues
4. Launch codex-review: Final verification
5. Commit with confidence

**Feature Development**

1. Launch codex-search: Research best practices and libraries
2. Launch codex-ask: Understand existing patterns in codebase
3. Launch codex-exec: Implement following patterns
4. Launch codex-exec: Create tests
5. Launch codex-review: Review implementation

**Research → Understand → Execute → Review**

1. Launch codex-search: Find current documentation and approaches
2. Launch codex-ask: Understand how it fits with current code
3. Launch codex-exec: Implement the solution
4. Launch codex-review: Verify quality and security

### Prerequisites

- Codex CLI installed and available in PATH
- ChatGPT Plus/Pro/Team/Enterprise subscription or OpenAI API key in `~/.codex/config.toml`
- Internet connection for API access

### Configuration

Global config (`~/.codex/config.toml`):

```toml
[general]
model = "gpt-4o"

[execution]
auto_approve = false

[api]
# If using API key:
# key = "sk-..."
```

Project config (`.codex/config.toml`, optional):

```toml
[project]
name = "your-project-name"
language = "typescript"
```

### Agent Files

```
.claude/agents/
└── codex.md  # Unified Codex agent (ask, exec, review, search modes)
```

## Copilot CLI Agents

Specialized Claude Code agents that integrate GitHub Copilot CLI capabilities for autonomous development tasks.

### Available Agents

**copilot-ask** - Answer questions about code (read-only)

**copilot-exec** - Execute development tasks with code modifications

**copilot-review** - Perform comprehensive code reviews (read-only)

**copilot-search** - Search the web for current information (read-only)

### Agent Files

```
.claude/agents/
└── copilot.md  # Unified Copilot agent (ask, exec, review, search modes)
```

## Gemini CLI Agents

Specialized Claude Code agents that integrate Gemini CLI capabilities for autonomous development tasks.

### Available Agents

**gemini-ask** - Answer questions about code (read-only)

**gemini-exec** - Execute development tasks with code modifications

**gemini-review** - Perform comprehensive code reviews (read-only)

**gemini-search** - Search the web for current information (read-only)

### Agent Files

```
.claude/agents/
└── gemini.md  # Unified Gemini agent (ask, exec, review, search modes)
```
