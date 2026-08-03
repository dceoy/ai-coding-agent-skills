# Codex custom subagents

These project-scoped TOML files define native Codex agent roles that separate planning and final review from implementation. Current Codex releases discover each standalone TOML file under `.codex/agents/` automatically; no per-agent registration in `.codex/config.toml` is required.

Invoke these roles only from a top-level Codex parent through Codex's native multi-agent tools. These TOML files are native role definitions, not prompts intended for nested `codex exec` invocations, shell wrappers, or equivalent subprocesses. If the runtime does not expose native named-agent dispatch, stop and report `unsupported`; do not replace a named role with a generic child, copied prompt, direct parent execution, or compatibility mode. Runtime metadata must prove the resolved definition, effective model, reasoning effort, sandbox, and permission mode.

- `planner_sol`: `gpt-5.6-sol`, maximum reasoning, read-only. Produces a five-part implementation contract with Luna-first routing.
- `advisor_sol`: `gpt-5.6-sol`, maximum reasoning, read-only. Provides technical advice or an attested fresh `ship / fix-first / rethink` review with an explicit remediation class.
- `worker_luna`: `gpt-5.6-luna`, maximum reasoning, workspace-write. Default worker for bounded, settled, and verifiable implementation contracts with exact file and artifact ownership.
- `worker_terra`: `gpt-5.6-terra`, maximum reasoning, workspace-write. Handles only bounded Terra escalation after an explicit Luna suitability failure or escalation.

## Permission model

The sandbox values above are defaults, not immutable per-agent boundaries. A spawned agent inherits the parent turn's live permission mode, and runtime overrides such as `/permissions` or `--yolo` take precedence over the TOML defaults.

Use separate permission phases:

- Planning or advice only: start the parent turn in read-only mode.
- Planning and implementation: use a workspace-write parent turn. Planner read-only behavior is instruction-enforced in this phase.
- Final review: end the workspace-write turn and start a separate parent session in read-only mode.

A workspace-write parent cannot produce an acceptable final verdict merely by instructing a child not to edit. The review session must expose effective read-only permission and must receive no inherited implementation history. Before accepting a verdict, require a separate read-only parent session to resolve the named `advisor_sol` definition through native multi-agent dispatch with `fork_turns: "none"`, `gpt-5.6-sol`, `reasoning_effort=max`, and effective read-only permission.

A generic child response or copied review prompt is not sufficient merely because it prints `VERDICT: ship`. If native named-agent dispatch or any required attestation is unavailable, block completion with `unsupported` or `REMEDIATION: parent-evidence`.

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

Start a new Codex session after installing or updating the files.

## Usage

### Plan and implement

Start the parent turn in workspace-write mode:

```text
From the top-level Codex parent, use native multi-agent dispatch to invoke `planner_sol` for the five-part implementation contract and resolve all material decisions before implementation. Require `worker_luna` ownership to enumerate every exact repository file and generated-artifact path; use a bounded Terra zone when the exact file set must be discovered. Capture the approved full baseline, including HEAD, staged and unstaged diffs, and relevant untracked contents or hashes. Use a clean HEAD-based worktree only when the relevant workspace is clean; otherwise seed isolation from an immutable snapshot of the full approved baseline or keep the current worktree under exclusive writes. Preflight the native named worker and model. Delegate to native `worker_luna` unless the contract requires bounded file discovery. If native named-agent dispatch cannot resolve the selected role or configured model, stop and report `unsupported`; do not use `codex exec`, nested Codex CLI processes, shell wrappers, direct parent execution, generic children, or compatibility modes. Treat worker change reports as intentional-edit claims and compute the authoritative baseline-relative delta in the parent. Block on unexpected or unattributable mutations, rerun validation in the parent session, freeze the reviewed repository state, and prepare a complete final-review evidence packet. Do not run final review in this workspace-write turn.
```

### Final review

End the implementation turn and start a separate parent session in read-only mode:

```text
From a fresh separate read-only parent session, use native multi-agent dispatch to invoke the named `advisor_sol` role with `fork_turns` set to `none`. Retain runtime metadata proving the named definition, `gpt-5.6-sol` model, `reasoning_effort=max`, and effective read-only permission. If native named-agent dispatch or any required attestation is unavailable, stop and report `unsupported` or `fix-first` with `REMEDIATION: parent-evidence`; never substitute a generic child or copied prompt. Review the frozen goal, complete baseline-relative tracked diff, relevant untracked-file evidence, interfaces, constraints, and parent verification evidence. Return VERDICT and REMEDIATION. Confirm that the repository still matches the frozen pre-review baseline; any intervening or reviewer-time mutation invalidates the verdict.
```

### Approval-gated workflow

Start planning in read-only mode:

```text
From a read-only parent session, use native multi-agent dispatch to invoke `planner_sol` for the five-part implementation contract and a Luna-first executor recommendation only. Resolve material decisions and do not modify files. Treat native named-agent availability as an execution prerequisite; if it is unavailable, stop and report `unsupported` rather than using a fallback.
```

After approval, use the plan-and-implement prompt in a workspace-write turn, then use the final-review prompt in a separate read-only session.

### Advice only

Start the parent turn in read-only mode:

```text
From a read-only parent session, use native multi-agent dispatch to invoke `advisor_sol` to evaluate this design. Return advice only and do not modify files.
```

## Routing policy

Use the main agent directly for simple questions and localized deterministic edits when delegation overhead is not justified. For planned delegated implementation, use `worker_luna` by default.

Before selecting a worker, settle all material architectural, product, security, authentication, authorization, data-model, migration, compatibility, and externally visible interface decisions. An unresolved material decision is a replanning or advice condition, not a reason to start Terra.

Luna is suitable when:

1. The objective is bounded and every modifiable repository file and generated-artifact path is enumerated exactly.
2. Architecture and externally visible interfaces are settled.
3. No material implementation decision remains unresolved.
4. Verification has concrete commands or inspectable acceptance evidence.

A module, package, or directory is not Luna ownership unless every modifiable path inside it is enumerated. A Luna task may still be non-trivial, span multiple files, or require substantial implementation. Complexity or apparent need for engineering judgment alone is not a Terra condition.

Use `worker_terra` in `terra-escalation` mode only after all material decisions are settled and one explicit condition exists:

- broad diagnosis inside a bounded ownership zone where the exact affected files are not yet known;
- cross-cutting adaptation whose exact file set must be discovered but remains inside that zone; or
- a documented Luna suitability failure or escalation identifying the concrete adaptive judgment Luna could not complete within exact ownership.

When exact file and artifact ownership is known, route to Luna first. The planner must define Terra's smallest bounded module, package, or directory ownership zone and explicit exclusions. Terra may discover files and make tactical decisions only inside that boundary while preserving settled interfaces and constraints.

Luna must perform its pre-edit suitability check. If bounded discovery is required, it returns control without changes. If it escalates after partial edits, it stops, reports every intentional partial change, and returns control to the parent for a reviewed sequential handoff. Never run write-capable workers concurrently.

## Native execution support

Before delegation, preflight whether the native runtime resolves the named role, loaded definition source, configured model and reasoning effort, configured sandbox, and effective permission mode. Retain the runtime metadata as the attestation; TOML contents and child self-reports are not substitutes.

If native named-agent dispatch cannot resolve `planner_sol`, `worker_luna`, `worker_terra`, or `advisor_sol`, or cannot attest the required effective model, `reasoning_effort=max`, sandbox, or permission mode, stop and report `unsupported`. Do not fall back to `codex exec`, nested Codex CLI processes, shell wrappers, direct parent execution, generic children, or compatibility modes. Runtime unavailability is never a Terra condition.

## Attribution and review integrity

Before starting a worker, capture the approved full baseline and establish a mechanically enforceable attribution boundary:

1. Capture `HEAD`, status, staged and unstaged diffs, the untracked-file inventory, and content or cryptographic hashes for relevant pre-existing untracked files.
2. Use a dedicated clean worktree rooted at the captured `HEAD` only when the relevant approved workspace is clean.
3. If relevant approved uncommitted state exists, either seed an isolated worktree from an immutable snapshot that exactly reproduces the full baseline and retain its provenance evidence, or use the current worktree while prohibiting all other writers from modifying approved ownership or verification-relevant paths until verification and evidence capture finish.
4. Never delegate in a `HEAD`-only worktree that omits relevant approved staged, unstaged, or untracked state.

A baseline identifies pre-existing state but cannot distinguish a worker write from a concurrent write made after capture. If an unexpected mutation appears or exclusive access was violated, stop and reconcile or restart from an isolated full-baseline snapshot. Do not label the ambiguous delta as worker-introduced.

Workers report only their intentional edits and verification results. The parent computes the authoritative baseline-relative tracked and relevant untracked delta, verifies only attributable changes, enforces the approved ownership boundary and execution mode, and reruns relevant checks. Freeze the verified state before ending the workspace-write turn. No writer may change reviewed or verification-relevant paths until final review completes.

The final review must run in a separate read-only parent session. Supply the complete baseline-relative tracked diff and relevant untracked evidence. Immutable base and head revisions may replace that packet only when they fully encode the reviewed change set and the relevant worktree is clean. Compare the repository with the frozen pre-review baseline after review; any intervening or reviewer-time mutation invalidates the verdict.

The reviewer returns a remediation class:

- `none`: valid only with `VERDICT: ship`.
- `parent-evidence`: the parent repairs missing baseline, review inputs, model/permission attestation, or review-session evidence and reruns review without invoking a worker.
- `repository-change`: route bounded edits to native `worker_luna`; use native `worker_terra` only for a valid Terra condition.
- `mixed`: repair evidence in the parent and delegate only the repository-change portion.
- `replan`: return architecture, requirements, or scope changes to the planner or user.

Every repository change requires new parent verification, a new frozen evidence packet, and a fresh separate read-only review.
