# Codex custom subagents

Four optional, native, read-only Codex roles live here:

- `planner`, `advisor`, `reviewer`: `gpt-6.1-sol` (`high`).
- `feedback-analyst`: `gpt-6-luna` (`medium`).

Their TOML files own model, effort, sandbox preference, and output contracts.
`../AGENTS.md` owns routing. The main agent performs all implementation.

## Install globally

Codex uses `$CODEX_HOME`, defaulting to `$HOME/.codex`.
From the repository root:

```bash
codex_home="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$codex_home/agents"
for file in .codex/agents/*.toml; do
  dest="$codex_home/agents/$(basename "$file")"
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    echo "Merge existing agent manually: $dest" >&2
    exit 1
  fi
done
cp .codex/agents/*.toml "$codex_home/agents/"
if [ -e "$codex_home/AGENTS.md" ] || [ -L "$codex_home/AGENTS.md" ] ||
   [ -e "$codex_home/AGENTS.override.md" ] || [ -L "$codex_home/AGENTS.override.md" ]; then
  echo "Merge .codex/AGENTS.md into your active instructions manually."
else
  cp .codex/AGENTS.md "$codex_home/AGENTS.md"
fi
```

Restart Codex after installation. Confirm the runtime exposes each named role
and uses its configured model/effort. MultiAgentV2 may hide role selection or
per-call model overrides; if the named role cannot be selected, do not
substitute an unnamed agent. Read-only TOML settings must not be treated as
proof of effective sandbox permissions.

Project-local `.codex/agents/` definitions can be discovered independently
of the global installation; `.codex/AGENTS.md` is not a root instruction file.
