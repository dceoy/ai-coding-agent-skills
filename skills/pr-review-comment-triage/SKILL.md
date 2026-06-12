---
name: pr-review-comment-triage
description: Triage and resolve review comments on a pull request. Use when the user asks to address PR feedback, review comments, requested changes, or unresolved review threads.
---

# PR Review Comment Triage

Triage pull request review comments, implement the accepted fixes when allowed, and reply to or resolve review threads when appropriate and allowed.

## When to Use

- A pull request has review comments, requested changes, or unresolved review threads.
- The user asks to address, fix, respond to, or resolve PR feedback.
- The user provides a PR URL, PR number, current branch with an associated PR, or copied review comments.

Do not use this skill for a first-pass code review with no existing feedback; use a code review skill instead.

## Agent Compatibility

This skill is tool-agnostic and can be executed by Claude Code, Codex CLI, Cursor CLI, or any agent with repository and pull request access.

Use the active platform tooling for pull request operations. For GitHub, prefer `gh pr view`, `gh pr checkout`, `gh pr diff`, and `gh api graphql` when available. If the current environment has read-only platform credentials, perform the code changes and provide the exact replies or resolution actions for a maintainer to apply manually.

## Inputs

- Pull request URL or number, or a current branch that has an associated pull request.
- Repository checkout or platform API access with permission to inspect the PR diff, plus branch edit access when fixes are allowed.
- Optional reviewer priorities from the user, such as "only address blocking comments" or "do not reply on GitHub".
- Optional operating mode flags: `dry_run`, `no_push`, and `no_reply`.

If no PR or review comments are identifiable, ask for the target PR or the copied comments before proceeding.

## Operating Modes

Use normal mode unless the user or environment specifies one of these flags:

- `dry_run`: inspect review feedback and report the triage only. Do not edit files, run write-mode formatters, commit, push, post GitHub replies, or resolve review threads.
- `no_push`: local edits and verification are allowed, but do not push commits or otherwise update the remote branch. Report the local diff or local commits that still need to be pushed.
- `no_reply`: do not post GitHub replies, submit reviews, or resolve review threads. Provide suggested replies and resolution actions in the final report instead.

When a mode disables an action, skip that destructive or externally visible action even if it appears later in the normal workflow.

## Workflow

1. **Establish the PR target**
   - Determine the PR number, URL, base branch, head branch, repository owner/name, and current local branch.
   - If the local branch is not the PR head branch, check out or fetch the PR head branch before editing unless `dry_run` only needs remote inspection.
   - Inspect repository instructions such as `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, and nearby package guidance relevant to changed files.
   - Capture the current working tree state and do not overwrite unrelated user changes.

2. **Collect review feedback**
   - Gather unresolved review threads, requested-change reviews, top-level PR comments, and relevant CI annotations if the user included them in the requested feedback.
   - For GitHub review threads, collect at least:
     - Thread ID and URL
     - Resolution state and outdated state
     - File path, line or original line, and diff hunk
     - All comments in the thread with author, timestamp, and body
   - Also inspect the PR diff and the current file contents around each commented line, since comment line numbers can drift after new commits.

   Example GitHub GraphQL query shape for paginating review threads:

   ```bash
   THREAD_CURSOR=null
   gh api graphql \
     -f owner='<owner>' \
     -f repo='<repo>' \
     -F number='<pr-number>' \
     -F threadCursor="$THREAD_CURSOR" \
     -f query='
   query($owner: String!, $repo: String!, $number: Int!, $threadCursor: String) {
     repository(owner: $owner, name: $repo) {
       pullRequest(number: $number) {
         reviewThreads(first: 100, after: $threadCursor) {
           pageInfo {
             hasNextPage
             endCursor
           }
           nodes {
             id
             isResolved
             isOutdated
             path
             line
             originalLine
             comments(first: 20) {
               pageInfo {
                 hasNextPage
                 endCursor
               }
               nodes {
                 author { login }
                 body
                 createdAt
                 url
               }
             }
           }
         }
       }
     }
   }'
   ```

   Repeat the query with `THREAD_CURSOR` set to `reviewThreads.pageInfo.endCursor` while `reviewThreads.pageInfo.hasNextPage` is true. For any thread whose `comments.pageInfo.hasNextPage` is true, paginate that thread's comments separately:

   ```bash
   COMMENT_CURSOR=null
   gh api graphql \
     -f threadId='<thread-id>' \
     -F commentCursor="$COMMENT_CURSOR" \
     -f query='
   query($threadId: ID!, $commentCursor: String) {
     node(id: $threadId) {
       ... on PullRequestReviewThread {
         comments(first: 100, after: $commentCursor) {
           pageInfo {
             hasNextPage
             endCursor
           }
           nodes {
             author { login }
             body
             createdAt
             url
           }
         }
       }
     }
   }'
   ```

   Repeat the comment query with `COMMENT_CURSOR` set to `comments.pageInfo.endCursor` until every thread's comments are collected. Do not silently inspect only the first page of review threads or comments.

3. **Classify every comment**
   - Create a tracking list with one item per thread or standalone comment.
   - Classify each item as one of:
     - **Fix**: Valid requested change that should be implemented.
     - **Answer**: Needs an explanation or confirmation, but no code change.
     - **Clarify**: Ambiguous, conflicting, or missing enough context to act safely.
     - **Already addressed**: Current code already satisfies the comment.
     - **Outdated**: The commented code no longer exists or the issue was removed by later commits.
     - **Won't fix**: Valid concern that should not be changed, with a clear reason.
   - Prefer fixing concrete correctness, security, test, compatibility, and maintainability issues over stylistic churn.
   - Do not dismiss an outdated thread until current code proves the concern is gone.

4. **Plan the changes**
   - Group related fixes by subsystem to minimize churn.
   - Identify tests, linters, formatters, snapshots, generated files, and documentation that should change with the fixes.
   - If comments conflict, follow repository policy first, then maintainer comments, then reviewer suggestions. Explain the conflict in the thread or final summary.
   - If a comment is ambiguous but a small safe fix clearly satisfies it, implement the fix. Otherwise ask for clarification instead of guessing.
   - If `dry_run` is enabled, stop after producing the triage, proposed fixes, verification plan, and suggested replies. Do not edit files.

5. **Implement accepted fixes when allowed**
   - Make the smallest coherent code changes needed to resolve the accepted comments.
   - Preserve unrelated user changes and avoid broad refactors.
   - Update or add tests for behavioral changes and reviewer-requested coverage.
   - Keep a mapping from each changed file or commit back to the comments it resolves.
   - Skip this step in `dry_run`.

6. **Verify**
   - Run targeted tests for changed behavior.
   - Run repository-required formatting, linting, typechecking, or local QA commands when practical.
   - If a check cannot run, record the command attempted, the failure, and the residual risk.
   - Re-read the updated diff and each addressed comment to confirm the fix actually resolves the concern.
   - In `dry_run`, verify by inspecting the current code and report the commands that should be run if fixes are later implemented.

7. **Commit and push when allowed**
   - In normal mode, commit the changes with a message that summarizes the review feedback addressed, then push the PR head branch.
   - In `dry_run`, do not commit or push.
   - In `no_push`, do not push. Leave changes uncommitted or committed locally according to the user's request and report the exact local state.
   - If multiple independent fixes are large enough to warrant separate commits, keep each commit focused and explain the grouping.

8. **Reply and resolve threads when allowed**
   - For each thread, leave a concise reply before resolving when:
     - A code change was made.
     - No code change was made but an explanation is needed.
     - The thread is outdated, duplicate, or intentionally not fixed.
   - Include what changed and, when useful, the commit SHA or verification command.
   - Resolve a review thread only after the fix is pushed or the answer clearly closes the discussion.
   - Do not resolve threads that need reviewer clarification or product decisions.
   - In `dry_run` or `no_reply`, do not post replies or resolve threads; provide suggested replies and resolution actions in the final report.
   - In `no_push`, do not resolve threads for code changes that are only local. Provide suggested replies until the fixes are pushed.

   Example GitHub GraphQL mutations:

   ```bash
   gh api graphql -f thread_id='<thread-id>' -f body='Fixed in <commit-sha>; verified with <command>.' -f query='
   mutation($thread_id: ID!, $body: String!) {
     addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $thread_id, body: $body}) {
       comment { url }
     }
   }'

   gh api graphql -f thread_id='<thread-id>' -f query='
   mutation($thread_id: ID!) {
     resolveReviewThread(input: {threadId: $thread_id}) {
       thread { isResolved }
     }
   }'
   ```

9. **Report results**
   - Summarize each comment disposition: fixed, answered, resolved as outdated, left open, or not fixed.
   - List commits pushed, local commits, or local diffs according to the active mode.
   - List verification commands run, or the verification plan for `dry_run`.
   - Call out unresolved threads, requested clarification, skipped checks, and any follow-up needed from reviewers.

## Reply Guidelines

- Be concise, factual, and appreciative without adding filler.
- Reference the specific fix instead of saying only "done".
- Avoid arguing with reviewers. When declining a suggestion, explain the tradeoff and offer an alternative if one exists.
- Do not reveal secrets or paste sensitive data from diffs, logs, or comments.
- Do not mark a comment resolved merely because it is inconvenient or because CI passed.

## Output Format

### Final Response

```markdown
Addressed PR review feedback.

- Mode: <normal / dry_run / no_push / no_reply>
- Fixed: <N> thread(s)
- Answered without code change: <N> thread(s)
- Resolved as outdated/already addressed: <N> thread(s)
- Left open: <N> thread(s), because <reason>

Commits:

- <sha> <subject>
- <none; dry_run/no_push/no local commit>

Verification:

- `<command>` - passed
- `<command>` - failed/skipped: <reason>
- Planned only: `<command>` - <dry_run reason>

Follow-up:

- <none or remaining reviewer/product questions>
```

### Manual Resolution Needed

Use this when the environment cannot post replies or resolve threads:

```markdown
Implemented the fixes, but could not update PR threads from this environment.

Suggested replies:

1. <thread URL or ID>
   Reply: <message>
   Action: resolve / leave open

Verification:

- `<command>` - <result>
```

## Constraints

- Keep the work scoped to the PR feedback unless the user asks for broader changes.
- Do not resolve threads that still need human input.
- Do not include unrelated changes in commits.
- Prefer platform-native review thread APIs over ad hoc scraping.
