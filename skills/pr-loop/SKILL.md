---
name: pr-loop
description: Implement same-repository GitHub Issues into a reviewed pull request, or review and fix an existing PR, iterating with fresh independent read-only native subagents until no actionable feedback remains. Use for issue-to-PR implementation or iterative PR review/fix work.
---

# PR Loop

Drive one or more same-repository Issues into a reviewed pull request, or drive an existing pull request through review and fix rounds until no actionable feedback remains.

The top-level agent owns every repository and GitHub mutation. Delegate only planning, review, and feedback analysis to fresh, independent, read-only subagents through the active runtime's native subagent mechanism.

## Core Invariants

- Use real native subagents with fresh context. Do not emulate them in the parent context, launch nested coding-agent CLIs, or require fixed agent names, models, providers, or configuration files.
- Treat each accepted subagent as a terminal leaf: it performs its assigned role directly and does not re-enter `pr-loop` or delegate again.
- If a required independent subagent cannot be launched, report `unsupported` and stop. Retry only when the runtime proves rejection occurred before execution was accepted; never duplicate ambiguously accepted work.
- Bind every review and feedback decision to an exact PR head SHA. If the head changes before an action based on that decision, discard the stale result and restart from the new head.
- Treat subagent output as advisory. The top-level agent validates plans, findings, dispositions, repository state, and GitHub state before acting.
- The top-level agent alone edits files, runs write-mode tooling, commits, pushes, opens or updates PRs, publishes reviews, replies, and resolves threads.
- Keep implementation and fixes scoped. Apply KISS, DRY, and YAGNI; prefer the smallest coherent change and avoid speculative abstraction or unrelated cleanup.
- Preserve unrelated local work. Stop before editing if the worktree cannot be safely isolated or bound to the intended base/head.

## Modes

Honor these optional caller constraints:

- `dry_run`: plan, review, and analyze only; perform no repository or GitHub mutation.
- `no_push`: implement, verify, and commit locally, but do not push, open a PR, or resolve feedback whose fix is unpublished.
- `no_reply`: do not publish reviews, replies, or resolutions; local implementation and push remain allowed unless another mode forbids them.

Actions suppressed by a mode are not failures. Record them in a run-level `run_mode_skips` ledger and report the affected feedback as `skipped_by_mode`, except an active unsuperseded `CHANGES_REQUESTED` review remains `awaiting_re_review`.

## Subagent Contract

Give each subagent only the context needed for its role:

- user request and settled prior decisions;
- exact target: Issue set or PR plus recorded head SHA;
- relevant repository context and governing constraints;
- active modes;
- a delegation boundary stating that the subagent is a read-only terminal leaf;
- role-specific evidence below.

### Planning

For an Issue-started run, dispatch one fresh planning subagent for the complete same-repository Issue set. Require exactly one decision-complete plan with:

- `STATUS: ready` or `STATUS: blocked`;
- scope and affected interfaces/areas;
- concrete implementation decisions and constraints;
- verification approach;
- for `blocked`, only the smallest missing decision needed to proceed.

### Review

For each review attempt, dispatch three fresh subagents against the exact recorded head SHA, one per lens:

- `correctness`;
- `tests/docs`;
- `security/performance`.

Concurrency is optional; independent contexts are mandatory. Give each the changed files and diff for that head. Candidate findings must include lens, severity (`critical`, `high`, `medium`, `low`), confidence, concrete impact, remediation direction, and a file/line anchor when safe.

Subagents return findings only; they never publish them. The top-level agent deduplicates by root cause and drops stale, speculative, style-only, unrelated, or low-confidence findings.

### Feedback Analysis

Dispatch one fresh feedback-analysis subagent after each validated review round. Give it the exact head SHA and every current feedback source:

- inline threads/comments: `thread:<id>`;
- PR-level comments: `comment:<id>`;
- review submissions/bodies: `review:<id>`, including reviewer, persisted state, submission time, and body;
- unpublished local findings, when review publication is suppressed: `finding:<head-sha>:<ordinal>`.

If one artifact contains multiple independent feedback items, decompose them into stable item-scoped IDs while retaining the parent artifact ID. Merge only items with the same root cause.

Require one disposition per distinct feedback item: `fix`, `already addressed`, `outdated`, `answer`, `clarify`, `defer`, or `won't fix`. A `fix` needs a concrete edit and verification plan. `defer` and `won't fix` must state `decision_terminal: true|false`. Include concise reply guidance and whether each source should be resolved, left open, or is not resolvable.

## Issue-Started Flow

1. Resolve the requested Issues and require them to belong to one repository.
2. Dispatch planning. If blocked, obtain the missing material decision and re-plan; otherwise validate the ready plan.
3. Unless `dry_run`, resolve the intended base branch and exact base SHA. Require a clean isolatable worktree, create a suitable branch from that SHA, and verify the branch starts there.
4. Implement directly in the top-level agent, run repository QA, and commit. Do not delegate implementation.
5. Unless `dry_run` or `no_push`, push the branch and open the PR.
6. Enter the PR Review Loop. If no PR exists because a mode suppressed publication, report the plan and local state and stop.

For an existing-PR request, enter the PR Review Loop directly.

## PR Review Loop

Use caller-specified review-attempt and same-head feedback-refresh limits when provided; otherwise they are unbounded. If only a review-attempt limit is supplied, use it for same-head feedback refreshes too. A review attempt begins when review subagents are dispatched. A same-head refresh re-runs only feedback analysis and does not consume another review attempt.

### 1. Freeze the target

Resolve the exact PR, including its head repository and head ref, and initialize the sticky run-level `run_mode_skips` ledger. Record the current head SHA. Every fix commit and push must target that exact head repository/ref, including fork PRs.

In normal posting mode, verify that current authentication can read the feedback needed by this loop before spending a review attempt. Use a non-mutating write-permission check when the runtime provides one; otherwise the actual review submission is the write test.

### 2. Review the exact head

Dispatch the three review subagents for the recorded head. Re-fetch the head when they finish. If it changed, discard the whole round and restart on the new SHA; the attempt still counts.

Validate and arbitrate the findings. Immediately before publication, re-fetch the head again and discard the round if it moved.

Unless `dry_run` or `no_reply`, publish exactly one GitHub review with action `COMMENT` and a non-empty body. Put safely anchorable findings inline and unanchorable findings in the body. If none remain, say only that no new actionable findings were found in this pass; do not imply older feedback is cleared. Re-fetch GitHub state and verify the exact review and intended comments persisted on the reviewed head.

When publication is suppressed, retain the arbitrated findings locally as `finding:<head-sha>:<ordinal>` and record the skipped publication in `run_mode_skips`.

### 3. Analyze all feedback

Snapshot all current feedback sources and dispatch feedback analysis. Treat the snapshot plus any local `finding:` sources as the analysis baseline for that head.

After analysis returns, re-fetch the head first. If it changed, discard the analysis and restart on the new head.

Then re-fetch the GitHub-backed feedback snapshot. If external feedback changed while analysis was running, do not act on stale dispositions. Redispatch feedback analysis on the same head with the fresh GitHub snapshot plus the unchanged local `finding:` set. Continue until the snapshot is stable or the applicable refresh limit is reached.

Ignore differences caused only by this loop's own recorded GitHub mutations; any other new or edited thread, comment, review, review state, or feedback content is an external delta.

### 4. Apply validated dispositions

Before editing, bind the local worktree to the exact recorded PR head repository/ref and SHA without discarding unrelated work. Stop if it is dirty, diverged, otherwise unsafe, or lacks required push access in normal push mode.

Batch all `fix` dispositions from the round into one coherent change against that same head, run QA once for the combined batch, make one commit, and push once unless a mode suppresses it. Do not partially publish a conflicting fix batch. After pushing, re-fetch and record the exact resulting head SHA as `expected_head`.

For non-fix dispositions:

- `already addressed` / `outdated`: re-validate the evidence against the exact current head before replying or resolving.
- `answer`: post the validated concise answer when replies are allowed.
- `clarify`: ask the question and leave the item open.
- `defer` / `won't fix`: explain the decision; resolve only when `decision_terminal: true` and the platform source is resolvable.

PR-level comments and review submissions have no thread-resolution action, so their normal terminal state is `not_resolvable` after any applicable reply. Inline parent threads may be resolved only when every feedback item contributing to that thread is resolve-eligible.

An active unsuperseded `CHANGES_REQUESTED` review is always `awaiting_re_review`, regardless of this loop's disposition. Only later persisted GitHub reviewer state or dismissal can supersede it; this loop must not dismiss or otherwise mutate reviewer state merely to clear the blocker.

Local `finding:` sources have no GitHub artifact. Their terminal state is `skipped_by_mode`; they may still drive local fixes when the active mode permits implementation.

### 5. Gate every publication on fresh state

Before any code-dependent reply or resolution, require the PR head to equal `expected_head` exactly. A descendant SHA is not sufficient. If the head differs, publish nothing from the stale analysis and restart review on the new head.

Before any GitHub reply or resolution, also reconcile the current feedback snapshot with the analysis baseline plus this loop's recorded mutations. If external feedback changed on the same reviewed head, refresh feedback analysis before acting. If feedback arrives after a fix push changed the head, start a new review attempt instead.

A failed attempted publication/reply/resolution is `failed_action`. An action intentionally suppressed by a mode is `skipped_by_mode` and is added to `run_mode_skips`.

### 6. Reconcile and continue or finish

Re-fetch the head after acting:

- if it differs from the reviewed head, start a new review attempt on the new SHA;
- if it is unchanged, take one final feedback snapshot and reconcile it against the current baseline plus recorded own mutations;
- if new external feedback exists on the same head, refresh feedback analysis only;
- never dispatch the three review subagents again for an unchanged head already carried through this loop.

Finish only when the final head is stable, the required normal-mode `COMMENT` review was verified for that head, the feedback snapshot is reconciled, and every feedback item is terminal.

Terminal states are `resolved`, `replied_left_open`, `not_resolvable`, `skipped_by_mode`, `awaiting_re_review`, or `failed_action`. Completion is blocked by:

- any `fix` still requiring publication;
- `clarify` awaiting input;
- `defer` or `won't fix` with `decision_terminal: false`;
- `awaiting_re_review`;
- `failed_action`;
- an unreconciled head or feedback delta;
- exhausted caller limits;
- unsupported or failed required subagent work;
- unsafe worktree/branch state, authentication/permission failure, or unresolved QA failure.

`replied_left_open` is terminal only when its disposition itself is terminal.

## Outcomes

- `success`: the final reviewed head is stable, required review publication is verified, feedback is reconciled, and no actionable or reviewer-blocked item remains.
- `completed_with_skips`: the same completion conditions hold, but `run_mode_skips` is non-empty because an active mode intentionally suppressed work.
- `stopped`: a blocker above prevents either successful outcome.

## Output

Report concisely:

- outcome and active modes;
- Issues implemented and resulting PR, when applicable;
- review attempts, final reviewed head SHA, and verified review-publication status;
- same-head feedback refreshes and any caller limit;
- disposition/terminal-state summary, including `awaiting_re_review`, `not_resolvable`, and all `run_mode_skips`;
- any blocker that stopped the loop.
