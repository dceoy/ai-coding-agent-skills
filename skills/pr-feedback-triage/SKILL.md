---
name: pr-feedback-triage
description: Triage pull request feedback against the current head, apply focused fixes, and finish the required replies and thread resolutions.
allowed-tools: Bash(git:*), Bash(gh:*), mcp__github__*, Read, Grep, Glob, Edit, MultiEdit, Write
---

# PR Feedback Triage

Drive all current PR feedback through analysis, focused fixes, replies, and thread resolution on the latest live head. Use the same procedure standalone or inside a larger PR loop.

## Invariants

- The top-level agent owns every repository and GitHub mutation; delegate feedback analysis only to one fresh independent read-only native subagent.
- Bind every disposition, fix, reply, and resolution to the exact PR head SHA and feedback snapshot used to decide it. If the head changes, discard stale prepared work and restart triage on the new live head.
- The feedback-analysis subagent is a terminal leaf: no mutation, re-entry, or further delegation. If it causes Git-visible mutation, reject its output and stop before any fix, reply, or resolution.
- Require a finite caller- or runtime-enforced subagent deadline; otherwise report `unsupported` and stop. Do not retry ambiguously accepted work.
- Treat subagent output as advisory and validate it before acting.
- Keep changes scoped to feedback. Apply KISS, DRY, and YAGNI and preserve unrelated local work.
- Never publish unrelated local state. Immediately before a fix batch, require the live head and feedback to equal the analyzed snapshot, then use a clean isolated worktree rooted exactly at that analyzed head; leave unrelated local changes or unpushed commits untouched. Push only the resulting feedback-fix commit(s) to the recorded PR head ref without force; if the push loses a concurrent head race, restart from the latest live snapshot.
- Do not require an intervening PR review when the head changes; review/merge gating belongs to the caller or orchestrator after triage.

## Feedback Contract

Snapshot the exact live head repository/ref/SHA and all current feedback. Paginate platform reads and preserve typed source IDs plus source-head provenance when available:

- `thread:<id>`: inline thread/comment, with original/review commit metadata when available;
- `comment:<id>`: PR-level comment, with source head when established, otherwise `none`;
- `review:<id>`: review submission with reviewer, persisted state, submission time, reviewed/source head SHA, and body;
- copied feedback: non-platform source.

Historical feedback remains in scope and must be revalidated against the current head. Split independent findings into stable item-scoped records while retaining parent source IDs; merge only the same root cause.

Require one disposition per distinct item: `fix`, `already addressed`, `outdated`, `answer`, `clarify`, `defer`, or `won't fix`. A `fix` includes the smallest concrete edit and verification; `defer` / `won't fix` include `decision_terminal: true|false`. Every item also includes source IDs, concise reply guidance or `none`, and `resolve`, `leave_open`, or `not_resolvable` for each source. Resolve a parent thread only when every contributing item is resolve-eligible.

## Flow

```mermaid
flowchart TD
  A[Snapshot live head + feedback] --> B[Fresh read-only feedback-analysis subagent]
  B --> C{State still current?}
  C -->|Head changed| A
  C -->|Same-head feedback delta| A
  C -->|Stable| D[Validate dispositions]
  D --> E{Fixes?}
  E -->|Yes| U{Live state still analyzed snapshot?}
  U -->|No| A
  U -->|Yes| F[Rebind clean isolated worktree at analyzed head<br/>Batch fixes + QA + commit + non-force push]
  F --> V{Push accepted?}
  V -->|No: concurrent head race| A
  V -->|Yes| W[expected_head = pushed SHA]
  W --> H{Revalidation holds?}
  E -->|No| G[expected_head = analyzed SHA]
  G --> H
  H -->|No| A
  H -->|Yes| I{Fresh state?}
  I -->|Head changed| A
  I -->|Same-head feedback delta| A
  I -->|Stable| J[Reply + resolve eligible threads]
  J --> K[Record own GitHub mutations]
  K --> L{Final state?}
  L -->|Head changed| A
  L -->|Same-head feedback delta| A
  L -->|Stable| M{Expected resolution still open?}
  M -->|Yes| N[Retry once]
  N --> O{Resolved?}
  O -->|No| P[failed_action]
  O -->|Yes| Q{Completion blocker?}
  M -->|No| Q
  P --> Q
  Q -->|Yes| R[Stopped]
  Q -->|No| S[Complete]
```

Ignore only this run's recorded GitHub mutations during reconciliation. Require exact head equality before replies or resolutions; ancestry is insufficient. If the head differs, publish nothing from stale prepared actions and restart from the latest live head. No intervening review is required by this skill.

Resolve `defer` / `won't fix` only when `decision_terminal: true`; `clarify` and non-terminal decisions remain open.

An active `CHANGES_REQUESTED` review is `awaiting_re_review`. Explicit dismissal clears it; a later same-reviewer `APPROVED` clears it, a later same-reviewer `CHANGES_REQUESTED` replaces it as the active follow-up, and `COMMENTED` does not supersede it. Do not dismiss reviewer state to clear it. `awaiting_re_review` is terminal for triage and must be reported for the caller's later review/merge gate.

## Terminal States

Track every platform source as `resolved`, `replied_left_open`, `not_resolvable`, `awaiting_re_review`, or `failed_action`. `replied_left_open` is terminal only when its disposition is terminal.

Completion is blocked by unpublished fixes, missing clarification, non-terminal defer/won't-fix decisions, failed actions, unresolved QA, or unreconciled head/feedback changes.

## Output

Report the analyzed/final head SHA, disposition counts, fixes and verification, replies/resolutions, terminal-state counts, and any remaining blocker or required reviewer/user action.
