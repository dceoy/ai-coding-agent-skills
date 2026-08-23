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
- `pr-loop` - Portable Issue-to-PR and iterative PR review/fix loop using the active runtime's own native independent-subagent mechanism, with no Oracle or `.codex/agents` dependency
- `pr-review` - Autonomous CI/GitHub PR review that posts concise, high-confidence findings by default

### AI Tools

- `oracle-chatgpt` - Send one arbitrary prompt to ChatGPT through Oracle browser mode and return the captured response without reinterpretation
- `x-timeline` - Read authenticated X timelines through agent-browser without engagement actions

### Skill Management

- `claude-agent-converter` - Convert Claude Code agents to portable skills
- `claude-command-converter` - Convert Claude Code commands to portable skills

## Codex Custom Subagents

Project-scoped definitions under `.codex/agents/` provide two native read-only Codex roles:

- `planner` - Produce a decision-complete implementation plan with `gpt-5.6-sol`
- `advisor` - Provide on-demand read-only technical advice or implementation review with `gpt-5.6-sol`

Both roles keep `gpt-5.6-sol` pinned but intentionally omit `model_reasoning_effort`. Their reasoning effort is adaptive by dispatch policy: before each native spawn, choose and pass the lowest adequate supported effort for the task instead of inheriting the parent or global default blindly. Use `medium` for routine non-trivial planning or review, `high` for complex or cross-cutting work, `xhigh` for unusually demanding work, and `max` only for the hardest quality-first work where maximum reasoning is materially useful. Implementation is performed directly by the top-level main agent; there are no dedicated Luna or Terra worker subagents. The main agent's reasoning effort remains the user-selected or current-session setting and is not overridden by this routing policy.

For non-trivial changes, invoke `planner` through native named-agent dispatch in a fresh child context: use `fork_turns: "none"` with MultiAgentV2, or `fork_context: false`/omitted with MultiAgentV1. Pass an explicit context packet covering the user request, prior decisions, task context, non-negotiable constraints, and open questions, select the reasoning effort per dispatch using the policy above, and require read-only behavior. Planner correctness therefore does not depend on inherited parent history. Resolve material decisions before main-agent implementation and run verification. Following Claude Code's [advisor pattern](https://code.claude.com/docs/en/advisor), invoke `advisor` in the same kind of fresh child context only when a stronger independent second opinion is useful at a key moment, such as before committing to a consequential approach, when progress is stuck or uncertain, or before completion when another check would materially increase confidence. The advisor receives a fresh context plus task-specific primary evidence instead of inheriting the parent agent's conclusions. Advisor timing is model-driven rather than a mandatory final-review phase. Treat returned verdict labels as guidance classifications rather than approval gates: apply advice that is supported by primary evidence, surface conflicts when verified evidence contradicts a recommendation, rerun relevant verification after changes, and consult advisor again only when another opinion remains useful or the user explicitly requests it. Completion never requires looping solely to obtain `VERDICT: ship`.

Invoke these roles only through native multi-agent dispatch. Report `unsupported` only when native named-role dispatch is unavailable or runtime evidence explicitly shows a generic/different-agent fallback, incompatible model override, failure to honor an explicitly requested per-dispatch reasoning effort or the requested fresh-context isolation, or a writable invocation outside a Git worktree; missing runtime telemetry, an adaptively selected reasoning effort, or a writable effective sandbox alone is not a failure when the mutation guard can be established. The named agents must not modify files regardless of available write capability. In a Git worktree, reject a result when the post-dispatch Git-visible state differs from its recorded baseline or available runtime evidence shows a mutating action, including a transient edit later restored. An unborn repository uses an explicit no-`HEAD` sentinel rather than failing the guard. Outside a Git worktree, require an effective read-only sandbox instead of accepting a writable one. This guard protects persistent Git-visible state but does not attest that a writable runtime performed no transient writes. Do not fall back to nested `codex exec`, shell wrappers, copied prompts, or generic agents.

See [.codex/agents/README.md](./.codex/agents/README.md) for installation and usage examples. Future planner parent-context inheritance is tracked separately in [#76](https://github.com/dceoy/ai-coding-agent-skills/issues/76).

## Structure

```text
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
    directly and fails closed as unavailable if it is missing or cannot enforce the safeguards `SKILL.md` documents.
  - The current upstream release, v0.34.0, does not bind a confirmation ID to its pending request, so `x-timeline`'s
    guarded navigation/tab-selection step fails closed as unavailable on that version; a newer release that closes
    this gap is required before that step can run.

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
- On Windows, ensure symlink support is enabled

## Contributing

See [AGENTS.md](./AGENTS.md) for repository guidelines and agent-specific rules.

## License

See [LICENSE](./LICENSE) for details.
