---
name: code-review
description: Perform comprehensive code review on a pull request, checking for bugs, AGENTS.md/CLAUDE.md compliance, and historical context issues. Use when the user asks to review a PR or current changes.
allowed-tools: Bash(gh issue view:*), Bash(gh search:*), Bash(gh issue list:*), Bash(gh pr comment:*), Bash(gh pr diff:*), Bash(gh pr view:*), Bash(gh pr list:*)
---

# Code Review Skill

Provide thorough, multi-agent code review for pull requests with high-confidence issue detection.

## When to Use

- Reviewing a pull request before merge.
- Checking code changes for bugs and AGENTS.md/CLAUDE.md compliance.
- Validating that changes align with historical context and existing code comments.

## Agent Compatibility

This skill is tool-agnostic and can be executed by Claude Code, Codex CLI, or Cursor CLI.
When posting the PR comment, replace `<agent-name>` in the output template with the active agent name.

## Inputs

- Pull request URL or number when reviewing a PR.
- Current branch or local diff when the user asks to review local changes.
- Repository context with AGENTS.md/CLAUDE.md files.

If a PR is not specified and local changes are present, review the local diff. If neither a PR nor local changes are available, ask for the target before proceeding.

## Workflow

1. **Eligibility Check** (fast agent): For PR reviews, verify the PR is eligible for review:
   - Not closed
   - Not a draft
   - Not automated or trivially simple
   - No prior code review from this tool

2. **Gather AGENTS.md/CLAUDE.md Files** (fast agent): Collect paths to relevant guideline files (but not their contents):
   - Root AGENTS.md or CLAUDE.md (if exists)
   - AGENTS.md/CLAUDE.md files in directories modified by the PR
   - Equivalent files for local changes when not reviewing a PR

3. **Summarize Changes** (fast agent): View the PR or local diff and return a summary of the change.

4. **Parallel Code Review** (5 default agents): Each agent reviews independently and returns issues with reasons:
   - **Agent 1**: Audit changes for AGENTS.md/CLAUDE.md compliance. These files guide agents as they write code, so apply only instructions relevant to review.
   - **Agent 2**: Shallow scan for obvious bugs — read only the changed lines, focus on large issues, avoid nitpicks and likely false positives.
   - **Agent 3**: Review git blame and history for context-aware bug detection.
   - **Agent 4**: Check previous PRs touching these files for relevant comments that may also apply to the current PR.
   - **Agent 5**: Read code comments in modified files and verify the changes comply with any guidance in those comments.

5. **Score Issues** (fast agents, one per issue, parallel): For each issue found, score confidence (0-100). Give this rubric to the agent verbatim:
   - **0**: Not confident at all. This is a false positive that doesn't stand up to light scrutiny, or is a pre-existing issue.
   - **25**: Somewhat confident. This might be a real issue, but may also be a false positive. The agent wasn't able to verify that it's a real issue. If the issue is stylistic, it is one that was not explicitly called out in the relevant AGENTS.md/CLAUDE.md.
   - **50**: Moderately confident. The agent was able to verify this is a real issue, but it might be a nitpick or not happen very often in practice. Relative to the rest of the PR, it's not very important.
   - **75**: Highly confident. The agent double checked the issue, and verified that it is very likely it is a real issue that will be hit in practice. The existing approach in the PR is insufficient. The issue is very important and will directly impact the code's functionality, or it is an issue that is directly mentioned in the relevant AGENTS.md/CLAUDE.md.
   - **100**: Absolutely certain. The agent double checked the issue, and confirmed that it is definitely a real issue, that will happen frequently in practice. The evidence directly confirms this.

   For issues flagged due to AGENTS.md/CLAUDE.md instructions, the scoring agent must double-check that the file actually calls out that issue specifically.

6. **Filter Issues**: Keep only issues with score >= 80. If none meet this threshold, do not post a comment.

7. **Re-check Eligibility** (fast agent): For PR reviews, confirm the PR is still eligible for review.

8. **Post or Report Results**:
   - For PR reviews, use `gh pr comment` to post results to the PR.
   - For local reviews or when the user did not ask to post, return the findings in the final response.

## False Positive Guidelines

Exclude these from reported issues:

- Pre-existing issues (not introduced by the PR)
- Apparent bugs that aren't actually bugs
- Pedantic nitpicks a senior engineer wouldn't flag
- Issues caught by linters, typecheckers, or compilers
- General code quality issues unless required in AGENTS.md/CLAUDE.md
- AGENTS.md/CLAUDE.md issues explicitly silenced in code (e.g. lint-ignore comments)
- Intentional functionality changes related to the broader change
- Real issues on lines not modified by the PR
- For local review, real issues outside the reviewed diff

## Output Format

### When Issues Found

```markdown
### Code review

Found N issues:

1. <brief description> (AGENTS.md/CLAUDE.md says "<relevant quote>")

<link to file and line with full sha1 + line range>

2. <brief description> (some/other/AGENTS.md says "<...>")

<link to file and line with full sha1 + line range>

🤖 Generated with <agent-name>

<sub>- If this code review was useful, please react with 👍. Otherwise, react with 👎.</sub>
```

### When No Issues Found

```markdown
### Code review

No issues found. Checked for bugs and AGENTS.md/CLAUDE.md compliance.

🤖 Generated with <agent-name>
```

## Link Format Requirements

When linking to code:

- Use full git SHA (not `$(git rev-parse HEAD)` — the comment renders Markdown directly)
- Format: `https://github.com/owner/repo/blob/<full-sha>/path/file.ext#L<start>-L<end>`
- Include at least 1 line of context before and after the flagged line(s)
- Repo name must match the PR's repository

## Constraints

- Do not run builds, typechecks, or tests (CI handles these).
- Use `gh` CLI for all GitHub interactions.
- Create a todo list before starting.
- Cite and link every reported issue.
- Keep output brief.

## Outputs

- Comment posted to the pull request with review results.
- For local reviews, review findings returned in the response.
