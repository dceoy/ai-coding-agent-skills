# GitHub Posting

The top-level parent is the only actor allowed to publish PR-review feedback.

## Posting Contract

Unless the user explicitly selected `dry-run` or `no-post`, the review is incomplete until GitHub has accepted and persisted exactly one pull-request review for the exact reviewed head SHA.

Use action `COMMENT`. Do not use `APPROVE` or `REQUEST_CHANGES` unless the user explicitly asks for that separate review action.

Every submitted review must have a non-empty top-level body, including a clean review with no actionable findings.

## Before Posting

Immediately re-fetch the PR and compare its current head SHA with the SHA reviewed by discovery and validation subagents.

If the SHA changed:

- do not post stale inline comments;
- discard findings derived from the old head;
- restart review against the new head.

Also re-check current review feedback so a finding that was independently posted while the review was running is not duplicated.

## Inline vs Top-Level Feedback

Use inline comments for specific actionable findings when all are true:

- the finding maps to a changed line on the reviewed head;
- the line anchor is unambiguous;
- the comment explains one root cause and concrete impact;
- the requested remediation is local enough to be useful at that line.

Use the top-level review body for:

- cross-file root causes;
- missing tests or documentation that cannot be anchored safely;
- operational or compatibility concerns spanning multiple files;
- rare `needs-human` verification notes;
- the clean-result statement.

Do not duplicate the same finding inline and in the body. A short body may summarize the count and overall result while the full actionable detail remains inline.

## Comment Style

Keep published feedback concise and decision-oriented. Each finding should state:

1. what changed behavior is wrong;
2. the concrete impact or failing condition;
3. the smallest useful remediation direction.

Avoid praise attached to blocking findings, generic best practices, long tutorials, severity theatrics, and vague phrases such as "consider improving" without a concrete defect.

Use severity only when it helps prioritize multiple findings. The review should read as engineering feedback, not a scan dump.

## Clean Result

When no publishable findings remain after arbitration, use a non-empty body such as:

```text
No new actionable findings were found in this review pass.
```

Do not imply that unrelated existing feedback has been resolved or that the PR is approved.

## Verification

Capture the identifier returned by the GitHub review mutation when available, then re-fetch the PR's reviews and inline comments.

Success requires verifying that:

- the specific review exists and is persisted as a COMMENT review;
- it belongs to the exact reviewed head SHA when that metadata is available;
- the top-level body matches the intended review content;
- every intended inline comment exists at the expected changed location.

Do not treat process exit status, HTTP success alone, stdout, a job summary, or the parent's final response as proof that the review was published.

If publication succeeds but verification fails, re-read the current GitHub state once to rule out propagation delay. Do not create a second review merely because the first mutation's response was incomplete. If the exact submitted artifact still cannot be verified, report publication as failed rather than claiming success.

## Failure Handling

If the head moves before publication, restart on the new head.

If a line cannot be anchored safely, move that finding to the top-level body rather than guessing the line.

If GitHub mutation or verification fails, preserve the arbitrated review locally and report the posting failure clearly. Do not fall back to pretending that returning review Markdown in chat completed the GitHub review.

In `dry-run` or `no-post` mode, skip all mutations and return the arbitrated findings with an explicit statement that nothing was posted.
