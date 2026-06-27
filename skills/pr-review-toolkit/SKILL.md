---
name: review-pr
description: Comprehensive PR review using specialized agents — code quality, test coverage, error handling, comment accuracy, type design, and code simplification. Use when the user asks to review a PR, perform a pre-merge check, or validate code changes before pushing.
allowed-tools: Bash(git diff:*), Bash(gh pr view:*), Bash(gh pr list:*), Bash(gh pr diff:*), Glob, Grep, Read, Task
---

# PR Review Toolkit

Run a comprehensive pull request review using multiple specialized agents, each focusing on a different aspect of code quality.

## When to Use

- Reviewing a pull request before merge.
- Running a pre-commit quality check across multiple dimensions.
- Validating code changes for bugs, test gaps, silent failures, and style issues.
- Performing targeted reviews on specific aspects (tests, error handling, comments, types).

## Inputs

- Optional: review aspects to target (`comments`, `tests`, `errors`, `types`, `code`, `simplify`, `all`).
- Optional: `parallel` flag to run all agents concurrently.

If no aspects are specified, default to running all applicable reviews sequentially.

## Workflow

### 1. Determine Review Scope

- Check if a PR exists: `gh pr view`.
- If a PR is found, derive file scope from the PR diff: `gh pr diff --name-only`, or `git diff <base>...HEAD --name-only` using the base ref from `gh pr view --json baseRefName`.
- If no PR exists, fall back to local worktree changes: `git diff --name-only` (staged and unstaged).
- Parse user-specified review aspects; default to `all`.

### 2. Identify Applicable Reviews

Based on the changed files, determine which reviews apply:

| Review agent            | When applicable                              |
| ----------------------- | -------------------------------------------- |
| `code-reviewer`         | Always — general quality and CLAUDE.md rules |
| `pr-test-analyzer`      | When test files are present or logic changed |
| `comment-analyzer`      | When comments or docs were added or modified |
| `silent-failure-hunter` | When error handling or catch blocks changed  |
| `type-design-analyzer`  | When new types are introduced or modified    |
| `code-simplifier`       | After passing review — polish and refine     |

### 3. Launch Review Agents

**Sequential (default):** Run each applicable agent one at a time. Wait for each report before launching the next. Easier to act on findings interactively.

**Parallel (when user requests):** Launch all applicable agents simultaneously via Task. Faster for comprehensive reviews.

For each agent, pass the relevant scope — typically the git diff or specific changed files.

### 4. Aggregate Results

After all agents complete, produce a unified summary:

```markdown
# PR Review Summary

## Critical Issues (X found)

- [agent-name]: Issue description [file:line]

## Important Issues (X found)

- [agent-name]: Issue description [file:line]

## Suggestions (X found)

- [agent-name]: Suggestion [file:line]

## Strengths

- What is well-done in this PR

## Recommended Action

1. Fix critical issues first
2. Address important issues
3. Consider suggestions
4. Re-run targeted reviews after fixes
```

## Outputs

- Aggregated review report grouped by severity (Critical, Important, Suggestions, Strengths).
- Per-agent findings with file:line references and fix suggestions.
- Recommended action plan for addressing issues before merge.

## Constraints

- Do not run builds, typechecks, or tests — CI handles these.
- Use `gh` CLI for all GitHub interactions.
- Each agent is read-only: analyze and suggest only, never modify code directly.
- Report issues with specific file:line references and concrete fix examples.

## Specialized Agents

The following agents power each review dimension. They are provided by the `pr-review-toolkit` plugin and can be launched via the Task tool in Claude Code:

| Agent                   | Focus                                               |
| ----------------------- | --------------------------------------------------- |
| `code-reviewer`         | CLAUDE.md compliance, bugs, code quality            |
| `pr-test-analyzer`      | Behavioral test coverage and critical gaps          |
| `comment-analyzer`      | Comment accuracy, completeness, and rot risk        |
| `silent-failure-hunter` | Silent failures, broad catch blocks, fallback abuse |
| `type-design-analyzer`  | Type encapsulation, invariants, enforcement         |
| `code-simplifier`       | Clarity, consistency, maintainability               |

## Usage Examples

**Full review (default):**

Run all applicable review agents sequentially and aggregate findings.

**Targeted aspects:**

- `tests errors` — review only test coverage and error handling.
- `comments` — review only code comments.
- `simplify` — simplify code after passing review.

**Parallel review:**

Launch all agents simultaneously for faster comprehensive review.

## Workflow Integration

**Before committing:**

1. Write code.
2. Run `review-pr` with `code errors`.
3. Fix any critical issues.
4. Commit.

**Before creating PR:**

1. Stage all changes.
2. Run `review-pr` (all aspects).
3. Address all critical and important issues.
4. Re-run targeted reviews to verify fixes.
5. Create PR.

**After PR feedback:**

1. Make requested changes.
2. Run targeted reviews based on feedback areas.
3. Verify issues are resolved.
4. Push updates.
