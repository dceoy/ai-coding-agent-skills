Run an autonomous pull request review. This routine is review-only: do not modify code, push commits, merge branches, approve PRs, or request changes unless explicitly instructed.

Before starting any review work, configure Git identity:

```bash
git config user.name "claude"
git config user.email "noreply@anthropic.com"
```

## Setup

1. Set Git identity (above).
2. Confirm workspace state with `git status --short`.
   - Do not edit, reset, stash, clean, or otherwise modify source files.
   - If unexpected local changes are present and they make the PR diff ambiguous, stop and report that the review cannot be completed safely because local changes may contaminate the diff.
3. Identify the PR:
   - Use GitHub event context if available.
   - Otherwise: `gh pr view --json number,title,body,url,baseRefName,headRefName,author,isDraft`
4. Retrieve PR metadata and diff:
   - `gh pr view <PR> --json number,title,body,url,baseRefName,headRefName,files,commits,reviews,comments`
     (`comments` retrieves top-level issue comments only; it does **not** retrieve line-level review comments.)
   - `gh pr diff <PR>`
5. Fetch existing line-level PR review comments (required for deduplication in final arbitration):
   ```bash
   gh api --paginate repos/<owner>/<repo>/pulls/<PR>/comments
   ```
   Use the resolved owner, repo, and PR number from steps 3–4. These REST review comments cover line-level inline comments but do **not** expose review-thread resolution state. Use them for duplicate avoidance; if resolved/unresolved thread state is required, fetch review threads via GraphQL instead. Do not use `gh pr view --json reviewThreads` because it is not a valid field.
6. Read project guidance if present: `CLAUDE.md`, `AGENTS.md`, `README*`, contribution docs, test docs, style docs, CI configuration.
7. Review only changed files and directly related context needed to understand the diff.

## Reviewer passes

Execute the following internal review phases sequentially. Each pass produces candidate findings — not yet posted. The final arbitration pass filters them before anything is submitted.

### Pass 1 — code-quality-reviewer

Check:

- Explicit project rules from `CLAUDE.md`/`AGENTS.md` and local conventions.
- Correctness: functional bugs, edge-case failures, race conditions, null/undefined handling.
- Error handling: empty or broad catch blocks, silent fallbacks, lost error context, missing cleanup.
- Resource leaks: file, socket, and database connection lifecycle.
- Naming, duplication, complexity, and separation of concerns.
- API and backward compatibility, migration risks.
- Type safety and invariant correctness.
- Whether the implementation matches the PR title/body intent.
- If applicable: strict null handling, narrowing correctness, discriminated union exhaustiveness.

### Pass 2 — performance-reviewer

Only report findings with plausible measurable impact or clear scalability risk. Do not flag premature optimization.

Check:

- Algorithmic complexity and repeated work inside loops.
- N+1 queries; prefer batching, pagination, or projection.
- Unnecessary blocking operations in async code.
- Retry storms or unbounded retry loops.
- Memory and resource leaks, excessive allocations.
- Missing caching for expensive or repeated operations.
- File, database, and socket lifecycle and cleanup.

### Pass 3 — test-coverage-reviewer

Focus on behavioral coverage, not line coverage.

Check:

- Critical new behavior, business logic, and user-facing branches.
- Error paths, boundary conditions, and negative cases.
- Async/concurrency failure paths where relevant.
- Integration points and regression-prone code paths.
- Assertion quality: tests must assert behavior/contracts, not implementation details.
- Test isolation and determinism.
- Missing regression tests for bug fixes.

Rate each gap 1–10:

- 9–10: could prevent data loss, security issue, system failure, or severe regression.
- 7–8: important user-facing or business logic regression risk.
- 5–6: meaningful edge case or maintainability improvement.
- 1–4: optional; ignore unless the project explicitly requires them.

Carry gaps rated 7–10 to arbitration. Gaps rated 5–6 go to the top-level summary only.

### Pass 4 — documentation-accuracy-reviewer

Check changed or affected comments, docstrings, README, API docs, examples, and configuration docs:

- Factual accuracy against the implementation.
- Parameter, return, exception, side-effect, and edge-case claims.
- Misleading, outdated, ambiguous, or likely-to-rot comments.
- Missing docs for changed public API behavior.
- Comments that merely restate obvious code (flag for removal).
- Prefer comments explaining _why_ over comments explaining obvious _what_.

Flag only factual inaccuracies, materially misleading docs, and missing docs for changed public behavior. Style-only improvements go to the summary or are dropped.

### Pass 5 — security-code-reviewer

Require an explicit attack surface and trust-boundary check when the diff touches: external input, authn/authz, secrets, network/API boundaries, subprocesses, serialization, file paths, database queries, or third-party dependencies.

Check:

- Injection: SQL, command, LDAP, XPath.
- XSS and output encoding.
- CSRF protection.
- Authentication bypass and authorization/IDOR flaws.
- Privilege escalation.
- Sensitive data exposure: secrets, PII in logs or responses.
- Insecure deserialization.
- Path traversal and insecure file handling.
- Weak or missing cryptography.
- Input validation gaps.
- Security misconfiguration.
- Race conditions and TOCTOU risks.
- Insufficient security logging.

If uncertain, include it only as a top-level "needs human verification" note when the attack surface is material and the verification target is concrete. Do not post uncertain security claims inline.

## Final arbitration

After all five passes, consolidate findings before posting:

- **Deduplicate**: when findings share a root cause, keep the most specific; drop the rest.
- **Drop**: speculative, low-confidence, style-only, or broad rewrite suggestions.
- **Drop**: findings already covered by existing review comments. Compare candidate findings against:
  - Line-level PR review comments fetched in step 5.
  - Top-level issue comments from `comments` in step 4.
  - Prior review bodies from `reviews` in step 4.

  Treat a finding as duplicate only when the specific actionable root cause is already covered, even if the wording differs. Do not drop a finding merely because a related area was discussed. When REST review comments lack resolution state, use the current diff as the source of truth: suppress stale already-fixed feedback, but do not repost an active issue that is already clearly covered.
- **Promote only** findings that are:
  - High-confidence and actionable.
  - Tied to the PR diff or directly related context.
  - Likely to affect correctness, security, reliability, performance, compatibility, maintainability, or reviewer decision-making.
- Keep praise and general observations top-level only.
- Keep inline comments concise and issue-focused.
- Avoid forcing a finding when no meaningful issue exists.

## Severity thresholds

| Severity   | Criteria                                                                                                                                 | Posting                                                                  |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `CRITICAL` | Data loss, security vulnerability, production outage, broken core behavior, severe compatibility break, explicit project-rule violation. | Post inline when mapped to a changed line.                               |
| `HIGH`     | Important correctness, reliability, security, performance, or API contract issue that should be addressed before merge.                  | Post inline when mapped to a changed line.                               |
| `MEDIUM`   | Real but non-blocking issue, meaningful test gap, maintainability concern, documentation mismatch.                                       | Summarize top-level only unless explicitly required by project guidance. |
| `LOW`      | Nice-to-have, subjective style, minor cleanup, speculative improvement.                                                                  | Suppress unless explicitly required by project guidance.                 |

## Inline vs top-level comment policy

Use **inline comments** for:

- Specific actionable issues on changed diff lines.
- Concrete bug, security, test, performance, documentation, or type-design findings.
- Findings where the exact line is the best place for the author to act.

Use **top-level comments** for:

- Overall summary.
- Cross-file or architectural observations.
- Missing tests that cannot be tied to one changed line.
- Documentation or release-note gaps spanning multiple files.
- Strengths, praise, and general observations.
- Human-verification notes.

**Never:**

- Post duplicate comments for the same root cause.
- Post inline comments when line mapping is uncertain.
- Post broad style preferences.
- Post "consider" comments unless the risk and recommendation are concrete.
- Use `APPROVE` or `REQUEST_CHANGES` unless explicitly instructed.

## Posting strategy

1. Collect all inline comments (CRITICAL and HIGH findings only).
2. Submit them as a single GitHub PR review with event `COMMENT`.
3. Include the summary as the review body.
4. Use `gh api` for precise inline comments when needed.
5. Use `gh pr review` only when it can preserve inline comments correctly.
6. Do not fall back to summary-only review unless there are no suitable inline findings.

## Output format

When issues are found (submit the body below directly — do not include the outer code fence):

```markdown
# PR Review Summary

## Critical Issues

- [lens] Finding — `path:line`
  - Impact:
  - Recommendation:

## Important Issues

- [lens] Finding — `path:line`
  - Impact:
  - Recommendation:

## Suggestions

- [lens] Finding — `path:line`
  - Rationale:
  - Recommendation:

## Strengths

- Short bullets only.

## Recommended Action

Concise merge guidance, without approving or requesting changes unless explicitly instructed.
```

When no high-confidence issues are found (submit the body below directly — do not include the outer code fence):

```markdown
# PR Review Summary

No high-confidence blocking issues found.

## Checked

- Code quality and project guidelines
- Security
- Performance
- Test coverage
- Documentation accuracy
- Error handling and silent failures
- Type design and invariants
- Simplification opportunities

## Notes

- Mention only meaningful non-blocking observations or human-review areas.
```
