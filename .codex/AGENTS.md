# Global Codex instructions

This file is the user-wide installation template. Project-local Codex sessions read the same routing policy from the repository-root `AGENTS.md`.

## Native named-agent dispatch

`planner` and `advisor` must be dispatched only through Codex's native multi-agent tools. Their TOML files define native read-only roles; do not invoke them through `codex exec`, nested Codex CLI processes, shell wrappers, equivalent subprocess dispatch, copied prompts, or agent simulations.

Implementation is owned by the top-level main agent. Do not delegate implementation to named or generic worker subagents. If native named-agent dispatch is unavailable for a phase that requires `planner` or `advisor`, stop and report `unsupported`; do not silently omit or simulate that phase.

## Model routing

This section applies only to the top-level main agent. The named `planner` and `advisor` agents must follow their own definitions and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and narrow, deterministic edits when planning overhead is not justified.

### Project identity and baseline modes

Before planning or any write, fix an explicit workspace boundary as `PROJECT_ROOT` and canonicalize it with `cd "$PROJECT_ROOT" && pwd -P`. Do not walk upward and adopt an unrelated Git repository. Every owned path, manifest path, and expected-absent record is relative to this physical project root. If the root cannot be fixed and re-resolved independently, treat the workflow as unsupported.

Classify the initial state into exactly one baseline mode:

- `git-head`: `PROJECT_ROOT` is inside a valid Git worktree and `git rev-parse --verify HEAD` resolves to a commit.
- `git-unborn`: `PROJECT_ROOT` is inside a valid Git worktree, but `HEAD` does not resolve. Record `HEAD` as `unborn:<full-symbolic-ref>` from `git symbolic-ref -q HEAD`; a missing or invalid symbolic ref makes the state unsupported.
- `filesystem`: no Git worktree applies to `PROJECT_ROOT`. Record `HEAD: absent`, `git-dir: absent`, and `common-dir: absent`.

A present `.git` marker or discovered Git administration directory that cannot be validated is corrupt or ambiguous state, not `filesystem`; fail closed.

The canonical project identity always includes the physical `PROJECT_ROOT` and baseline mode. For `git-head` and `git-unborn`, it also includes the physical Git worktree root, worktree Git directory, and common Git directory produced by `cd "$(git rev-parse --show-toplevel)" && pwd -P`, `cd "$(git rev-parse --git-dir)" && pwd -P`, and `cd "$(git rev-parse --git-common-dir)" && pwd -P`. `PROJECT_ROOT` must be inside that worktree, and the approved ownership boundary must remain inside `PROJECT_ROOT`.

Use a deterministically sorted, byte-safe project-relative filesystem manifest whenever Git has no resolved `HEAD`, and as the content manifest required by the selected mode. Do not follow symlinks. Record directories with path, kind, and mode; regular files with path, kind, mode, byte length, and SHA-256 over raw bytes; symlinks with path, kind, mode, and SHA-256 over raw link-target bytes; and required missing paths as explicit `expected-absent` records. Sockets, FIFOs, devices, unreadable entries, path escapes, or unstable filesystem kinds make the baseline unsupported unless the planner explicitly excludes them as mutable scratch that cannot influence implementation or verification.

For `git-head`, retain the exact commit ID, complete porcelain-v2 status, staged and unstaged diffs, untracked inventory, tracked-content manifest, verification-relevant ignored paths, and expected-absent records. For `git-unborn`, retain the symbolic `HEAD` marker, complete porcelain-v2 status, staged diff against the empty tree, unstaged diff, a deterministic index manifest from the exact `git ls-files --stage -z` records, and a complete project-root filesystem manifest excluding only Git administrative storage covered by the semantic Git evidence and planner-declared non-influential scratch paths. Repository-local Git configuration, attributes, excludes, and hooks that can influence verification must be frozen as verification inputs. For `filesystem`, do not require Git commands; retain the complete project-root filesystem manifest and planner-declared exclusions. In every mode, a symlink target outside `PROJECT_ROOT` is an external input if its target content can influence results.

### Planning mutation guard

A workspace-write parent must capture the complete initial-mode project baseline before invoking `planner`. This pre-planning guard includes canonical identity, mode-specific Git evidence when applicable, the required filesystem or tracked-content manifest, relevant untracked and ignored-path evidence, and expected-absent records. Planner-declared external inputs that are not yet known are captured after planning and before implementation.

Pass the fixed `PROJECT_ROOT`, initial baseline mode, and guard identity to `planner`. Immediately after `planner` returns, independently recapture the same project evidence and compare it byte-for-byte with the pre-planning guard. Any file, Git/index/worktree, ignored-path, expected-absent, project-root, or baseline-mode change invalidates the contract and stops the workflow. Do not absorb a planner mutation into the pre-implementation baseline.

A planning-only parent session with effective read-only permission may replace the workspace-write guard, but a later write-capable implementation session must still re-resolve the same project identity and compare the complete project baseline before accepting the contract. When the comparison is exact, the guard snapshot may be reused as the project portion of the pre-implementation baseline.

### Baseline-mode transitions

Only these transitions are supported, and each must be explicitly authorized by the planner contract:

- `filesystem -> git-unborn`
- `filesystem -> git-head`, with a recorded `git-unborn` checkpoint after Git initialization and before the first commit
- `git-unborn -> git-head`

Transitions from `git-head`, transitions back to `filesystem` or `git-unborn`, and any unlisted transition are unsupported.

A transition bridge must preserve the immutable initial baseline and connect it to the final-mode baseline. It contains:

1. The initial canonical identity, initial mode, and complete initial-mode evidence.
2. The authorized transition and the exact commands or operations that performed it.
3. Every intermediate Git checkpoint: physical worktree/Git/common directories, symbolic `HEAD`, complete status, index manifest, staged and unstaged evidence, and verification-relevant Git configuration, attributes, excludes, and hooks.
4. A source-to-final project-relative filesystem-manifest delta, including expected-absent, untracked, ignored-path, and external-input evidence.
5. When a first commit is created, its commit and tree IDs, the final stage-zero index manifest, and evidence that the commit tree matches the intended final tracked content.

A clean final `git status` or final commit pair is never sufficient by itself. The final review packet must include both the immutable initial baseline and the complete transition bridge.

For non-trivial implementation tasks:

1. Fix `PROJECT_ROOT`, classify the initial baseline mode, and capture the pre-planning guard before invoking `planner`.
2. Invoke `planner` and require its five-part implementation contract: objective, files and ownership, interfaces, constraints, and verification.
3. Recompute and compare the complete project baseline against the pre-planning guard. Reject the contract on any mismatch.
4. Require the contract to preserve the fixed `PROJECT_ROOT` and initial baseline mode; authorize only a supported transition; and declare either a hermetic boundary or every verification-relevant ignored or otherwise excluded project-relative path and every mutable external input that can influence results. External inputs include applicable executable identities, repository-local and user or global configuration, external files, environment-variable names with non-secret stable identities or, for non-secret values only, value digests, service endpoints with immutable response or artifact identifiers, container or operating-system identity, locale, clock assumptions, and random seeds. Never read, print, serialize, copy into evidence, or compute an unkeyed digest of a secret value. Represent a secret only by a non-secret immutable secret-manager version or revision identifier, or by an externally produced keyed attestation whose key and raw secret never enter the agent context. If no safe comparable identity exists, treat verification as unsupported.
5. Do not begin implementation while a material architectural, product, security, authentication, authorization, data-model, migration, compatibility, externally visible interface, project-root, baseline-mode, transition, or unverifiable external-input decision remains unresolved. Return the smallest blocking question to `planner`, `advisor`, or the user.
6. Capture the approved pre-implementation baseline. Reuse the unchanged pre-planning project guard when valid, then add the planner-declared ignored/excluded-path inventory and frozen or independently attestable evidence for every verification-relevant external input. Establish exclusive write ownership over every approved and verification-relevant project path until final evidence capture.
7. Retain runtime metadata for the planning, main-agent implementation, and final-review phases. Require configured and effective `reasoning_effort=xhigh` for `planner`, the main implementation agent, and `advisor`. For named roles, metadata must also identify the resolved role, loaded definition source, configured and effective model, configured sandbox, and effective permission mode. Missing or lower required reasoning is a fail-closed result.
8. The main agent implements the contract directly. It may discover exact affected files only inside a bounded ownership zone explicitly approved by the contract. It must not delegate implementation to a worker subagent.
9. If implementation exposes a material decision not covered by the contract, requires crossing the approved ownership boundary, performs an unauthorized or unsupported baseline-mode transition, or introduces a verification-relevant external input that is not frozen, replayable, or independently attestable, stop and return to `planner`, `advisor`, or the user instead of silently expanding scope.
10. Compute the complete baseline-relative delta. Without a mode transition, use the initial mode's Git/index/worktree and manifest evidence. With a transition, use the complete transition bridge from the immutable initial baseline to the final-mode baseline. Inspect every attributable change, preserve pre-existing work, reject unexpected or unattributable concurrent mutations, and rerun all relevant verification in the main session.
11. Freeze the verified state and capture a complete review packet. It must include the pre-planning guard, post-planner equality evidence, approved contract, immutable initial baseline, transition bridge when applicable, final canonical identity and mode-specific evidence, path and filesystem manifests, expected-absent records, ignored or excluded-path inventory, external-input evidence or hermetic declaration, complete baseline-relative change set, and verification evidence.
12. For a tracked gitlink/submodule in a Git mode (mode `160000`), record the path, `gitlink` kind, mode, full stage-zero index object ID, checked-out submodule `HEAD`, exact dirty-state output, and a SHA-256 digest over that canonical tuple. A gitlink is valid only when its stage-zero index entry exists, its checked-out `HEAD` resolves, and its status is clean; unmerged, missing, uninitialized, or dirty gitlinks invalidate the freeze. Apply the same rule recursively and never mutate submodules automatically.
13. End the workspace-write implementation turn. Start a fresh, separate parent session in read-only mode and invoke `advisor` with no inherited implementation history (`fork_turns: "none"`). Before dispatch, independently compare the pre-planning guard, post-planner equality evidence, initial and final identities, baseline modes, transition bridge, Git evidence when applicable, path inventory, filesystem manifest, ignored or excluded-path inventory, external-input evidence, and hermetic boundary against the original frozen packet. A mismatch or missing comparison evidence stops the review.
14. Require runtime evidence that the native `advisor` definition resolved with `gpt-5.6-sol`, `reasoning_effort=xhigh`, `fork_turns: "none"`, a fresh session, and effective read-only permission. The advisor must independently repeat every planning-guard, project-state, transition, external-input, hermetic-boundary, and frozen-baseline comparison before inspecting files or running verification. Missing, unverifiable, or mismatched evidence requires `fix-first` with `REMEDIATION: parent-evidence`; never accept `ship`.
15. After review, the fresh parent must recompute the same final canonical identity, mode-specific Git evidence, path inventory, filesystem manifest, ignored or excluded-path inventory, external-input evidence, and hermetic boundary and compare them against the original frozen packet. Any project mutation, external-input change, identity mismatch, mode change, or evidence mismatch invalidates the verdict and requires a new freeze and fresh review.
16. Do not report completion unless the attested `advisor` returns `VERDICT: ship`. Project changes required by review are implemented directly by the main agent, followed by new verification, a new frozen evidence packet, and a fresh review.

For architecture, design evaluation, or technical advice without implementation, invoke `advisor` and keep the work read-only.

Do not invoke a subagent when the main agent can complete a non-implementation task safely and efficiently without delegation.
