# Codex custom subagents

These project-scoped agents separate planning and final review from implementation. Current Codex releases discover each standalone TOML file under `.codex/agents/` automatically; no per-agent registration in `.codex/config.toml` is required.

The invocation examples target local Codex app, CLI, and IDE sessions. Tool-backed or programmatic Codex integrations may not expose named project agents; verify runtime support before relying on these definitions. See [openai/codex#15250](https://github.com/openai/codex/issues/15250).

| Agent          | Model           | Reasoning | Configured sandbox | Purpose                                                                      |
| -------------- | --------------- | --------- | ------------------ | ---------------------------------------------------------------------------- |
| `planner_sol`  | `gpt-5.6-sol`   | Max       | Read-only          | Produce a five-part implementation contract with Luna-first routing          |
| `advisor_sol`  | `gpt-5.6-sol`   | Max       | Read-only          | Provide technical advice or a fresh `ship / fix-first / rethink` review      |
| `worker_luna`  | `gpt-5.6-luna`  | Max       | Workspace write    | Default worker for bounded, settled, and verifiable implementation contracts |
| `worker_terra` | `gpt-5.6-terra` | Max       | Workspace write    | Escalation worker for bounded discovery or Luna-documented adaptive judgment |

## Permission model

The sandbox values above are agent-file defaults, not immutable per-agent boundaries. A spawned agent inherits the parent turn's live permission mode, and runtime overrides such as `/permissions` or `--yolo` take precedence over the TOML defaults.

Use these parent permission modes:

- Planning, advice, or final review only: start the parent turn in read-only mode.
- Implementation: start a separate parent turn in workspace-write mode.
- One-turn planning and implementation: use workspace-write mode, but understand that planner and reviewer read-only behavior is instruction-enforced rather than sandbox-enforced.

A read-only parent prevents implementation workers from writing. A workspace-write parent can grant write access to planning or review agents despite their configured defaults. A named final review must be spawned with `fork_turns: "none"` so it receives no inherited implementation history. For a final review under a broadened parent permission, capture the repository state immediately before and after review and reject the verdict if any mutation occurs.

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

### Plan, implement, verify, and review in one turn

Start the parent turn in workspace-write mode. This convenience workflow relies on planner and reviewer instructions to avoid edits:

```text
Use planner_sol to produce the five-part implementation contract and resolve all material decisions before implementation. Capture the repository baseline, including content or hashes for relevant pre-existing untracked files, then delegate to worker_luna unless the contract requires bounded file discovery. Treat adaptive judgment as a Terra condition only after Luna reports a concrete suitability failure or escalation. If Luna declines or escalates, inspect its state and either replan or hand off sequentially to worker_terra. Compare the result against the baseline, rerun validation in the parent session, capture a pre-review baseline with the same relevant untracked-file evidence, and spawn advisor_sol with fork_turns set to none for final review. Reject the verdict if review mutates the repository, and do not report completion unless the verdict is ship.
```

### Approval-gated workflow

Start the planning turn in read-only mode:

```text
Use planner_sol to produce the five-part implementation contract and a Luna-first executor recommendation only. Resolve material decisions and do not modify files.
```

After reviewing the contract, start a separate parent turn in workspace-write mode:

```text
Capture the repository baseline, including content or hashes for relevant pre-existing untracked files. Implement the approved contract with worker_luna unless bounded file discovery is required. Escalate adaptive judgment to worker_terra only after a documented Luna suitability failure. Compare the result against the baseline, rerun all validation, capture a pre-review baseline with the same relevant untracked-file evidence, and spawn advisor_sol with fork_turns set to none for final review.
```

### Advice only

Start the parent turn in read-only mode:

```text
Use advisor_sol to evaluate this design. Return advice only and do not modify files.
```

### Final review only

Start the parent turn in read-only mode when enforced isolation is required:

```text
Spawn advisor_sol with fork_turns set to none. Review the stated goal, the complete baseline-relative tracked diff, content evidence for newly relevant untracked files, before-and-after content or hash evidence for relevant pre-existing untracked files, interfaces, constraints, and verification evidence. Use immutable base and head revisions instead only when they fully encode the entire reviewed change set and the relevant worktree is clean. Return only ship, fix-first, or rethink and do not modify files.
```

## Routing policy

The routing policy applies only to the root or main agent. Named custom agents follow their agent-specific instructions and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and localized deterministic edits when delegation overhead is not justified. For planned delegated implementation, use `worker_luna` by default.

Before selecting any worker, settle all material architectural, product, security, authentication, authorization, data-model, migration, compatibility, and externally visible interface decisions. An unresolved material decision is a replanning or advice condition, not a reason to start Terra.

Luna is suitable when:

1. The objective and exact file ownership are bounded.
2. Architecture and externally visible interfaces are settled.
3. No material implementation decision remains unresolved.
4. Verification has concrete commands or inspectable acceptance evidence.

A Luna task may be non-trivial, span multiple files, or require substantial implementation. Complexity or apparent need for engineering judgment alone is not a Terra condition.

Use `worker_terra` only after all material decisions are settled and an explicit Terra condition exists:

- broad diagnosis inside a bounded ownership zone where the exact affected files are not yet known;
- cross-cutting adaptation whose exact file set must be discovered but remains inside that zone; or
- a documented Luna suitability failure or escalation identifying the concrete adaptive judgment Luna could not complete within exact ownership.

When exact ownership is known, route to Luna first. Do not choose Terra solely because the work appears judgment-heavy; Luna must first identify the concrete blocking judgment before an adaptive-judgment escalation.

The planner must define Terra's smallest bounded ownership zone and explicit exclusions. Terra may discover the exact affected files and make tactical decisions only inside that boundary while preserving settled interfaces and constraints. Crossing the boundary or encountering a new material decision requires replanning or advice.

Luna must perform its pre-edit suitability check. If bounded file discovery is required, it returns control without changes and states the exact discovery condition. For adaptive judgment within exact ownership, Luna attempts the work and may escalate only after identifying the concrete blocking judgment. If it escalates after partial edits, it stops, reports every partial change, and returns control to the parent. The parent must inspect that state, update the contract when necessary, and perform a sequential handoff. Never run write-capable workers concurrently.

The planner must produce these five contract sections:

1. Objective
2. Files and ownership, using exact files for Luna or a bounded ownership zone plus exclusions for Terra
3. Interfaces
4. Constraints, including settled decisions, the Luna-first executor recommendation, and any explicit Terra condition
5. Verification

## Baseline and review integrity

Before starting a worker, the parent must capture the repository state, including:

- current `HEAD`;
- `git status --short` or equivalent status evidence;
- staged and unstaged diffs;
- the untracked-file inventory;
- content evidence for newly relevant untracked files; and
- content or cryptographic hashes for every relevant pre-existing untracked file inside the approved ownership boundary or used by verification, so same-path content mutations are detectable.

After the worker returns, compare the repository against that captured state, including the recorded content or hashes for relevant pre-existing untracked files. Review and validate only the worker-introduced delta, while preserving and excluding pre-existing or concurrent edits. A current working-tree diff by itself is insufficient because it cannot attribute changes to the worker, detect committed mutations reliably, or detect content changes to a pre-existing untracked path.

After parent verification, capture a second repository baseline immediately before starting the final review, including content or hashes for every relevant pre-existing untracked file. Spawn `advisor_sol` with `fork_turns: "none"` so the reviewer receives no inherited implementation history. Supply the complete baseline-relative tracked diff, content evidence for newly relevant untracked files, before-and-after content or hash evidence for relevant pre-existing untracked files, interfaces, constraints, and verification evidence. Explicit immutable base and head revisions may replace that evidence only when they fully encode the entire reviewed change set and the relevant worktree is clean. Compare the repository state again after the reviewer returns, including relevant untracked-file content or hashes. Any reviewer-time mutation invalidates the verdict and must be investigated without overwriting unrelated changes.

Treat every worker report as claims. The main agent must verify the baseline-relative change set, enforce the approved ownership boundary, rerun relevant checks, and reconcile the report with actual evidence.

Completion requires `VERDICT: ship`. Any later change to the reviewed change set or verification-relevant repository state invalidates the verdict and requires a new parent verification pass and fresh no-history review.

For `fix-first` findings, route bounded corrections to `worker_luna` by default, even when the initial implementation used Terra. Use `worker_terra` only when the finding introduces a valid Terra condition. Return `rethink` findings or newly unresolved material decisions to `planner_sol`, `advisor_sol`, or the user.
