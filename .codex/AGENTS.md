# Codex named-agent routing

Install this template as `$CODEX_HOME/AGENTS.md`; a file under the repository's
`.codex/` directory is not automatically loaded from the repository root.

Delegate only when independent analysis adds value. Use native Codex named-agent
dispatch, not nested `codex exec`, shell wrappers, copied prompts, or generic
agents pretending to be named roles:

- `planner`: decision-complete plans for non-trivial changes. Supply the user
  request, settled decisions, repository context, constraints, and open questions.
- `advisor`: independent advice on consequential design or implementation risks.
- `reviewer`: one bounded PR-review discovery or validation task against an exact
  revision. Supply task kind, scope, evidence, and candidate IDs where applicable.
- `feedback-analyst`: item-level review-feedback disposition with source IDs.

Keep implementation and verification in the top-level main agent. All named
agents are read-only terminal leaves: no writes, publishing, or further delegation.
Treat findings as evidence to assess, not an approval gate.

Use the model and reasoning effort configured in each agent TOML. Change them
only when a supported native dispatch interface permits an explicit override;
do not assume hidden fields are available or silently accept another model.
Use a fresh child context: `fork_turns: "none"` in MultiAgentV2, or
`fork_context: false` (or omitted) in MultiAgentV1. Supply task context explicitly.

If the runtime cannot select the named role or honor its requirements, skip that
delegation and continue in the main agent. Do not simulate it with another agent
or a child CLI process. Sandbox declarations and prompt prohibitions are not
security guarantees: check the effective permissions and inspect Git-visible
changes after any read-only review. Do not claim transient writes are detectable
from a final Git diff.
