Run an autonomous pull request review equivalent to Anthropic's pr-review-toolkit.

This routine is review-only. Do not modify code, push commits, merge branches, approve PRs, or request changes unless explicitly instructed elsewhere. The only allowed local repository change before review is configuring Git identity for the session.

Before starting any review work, configure Git identity:

```bash
git config user.name "claude"
git config user.email "noreply@anthropic.com"
```

Objective:
Review the pull request diff using six review lenses:

1. General code quality and project guideline compliance
2. Test coverage quality
3. Error handling and silent failure risks
4. Comment and documentation accuracy
5. Type design and invariant quality
6. Simplification and maintainability opportunities

Success criteria:

- Review only the PR diff and directly related context.
- Surface actionable findings with exact file and line references.
- Use GitHub inline review comments for high-confidence, actionable issues whenever the issue maps to a changed line in the PR diff.
- Post one concise summary review comment covering Critical Issues, Important Issues, Suggestions, Strengths, and Recommended Action.
- Avoid false positives, speculative concerns, broad rewrites, and style nitpicks unless they violate explicit project guidance.
- If no serious issues are found, say so clearly and summarize what was checked.

Workflow:

1. Initialize review environment

- Run:

  - `git config user.name "claude"`
  - `git config user.email "noreply@anthropic.com"`

- Confirm the repository is clean enough for review:

  - `git status --short`

- Do not edit source files.

2. Identify the PR and scope

- Use GitHub event context if available.
- Otherwise infer the current branch's PR with:

  - `gh pr view --json number,title,body,url,baseRefName,headRefName,author,isDraft`

- Retrieve PR metadata, changed files, review threads, and diff:

  - `gh pr view <PR> --json number,title,body,url,baseRefName,headRefName,files,commits,reviews,reviewThreads`
  - `gh pr diff <PR>`

- Review only changed files and directly related code needed to understand the diff.
- Read project guidance files if present: `CLAUDE.md`, `AGENTS.md`, `README*`, contribution docs, test docs, style docs, and relevant CI configuration.

3. Determine applicable review lenses

- Always run General Code Review.
- Run Test Coverage Review when production behavior changed, tests changed, or new logic was introduced.
- Run Error Handling Review when the diff includes exceptions, try/catch, try/except, Result/Either handling, retries, fallbacks, logging, null/default handling, async/concurrency failure paths, external I/O, or validation.
- Run Comment Analysis when comments, docstrings, README/docs, or generated documentation changed, or when comments describe non-trivial behavior in changed code.
- Run Type Design Review when the diff introduces or changes classes, structs, interfaces, type aliases, schemas, enums, data models, validators, value objects, public APIs, or domain entities.
- Run Simplification Review after the correctness-oriented reviews, only for recently changed code and only where clarity can improve without behavior changes.

4. General Code Review
   Check:

- Explicit project rules in CLAUDE.md/AGENTS.md and local conventions.
- Functional bugs, edge-case failures, race conditions, null/undefined issues, resource leaks, security issues, and performance regressions.
- API compatibility, backward compatibility, migration risks, configuration defaults, and observability.
- Whether the implementation matches the PR title/body and linked issue intent.

Confidence scoring:

- 91-100: critical bug or explicit project-rule violation
- 80-90: important issue requiring attention
- 51-79: valid but lower-impact issue; include only in summary if useful
- Below 80: do not post as a finding

Create inline comments for confidence >=80 when the issue maps to a changed PR diff line.

5. Test Coverage Review
   Focus on behavioral coverage, not line coverage.
   Check:

- Critical new behavior, business logic, and user-facing branches.
- Negative cases, validation failures, boundary conditions, and error paths.
- Async/concurrency behavior where relevant.
- Integration points and regression-prone code paths.
- Whether tests assert behavior/contracts rather than implementation details.
- Whether tests are resilient to reasonable refactoring.

Rate each proposed test gap from 1-10:

- 9-10: could prevent data loss, security issues, system failure, or severe production regression
- 7-8: important user-facing or business logic regression risk
- 5-6: meaningful edge case or maintainability improvement
- 1-4: optional/nice-to-have

Create inline comments for 8-10 gaps when the missing test can be tied to a changed line. Put 5-7 gaps in the summary. Ignore 1-4 unless the project explicitly requires them.

6. Error Handling and Silent Failure Review
   Check every changed error path:

- Empty or broad catch blocks.
- Errors that are logged but execution continues incorrectly.
- Fallback behavior that masks failure or returns default/null/undefined without sufficient context.
- Retry logic that fails silently or loses the root cause.
- Optional chaining/null coalescing that hides required operations.
- Missing user-facing or operator-facing feedback.
- Missing contextual logging for production diagnosis.
- Error propagation and cleanup/resource handling.

For each issue include:

- Location
- Severity: CRITICAL, HIGH, or MEDIUM
- Hidden failure mode
- User/operator impact
- Concrete remediation

Create inline comments for CRITICAL and HIGH findings when the issue maps to the PR diff.

7. Comment and Documentation Accuracy Review
   For changed comments, docstrings, and docs:

- Verify factual accuracy against implementation.
- Check parameter, return, exception, side-effect, and edge-case claims.
- Flag misleading, outdated, ambiguous, or likely-to-rot comments.
- Flag comments that merely restate obvious code and should be removed.
- Prefer comments explaining “why” over comments explaining obvious “what”.
- Suggest precise rewrites where needed.

Create inline comments for factually wrong or materially misleading comments. Summarize lower-priority documentation improvements.

8. Type Design and Invariant Review
   For each changed or new type/schema/model:

- Identify invariants.
- Rate 1-10:

  - Encapsulation
  - Invariant expression
  - Invariant usefulness
  - Invariant enforcement

- Check whether invalid states can be constructed.
- Check constructor/factory validation and mutation guards.
- Prefer compile-time guarantees where feasible.
- Avoid over-engineered recommendations that do not fit the repository style.

Create inline comments only for concrete type-design issues that can cause bugs, invalid states, or API misuse. Include ratings in the summary when useful.

9. Simplification Review
   Only suggest simplification where it preserves behavior exactly.
   Check:

- Unnecessary complexity, nesting, cleverness, duplication, or over-abstraction.
- Unclear names or structure in changed code.
- Redundant comments.
- Opportunities to align with existing project patterns.
- Whether suggested simplification improves debuggability and maintainability.

Do not recommend changes that are merely shorter. Prefer clarity over brevity. Do not propose speculative rewrites.

10. Inline comment policy
    Inline comments are the preferred delivery format for concrete review findings.

Before posting inline comments:

- Confirm the file and line are part of the PR diff and can accept GitHub review comments.
- Prefer commenting on the most specific changed line that introduced or exposes the issue.
- Ensure each comment is actionable and includes a concrete fix direction.
- Do not duplicate existing unresolved review comments.
- Do not post multiple comments for the same root cause; consolidate related issues.
- Do not force an inline comment when line mapping is uncertain. Put that issue in the summary instead.
- Keep comments concise, technical, and neutral.
- Use GitHub review comments rather than ordinary issue comments when possible.

Posting strategy:

- Collect all inline comments first.
- Submit them as a single GitHub PR review with event `COMMENT`.
- Include the summary as the review body.
- Use `APPROVE` or `REQUEST_CHANGES` only when explicitly instructed.

Use `gh api` for precise inline review comments when needed. Use `gh pr review` only when it can preserve inline comments correctly. Do not fall back to summary-only review unless there are no suitable inline findings.

11. Final summary format
    Post or return a summary in this structure:

# PR Review Summary

## Critical Issues

- [lens] Description — `path:line`

  - Impact:
  - Recommendation:

## Important Issues

- [lens] Description — `path:line`

  - Impact:
  - Recommendation:

## Suggestions

- [lens] Description — `path:line`

  - Rationale:
  - Recommendation:

## Strengths

- Note well-designed, well-tested, or well-scoped parts of the PR.

## Recommended Action

1. Fix Critical Issues first.
2. Address Important Issues before merge.
3. Consider Suggestions if they improve maintainability without expanding scope.
4. Re-run the relevant review lenses after fixes.

If no high-confidence issues are found, use:

# PR Review Summary

No high-confidence blocking issues found.

## Checked

- General code quality and project guidelines
- Test coverage
- Error handling and silent failures
- Comments/documentation accuracy
- Type design
- Simplification opportunities

## Notes

- Mention any non-blocking observations or areas human reviewers may still want to inspect, such as product intent, architecture trade-offs, or domain-specific correctness.
