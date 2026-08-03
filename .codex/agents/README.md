# Codex custom subagents

These project-scoped agents separate high-quality planning and advice from implementation. Current Codex releases discover each standalone TOML file under `.codex/agents/` automatically; no per-agent registration in `.codex/config.toml` is required.

The invocation examples target local Codex app, CLI, and IDE sessions. Tool-backed or programmatic Codex integrations may not expose named project agents; verify runtime support before relying on these definitions. See [openai/codex#15250](https://github.com/openai/codex/issues/15250).

| Agent          | Model           | Configured sandbox | Purpose                                                                |
| -------------- | --------------- | ------------------ | ---------------------------------------------------------------------- |
| `planner_sol`  | `gpt-5.6-sol`   | Read-only          | Produce a decision-complete implementation plan and select an executor |
| `advisor_sol`  | `gpt-5.6-sol`   | Read-only          | Provide architectural or technical advice without implementation       |
| `worker_terra` | `gpt-5.6-terra` | Workspace write    | Implement non-trivial approved plans                                   |
| `worker_luna`  | `gpt-5.6-luna`  | Workspace write    | Implement narrow, deterministic, mechanically verifiable plans         |

## Permission model

The sandbox values above are agent-file defaults, not immutable per-agent boundaries. A spawned agent inherits the parent turn's live permission mode, and runtime overrides such as `/permissions` or `--yolo` take precedence over the TOML defaults.

Use these parent permission modes:

- Planning or advice only: start the parent turn in read-only mode.
- Implementation: start a separate parent turn in workspace-write mode.
- One-turn planning and implementation: use workspace-write mode, but understand that the planner's read-only behavior is instruction-enforced rather than sandbox-enforced.

A read-only parent prevents implementation workers from writing. A workspace-write parent can grant write access to planning agents despite their configured defaults.

## User-wide installation

The files in this repository are project-scoped by default. Codex uses `$CODEX_HOME` as its home directory when set and otherwise defaults to `$HOME/.codex`.

To copy the agent definitions and routing instructions for every Codex project:

```bash
codex_home="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$codex_home/agents"

for file in .codex/agents/*.toml; do
  destination="$codex_home/agents/$(basename "$file")"
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    printf 'Keep the existing %s and merge, back up, or remove it before installing this definition.\n' "$destination" >&2
    exit 1
  fi
done

for file in .codex/agents/*.toml; do
  cp "$file" "$codex_home/agents/$(basename "$file")"
done

if [ -e "$codex_home/AGENTS.override.md" ] || [ -L "$codex_home/AGENTS.override.md" ]; then
  printf 'Keep the existing %s and merge the Model routing section from .codex/AGENTS.md into that active override manually.\n' "$codex_home/AGENTS.override.md"
elif [ -e "$codex_home/AGENTS.md" ] || [ -L "$codex_home/AGENTS.md" ]; then
  printf 'Keep the existing %s and merge the Model routing section from .codex/AGENTS.md manually.\n' "$codex_home/AGENTS.md"
else
  cp .codex/AGENTS.md "$codex_home/AGENTS.md"
fi
```

The agent preflight stops before copying any definitions when a same-named file or symlink already exists. Preserve the existing definition and merge it manually, or back it up and remove it before rerunning the installation.

Codex prefers a non-empty `AGENTS.override.md` over `AGENTS.md` in its home directory. If an override exists, merge the routing section into that file or remove it only after preserving its instructions. Do not replace either existing file or symlink until its current instructions have been preserved.

To keep the agent definitions synchronized with this repository, use symlinks from a local clone:

```bash
codex_home="${CODEX_HOME:-$HOME/.codex}"
repo_root="$(git rev-parse --show-toplevel)"
mkdir -p "$codex_home/agents"

for file in "$repo_root"/.codex/agents/*.toml; do
  destination="$codex_home/agents/$(basename "$file")"
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    printf 'Keep the existing %s and merge, back up, or remove it before installing this symlink.\n' "$destination" >&2
    exit 1
  fi
done

for file in "$repo_root"/.codex/agents/*.toml; do
  ln -s "$file" "$codex_home/agents/$(basename "$file")"
done

if [ -e "$codex_home/AGENTS.override.md" ] || [ -L "$codex_home/AGENTS.override.md" ]; then
  printf 'Keep the existing %s and merge the Model routing section from the repository file into that active override manually.\n' "$codex_home/AGENTS.override.md"
elif [ -e "$codex_home/AGENTS.md" ] || [ -L "$codex_home/AGENTS.md" ]; then
  printf 'Keep the existing %s and merge the Model routing section from the repository file manually.\n' "$codex_home/AGENTS.md"
else
  ln -s "$repo_root/.codex/AGENTS.md" "$codex_home/AGENTS.md"
fi
```

The symlink preflight likewise stops before creating any links when a destination already exists.

Start a new Codex session after installing or updating the files.

## Usage

Ask Codex to delegate explicitly by agent name.

### Plan and implement in one turn

Start the parent turn in workspace-write mode. This convenience workflow relies on the planner instructions to avoid edits:

```text
Use planner_sol to plan this task. After the plan is complete, delegate implementation to the recommended worker_terra or worker_luna agent. Use only one active write-capable worker at a time, and do not run workers concurrently.
```

### Approval-gated workflow

Start the planning turn in read-only mode:

```text
Use planner_sol to produce the implementation plan only. Do not modify files.
```

After reviewing the plan, start a separate parent turn in workspace-write mode:

```text
Implement the approved plan with worker_terra.
```

### Advice only

Start the parent turn in read-only mode:

```text
Use advisor_sol to evaluate this design. Return advice only and do not modify files.
```

## Routing policy

The routing policy applies only to the root or main agent. Named custom agents follow their agent-specific instructions and must not spawn or delegate to another subagent.

Use `worker_luna` only for localized, low-risk changes with explicit scope and mechanical validation. Use `worker_terra` when the change requires diagnosis, non-trivial reasoning, cross-cutting edits, or adaptation to repository state.

Use only one active write-capable worker at a time. A sequential Luna-to-Terra handoff is allowed only after Luna has stopped, reported every partial edit, and returned control to the parent. The parent must review that state before starting Terra; workers must not spawn or delegate to another write-capable worker themselves.

If an implementation agent encounters an unplanned architectural, security, compatibility, or data-model decision, return control to `planner_sol` or `advisor_sol` instead of silently expanding the plan.
