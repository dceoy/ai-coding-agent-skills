# Codex named-agent routing

Install this template as `$CODEX_HOME/AGENTS.md`; a file under the repository's
`.codex/` directory is not automatically loaded from the repository root.

## Delegation

Use native Codex named-agent dispatch when a role adds material value:

- For non-trivial implementation where planning reduces rework or risk, invoke
  `planner` before editing. Supply the request, prior decisions, repository
  context, constraints, and open questions.
- For consequential architecture, security, or cross-system decisions, invoke
  `advisor` for an independent assessment.
- For substantive PR reviews, invoke `reviewer` for bounded discovery or
  validation against an exact revision. Supply task kind, scope, and evidence.
- For multi-item or ambiguous review feedback, invoke `feedback-analyst` with
  the feedback snapshot and source IDs.

Use the main agent for simple questions and deterministic edits; do not add
delegation merely as a process gate. Never use nested `codex exec`, shell
wrappers, copied prompts, or generic agents posing as named roles.

Keep implementation and verification in the top-level main agent. All named
agents are read-only terminal leaves: no writes, publishing, or further delegation.
Treat findings as evidence to assess, not an approval gate.

Use the model and reasoning effort pinned in each agent TOML. These settings
take precedence over spawn-time overrides. For a different model or effort,
use a separately configured role (if supported) or work in the main agent.
Use a fresh child context: `fork_turns: "none"` in MultiAgentV2, or
`fork_context: false` (or omitted) in MultiAgentV1. Supply task context explicitly.

If the runtime cannot select the named role or honor its requirements, skip
delegation and work in the main agent; never simulate a named role with another
agent or CLI. Parent sandbox overrides may supersede a TOML's read-only setting.
Prefer a verified effective read-only child sandbox. Otherwise, in a Git worktree,
record HEAD, staged/unstaged diffs, and non-ignored untracked content hashes before
dispatch; compare afterward and reject new mutations while preserving prior
changes. Outside Git, require effective read-only permissions. This detects only
persistent Git-visible changes, not transient writes.
