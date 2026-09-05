---
name: pr-feedback-triage
description: Triage pull request feedback against an exact head into validated fixes, replies, clarification requests, or terminal follow-ups.
allowed-tools: Bash(git:*), Bash(gh:*), mcp__github__*, Read, Grep, Glob, Edit, MultiEdit, Write
---

# PR Feedback Triage

Triage all current PR feedback against one exact head SHA. Keep the analysis reusable by a larger PR loop while remaining able to execute fixes and GitHub actions when invoked standalone.

## Ownership

- Bind every decision to the exact PR head SHA and feedback snapshot used to make it.
- If a caller or orchestrator owns repository/GitHub mutations, operate analysis-only: do not edit, commit, push, reply, or resolve. Return the dispositions and required actions below.
- Otherwise this skill owns the focused fixes and GitHub actions needed to finish triage.
- Keep changes scoped to review feedback. Apply KISS, DRY, and YAGNI and preserve unrelated local work.

## Snapshot

Identify the PR, exact head repository/ref/SHA, and all current feedback:

- inline review threads/comments;
- PR-level comments;
- review submissions/bodies, including reviewer, persisted state, submission time, and body;
- copied feedback supplied by the user.

Paginate platform reads. Preserve source IDs. If one artifact contains independent findings, split them into stable item-scoped records while retaining the parent source ID. Merge only items with the same root cause; prefer inline context when duplicate bot summaries and inline findings overlap.

Before acting on the analysis, re-fetch the head and feedback:

- if the head changed, discard the analysis and restart triage on the new SHA;
- if external feedback changed on the same head, refresh triage with the new snapshot;
- ignore deltas caused only by this run's recorded GitHub mutations.

## Dispositions

Return one validated disposition per distinct feedback item:

- `fix`: the finding is valid; specify the smallest concrete edit and verification.
- `already addressed`: current code already satisfies it; provide brief evidence.
- `outdated`: the finding no longer applies to the current head; provide brief evidence.
- `answer`: no code change is needed; provide a concise answer.
- `clarify`: material context or a decision is missing; ask one focused question and leave it open.
- `defer` / `won't fix`: state the reason and `decision_terminal: true|false`.

Each item must retain its source IDs and state whether each source should be `resolve`, `leave_open`, or `not_resolvable`. A parent review thread may be resolved only when every item contributing to it is resolve-eligible.

## Standalone Execution

Skip this section in analysis-only mode.

1. Verify the worktree can be safely bound to the recorded PR head without overwriting or publishing unrelated work. Stop on unsafe, dirty, or diverged state that cannot be isolated.
2. Set `expected_head` to the analyzed head. If any `fix` dispositions exist, batch them into one coherent change against that head, run appropriate QA once, commit once, push once, then replace `expected_head` with the exact pushed head SHA. Do not partially publish a conflicting batch.
3. Reconcile head and feedback before any reply or resolution. Require `current_head == expected_head`; an ancestor relationship is insufficient. If the head differs, publish nothing from the stale analysis and restart. Refresh triage first if same-head external feedback changed.
4. Apply validated platform actions. Keep replies to one sentence by default; prefer resolve-only for self-evident fixes, already-addressed items, and outdated items. Do not post a PR-level status summary unless it communicates a decision, blocker, or requested action.
5. Re-fetch threads after acting. Retry an expected resolution once when safe; otherwise record `failed_action`.

For `defer` / `won't fix`, resolve only when `decision_terminal: true`; otherwise reply if useful and leave the item open. `clarify` always remains open pending input.

An active unsuperseded `CHANGES_REQUESTED` review is `awaiting_re_review` even after its findings are handled. Do not dismiss reviewer state to clear it. A later `COMMENTED` review does not clear the blocker; a later review from the same reviewer supersedes it only when its state is `APPROVED` or `CHANGES_REQUESTED`.

## Terminal States

Track every incorporated source to one explicit state:

- `resolved`: the thread is confirmed resolved;
- `replied_left_open`: a reply/question was posted and the item intentionally remains open;
- `not_resolvable`: the source has no thread-resolution action;
- `awaiting_re_review`: an active change-request review still blocks completion;
- `failed_action`: required publication or platform action failed.

`replied_left_open` is terminal only when the disposition itself is terminal. Completion is blocked by unpublished fixes, missing clarification, non-terminal defer/won't-fix decisions, `awaiting_re_review`, failed actions, unresolved QA, or unreconciled head/feedback changes.

## Output

Report concisely:

- exact analyzed head SHA;
- counts by disposition and terminal state;
- fixes and verification performed, or the implementation plan in analysis-only mode;
- replies/resolutions performed or requested;
- any remaining blocker or required reviewer/user action.
