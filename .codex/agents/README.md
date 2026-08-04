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

To keep definitions synchronized with a local clone, repeat the regular-file copy steps above. Use regular-file copies; Codex discovery may skip agent-definition symlinks. After copying, start a fresh Codex session and verify that native `planner` and `advisor` resolve from the expected definitions with the required role, model, reasoning, sandbox, and permission metadata. If either role is unavailable or the runtime cannot provide that capability evidence, stop and report `unsupported`.

Remove obsolete `planner-sol.toml`, `advisor-sol.toml`, `worker-luna.toml`, and `worker-terra.toml` files from existing user-wide installations to avoid duplicate or stale roles.

## Usage

### Plan and implement

Start the parent turn in workspace-write mode:

```text
Use native multi-agent dispatch to invoke `planner` and obtain its five-part implementation contract. Resolve every material decision before editing. Require verification to declare a complete hermetic boundary or enumerate every verification-relevant ignored repository path and mutable external input. External-input evidence must cover applicable executable identities, user/global configuration, external files, environment-variable names with non-secret stable identities or, for non-secret values only, value digests, service endpoints with immutable response or artifact identifiers, container or operating-system identity, locale, clock assumptions, and random seeds. Never read, print, serialize, copy into evidence, or compute an unkeyed digest of a secret value. Represent a secret only by a non-secret immutable secret-manager version or revision identifier, or by an externally produced keyed attestation whose key and raw secret never enter the agent context. If no safe comparable identity exists, treat verification as unsupported. Capture the complete pre-implementation repository and external-input baseline, then implement the approved contract directly in the top-level main agent with reasoning_effort=xhigh. Compute and inspect the full baseline-relative delta, rerun verification in the main session, and freeze the reviewed repository and external environment state. Do not run final review in this workspace-write turn.
```

### Final review

End the implementation turn and start a fresh separate parent session in read-only mode:

```text
Use native multi-agent dispatch to invoke `advisor` with `fork_turns` set to `none`. Before dispatch, independently resolve and compare the canonical repository/worktree identity, complete frozen review baseline, original path inventory, ignored-path inventory, verification-relevant external-input inventory and evidence, hermetic boundary when applicable, and original SHA-256 manifest against the implementation packet. Retain runtime metadata proving the named definition, `gpt-5.6-sol`, `reasoning_effort=xhigh`, a fresh session, and effective read-only permission. Pass the original packet and parent comparison evidence to `advisor`; require it to repeat every repository-state and external-input comparison before inspecting files or running verification. After review, recompute and compare the same repository and external evidence against the original packet. Any mismatch invalidates the verdict.
```

The canonical repository/worktree identity is the physical-path triplet produced by `cd "$(git rev-parse --show-toplevel)" && pwd -P`, `cd "$(git rev-parse --git-dir)" && pwd -P`, and `cd "$(git rev-parse --git-common-dir)" && pwd -P`.

The complete frozen review baseline includes that triplet, exact `HEAD`, complete unedited `git status --porcelain=v2 --branch --untracked-files=all` output, a deterministically sorted repository-relative path inventory, the planner-declared verification-relevant ignored-path inventory and external-input inventory or a hermetic-verification declaration, and the original SHA-256 manifest for every tracked path, every non-ignored untracked file, and every verification-relevant ignored path. Repository manifest records include path, filesystem kind and mode, and a digest over raw file bytes or symlink-target bytes; expected-absent paths receive explicit records.

External-input records identify each input without exposing secret values, explain how it influences verification, and contain a reproducible digest for non-secret values, immutable identifier, or other independently comparable attestation. A secret input may be represented only by a non-secret immutable secret-manager version or revision identifier, or by an externally produced keyed attestation whose key and raw secret never enter the agent context. Never read, print, serialize, copy into evidence, or compute an unkeyed digest of a secret value. Plaintext secrets, raw secret values, and unkeyed secret-derived digests invalidate the packet. Every external input must be frozen, replayable, or independently attestable. An input that cannot be safely identified and compared blocks verification and final review.

A hermetic-verification declaration may replace both inventories only when it identifies immutable inputs and the complete environment boundary and lists excluded mutable scratch or cache paths with evidence that they cannot influence outcomes.

For a tracked gitlink/submodule (mode `160000`), record the path, `gitlink` kind, mode, full stage-zero index object ID, checked-out submodule `HEAD`, exact dirty-state output, and a SHA-256 digest over that canonical tuple. Unmerged, missing, uninitialized, or dirty gitlinks invalidate the freeze. Apply the same rule recursively and never mutate submodules automatically.

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

Verification must cover both repository state and all mutable non-repository inputs that can influence results. Prefer a hermetic environment. When verification is not hermetic, require frozen, replayable, or independently attestable evidence for the complete external-input inventory. For secret inputs, evidence must use only a non-secret immutable secret-manager version or revision identifier, or an externally produced keyed attestation whose key and raw secret never enter the agent context; never read, expose, or unkeyed-hash secret values. Missing or unverifiable inputs are a fail-closed result, not permission to assume stability.

An unresolved material architectural, product, security, authentication, authorization, data-model, migration, compatibility, externally visible interface, or external-input decision is a replanning or advice condition. It is not permission to expand scope during implementation.

## Native execution support

Before planning or final review, verify that the native runtime resolves the named role, loaded definition source, configured model and reasoning effort, configured sandbox, and effective permission mode. Runtime metadata is the attestation; TOML contents and child self-reports are not substitutes.

Require effective `reasoning_effort=xhigh` for `planner`, the main implementation phase, and `advisor`. If native named-agent dispatch cannot resolve `planner` or `advisor`, or cannot attest the required effective model, reasoning effort, sandbox, or permission mode for those roles, stop and report `unsupported`. Do not fall back to `codex exec`, nested Codex CLI processes, shell wrappers, generic children, copied prompts, or compatibility modes.

## Attribution and review integrity

Before implementation, capture the complete repository baseline and every verification-relevant external-input record. Prevent other writers from modifying approved or verification-relevant repository paths until final evidence capture. External inputs must remain frozen or must be independently re-attestable throughout implementation and review.

The main agent owns implementation, authoritative baseline-relative repository and external-input evidence, scope enforcement, inspection, and verification. If an unexpected mutation appears, exclusive access is violated, or external evidence changes, stop and reconcile rather than attributing or ignoring the change.

Freeze the verified repository and external environment state before ending the workspace-write turn. Final review must run in a fresh separate read-only parent session and receive the complete original packet. The parent and advisor must verify all repository-state, ignored-path, external-input, hermetic-boundary, manifest, and runtime-attestation values before inspection or verification; the parent repeats them after review. Any mismatch invalidates the verdict.

The reviewer returns a remediation class:

- `none`: valid only with `VERDICT: ship`.
- `parent-evidence`: repair missing baseline, external-input, review-input, model, permission, or session evidence without changing the repository.
- `repository-change`: the main agent implements the bounded fix directly.
- `mixed`: repair evidence and implement the repository-change portion directly.
- `replan`: return architecture, requirements, verification environment, or scope changes to `planner` or the user.

Every repository change or verification-relevant external-input change requires new main-agent verification, a new frozen evidence packet, and a fresh separate read-only review.
