---
name: copilot-cli
description: Use GitHub Copilot CLI whenever the user wants Copilot-powered help with a repository, including understanding code, generating or modifying code, reviewing changes, or researching current documentation and best practices. This unified skill covers ask, exec, review, and search modes, so use it even when the request spans multiple phases such as research -> implementation -> review. Requires GitHub Copilot CLI installed; web research uses WebSearch/WebFetch because Copilot CLI itself does not have built-in web search.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, WebFetch, WebSearch
---

# Copilot CLI Skill

Use GitHub Copilot CLI as a unified interface for Copilot-assisted analysis, execution, review, and research. Start by selecting the right mode, gather the right context, then run Copilot with a prompt that matches the user's goal.

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

- The user explicitly asks to use GitHub Copilot or GitHub Copilot CLI
- The task should be executed through Copilot rather than handled directly
- The user wants Copilot-driven code understanding, edits, review, or research
- The request naturally combines research, implementation, and review in one workflow

## Prerequisites

Verify GitHub Copilot CLI is available:

```bash
copilot --version
```

Authentication and setup:

```bash
copilot
# Then run: /login
# Follow the prompts and accept the trust prompt for the current directory
```

Requirements:

- Active GitHub Copilot subscription
- GitHub Copilot CLI installed and available in `PATH`
- Trust acceptance for the current working directory

## Common Workflow

### 1. Understand the Task

Clarify:

- What the user wants to accomplish
- Whether the task is read-only or changes code
- Which files, directories, or symbols matter
- What output or deliverable is expected
- Any constraints, versions, or compatibility requirements

### 2. Gather Local Context

Before invoking Copilot, inspect the relevant project context:

```bash
git status
git diff
```

Then use `Read`, `Grep`, and `Glob` to narrow the scope and collect file paths.

### 3. Launch Copilot CLI

```bash
cd /path/to/project
copilot
```

Useful Copilot CLI features:

- `@path/to/file` to focus on a file
- `#symbol` to reference a function or class
- `/usage` to check usage
- `/model` to switch models if needed
- `/agent` to choose a custom agent if available
- `/add-dir path` to expand workspace context
- `/cwd path` to change working directory
- `?` or `copilot help` to list commands

### 4. Run the Matching Mode

Use the mode-specific prompt structure below.

### 5. Verify and Report

After Copilot responds:

- Verify file paths, line numbers, and code examples before presenting them
- Review any proposed file edits or commands before approving them
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

Good Ask mode tasks:

- "How does authentication work here?"
- "Where is the webhook signature verified?"
- "Why does this component re-render so often?"

Expected output:

- Short summary
- Detailed explanation
- File references with line numbers
- Relevant code snippets
- Important context and edge cases

## Exec Mode

Use Exec mode when Copilot should modify code.

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

Exec mode workflow:

1. Check `git status` and relevant files first.
2. Provide the task with specific file paths when possible.
3. Review every Copilot approval prompt before accepting.
4. Re-check `git status` and `git diff`.
5. Run relevant tests or lint if the repository provides them.

Good Exec mode tasks:

- "Add input validation to the registration endpoint"
- "Refactor this module to share the parsing logic"
- "Generate tests for the new permission checks"

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

Good Review mode tasks:

- "Review the staged changes before I commit"
- "Check this PR for security issues"
- "What is wrong with this refactor?"

Present findings in severity order and keep the review read-only.

## Search Mode

Use Search mode for current external information.

### Important note

GitHub Copilot CLI does **not** have built-in web search. For this mode:

- Use `WebSearch` for broad research
- Use `WebFetch` to verify official sources
- Use Copilot CLI optionally to apply the findings to the local codebase

Search workflow:

1. Parse the research need and capture versions or framework context.
2. Search the web with focused queries.
3. Fetch official documentation or primary sources.
4. If helpful, ask Copilot how the findings fit the current codebase.
5. Present results with citations and any local integration notes.

Example web queries:

- `Next.js 15 authentication best practices`
- `React useEffect cleanup official documentation`
- `TypeScript generic constraints examples`
- `ECONNREFUSED Node.js troubleshooting`

Optional Copilot prompt after research:

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

## Custom Instructions

Copilot CLI automatically loads repository instructions if present:

- `.github/copilot-instructions.md`
- `.github/copilot-instructions/**/*.instructions.md`
- `AGENTS.md`

## Error Handling

- If `copilot` is not available, install it per `README.md` and ensure it is in `PATH`.
- If authentication fails, run `/login` again inside Copilot CLI.
- If the trust prompt blocks access to files, accept trust for the current directory and retry.
- If results are vague, narrow the scope and include explicit file paths or symbols.
- If research results conflict, prefer official documentation and version-specific sources.

## Limitations

- Copilot CLI is interactive and approval-driven
- Code changes still require human review and validation
- Search mode depends on `WebSearch` and `WebFetch` for current information
- Large or ambiguous tasks may need multiple prompt iterations

---

**Remember**: Use GitHub Copilot CLI as the primary engine for Copilot-assisted work. Pick the correct mode first, gather context before prompting, and always verify the result before handing it back.
