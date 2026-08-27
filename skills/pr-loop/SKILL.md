---
name: pr-loop
description: Implement one or more same-repository GitHub Issues into a pull request, or review and improve an existing pull request, by orchestrating issue-plan, pr-review, and pr-feedback-triage until no actionable feedback remains.
---

# PR Loop

Orchestrate an Issue-to-PR or PR review/fix loop by composing the repository's existing skills. This skill owns sequencing only; do not duplicate planning, review, subagent, posting, or feedback-triage logic here.

- [`issue-plan`](../issue-plan/SKILL.md) produces the advisory implementation plan for Issue-started work.
- [`pr-review`](../pr-review/SKILL.md) independently reviews one exact PR head and owns review strategy, validation, publication, and review-specific subagent contracts.
- [`pr-feedback-triage`](../pr-feedback-triage/SKILL.md) owns feedback collection, dispositions, focused fixes, verification, publication gates, replies, and thread resolution.
- The top-level main agent owns Issue implementation, repository QA, branch/commit/push, and opening the initial PR.

Treat every composed skill's output as advisory except for platform mutations that the skill explicitly owns. Validate advice against the current repository, requested scope, and exact PR before acting.

## Caller constraints

Preserve explicit caller constraints such as `dry_run`, `no_push`, and `no_reply` throughout the loop and pass their semantics to the composed skills. Translate only naming differences required by a child skill, such as `no_reply` to `pr-review`'s no-post behavior. Do not invent additional restrictions or report suppressed work as completed.

For Issue-started work, `dry_run` stops after planning and analysis, while `no_push` may produce verified local commits but cannot enter a remote PR loop because no PR is opened.

## Issue-started flow

1. Resolve the requested Issue or same-repository Issue set and run `issue-plan`.
2. If planning returns `STATUS: blocked`, stop and report the smallest missing decision. Otherwise validate the ready plan against the requested Issue scope.
3. Unless prevented by the caller's mode, create a clean branch from the intended base, implement the plan directly in the main agent, and run the repository's normal QA.
4. Commit the scoped change. Unless `no_push` or `dry_run` prevents it, push the branch and open the pull request using normal repository conventions.
5. Enter the PR loop below. If no remote PR was opened, report the local state and stop.

For an existing-PR request, skip Issue planning and enter the PR loop directly.

## PR loop

Honor an explicit caller iteration limit; otherwise do not invent one.

1. Resolve the exact open pull request and record its current head SHA.
2. Run `pr-review` for that pull request. Its returned reviewed head is the only head for which that review result is valid.
3. Re-fetch the PR head. If it differs from the reviewed head, discard head-scoped conclusions and review the new head from step 1.
4. Run `pr-feedback-triage` against all current feedback, preserving caller modes and scope.
5. If triage reports a blocker that needs user, reviewer, permission, publication, or QA intervention, stop and report it rather than fabricating progress.
6. Re-fetch the PR head after triage:
   - If the head changed, whether from this loop or externally, restart at step 1 and review the new head.
   - If the head is unchanged, re-fetch current feedback. If new actionable feedback appeared after triage, run `pr-feedback-triage` again on the same head without repeating `pr-review`.
   - If the head is unchanged and no actionable feedback remains, finish.

Do not reuse review or triage advice after observing a head change. Do not repeat `pr-review` merely because feedback changed while the reviewed head stayed unchanged; `pr-feedback-triage` owns feedback-only refreshes and their mutation safety.

## Stop conditions

Stop and report the current state when any composed skill reports `unsupported`, when the local worktree cannot be safely used without mixing unrelated work, when required GitHub permissions or publication fail, when repository QA fails and cannot be resolved in scope, when feedback requires unresolved human input, or when the caller's explicit iteration limit is reached.

A caller mode that intentionally suppresses push, posting, replies, or resolution is not a successful full loop. Report the suppressed work explicitly.

## Result

Return a concise summary containing:

- the Issue set when applicable and final PR;
- the final reviewed head SHA and number of review rounds;
- fixes and verification performed;
- any work suppressed by caller mode; and
- remaining blocker or confirmation that no actionable feedback remains on the unchanged final head.
