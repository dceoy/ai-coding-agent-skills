# GitHub Posting

The top-level parent is the only actor allowed to publish PR-review feedback.

## Posting contract

Unless the user selected `dry-run` or `no-post`, the review is incomplete until GitHub has accepted and persisted exactly one `COMMENT` pull-request review for the frozen reviewed head.

Every review has a non-empty top-level body, including a clean review, and contains fresh run markers:

```text
<!-- pr-review-skill -->
<!-- pr-review-skill-run: <reviewed-head-sha>-<fresh-UTC-timestamp-and-random-nonce> -->
```

Use a new marker for every invocation so an older review cannot satisfy verification accidentally.

## Snapshot rule

Never mix analysis from different head SHAs.

If the runtime can explicitly bind review publication to the frozen reviewed commit, publish against that exact commit even when the live PR head has advanced. The resulting review may be rendered as outdated; that is acceptable because its target is unambiguous.

If the runtime cannot guarantee commit-bound publication, immediately re-fetch the live PR head before posting. If it differs from the reviewed head, discard the stale result and restart against the new snapshot rather than publishing feedback with an ambiguous target.

In either mode, re-check current feedback before publication when practical so independently posted findings are not duplicated.

## Inline vs top-level

Use inline comments for specific actionable findings when the finding maps unambiguously to a changed line on the reviewed snapshot. Use the review body for cross-file findings, unanchorable test/documentation/operational concerns, rare material `needs-human` notes, and the clean-result statement.

Do not duplicate one finding both inline and in the body. If an inline anchor is unsafe, move the finding to the body rather than guessing.

Each published finding should state the changed behavior that is wrong, its concrete impact or failing condition, and the smallest useful remediation direction. Avoid generic best practices, tutorials, praise attached to defects, and vague suggestions without a concrete failure.

## Clean result

When no publishable findings remain, still submit a non-empty COMMENT review such as:

```text
No new actionable findings were found in this review pass.
```

Do not imply approval or resolution of unrelated existing feedback.

## Verification

After submission, re-fetch reviews and inline comments. Success requires evidence that the specific current-run COMMENT review persisted, is associated with the reviewed head when GitHub exposes that metadata, contains the intended top-level body and fresh run marker, and includes every intended inline comment at the expected location.

A returned review ID is useful but does not replace current-run marker verification. Do not treat process exit status, HTTP success alone, stdout, or the parent's final response as proof of publication.

If mutation succeeds but verification is inconclusive, re-read GitHub state once to rule out propagation delay. Do not create a second review merely because the first response was incomplete. If the intended artifact still cannot be verified, report publication failure.

In `dry-run` or `no-post` mode, skip mutation and return the arbitrated findings with an explicit statement that nothing was posted.
