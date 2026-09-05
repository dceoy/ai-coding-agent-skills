---
name: pr-feedback-triage
description: Triage pull request feedback against an exact head, apply focused fixes, and finish the required replies and thread resolutions.
allowed-tools: Bash(git:*), Bash(gh:*), mcp__github__*, Read, Grep, Glob, Edit, MultiEdit, Write
---

# PR Feedback Triage

Drive all current PR feedback for one exact head through analysis, focused fixes, replies, and thread resolution. Use the same procedure standalone or inside a larger PR loop.

The top-level agent owns every repository and GitHub mutation. Delegate feedback analysis only to one fresh independent read-only native subagent; when composed into a larger orchestrator, execute this skill in that same top-level context rather than launching the skill itself as a subagent.

## Invariants

- Bind every disposition, fix, reply, and resolution to the exact PR head SHA and feedback snapshot used to decide it.
- The feedback-analysis subagent is a terminal read-only leaf: no edits, commits, pushes, replies, resolutions, re-entry, or further delegation.
- If the required subagent cannot run with a finite caller- or runtime-enforced deadline, report `unsupported` and stop. Do not retry ambiguously accepted work.
- Treat subagent output as advisory; the top-level agent validates dispositions and current repository/GitHub state before acting.
- Keep changes scoped to feedback. Apply KISS, DRY, and YAGNI and preserve unrelated local work.

## Feedback Analysis

Snapshot the exact head repository/ref/SHA and all current feedback. Preserve typed source IDs and source-head provenance when GitHub exposes it:

- `thread:<id>` for inline threads/comments, with original/review commit metadata when available;
- `comment:<id>` for PR-level comments, with source head when established, otherwise `none`;
- `review:<id>` for review submissions, including reviewer, persisted state, submission time, reviewed/source head SHA, and body;
- user-supplied copied feedback, marked as non-platform sources.

Paginate platform reads. Historical feedback remains in scope: source head is provenance, not a reason to discard the item. Split artifacts containing independent findings into stable item-scoped records while retaining the parent source ID; merge only the same root cause.

Dispatch one fresh feedback-analysis subagent with the recorded head, snapshot, current diff/code evidence needed to revalidate each item, and settled constraints. Require one disposition per distinct item:

- `fix`: smallest concrete edit and verification;
- `already addressed`: brief current-code evidence;
- `outdated`: brief evidence that it no longer applies;
- `answer`: concise answer with no code change;
- `clarify`: one focused question;
- `defer` / `won't fix`: reason plus `decision_terminal: true|false`.

For every item require source IDs, concise reply guidance or `none`, and `resolve`, `leave_open`, or `not_resolvable` for each source. Resolve a parent thread only when every contributing item is resolve-eligible.

After analysis returns, re-fetch the head and feedback. If the head changed, discard the analysis and restart on the new head. If external feedback changed on the same head, redispatch analysis with the fresh snapshot. Ignore only mutations explicitly recorded as this run's own.

## Execute

1. Validate the dispositions. If fixes exist, bind a safe worktree to the analyzed head, batch all fixes into one coherent change, run appropriate QA once, commit once, and push once. Never publish unrelated work or a partial conflicting batch.
2. Set `expected_head` to the analyzed SHA when no fix was pushed, otherwise to the exact pushed SHA. Revalidate prepared dispositions and actions against `expected_head`; refresh analysis if any no longer holds.
3. Before any reply or resolution require `current_head == expected_head`; ancestry is insufficient. Reconcile feedback against the analysis baseline plus this run's recorded mutations; refresh analysis first on any external delta.
4. Apply the validated replies and resolutions. Keep replies to one sentence by default and prefer resolve-only for self-evident fixes, already-addressed items, and outdated items.
5. Re-fetch the head and full feedback snapshot after acting. Reconcile external deltas and terminal states; retry an expected resolution once when safe, otherwise record `failed_action`. Restart on any external head/feedback change before completion.

Resolve `defer` / `won't fix` only when `decision_terminal: true`; `clarify` and non-terminal decisions remain open.

An active `CHANGES_REQUESTED` review is `awaiting_re_review`. Explicit dismissal clears it; a later same-reviewer `APPROVED` clears it, a later same-reviewer `CHANGES_REQUESTED` replaces it as the active blocker, and `COMMENTED` does not supersede it. Do not dismiss reviewer state to clear it.

## Terminal States

Track every platform source as `resolved`, `replied_left_open`, `not_resolvable`, `awaiting_re_review`, or `failed_action` after execution. `replied_left_open` is terminal only when its disposition is terminal.

Completion is blocked by unpublished fixes, missing clarification, non-terminal defer/won't-fix decisions, `awaiting_re_review`, failed actions, unresolved QA, or unreconciled head/feedback changes.

## Output

Report the analyzed/final head SHA, disposition counts, fixes and verification, replies/resolutions, terminal-state counts, and any remaining blocker or required reviewer/user action.
