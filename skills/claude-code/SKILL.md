---
name: claude-code
description: Use Claude Code whenever the user wants Claude-powered help with a repository, including understanding code, generating or modifying code, reviewing changes, or researching current documentation and best practices. This unified skill covers ask, exec, review, and search modes, so use it even when the request spans multiple phases such as research -> implementation -> review. Requires Claude Code CLI installed; when current external information matters, combine Claude Code with WebSearch/WebFetch for source-backed research.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, WebFetch, WebSearch
---

# Claude Code Skill

Use Claude Code as a unified interface for Claude-assisted analysis, execution, review, and research. Start by selecting the right mode, gather the right context, then run Claude Code with a prompt that matches the user's goal.

## Mode Selection

Choose the mode that best matches the request:

- **Ask mode** for read-only questions about how code works, where something is implemented, architecture, patterns, and debugging context.
- **Exec mode** for creating or modifying code, fixing bugs, refactoring, or generating tests.
- **Review mode** for read-only code review, security checks, performance analysis, and pre-commit validation.
- **Search mode** for current documentation, best practices, troubleshooting, and library comparisons.

If the task spans multiple phases, move through the modes explicitly:

1. **Search** for current guidance when outside information matters.
2. **Ask** how the current codebase works or where changes belong.
3. **Exec** the implementation or refactor.
4. **Review** the result before handoff or commit.

## When to Use

Use this skill when:

- The user explicitly asks to use Claude or Claude Code
- The task should be executed through Claude Code rather than handled directly
- The user wants Claude-driven code understanding, edits, review, or research
- The request naturally combines research, implementation, and review in one workflow

## Prerequisites

Verify Claude Code CLI is available:

```bash
claude --version
```

Authentication and setup:

```bash
claude
# Follow the CLI onboarding flow and authenticate if prompted
```

Requirements:

- Claude Code CLI installed and available in `PATH`
- Valid Claude Code authentication for the current environment
- For current external research, access to `WebSearch` and `WebFetch` or another approved source-verification workflow

## Common Workflow

### 1. Understand the Task

Clarify:

- What the user wants to accomplish
- Whether the task is read-only or changes code
- Which files, directories, symbols, or errors matter
- What output or deliverable is expected
- Any constraints, versions, or compatibility requirements

### 2. Gather Local Context

Before invoking Claude Code, inspect the relevant project context:

```bash
git status
git diff
```

Then use `Read`, `Grep`, and `Glob` to narrow the scope and collect file paths. If the repository has local instructions such as `AGENTS.md`, `CLAUDE.md`, or similar guidance, summarize the relevant constraints in the Claude Code prompt.

### 3. Launch Claude Code

Use Claude Code in one-shot mode when a single prompt is enough:

```bash
cd /path/to/project
claude -p "Explain how authentication works in this repository."
```

Useful patterns:

- `claude -p "..."` for focused one-shot ask, review, or planning tasks
- `claude` for interactive multi-step work when the task needs follow-up prompts or approvals
- `claude --help` to review available flags and workflows

### 4. Run the Matching Mode

Use the mode-specific prompt structure below.

### 5. Verify and Report

After Claude Code responds:

- Verify file paths, line numbers, and code examples before presenting them
- Review any proposed edits or commands before approving them
- Run relevant tests, lint, or checks when code changes were made
- Summarize what happened, what changed, and any follow-up items

## Ask Mode

Use Ask mode for read-only code understanding.

Prompt template:

```text
Explain [QUESTION OR FEATURE] in this codebase.

Please provide:
1. A direct answer
2. Specific file paths and line numbers
3. Relevant code examples from the repository
4. Related dependencies, data flow, or gotchas

Do NOT make any changes - this is read-only analysis.
```

Suggested command:

```bash
claude -p "Explain [QUESTION OR FEATURE] in this codebase.

Please provide:
1. A direct answer
2. Specific file paths and line numbers
3. Relevant code examples from the repository
4. Related dependencies, data flow, or gotchas

Do NOT make any changes - this is read-only analysis."
```

Good Ask mode tasks:

- "How does authentication work here?"
- "Where is the webhook signature verified?"
- "Why does this component re-render so often?"
- "What could cause this error path to fail?"

Expected output:

- Short summary
- Detailed explanation
- File references with line numbers
- Relevant code snippets
- Important context and edge cases

## Exec Mode

Use Exec mode when Claude Code should modify code.

Prompt template:

```text
[TASK DESCRIPTION]

Follow these guidelines:
- Follow existing code patterns and conventions
- Keep changes focused to the requested scope
- Add imports, types, and error handling as needed
- Preserve readability and maintainability
- Explain any assumptions you made

Before applying changes, preview the plan.
After making changes, summarize the files modified and validation performed.
```

Suggested command:

```bash
claude -p "[TASK DESCRIPTION]

Follow these guidelines:
- Follow existing code patterns and conventions
- Keep changes focused to the requested scope
- Add imports, types, and error handling as needed
- Preserve readability and maintainability
- Explain any assumptions you made

Before applying changes, preview the plan.
After making changes, summarize the files modified and validation performed."
```

Exec mode workflow:

1. Check `git status` and relevant files first.
2. Provide the task with specific file paths when possible.
3. Use Claude Code's standard approval flow so changes stay reviewable.
4. Re-check `git status` and `git diff`.
5. Run relevant tests or lint if the repository provides them.

Good Exec mode tasks:

- "Add input validation to the registration endpoint"
- "Refactor this module to share parsing logic"
- "Generate tests for the new permission checks"
- "Fix the failing null-handling path in this service"

Report:

- Files modified or created
- Summary of changes
- Validation performed
- Any remaining risks or follow-ups

## Review Mode

Use Review mode for read-only code review.

Prompt template:

```text
Perform a comprehensive code review of [SCOPE].

Check for:
1. Critical issues: security vulnerabilities, runtime errors, data loss risks
2. Important issues: logic bugs, performance problems, type safety gaps
3. Suggestions: maintainability, patterns, or documentation improvements

For each issue, include:
- Severity
- File path and line number
- Why it matters
- How to fix it

Do NOT make any changes - this is review only.
```

Suggested command:

```bash
claude -p "Perform a comprehensive code review of [SCOPE].

Check for:
1. Critical issues: security vulnerabilities, runtime errors, data loss risks
2. Important issues: logic bugs, performance problems, type safety gaps
3. Suggestions: maintainability, patterns, or documentation improvements

For each issue, include:
- Severity
- File path and line number
- Why it matters
- How to fix it

Do NOT make any changes - this is review only."
```

Good Review mode tasks:

- "Review the staged changes before I commit"
- "Check this PR for security issues"
- "What is wrong with this refactor?"
- "Review these uncommitted changes for performance regressions"

Present findings in severity order and keep the review read-only.

## Search Mode

Use Search mode for current external information.

### Important note

Claude Code is strongest at local code understanding and execution. When the task depends on current external information:

- Use `WebSearch` for broad research
- Use `WebFetch` to verify official documentation or primary sources
- Use Claude Code optionally to connect the findings back to the local codebase

Search workflow:

1. Parse the research need and capture versions or framework context.
2. Search the web with focused queries.
3. Fetch official documentation or primary sources.
4. If helpful, ask Claude Code how the findings fit the current codebase.
5. Present results with citations and any local integration notes.

Example web queries:

- `Next.js 15 authentication best practices`
- `React useEffect cleanup official documentation`
- `TypeScript generic constraints examples`
- `ECONNREFUSED Node.js troubleshooting`

Optional Claude Code prompt after research:

```text
Based on these web findings, analyze how we should apply [TOPIC] in this codebase.

Please provide:
- Relevant files or patterns in the repository
- Compatibility concerns
- Recommended integration approach

Do NOT make any changes - analysis only.
```

Search output should include:

- Direct answer or recommendation
- Official documentation links
- Key findings with citations
- Version-specific caveats
- Local codebase implications when relevant

## Claude Code-Specific Strengths

Claude Code is especially helpful when the task benefits from:

- **Repository-aware reasoning**: trace behavior across files, modules, and workflows before changing code
- **Focused prompt-to-edit workflows**: move from explanation to implementation to review in one tool
- **Iterative execution**: keep context in an interactive Claude Code session for multi-step work
- **Local-instruction alignment**: incorporate repository guidance such as `AGENTS.md` and `CLAUDE.md` into prompts before acting

## Local Instructions

Before asking Claude Code to change or review a project, inspect repository guidance such as:

- `AGENTS.md`
- `CLAUDE.md`

This keeps Claude Code aligned with local conventions, testing expectations, and safety requirements.

## Error Handling

- If `claude` is not available, install it per `README.md` and ensure it is in `PATH`.
- If authentication fails, run `claude` and complete the onboarding flow again.
- If results are vague, narrow the scope and include explicit file paths, symbols, or errors.
- If research results conflict, prefer official documentation and version-specific sources.
- If the task is too broad, split it into phases and reuse outputs from earlier modes.

## Limitations

- Claude Code is prompt-driven and may need multiple iterations for complex work
- Code changes still require human review and validation
- Search mode depends on `WebSearch` and `WebFetch` for current information
- Large or ambiguous tasks may need to be broken into smaller phases

---

**Remember**: Use Claude Code as the primary engine for Claude-assisted work. Pick the correct mode first, gather context before prompting, and always verify the result before handing it back.
