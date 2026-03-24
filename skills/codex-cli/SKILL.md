---
name: codex-cli
description: Use OpenAI Codex CLI whenever the user wants Codex-powered help with a repository, including understanding code, generating or modifying code, reviewing changes, or researching current documentation and best practices. This unified skill covers ask, exec, review, and search modes, so use it even when the request spans multiple phases such as research -> implementation -> review. Requires Codex CLI installed; native web research uses `codex --search`, with `WebFetch` or `WebSearch` as verification or fallback when helpful.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, WebFetch, WebSearch
---

# Codex CLI Skill

Use OpenAI Codex CLI as a unified interface for Codex-assisted analysis, execution, review, and research. Start by selecting the right mode, gather the right context, then run Codex with a prompt that matches the user's goal.

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

- The user explicitly asks to use OpenAI Codex or Codex CLI
- The task should be executed through Codex rather than handled directly
- The user wants Codex-driven code understanding, edits, review, or research
- The request naturally combines research, implementation, and review in one workflow

## Prerequisites

Verify Codex CLI is available:

```bash
codex --version
```

Authentication and setup:

```bash
codex
# Follow the prompts to sign in with ChatGPT
# or configure an API key in ~/.codex/config.toml
```

Requirements:

- Codex CLI installed and available in `PATH`
- Valid Codex authentication via ChatGPT subscription or API key
- For native web research, enable web search in `~/.codex/config.toml`:

  ```toml
  [features]
  web_search_request = true
  ```

## Common Workflow

### 1. Understand the Task

Clarify:

- What the user wants to accomplish
- Whether the task is read-only or changes code
- Which files, directories, symbols, or errors matter
- What output or deliverable is expected
- Any constraints, versions, or compatibility requirements

### 2. Gather Local Context

Before invoking Codex, inspect the relevant project context:

```bash
git status
git diff
```

Then use `Read`, `Grep`, and `Glob` to narrow the scope and collect file paths. If the repository has local instructions such as `AGENTS.md`, `CLAUDE.md`, or similar guidance, summarize the relevant constraints in the Codex prompt.

### 3. Launch Codex CLI

Use Codex in one-shot mode for most tasks:

```bash
cd /path/to/project
codex --sandbox=read-only exec "Explain how authentication works in this repository."
```

Useful patterns:

- `codex --sandbox=read-only exec "..."` for analysis, review, and research
- `codex --sandbox=workspace-write exec "..."` for code changes
- `codex --sandbox=read-only --search exec "..."` for native web research
- `codex --help` to review available flags and supported workflows

### 4. Run the Matching Mode

Use the mode-specific prompt structure below.

### 5. Verify and Report

After Codex responds:

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
codex --sandbox=read-only exec "Explain [QUESTION OR FEATURE] in this codebase.

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

Use Exec mode when Codex should modify code.

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
codex --sandbox=workspace-write exec "[TASK DESCRIPTION]

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
3. Use Codex's standard approval flow; avoid auto-approval flags so changes stay reviewable.
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
codex --sandbox=read-only exec "Perform a comprehensive code review of [SCOPE].

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

Codex CLI supports native web research through `--search`. For this mode:

- Ask Codex to cite source URLs and prefer official documentation
- Use `WebFetch` to verify especially important sources when needed
- Use `WebSearch` as a fallback if native Codex web search is unavailable in the environment
- Optionally follow up with Ask mode to connect the findings back to the local codebase

Prompt template:

```text
Research [TOPIC] using web search.

Please provide:
- A direct answer or recommendation
- Official documentation links
- Key findings with citations
- Version-specific caveats
- Any relevant compatibility or security considerations

Do NOT make any changes - this is research only.
```

Suggested command:

```bash
codex --sandbox=read-only --search exec "Research [TOPIC] using web search.

Please provide:
- A direct answer or recommendation
- Official documentation links
- Key findings with citations
- Version-specific caveats
- Any relevant compatibility or security considerations

Do NOT make any changes - this is research only."
```

Search workflow:

1. Parse the research need and capture versions or framework context.
2. Ask Codex to use web search and cite URLs.
3. Prefer official documentation or authoritative standards when sources conflict.
4. If helpful, ask Codex how the findings fit the current codebase.
5. Present results with citations and any local integration notes.

Good Search mode tasks:

- "What are the current authentication best practices for Next.js 15?"
- "Compare Prisma vs Drizzle for a TypeScript service in 2026."
- "Find the latest official docs for React Server Components."
- "Research solutions for this ECONNREFUSED error in Node.js."

Search output should include:

- Direct answer or recommendation
- Official documentation links
- Key findings with citations
- Version-specific caveats
- Local codebase implications when relevant

## Codex-Specific Strengths

Codex CLI is especially helpful when the task benefits from:

- **Native sandboxing**: switch between `read-only` and `workspace-write` modes based on whether the task should modify code
- **Prompt-driven execution**: run focused one-shot tasks with explicit instructions and repository context
- **Native web search**: use `--search` for current docs, troubleshooting, and best-practice research
- **Mode chaining**: move from research to analysis to implementation to review without changing tools

## Error Handling

- If `codex` is not available, install it per `README.md` and ensure it is in `PATH`.
- If authentication fails, run `codex` again and complete the sign-in flow or configure `~/.codex/config.toml`.
- If native web search is unavailable, use `WebSearch` and `WebFetch` to gather and verify sources, then continue with Ask mode or Exec mode as needed.
- If results are vague, narrow the scope and include explicit file paths, symbols, or errors.
- If review results include likely false positives, verify each one against the current code before reporting it.
- If the task is too broad, split it into phases and reuse the outputs from earlier modes.

## Limitations

- Codex CLI is prompt-driven and may need multiple iterations for complex work
- Code changes still require human review and validation
- Search mode depends on native search availability or external source verification
- Large or ambiguous tasks may need to be broken into smaller phases

---

**Remember**: Use OpenAI Codex CLI as the primary engine for Codex-assisted work. Pick the correct mode first, gather context before prompting, and always verify the result before handing it back.
