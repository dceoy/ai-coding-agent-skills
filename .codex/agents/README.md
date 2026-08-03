# Codex custom subagents

These project-scoped agents separate high-quality planning and final review from implementation. Current Codex releases discover each standalone TOML file under `.codex/agents/` automatically; no per-agent registration in `.codex/config.toml` is required.

The invocation examples target local Codex app, CLI, and IDE sessions. Tool-backed or programmatic Codex integrations may not expose named project agents; verify runtime support before relying on these definitions. See [openai/codex#15250](https://github.com/openai/codex/issues/15250).

| Agent          | Model           | Configured sandbox | Purpose                                                                    |
| -------------- | --------------- | ------------------ | -------------------------------------------------------------------------- |
| `planner_sol`  | `gpt-5.6-sol`   | Read-only          | Produce a five-part, decision-complete implementation contract             |
| `advisor_sol`  | `gpt-5.6-sol`   | Read-only          | Provide technical advice or a fresh `ship / fix-first / rethink` review    |
| `worker_terra` | `gpt-5.6-terra` | Workspace write    | Implement approved non-trivial contracts and report verification evidence |

`worker_luna` was removed after reevaluating its routing value. Narrow, deterministic edits are already handled directly by the main agent, while delegated implementation benefits from one consistent Terra contract and review path.

## Permission model

The sandbox values above are agent-file defaults, not immutable per-agent boundaries. A spawned agent inherits the parent turn's live permission mode, and runtime overrides such as `/permissions` or `--yolo` take precedence over the TOML defaults.

Use these parent permission modes:

- Planning, advice, or final review only: start the parent turn in read-only mode.
- Implementation: start a separate parent turn in workspace-write mode.
- One-turn planning and implementation: use workspace-write mode, but understand that planner and reviewer read-only behavior is instruction-enforced rather than sandbox-enforced.

A read-only parent prevents implementation workers from writing. A workspace-write parent can grant write access to planning or review agents despite their configured defaults. For a final review under a broadened parent permission, capture the repository state before and after review and reject the verdict if any mutation occurs.

## User-wide installation

The files in this repository are project-scoped by default. Codex uses `$CODEX_HOME` as its home directory when set and otherwise defaults to `$HOME/.codex`.

Before updating an installation created from an earlier version, review and remove the retired `$CODEX_HOME/agents/worker-luna.toml` or `$HOME/.codex/agents/worker-luna.toml`. Preserve it first if it contains local customizations. Leaving it installed does not change this repository's routing policy, but Codex may continue to expose the stale role by name.

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

Start a new Codex session after installing, removing a retired role, or updating the files.

## Usage

Ask Codex to delegate explicitly by agent name.

### Plan, implement, verify, and review in one turn

Start the parent turn in workspace-write mode. This convenience workflow relies on planner and reviewer instructions to avoid edits:

```text
Use planner_sol to produce the five-part implementation contract. Delegate it to worker_terra. Inspect the complete diff and rerun validation in the parent session, then use a fresh advisor_sol context for final review. Do not report completion unless the verdict is ship.
```

### Approval-gated workflow

Start the planning turn in read-only mode:

```text
Use planner_sol to produce the five-part implementation contract only. Do not modify files.
```

After reviewing the contract, start a separate parent turn in workspace-write mode:

```text
Implement the approved contract with worker_terra. Inspect the complete diff and rerun all validation before requesting final review from a fresh advisor_sol context.
```

### Advice only

Start the parent turn in read-only mode:

```text
Use advisor_sol to evaluate this design. Return advice only and do not modify files.
```

### Final review only

Start the parent turn in read-only mode when enforced isolation is required:

```text
Use a fresh advisor_sol context to review the stated goal, complete change set, interfaces, constraints, and verification evidence. Return only ship, fix-first, or rethink and do not modify files.
```

## Routing policy

The routing policy applies only to the root or main agent. Named custom agents follow their agent-specific instructions and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and localized, deterministic edits. Use `planner_sol` and `worker_terra` for delegated non-trivial implementation.

The planner must produce these five contract sections:

1. Objective
2. Files and ownership
3. Interfaces
4. Constraints
5. Verification

Treat the worker report as claims. The main agent must inspect the complete working-tree diff, verify scope, rerun relevant checks, and reconcile the report with actual evidence.

After parent verification, start a fresh `advisor_sol` context with the goal, allowed change set, complete diff or revisions, interfaces and constraints, and verification evidence. Completion requires `VERDICT: ship`. Any later code change invalidates the verdict and requires a new final review.

If implementation encounters an unplanned architectural, security, compatibility, data-model, authentication, authorization, or migration decision, return control to `planner_sol` or `advisor_sol` instead of silently expanding the contract.
