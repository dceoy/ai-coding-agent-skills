# Global Codex instructions

This file is the user-wide installation template. Project-local Codex sessions read the same routing policy from the repository-root `AGENTS.md`.

## Native named-agent dispatch

`planner` and `advisor` must be dispatched only through Codex's native multi-agent tools. Their TOML files define native read-only roles; do not invoke them through `codex exec`, nested Codex CLI processes, shell wrappers, equivalent subprocess dispatch, copied prompts, or agent simulations.

Implementation is owned by the top-level main agent. Do not delegate implementation to named or generic worker subagents. If native named-agent dispatch is unavailable for a phase that requires `planner` or `advisor`, stop and report `unsupported`; do not silently omit or simulate that phase.

## Model routing

This section applies only to the top-level main agent. The named `planner` and `advisor` agents must follow their own definitions and must not spawn or delegate to another subagent.

Use the main agent directly for simple questions and narrow, deterministic edits when planning overhead is not justified.

For non-trivial implementation tasks:

1. Invoke `planner` before modifying files.
2. Require its five-part implementation contract: objective, files and ownership, interfaces, constraints, and verification.
3. Do not begin implementation while a material architectural, product, security, authentication, authorization, data-model, migration, compatibility, or externally visible interface decision remains unresolved. Return the smallest blocking question to `planner`, `advisor`, or the user.
4. Preserve the approved contract's scope, settled decisions, interfaces, acceptance checks, ownership boundary, and explicit exclusions.
5. Capture the approved pre-implementation baseline: current `HEAD`, porcelain-v2 status, staged and unstaged diffs, the untracked-file inventory, and content or cryptographic hashes for every relevant untracked file. Establish exclusive write ownership over every approved and verification-relevant path until final evidence capture.
6. Retain runtime metadata for the planning, main-agent implementation, and final-review phases. Require configured and effective `reasoning_effort=xhigh` for `planner`, the main implementation agent, and `advisor`. For the named roles, metadata must also identify the resolved role, loaded definition source, configured and effective model, configured sandbox, and effective permission mode. Missing or lower required reasoning is a fail-closed result.
7. The main agent implements the contract directly. It may discover exact affected files only inside a bounded ownership zone explicitly approved by the contract. It must not delegate implementation to a worker subagent.
8. If implementation exposes a material decision not covered by the contract or requires crossing the approved ownership boundary, stop and return to `planner`, `advisor`, or the user instead of silently expanding scope.
9. Compute the complete baseline-relative tracked and relevant untracked delta. Inspect every attributable change, preserve pre-existing work, reject unexpected or unattributable concurrent mutations, and rerun all relevant verification in the main session.
10. Freeze the verified repository state and capture a complete frozen review baseline. It must include the canonical repository/worktree identity, exact `HEAD`, complete unedited `git status --porcelain=v2 --branch --untracked-files=all` output, a deterministically sorted repository-relative path inventory, and the original SHA-256 manifest for every tracked path present in the worktree and every non-ignored untracked file. Each manifest record must include the path, filesystem kind and mode, and a digest over raw file bytes or symlink-target bytes; include explicit expected-absent records for deleted paths in the reviewed change set. For a tracked gitlink/submodule (mode `160000`), record the path, `gitlink` kind, mode, full stage-zero index object ID, checked-out submodule `HEAD`, and exact dirty-state output, plus a SHA-256 digest over that canonical tuple. A gitlink is valid only when its stage-zero index entry exists, its checked-out `HEAD` resolves, and its status is clean; unmerged, missing, uninitialized, or dirty gitlinks invalidate the freeze. Apply the same rule to nested tracked gitlinks, and never initialize, clean, reset, or otherwise mutate a submodule automatically. Define the canonical repository/worktree identity as this physical-path triplet: worktree root `cd "$(git rev-parse --show-toplevel)" && pwd -P`, worktree Git directory `cd "$(git rev-parse --git-dir)" && pwd -P`, and common Git directory `cd "$(git rev-parse --git-common-dir)" && pwd -P`.
11. End the workspace-write implementation turn. Start a fresh, separate parent session in read-only mode and invoke `advisor` with no inherited implementation history (`fork_turns: "none"`). Before dispatching `advisor`, the fresh parent must independently resolve the canonical repository/worktree identity and recompute `HEAD`, complete porcelain-v2 status, the original path inventory, and the original SHA-256 manifest. It must compare every value exactly with the complete frozen review baseline; a mismatch or missing comparison evidence stops the review. Provide the advisor with the user goal, approved contract, complete baseline-relative change set, relevant untracked-file evidence, main-session verification evidence, canonical identity, complete frozen review baseline, original path inventory, original SHA-256 manifest, and the parent comparison evidence.
12. Require runtime evidence that the native `advisor` definition resolved with `gpt-5.6-sol`, `reasoning_effort=xhigh`, `fork_turns: "none"`, a fresh session, and effective read-only permission. The advisor must complete this check before inspecting files or running verification. It must independently repeat the canonical identity and frozen-baseline comparisons against the original packet received from the parent. If the target identity, baseline, manifest, comparison, or required runtime evidence is missing or mismatched, the reviewer must return `fix-first` with `REMEDIATION: parent-evidence`; never accept `ship`.
13. After review, the fresh parent must recompute the same canonical identity, `HEAD`, complete porcelain-v2 status, path inventory, and SHA-256 manifest and compare them against the original frozen review baseline, not a reviewer-generated replacement. Any mutation, identity mismatch, or manifest mismatch during or after review invalidates the verdict and requires a new freeze and fresh review.
14. Do not report completion unless the attested `advisor` returns `VERDICT: ship`. Repository changes required by review are implemented directly by the main agent, followed by new verification, a new frozen evidence packet, and a fresh review.

For architecture, design evaluation, or technical advice without implementation, invoke `advisor` and keep the work read-only.

Do not invoke a subagent when the main agent can complete a non-implementation task safely and efficiently without delegation.
