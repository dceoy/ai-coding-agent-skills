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

## Project identity and baseline modes

Fix an explicit workspace boundary as `PROJECT_ROOT` before planning or any write, and canonicalize it with `cd "$PROJECT_ROOT" && pwd -P`. Do not walk upward and adopt an unrelated Git repository. Every owned path and manifest record is project-relative.

Use exactly one initial baseline mode:

- `git-head`: a valid Git worktree with a resolvable commit `HEAD`.
- `git-unborn`: a valid Git worktree without a resolvable `HEAD`; record `HEAD` as `unborn:<full-symbolic-ref>` from `git symbolic-ref -q HEAD`.
- `filesystem`: no Git worktree applies to `PROJECT_ROOT`; record `HEAD: absent`, `git-dir: absent`, and `common-dir: absent`.

A present but invalid `.git` marker is unsupported, not `filesystem`. Git initialization or creation of the first commit is a baseline-mode transition and must be explicitly authorized by the planner contract.

The canonical identity always contains the physical `PROJECT_ROOT` and mode. Git modes additionally contain the physical worktree root, worktree Git directory, and common Git directory. `PROJECT_ROOT` and all owned paths must remain inside the resolved worktree and approved project boundary.

For `git-head`, retain the commit ID, complete porcelain-v2 status, staged and unstaged diffs, untracked inventory, tracked-content manifest, verification-relevant ignored paths, and expected-absent records. For `git-unborn`, retain the symbolic `HEAD`, complete porcelain-v2 status, staged diff against the empty tree, unstaged diff, a deterministic index manifest from exact `git ls-files --stage -z` records, and a complete project-root filesystem manifest. For `filesystem`, use no Git commands and retain a complete project-root filesystem manifest.

A filesystem manifest is a deterministically sorted, byte-safe project-relative inventory. Do not follow symlinks. Record directories with path, kind, and mode; regular files with path, kind, mode, byte length, and SHA-256 over raw bytes; symlinks with path, kind, mode, and SHA-256 over raw link-target bytes; and required missing paths as `expected-absent`. Sockets, FIFOs, devices, unreadable entries, path escapes, and unstable filesystem kinds are unsupported unless explicitly excluded as mutable scratch that cannot influence implementation or verification. In `git-unborn`, Git administrative storage may be excluded from raw filesystem hashing only when semantic Git evidence covers it; repository-local Git configuration, attributes, excludes, and hooks that can influence verification remain frozen inputs. Out-of-root symlink target content is an external input when it can influence results.

The implementation packet and fresh review must use the same mode-specific identity and evidence. A mode transition must appear in the baseline-relative delta; any unapproved transition or mismatched root, mode, Git evidence, manifest, exclusion inventory, or external-input evidence invalidates the verdict.

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
Use native multi-agent dispatch to invoke `planner` and obtain its five-part implementation contract. Fix the physical PROJECT_ROOT, select git-head, git-unborn, or filesystem baseline mode, and resolve every material decision before editing. Require verification to declare a complete hermetic boundary or enumerate every verification-relevant ignored or excluded project path and mutable external input. External-input evidence must cover applicable executable identities, repository-local and user/global configuration, external files and out-of-root symlink targets, environment-variable names with non-secret stable identities or, for non-secret values only, value digests, service endpoints with immutable response or artifact identifiers, container or operating-system identity, locale, clock assumptions, and random seeds. Never read, print, serialize, copy into evidence, or compute an unkeyed digest of a secret value. Represent a secret only by a non-secret immutable secret-manager version or revision identifier, or by an externally produced keyed attestation whose key and raw secret never enter the agent context. If no safe comparable identity exists, treat verification as unsupported. Capture the complete mode-specific pre-implementation project and external-input baseline, then implement the approved contract directly in the top-level main agent with reasoning_effort=xhigh. Compute and inspect the full baseline-relative delta, rerun verification in the main session, and freeze the reviewed project and external environment state. Do not run final review in this workspace-write turn.
```

### Final review

End the implementation turn and start a fresh separate parent session in read-only mode:

```text
Use native multi-agent dispatch to invoke `advisor` with `fork_turns` set to `none`. Before dispatch, independently resolve and compare the physical PROJECT_ROOT, baseline mode, mode-specific HEAD and Git evidence, complete frozen review baseline, original path inventory and filesystem manifest, ignored or excluded-path inventory, verification-relevant external-input inventory and evidence, and hermetic boundary when applicable against the implementation packet. Retain runtime metadata proving the named definition, `gpt-5.6-sol`, `reasoning_effort=xhigh`, a fresh session, and effective read-only permission. Pass the original packet and parent comparison evidence to `advisor`; require it to repeat every project-state and external-input comparison before inspecting files or running verification. After review, recompute and compare the same project and external evidence against the original packet. Any mismatch invalidates the verdict.
```

For `git-head`, immutable base and head revisions may replace baseline-relative change evidence only when they fully encode the reviewed change set and the relevant worktree is clean. They are not a substitute in `git-unborn` or `filesystem` mode.

A hermetic-verification declaration may replace both excluded-path and external-input inventories only when it identifies immutable inputs and the complete environment boundary and lists excluded mutable scratch or cache paths with evidence that they cannot influence outcomes.

For a tracked gitlink/submodule in a Git mode (mode `160000`), record the path, `gitlink` kind, mode, full stage-zero index object ID, checked-out submodule `HEAD`, exact dirty-state output, and a SHA-256 digest over that canonical tuple. Unmerged, missing, uninitialized, or dirty gitlinks invalidate the freeze. Apply the same rule recursively and never mutate submodules automatically.

### Approval-gated workflow

Start planning in read-only mode:

```text
Use native multi-agent dispatch to invoke `planner` for the five-part implementation contract only. Fix PROJECT_ROOT and the baseline mode, resolve material decisions, and do not modify files.
```

After approval, perform implementation directly in a workspace-write main-agent turn, then use the final-review prompt in a separate read-only session.

### Advice only

Start the parent turn in read-only mode:

```text
Use native multi-agent dispatch to invoke `advisor` to evaluate this design. Return advice only and do not modify files.
```

## Routing policy

Use the main agent directly for simple questions and narrow deterministic edits. For non-trivial implementation, use `planner` first and then implement directly in the main agent.

The planner must define the physical project root, baseline mode, any authorized mode transition, and exact modifiable file and generated-artifact paths whenever they are knowable. When diagnosis or cross-cutting adaptation requires file discovery, it may instead define the smallest bounded module, package, or directory ownership zone plus explicit exclusions. The main agent may discover and modify files only inside that approved zone.

Verification must cover the selected project-state baseline and all mutable inputs outside its manifest that can influence results. Prefer a hermetic environment. When verification is not hermetic, require frozen, replayable, or independently attestable evidence for the complete external-input inventory. For secret inputs, evidence must use only a non-secret immutable secret-manager version or revision identifier, or an externally produced keyed attestation whose key and raw secret never enter the agent context; never read, expose, or unkeyed-hash secret values. Missing or unverifiable inputs are a fail-closed result, not permission to assume stability.

An unresolved material architectural, product, security, authentication, authorization, data-model, migration, compatibility, externally visible interface, project-root, baseline-mode, or external-input decision is a replanning or advice condition. It is not permission to expand scope during implementation.

## Native execution support

Before planning or final review, verify that the native runtime resolves the named role, loaded definition source, configured model and reasoning effort, configured sandbox, and effective permission mode. Runtime metadata is the attestation; TOML contents and child self-reports are not substitutes.

Require effective `reasoning_effort=xhigh` for `planner`, the main implementation phase, and `advisor`. If native named-agent dispatch cannot resolve `planner` or `advisor`, or cannot attest the required effective model, reasoning effort, sandbox, or permission mode for those roles, stop and report `unsupported`. Do not fall back to `codex exec`, nested Codex CLI processes, shell wrappers, generic children, copied prompts, or compatibility modes.

## Attribution and review integrity

Before implementation, capture the complete mode-specific project baseline and every verification-relevant external-input record. Prevent other writers from modifying approved or verification-relevant project paths until final evidence capture. External inputs must remain frozen or must be independently re-attestable throughout implementation and review.

The main agent owns implementation, authoritative baseline-relative project and external-input evidence, scope enforcement, inspection, and verification. If an unexpected mutation appears, exclusive access is violated, the baseline mode changes without authorization, or external evidence changes, stop and reconcile rather than attributing or ignoring the change.

Freeze the verified project and external environment state before ending the workspace-write turn. Final review must run in a fresh separate read-only parent session and receive the complete original packet. The parent and advisor must verify all project-root, baseline-mode, Git-state when applicable, filesystem-manifest, excluded-path, external-input, hermetic-boundary, and runtime-attestation values before inspection or verification; the parent repeats them after review. Any mismatch invalidates the verdict.

The reviewer returns a remediation class:

- `none`: valid only with `VERDICT: ship`.
- `parent-evidence`: repair missing baseline, external-input, review-input, model, permission, or session evidence without changing the project.
- `repository-change`: the main agent implements the bounded fix directly.
- `mixed`: repair evidence and implement the project-change portion directly.
- `replan`: return architecture, requirements, verification environment, project root, baseline mode, or scope changes to `planner` or the user.

Every project change, baseline-mode change, or verification-relevant external-input change requires new main-agent verification, a new frozen evidence packet, and a fresh separate read-only review.
