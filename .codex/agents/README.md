# Codex custom subagents

These project-scoped TOML files define two native read-only Codex roles:

- `planner`: `gpt-5.6-sol`, xhigh reasoning, read-only. Produces a decision-complete five-part implementation contract.
- `advisor`: `gpt-5.6-sol`, xhigh reasoning, read-only. Provides technical advice or an attested fresh `ship / fix-first / rethink` final review.

Implementation is performed directly by the top-level main agent. There are no dedicated Luna or Terra worker roles. Invoke these roles only through Codex native multi-agent tools; do not use nested `codex exec`, shell wrappers, copied prompts, generic children, or simulations.

## Permission model

The TOML sandbox values are defaults. A spawned agent can inherit the parent turn's live permission mode, and runtime overrides take precedence.

Use separate phases:

- Planning-only or advice: an effective read-only parent session.
- Planning and implementation in one workspace-write turn: capture a complete pre-planning project guard before invoking `planner`, then recapture and byte-compare the same evidence immediately after planning. Any mutation invalidates the contract.
- Final review: end the workspace-write turn and start a fresh parent session with effective read-only permission and no inherited implementation history.

Run `planner`, the main implementation phase, and `advisor` with configured and effective `reasoning_effort=xhigh`.

## Project identity and baseline modes

Fix a physical `PROJECT_ROOT` before planning or any write.

Initial modes:

- `git-head`: valid Git worktree with a resolvable commit `HEAD`.
- `git-unborn`: valid Git worktree without a resolvable commit; record `HEAD` as `unborn:<full-symbolic-ref>`.
- `filesystem`: no Git worktree applies; record `HEAD: absent`, `git-dir: absent`, and `common-dir: absent`.

A present but invalid Git marker is unsupported, not `filesystem`. Git modes also record the physical worktree root, worktree Git directory, and common Git directory.

The project manifest is deterministically sorted and byte-safe. Do not follow symlinks. Record directories with path, kind, and mode; regular files with path, kind, mode, byte length, and SHA-256 over raw bytes; symlinks with path, kind, mode, and SHA-256 over raw link-target bytes; and required missing paths as `expected-absent`.

## Planning mutation guard

Before dispatching `planner` from a workspace-write parent, capture the complete initial-mode project baseline:

- canonical project identity;
- mode-specific Git/index/worktree evidence when applicable;
- tracked-content or complete filesystem manifest;
- relevant untracked and ignored-path evidence;
- expected-absent records.

After `planner` returns, capture the same evidence again and compare it byte-for-byte. Do not treat planner-created changes as the starting baseline. A planning-only read-only session may replace this guard, but the later write-capable session must still verify the same identity and state before accepting the contract.

Planner-declared external inputs that were not knowable before planning are captured after planning and before implementation.

## Baseline-mode transitions

Supported transitions are limited to:

- `filesystem -> git-unborn`
- `filesystem -> git-head`, through a recorded `git-unborn` checkpoint
- `git-unborn -> git-head`

Every other transition is unsupported.

A transition bridge contains:

1. Immutable initial identity, mode, and complete source evidence.
2. Exact authorized transition commands or operations.
3. Every intermediate Git checkpoint, including physical Git identity, symbolic `HEAD`, status, index, staged/unstaged state, and verification-relevant Git configuration.
4. Source-to-final filesystem-manifest delta plus expected-absent, untracked, ignored-path, and external-input evidence.
5. For a first commit, commit/tree IDs, final stage-zero index, and evidence that the commit tree matches the intended tracked content.

A clean final status or final commit pair is not a substitute. The final packet carries both the source baseline and transition bridge.

## User-wide installation

Codex uses `$CODEX_HOME` when set and otherwise defaults to `$HOME/.codex`.

```bash
codex_home="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$codex_home/agents"

for file in .codex/agents/*.toml; do
  destination="$codex_home/agents/$(basename "$file")"
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    printf 'Preserve and merge or remove %s before installation.\n' "$destination" >&2
    exit 1
  fi
done

for file in .codex/agents/*.toml; do
  cp "$file" "$codex_home/agents/$(basename "$file")"
done

if [ -e "$codex_home/AGENTS.override.md" ] || [ -L "$codex_home/AGENTS.override.md" ]; then
  printf 'Merge .codex/AGENTS.md into the active AGENTS.override.md manually.\n'
elif [ -e "$codex_home/AGENTS.md" ] || [ -L "$codex_home/AGENTS.md" ]; then
  printf 'Merge .codex/AGENTS.md into the existing AGENTS.md manually.\n'
else
  cp .codex/AGENTS.md "$codex_home/AGENTS.md"
fi
```

Use regular-file copies; agent-definition symlinks may not be discovered. Remove obsolete `planner-sol.toml`, `advisor-sol.toml`, `worker-luna.toml`, and `worker-terra.toml` from existing user-wide installations.

After installation, start a fresh Codex session and verify that native `planner` and `advisor` resolve from the expected definitions with the required model, reasoning, sandbox, and effective permission metadata.

## Usage

### Plan and implement

Start a workspace-write parent turn:

```text
Fix physical PROJECT_ROOT and classify the initial mode. Capture the complete pre-planning project guard before invoking native planner. After planner returns, recapture and byte-compare the same project evidence; stop on any mutation. Validate the five-part contract, capture planner-declared ignored/excluded paths and external inputs, then implement directly in the top-level main agent with reasoning_effort=xhigh. For a baseline-mode transition, retain the complete source baseline and transition bridge. Verify, freeze the full packet, and do not run final review in this turn.
```

### Final review

Start a fresh separate read-only parent session:

```text
Invoke native advisor with fork_turns set to none. Before dispatch, compare the pre-planning guard, post-planner equality evidence, immutable source baseline, transition bridge when applicable, final canonical identity and mode-specific evidence, path/filesystem manifests, ignored/excluded paths, external-input evidence or hermetic boundary, and verification evidence against the original packet. Require attested gpt-5.6-sol, reasoning_effort=xhigh, a fresh session, and effective read-only permission. Repeat final-state comparison after review; any mismatch invalidates the verdict.
```

### Advice only

```text
Use native advisor to evaluate this design. Return advice only and do not modify files.
```

## Review integrity

Prevent other writers from modifying approved or verification-relevant project paths until final evidence capture. External inputs must remain frozen, replayable, or independently attestable.

Never read, print, serialize, copy into evidence, or compute an unkeyed digest of a secret value. Represent secrets only with non-secret immutable secret-manager version identifiers or externally produced keyed attestations whose key and raw secret never enter the agent context.

The reviewer remediation classes are:

- `none`: valid only with `VERDICT: ship`.
- `parent-evidence`: repair missing guard, baseline, transition, external-input, review-input, model, permission, or session evidence.
- `repository-change`: implement a bounded project fix in the main agent.
- `mixed`: repair evidence and implement project changes.
- `replan`: return architecture, requirements, verification environment, project root, baseline mode, transition, or scope changes to `planner` or the user.

Every project change, baseline-mode transition, or verification-relevant external-input change requires new verification, a new frozen packet, and a fresh separate read-only review.
