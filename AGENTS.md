# Repository Guidelines

## Repository Purpose

This is a single-source skill library shared across AI coding runtimes. The `skills/` directory is the authoritative source of truth; runtime-specific directories reference it via symlinks.

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

A present `.git` marker or discovered Git administration directory that cannot be validated is corrupt or ambiguous state, not `filesystem`; fail closed. A transition between modes, including Git initialization or creation of the first commit, must be explicitly authorized by the planner contract and represented in the baseline-relative delta.

The canonical project identity always includes the physical `PROJECT_ROOT` and baseline mode. For `git-head` and `git-unborn`, it also includes the physical Git worktree root, worktree Git directory, and common Git directory produced by `cd "$(git rev-parse --show-toplevel)" && pwd -P`, `cd "$(git rev-parse --git-dir)" && pwd -P`, and `cd "$(git rev-parse --git-common-dir)" && pwd -P`. `PROJECT_ROOT` must be inside that worktree, and the approved ownership boundary must remain inside `PROJECT_ROOT`.

Use a deterministically sorted, byte-safe project-relative filesystem manifest whenever Git has no resolved `HEAD`, and as the content manifest required by the selected mode. Do not follow symlinks. Record directories with path, kind, and mode; regular files with path, kind, mode, byte length, and SHA-256 over raw bytes; symlinks with path, kind, mode, and SHA-256 over raw link-target bytes; and required missing paths as explicit `expected-absent` records. Sockets, FIFOs, devices, unreadable entries, path escapes, or unstable filesystem kinds make the baseline unsupported unless the planner explicitly excludes them as mutable scratch that cannot influence implementation or verification.

For `git-head`, retain the exact commit ID, complete porcelain-v2 status, staged and unstaged diffs, untracked inventory, tracked-content manifest, verification-relevant ignored paths, and expected-absent records. For `git-unborn`, retain the symbolic `HEAD` marker, complete porcelain-v2 status, staged diff against the empty tree, unstaged diff, a deterministic index manifest from the exact `git ls-files --stage -z` records, and a complete project-root filesystem manifest excluding only Git administrative storage covered by the semantic Git evidence and planner-declared non-influential scratch paths. Repository-local Git configuration, attributes, excludes, and hooks that can influence verification must be frozen as verification inputs. For `filesystem`, do not require Git commands; retain the complete project-root filesystem manifest and planner-declared exclusions. In every mode, a symlink target outside `PROJECT_ROOT` is an external input if its target content can influence results.

For non-trivial implementation tasks:

1. Invoke `planner` before modifying files.
2. Require its five-part implementation contract: objective, files and ownership, interfaces, constraints, and verification. The contract must declare `PROJECT_ROOT`, the baseline mode, any authorized mode transition, and either a hermetic boundary or every verification-relevant ignored or otherwise excluded project-relative path and every mutable external input that can influence results. External inputs include applicable executable identities, repository-local and user or global configuration, external files, environment-variable names with non-secret stable identities or, for non-secret values only, value digests, service endpoints with immutable response or artifact identifiers, container or operating-system identity, locale, clock assumptions, and random seeds. Never read, print, serialize, copy into evidence, or compute an unkeyed digest of a secret value. Represent a secret only by a non-secret immutable secret-manager version or revision identifier, or by an externally produced keyed attestation whose key and raw secret never enter the agent context. If no safe comparable identity exists, treat verification as unsupported.
3. Do not begin implementation while a material architectural, product, security, authentication, authorization, data-model, migration, compatibility, externally visible interface, project-root, baseline-mode, or unverifiable external-input decision remains unresolved. Return the smallest blocking question to `planner`, `advisor`, or the user.
4. Preserve the approved contract's scope, settled decisions, interfaces, acceptance checks, ownership boundary, project root, baseline mode, authorized mode transitions, verification-relevant ignored or excluded-path inventory, external-input inventory and evidence, hermetic boundary, and explicit exclusions.
5. Capture the approved pre-implementation baseline for the selected mode. Include canonical project identity; `HEAD` as a commit, `unborn:<ref>`, or `absent`; all required Git evidence for `git-head` or `git-unborn`; the applicable filesystem manifest and expected-absent records; and frozen or independently attestable evidence for every verification-relevant external input. Establish exclusive write ownership over every approved and verification-relevant project path until final evidence capture.
6. Retain runtime metadata for the planning, main-agent implementation, and final-review phases. Require configured and effective `reasoning_effort=xhigh` for `planner`, the main implementation agent, and `advisor`. For named roles, metadata must also identify the resolved role, loaded definition source, configured and effective model, configured sandbox, and effective permission mode. Missing or lower required reasoning is a fail-closed result.
7. The main agent implements the contract directly. It may discover exact affected files only inside a bounded ownership zone explicitly approved by the contract. It must not delegate implementation to a worker subagent.
8. If implementation exposes a material decision not covered by the contract, requires crossing the approved ownership boundary, changes the baseline mode without explicit authorization, or introduces a verification-relevant external input that is not frozen, replayable, or independently attestable, stop and return to `planner`, `advisor`, or the user instead of silently expanding scope.
9. Compute the complete baseline-relative delta using the selected mode: Git/index/worktree plus relevant untracked, ignored, and external-input evidence for `git-head`; index, worktree, complete filesystem-manifest, and external-input evidence for `git-unborn`; or complete filesystem-manifest and external-input evidence for `filesystem`. Inspect every attributable change, preserve pre-existing work, reject unexpected or unattributable concurrent mutations, and rerun all relevant verification in the main session.
10. Freeze the verified state and capture a complete review baseline for the final mode. It must include the canonical project identity, mode-specific `HEAD` marker, all required Git evidence when applicable, a deterministically sorted project-relative path inventory, the planner-declared ignored or excluded-path inventory, the planner-declared external-input inventory and evidence or a hermetic-verification declaration, and the original mode-appropriate SHA-256 filesystem manifest. Include expected-absent records. External-input records must identify the input without exposing secret values, state how it influences verification, and contain a reproducible digest for non-secret values, immutable identifier, or other independently comparable attestation. For a secret input, the record may contain only a non-secret immutable secret-manager version or revision identifier, or an externally produced keyed attestation whose key and raw secret never enter the agent context. Plaintext secrets, raw secret values, and unkeyed secret-derived digests invalidate the freeze. An input that cannot be safely identified and compared invalidates the freeze. A hermetic declaration may replace both inventories only when it identifies immutable inputs and the complete environment boundary and lists excluded mutable scratch or cache paths with evidence that they cannot influence outcomes.
11. For a tracked gitlink/submodule in a Git mode (mode `160000`), record the path, `gitlink` kind, mode, full stage-zero index object ID, checked-out submodule `HEAD`, exact dirty-state output, and a SHA-256 digest over that canonical tuple. A gitlink is valid only when its stage-zero index entry exists, its checked-out `HEAD` resolves, and its status is clean; unmerged, missing, uninitialized, or dirty gitlinks invalidate the freeze. Apply the same rule recursively and never mutate submodules automatically.
12. End the workspace-write implementation turn. Start a fresh, separate parent session in read-only mode and invoke `advisor` with no inherited implementation history (`fork_turns: "none"`). Before dispatch, independently re-resolve and compare `PROJECT_ROOT`, baseline mode, mode-specific identity and `HEAD` marker, Git evidence when applicable, path inventory, filesystem manifest, ignored or excluded-path inventory, external-input evidence, and hermetic boundary against the original frozen packet. A mismatch or missing comparison evidence stops the review. Provide the advisor with the user goal, approved contract, complete baseline-relative change set, repository or filesystem-state evidence, external-input evidence, verification evidence, canonical project identity, complete frozen baseline, and parent comparison evidence.
13. Require runtime evidence that the native `advisor` definition resolved with `gpt-5.6-sol`, `reasoning_effort=xhigh`, `fork_turns: "none"`, a fresh session, and effective read-only permission. The advisor must independently repeat every project-state, external-input, hermetic-boundary, and frozen-baseline comparison before inspecting files or running verification. Missing, unverifiable, or mismatched evidence requires `fix-first` with `REMEDIATION: parent-evidence`; never accept `ship`.
14. After review, the fresh parent must recompute the same canonical project identity, baseline mode, mode-specific `HEAD` and Git evidence, path inventory, filesystem manifest, ignored or excluded-path inventory, external-input evidence, and hermetic boundary and compare them against the original frozen baseline. Any project mutation, external-input change, identity mismatch, mode change, or evidence mismatch invalidates the verdict and requires a new freeze and fresh review.
15. Do not report completion unless the attested `advisor` returns `VERDICT: ship`. Project changes required by review are implemented directly by the main agent, followed by new verification, a new frozen evidence packet, and a fresh review.

For architecture, design evaluation, or technical advice without implementation, invoke `advisor` and keep the work read-only.

Do not invoke a subagent when the main agent can complete a non-implementation task safely and efficiently without delegation.

## SKILL.md Frontmatter

Each `SKILL.md` uses YAML frontmatter:

```yaml
---
name: <skill-name>
description: <one-line description used for skill triggering>
allowed-tools: Bash, Read, Write, ... # tools the skill may use
---
```

## Adding or Modifying Skills

1. Create or edit `skills/<skill-name>/SKILL.md` — this is the canonical skill definition.
2. Claude Code picks up the skill automatically via `.claude/skills -> ../skills`. For non-Claude runtimes,
   add a per-skill symlink: `ln -s ../../skills/<skill-name> .agents/skills/<skill-name>`.
3. Keep `description` in the frontmatter precise — it controls when the skill auto-triggers in Claude Code.

## Autonomous and Scheduled Use

Do not duplicate skill instructions into separate routine files unless a runtime truly requires a self-contained prompt. Prefer invoking the canonical skill under `skills/` and passing schedule, PR, branch, or CI context from the runtime configuration.

For autonomous PR review, `skills/pr-review/SKILL.md` is the source of truth. It defines the GitHub posting contract used by CI, GitHub Actions, Claude Code Routines, and other automated review contexts.

## Local QA

Before committing, run the following checks:

| Check             | Command                          |
| ----------------- | -------------------------------- |
| Format Markdown   | `npx -y prettier -w './**/*.md'` |
| Lint Python       | `uv run ruff check`              |
| Type-check Python | `uv run pyright`                 |
| Run tests         | `uv run pytest`                  |

## Commit & Pull Request Guidelines

- Format Markdown files using `npx -y prettier -w './**/*.md'` before committing.
- Keep PRs focused and include: concise summary, affected workflow paths, linked issue/context, and regenerated `README.md` when workflow inventory changes.
- Branch names use appropriate prefixes on creation (e.g., `feature/...`, `bugfix/...`, `refactor/...`, `docs/...`, `chore/...`).
- When instructed to create a PR, create it as a draft with appropriate labels by default.
