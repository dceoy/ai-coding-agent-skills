# Codex custom subagents

These project-scoped agents separate planning and final review from implementation. Current Codex releases discover each standalone TOML file under `.codex/agents/` automatically; no per-agent registration in `.codex/config.toml` is required.

The examples target local Codex app, CLI, and IDE sessions. Tool-backed or programmatic integrations may not expose named project agents; verify runtime support before relying on these definitions. See [openai/codex#15250](https://github.com/openai/codex/issues/15250). Some current builds also reject Luna as a spawned subagent even when it is available as a top-level model; see [openai/codex#34700](https://github.com/openai/codex/issues/34700). Generic spawned children may not prove that a named definition loaded, so worker and reviewer attestation is mandatory.

- `planner_sol`: `gpt-5.6-sol`, maximum reasoning, read-only. Produces a five-part implementation contract with Luna-first routing.
- `advisor_sol`: `gpt-5.6-sol`, maximum reasoning, read-only. Provides technical advice or an attested fresh `ship / fix-first / rethink` review with an explicit remediation class.
- `worker_luna`: `gpt-5.6-luna`, maximum reasoning, workspace-write. Default worker for bounded, settled, and verifiable implementation contracts.
- `worker_terra`: `gpt-5.6-terra`, maximum reasoning, workspace-write. Handles bounded Terra escalation or constrained Luna-compatible execution when Luna cannot be spawned.

## Permission model

The sandbox values above are defaults, not immutable per-agent boundaries. A spawned agent inherits the parent turn's live permission mode, and runtime overrides such as `/permissions` or `--yolo` take precedence over the TOML defaults.

Use separate permission phases:

- Planning or advice only: start the parent turn in read-only mode.
- Planning and implementation: use a workspace-write parent turn. Planner read-only behavior is instruction-enforced in this phase.
- Final review: end the workspace-write turn and start a separate parent session in read-only mode.

A workspace-write parent cannot produce an acceptable final verdict merely by instructing a child not to edit. The review session must expose effective read-only permission and must receive no inherited implementation history. Before accepting a verdict, require one of these attested paths:

1. The separate read-only parent session resolved the named `advisor_sol` definition, selected `gpt-5.6-sol`, used `fork_turns: "none"`, and enforced effective read-only permission.
2. The separate read-only parent session received the `advisor_sol` final-review instructions explicitly and exposes visible model, permission, and session-isolation evidence.

A generic child response is not sufficient merely because it prints `VERDICT: ship`. If neither path can be attested, block completion with `REMEDIATION: parent-evidence`.

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
Use planner_sol to produce the five-part implementation contract and resolve all material decisions before implementation. Establish an attribution boundary: prefer a dedicated clean worktree, or ensure exclusive writes to all owned and verification-relevant paths. Capture the repository baseline and relevant untracked-file content or hashes. Preflight the selected named worker and model. Delegate to worker_luna unless the contract requires bounded file discovery. If Luna cannot be spawned because of a runtime limitation, execute the exact contract in the parent when safe or invoke worker_terra in explicit luna-compatibility mode with Luna's exact ownership and no discovery or adaptive authority. Compare the result against the baseline, block on unexpected or unattributable mutations, rerun validation in the parent session, freeze the reviewed repository state, and prepare a complete final-review evidence packet. Do not run final review in this workspace-write turn.
```

### Final review

End the implementation turn and start a separate parent session in read-only mode:

```text
Invoke advisor_sol with fork_turns set to none and retain evidence that the named definition, gpt-5.6-sol model, and effective read-only permission resolved. If named-agent attestation is unavailable, supply the advisor_sol final-review instructions explicitly in this separate read-only session and retain visible model, permission, and isolation evidence. Review the frozen goal, complete baseline-relative tracked diff, relevant untracked-file evidence, interfaces, constraints, and parent verification evidence. Return VERDICT and REMEDIATION. Confirm that the repository still matches the frozen pre-review baseline; any intervening or reviewer-time mutation invalidates the verdict.
```

### Approval-gated workflow

Start planning in read-only mode:

```text
Use planner_sol to produce the five-part implementation contract and a Luna-first executor recommendation only. Resolve material decisions and do not modify files. Treat runtime model availability as an execution concern, not a Terra condition.
```

After approval, use the plan-and-implement prompt in a workspace-write turn, then use the final-review prompt in a separate read-only session.

### Advice only

Start the parent turn in read-only mode:

```text
Use advisor_sol to evaluate this design. Return advice only and do not modify files.
```

## Routing policy

Use the main agent directly for simple questions and localized deterministic edits when delegation overhead is not justified. For planned delegated implementation, use `worker_luna` by default.

Before selecting a worker, settle all material architectural, product, security, authentication, authorization, data-model, migration, compatibility, and externally visible interface decisions. An unresolved material decision is a replanning or advice condition, not a reason to start Terra.

Luna is suitable when:

1. The objective and exact file ownership are bounded.
2. Architecture and externally visible interfaces are settled.
3. No material implementation decision remains unresolved.
4. Verification has concrete commands or inspectable acceptance evidence.

A Luna task may be non-trivial, span multiple files, or require substantial implementation. Complexity or apparent need for engineering judgment alone is not a Terra condition.

Use `worker_terra` in `terra-escalation` mode only after all material decisions are settled and one explicit condition exists:

- broad diagnosis inside a bounded ownership zone where the exact affected files are not yet known;
- cross-cutting adaptation whose exact file set must be discovered but remains inside that zone; or
- a documented Luna suitability failure or escalation identifying the concrete adaptive judgment Luna could not complete within exact ownership.

When exact ownership is known, route to Luna first. The planner must define Terra's smallest bounded ownership zone and explicit exclusions. Terra may discover files and make tactical decisions only inside that boundary while preserving settled interfaces and constraints.

Luna must perform its pre-edit suitability check. If bounded discovery is required, it returns control without changes. If it escalates after partial edits, it stops, reports every partial change, and returns control to the parent for a reviewed sequential handoff. Never run write-capable workers concurrently.

## Execution-environment fallback

Before delegation, preflight whether the runtime can resolve the named worker definition and configured model and retain either successful resolution evidence or the concrete failure.

If a Luna-suitable task cannot spawn `worker_luna`:

1. Do not reinterpret the failure as a Terra condition.
2. Prefer direct parent execution when it can safely honor the exact contract.
3. Otherwise invoke `worker_terra` in explicit `luna-compatibility` mode.
4. Preserve Luna's exact ownership, suitability checks, interfaces, constraints, and verification.
5. Grant no discovery, adaptive-judgment, or scope-expansion authority.
6. Stop with an unsupported-runtime result when no compliant executor is available.

## Attribution and review integrity

Before starting a worker, establish a mechanically enforceable attribution boundary:

1. Prefer a dedicated clean git worktree rooted at the captured `HEAD`.
2. If the current worktree is used, prohibit all other writers from modifying approved ownership or verification-relevant paths until verification and evidence capture finish.
3. Capture `HEAD`, status, staged and unstaged diffs, the untracked-file inventory, and content or cryptographic hashes for relevant pre-existing untracked files.

A baseline identifies pre-existing state but cannot distinguish a worker write from a concurrent write made after capture. If an unexpected mutation appears or exclusive access was violated, stop and reconcile or restart from an isolated worktree. Do not label the ambiguous delta as worker-introduced.

After the worker returns, verify only attributable changes, enforce the approved ownership boundary and execution mode, and rerun relevant checks. Freeze the verified state before ending the workspace-write turn. No writer may change reviewed or verification-relevant paths until final review completes.

The final review must run in a separate read-only parent session. Supply the complete baseline-relative tracked diff and relevant untracked evidence. Immutable base and head revisions may replace that packet only when they fully encode the reviewed change set and the relevant worktree is clean. Compare the repository with the frozen pre-review baseline after review; any intervening or reviewer-time mutation invalidates the verdict.

The reviewer returns a remediation class:

- `none`: valid only with `VERDICT: ship`.
- `parent-evidence`: the parent repairs missing baseline, review inputs, model/permission attestation, or review-session evidence and reruns review without invoking a worker.
- `repository-change`: route bounded edits to Luna or Luna compatibility; use Terra escalation only for a valid Terra condition.
- `mixed`: repair evidence in the parent and delegate only the repository-change portion.
- `replan`: return architecture, requirements, or scope changes to the planner or user.

Every repository change requires new parent verification, a new frozen evidence packet, and a fresh separate read-only review.
