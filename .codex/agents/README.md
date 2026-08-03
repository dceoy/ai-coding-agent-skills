# Codex custom subagents

These project-scoped TOML files define two native read-only Codex roles. Current Codex releases discover each standalone TOML file under `.codex/agents/` automatically; no per-agent registration in `.codex/config.toml` is required.

Invoke these roles only from a top-level Codex parent through Codex's native multi-agent tools. The TOML files are native role definitions, not prompts for nested `codex exec` invocations, shell wrappers, copied prompts, or equivalent subprocesses. If native named-agent dispatch is unavailable, stop and report `unsupported`; do not replace a required role with a generic child or simulation.

- `planner`: `gpt-5.6-sol`, xhigh reasoning, read-only. Produces a decision-complete five-part implementation contract.
- `advisor`: `gpt-5.6-sol`, xhigh reasoning, read-only. Provides technical advice or an attested fresh `ship / fix-first / rethink` final review.

Implementation is performed directly by the top-level main agent. There are no dedicated Luna or Terra worker roles.

## Permission model

The sandbox values in the TOML files are defaults, not immutable per-agent boundaries. A spawned agent inherits the parent turn's live permission mode, and runtime overrides such as `/permissions` or `--yolo` take precedence.

Use separate phases:

- Planning or advice only: start the parent turn in read-only mode.
- Planning and implementation: use a workspace-write parent turn. `planner` remains instruction-enforced read-only.
- Final review: end the workspace-write turn and start a fresh parent session in read-only mode.

Run `planner`, the main implementation phase, and `advisor` with configured and effective `reasoning_effort=xhigh`. Final review must expose effective read-only permission, use `fork_turns: "none"`, and receive no inherited implementation history.

## User-wide installation

The files in this repository are project-scoped by default. Codex uses `$CODEX_HOME` when set and otherwise defaults to `$HOME/.codex`.

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

The preflight stops before copying definitions when a same-named file or symlink already exists. Preserve and merge the existing definition, or back it up and remove it before rerunning installation.

Codex prefers a non-empty `AGENTS.override.md` over `AGENTS.md` in its home directory. If an override exists, merge the routing section into that file or remove it only after preserving its instructions.

To keep definitions synchronized with a local clone, use symlinks:

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

Start a new Codex session after installing or updating the files. Remove obsolete `planner-sol.toml`, `advisor-sol.toml`, `worker-luna.toml`, and `worker-terra.toml` files from existing user-wide installations to avoid duplicate or stale roles.

## Usage

### Plan and implement

Start the parent turn in workspace-write mode:

```text
Use native multi-agent dispatch to invoke `planner` and obtain its five-part implementation contract. Resolve every material decision before editing. Capture the complete pre-implementation baseline, then implement the approved contract directly in the top-level main agent with reasoning_effort=xhigh; do not delegate implementation to a worker subagent. Preserve the ownership boundary, compute and inspect the full baseline-relative delta, rerun verification in the main session, and freeze the reviewed state. Do not run final review in this workspace-write turn.
```

### Final review

End the implementation turn and start a fresh separate parent session in read-only mode:

```text
Use native multi-agent dispatch to invoke `advisor` with `fork_turns` set to `none`. Retain runtime metadata proving the named definition, `gpt-5.6-sol`, `reasoning_effort=xhigh`, a fresh session, and effective read-only permission. Review the frozen goal, implementation contract, complete baseline-relative tracked diff, relevant untracked-file evidence, and main-session verification evidence. Return VERDICT and REMEDIATION. Any repository mutation invalidates the verdict.
```

### Approval-gated workflow

Start planning in read-only mode:

```text
Use native multi-agent dispatch to invoke `planner` for the five-part implementation contract only. Resolve material decisions and do not modify files.
```

After approval, perform implementation directly in a workspace-write main-agent turn, then use the final-review prompt in a separate read-only session.

### Advice only

Start the parent turn in read-only mode:

```text
Use native multi-agent dispatch to invoke `advisor` to evaluate this design. Return advice only and do not modify files.
```

## Routing policy

Use the main agent directly for simple questions and narrow deterministic edits. For non-trivial implementation, use `planner` first and then implement directly in the main agent.

The planner must define exact modifiable file and generated-artifact paths whenever they are knowable. When diagnosis or cross-cutting adaptation requires file discovery, it may instead define the smallest bounded module, package, or directory ownership zone plus explicit exclusions. The main agent may discover and modify files only inside that approved zone.

An unresolved material architectural, product, security, authentication, authorization, data-model, migration, compatibility, or externally visible interface decision is a replanning or advice condition. It is not permission to expand scope during implementation.

## Native execution support

Before planning or final review, verify that the native runtime resolves the named role, loaded definition source, configured model and reasoning effort, configured sandbox, and effective permission mode. Runtime metadata is the attestation; TOML contents and child self-reports are not substitutes.

Require effective `reasoning_effort=xhigh` for `planner`, the main implementation phase, and `advisor`. If native named-agent dispatch cannot resolve `planner` or `advisor`, or cannot attest the required effective model, reasoning effort, sandbox, or permission mode for those roles, stop and report `unsupported`. Do not fall back to `codex exec`, nested Codex CLI processes, shell wrappers, generic children, copied prompts, or compatibility modes.

## Attribution and review integrity

Before implementation, capture `HEAD`, porcelain-v2 status, staged and unstaged diffs, the untracked-file inventory, and content or cryptographic hashes for relevant pre-existing untracked files. Prevent other writers from modifying approved or verification-relevant paths until final evidence capture.

The main agent owns implementation, the authoritative baseline-relative delta, scope enforcement, inspection, and verification. If an unexpected mutation appears or exclusive access was violated, stop and reconcile rather than attributing the change to the main implementation phase.

Freeze the verified state before ending the workspace-write turn. Final review must run in a fresh separate read-only parent session and receive the complete change set and verification evidence. Compare the repository with the frozen pre-review baseline after review; any intervening or reviewer-time mutation invalidates the verdict.

The reviewer returns a remediation class:

- `none`: valid only with `VERDICT: ship`.
- `parent-evidence`: repair missing baseline, review inputs, model or permission attestation, or review-session evidence without changing the repository.
- `repository-change`: the main agent implements the bounded fix directly.
- `mixed`: repair evidence and implement the repository-change portion directly.
- `replan`: return architecture, requirements, or scope changes to `planner` or the user.

Every repository change requires new main-agent verification, a new frozen evidence packet, and a fresh separate read-only review.
