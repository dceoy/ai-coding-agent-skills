Run an autonomous pull request review equivalent to Anthropic's pr-review-toolkit.

This routine is review-only. Do not modify code, push commits, merge branches, approve PRs, or request changes unless explicitly instructed elsewhere. Prefer high-signal GitHub review comments over exhaustive commentary.

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
- Post inline GitHub review comments only for high-confidence, actionable issues.
- Post one concise summary comment covering Critical Issues, Important Issues, Suggestions, Strengths, and Recommended Action.
- Avoid false positives, speculative concerns, broad rewrites, and style nitpicks unless they violate explicit project guidance.
- If no serious issues are found, say so clearly and summarize what was checked.

Workflow:

1. Identify the PR and scope

- Use GitHub event context if available.
- Otherwise infer the current branch's PR with:

  - `gh pr view --json number,title,body,url,baseRefName,headRefName,author,isDraft`

- Retrieve PR metadata, changed files, and diff:

  - `gh pr view <PR> --json number,title,body,url,baseRefName,headRefName,files,commits,reviews,reviewThreads`
  - `gh pr diff <PR>`

- Review only changed files and directly related code needed to understand the diff.
- Read project guidance files if present: `CLAUDE.md`, `AGENTS.md`, `README*`, contribution docs, test docs, style docs, and relevant CI configuration.

2. Determine applicable review lenses

- Always run General Code Review.
- Run Test Coverage Review when production behavior changed, tests changed, or new logic was introduced.
- Run Error Handling Review when the diff includes exceptions, try/catch, try/except, Result/Either handling, retries, fallbacks, logging, null/default handling, async/concurrency failure paths, external I/O, or validation.
- Run Comment Analysis when comments, docstrings, README/docs, or generated documentation changed, or when comments describe non-trivial behavior in changed code.
- Run Type Design Review when the diff introduces or changes classes, structs, interfaces, type aliases, schemas, enums, data models, validators, value objects, public APIs, or domain entities.
- Run Simplification Review after the correctness-oriented reviews, only for recently changed code and only where clarity can improve without behavior changes.

3. General Code Review
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

Only create inline comments for confidence >=80.

4. Test Coverage Review
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

Inline-comment only 8-10 gaps. Put 5-7 gaps in the summary. Ignore 1-4 unless the project explicitly requires them.

5. Error Handling and Silent Failure Review
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

Inline-comment CRITICAL and HIGH findings only.

6. Comment and Documentation Accuracy Review
   For changed comments, docstrings, and docs:

- Verify factual accuracy against implementation.
- Check parameter, return, exception, side-effect, and edge-case claims.
- Flag misleading, outdated, ambiguous, or likely-to-rot comments.
- Flag comments that merely restate obvious code and should be removed.
- Prefer comments explaining “why” over comments explaining obvious “what”.
- Suggest precise rewrites where needed.

Inline-comment factually wrong or materially misleading comments. Summarize lower-priority documentation improvements.

7. Type Design and Invariant Review
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

Inline-comment only concrete type-design issues that can cause bugs, invalid states, or API misuse. Include ratings in the summary when useful.

8. Simplification Review
   Only suggest simplification where it preserves behavior exactly.
   Check:

- Unnecessary complexity, nesting, cleverness, duplication, or over-abstraction.
- Unclear names or structure in changed code.
- Redundant comments.
- Opportunities to align with existing project patterns.
- Whether suggested simplification improves debuggability and maintainability.

Do not recommend changes that are merely shorter. Prefer clarity over brevity. Do not propose speculative rewrites.

9. GitHub review comment policy

Use GitHub inline review comments aggressively for concrete, diff-bound findings.

Default behavior:

- If a finding points to a specific changed line, post it as an inline review comment on that line.
- Use the final PR summary comment only for:

  - overall assessment,
  - findings that cannot be mapped safely to a changed line,
  - cross-file or architectural observations,
  - low-priority suggestions,
  - strengths and recommended action.

- Do not bury actionable line-specific issues only in the summary when they can be posted inline.

Inline comment criteria:
Post an inline comment when all of the following are true:

- The issue is actionable.
- The relevant file and line are part of the PR diff.
- The recommendation can be explained concisely.
- The confidence level is high enough:

  - General/code correctness: confidence >= 80
  - Test coverage gap: severity >= 8/10
  - Error handling issue: CRITICAL or HIGH
  - Comment/documentation issue: factually wrong or materially misleading
  - Type design issue: can cause invalid state, API misuse, or runtime bugs
  - Simplification issue: clearly improves maintainability without behavior change

Do not post inline comments for:

- speculative concerns,
- subjective style preferences,
- broad architectural ideas without a specific changed line,
- duplicate findings already covered by unresolved review comments,
- low-confidence line mapping,
- minor suggestions that would create review noise.

Inline comment format:
Use concise, technical, fix-oriented comments.

Recommended structure:

- Start with the concrete issue.
- Explain the impact in one sentence.
- Suggest a specific remediation.

Example:

This fallback silently converts a failed parse into an empty result, which can mask malformed input and make production diagnosis difficult. Consider returning an explicit error or logging the parse failure with enough context before falling back.

Posting mechanics:

- Prefer creating a single GitHub PR review containing multiple inline comments plus one summary body.
- Use `gh pr review` or `gh api` as appropriate.
- Ensure each inline comment targets a valid diff position.
- If using the GitHub Reviews API, resolve the correct `path`, `line` or `position`, and `side` from the PR diff before submitting comments.
- Submit the review as `COMMENT` by default.
- Do not use `APPROVE` or `REQUEST_CHANGES` unless explicitly instructed.
- If inline comment creation fails because the line is not commentable, move that finding to the final summary instead of forcing an invalid comment.

Before submitting:

- Check existing unresolved review threads and avoid duplicate comments.
- Consolidate multiple comments on the same root cause.
- Keep inline comments limited to high-signal findings.
- Preserve a professional, neutral tone.
- Do not include large code rewrites unless the fix is short and directly useful.

10. Final PR review summary

Always post one final PR review summary after inline comments.

The summary must not repeat every inline comment verbatim. Instead, aggregate the review outcome and reference the most important themes.

Use this structure:

# PR Review Summary

## Critical Issues

- Summarize any critical issues. Reference inline comments when applicable.

## Important Issues

- Summarize important issues. Reference inline comments when applicable.

## Suggestions

- Include non-blocking improvements, especially items not suitable for inline comments.

## Strengths

- Note well-designed, well-tested, well-scoped, or maintainable parts of the PR.

## Recommended Action

1. Fix Critical Issues first.
2. Address Important Issues before merge.
3. Consider Suggestions if they improve maintainability without expanding scope.
4. Re-run the relevant review lenses after fixes.

If no high-confidence issues are found, use:

# PR Review Summary

No high-confidence blocking issues found.

## Checked

- General code quality and project guideline compliance
- Test coverage
- Error handling and silent failure risks
- Comment and documentation accuracy
- Type design and invariant quality
- Simplification and maintainability opportunities

## Notes

- Mention any non-blocking observations or areas human reviewers may still want to inspect, such as product intent, architecture trade-offs, or domain-specific correctness.
