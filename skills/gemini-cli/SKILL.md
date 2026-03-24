---
name: gemini-cli
description: Use Google Gemini CLI whenever the user wants Gemini-powered help with a repository, including understanding code, generating or modifying code, reviewing changes, or researching current documentation and best practices. This unified skill covers ask, exec, review, and search modes, so use it even when the request spans multiple phases such as research -> implementation -> review. Gemini CLI is especially useful for multimodal inputs like images and PDFs, built-in Google Search grounding, and large-context analysis. Requires Gemini CLI installed.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob
---

# Gemini CLI Skill

Use Google Gemini CLI as a unified interface for Gemini-assisted analysis, execution, review, and research. Start by selecting the right mode, gather the right context, then run Gemini with a prompt that matches the user's goal.

## Mode Selection

Choose the mode that best matches the request:

- **Ask mode** for read-only questions about how code works, where something is implemented, architecture, debugging context, or interpreting local diagrams, screenshots, and PDFs.
- **Exec mode** for creating or modifying code, fixing bugs, refactoring, generating tests, or implementing from mockups or specifications.
- **Review mode** for read-only code review, security checks, performance analysis, and design or spec compliance validation.
- **Search mode** for current documentation, best practices, troubleshooting, comparisons, and standards research with built-in Google Search grounding.

If the task spans multiple phases, move through the modes explicitly:

1. **Search** for current guidance when outside information matters.
2. **Ask** how the current codebase works or where changes belong.
3. **Exec** the implementation or refactor.
4. **Review** the result before handoff or commit.

## When to Use

Use this skill when:

- The user explicitly asks to use Google Gemini or Gemini CLI
- The task should be executed through Gemini rather than handled directly
- The user wants Gemini-driven code understanding, edits, review, or research
- The request benefits from multimodal inputs such as diagrams, screenshots, PDFs, or wireframes
- The request benefits from Google Search grounding or large-context analysis
- The request naturally combines research, implementation, and review

## Prerequisites

Verify Gemini CLI is available:

```bash
gemini --version
```

Authentication and setup:

```bash
gemini
# Follow the prompts to sign in with a Google account
# or configure an API key from aistudio.google.com/apikey
```

Requirements:

- Gemini CLI installed and available in `PATH`
- Valid Gemini authentication via Google account or API key
- Access to relevant local files; keep images, PDFs, and other artifacts in the workspace so Gemini can reference them

## Common Workflow

### 1. Understand the Task

Clarify:

- What the user wants to accomplish
- Whether the task is read-only or changes code
- Which files, directories, symbols, or artifacts matter
- Whether multimodal inputs or current web information matter
- What output or deliverable is expected
- Any constraints, versions, or compatibility requirements

### 2. Gather Local Context

Before invoking Gemini, inspect the relevant project context:

```bash
git status
git diff
```

Then use `Read`, `Grep`, and `Glob` to narrow the scope and collect file paths. If the task depends on images, PDFs, or screenshots, confirm those files are present and name them explicitly in the prompt.

### 3. Launch Gemini CLI

```bash
cd /path/to/project
gemini
```

Useful Gemini CLI features:

- `-p` for prompt-based execution
- `--sandbox` to keep runs constrained
- `--include-directories src,lib,tests` to focus local context
- `-m gemini-2.5-pro` or `-m gemini-2.5-flash` when model selection matters
- Follow-up prompts in interactive sessions to preserve context across phases

### 4. Run the Matching Mode

Use the mode-specific prompt structures below.

### 5. Verify and Report

After Gemini responds:

- Verify file paths, line numbers, and code examples before presenting them
- Review proposed edits or commands before applying them
- Run relevant tests, lint, or checks when code changes were made
- Summarize what happened, what changed, and any follow-up items

## Ask Mode

Use Ask mode for read-only code understanding, debugging, and multimodal analysis.

Prompt template:

```text
Explain [QUESTION OR FEATURE] in this codebase.

Please provide:
1. A direct answer
2. Specific file paths and line numbers
3. Relevant code examples from the repository
4. Related dependencies, data flow, or gotchas

If helpful, also analyze these local artifacts: [IMAGE_OR_PDF_FILES].

Do NOT make any changes - this is read-only analysis.
```

Good Ask mode tasks:

- "How does authentication work here?"
- "Where is the webhook signature verified?"
- "Analyze architecture-diagram.pdf and explain which files implement each component."
- "What does this error screenshot suggest about the failing API flow?"

Expected output:

- Short summary
- Detailed explanation
- File references with line numbers
- Relevant code snippets
- Important context, edge cases, or artifact observations

## Exec Mode

Use Exec mode when Gemini should modify code or generate artifacts from specifications.

Prompt template:

```text
[TASK DESCRIPTION]

Follow these guidelines:
- Follow existing code patterns and conventions
- Keep changes focused to the requested scope
- Add imports, types, and error handling as needed
- Preserve readability and maintainability
- Use local artifacts such as [MOCKUP_OR_SPEC_FILES] when relevant
- Explain any assumptions you made

Before applying changes, preview the plan.
After making changes, summarize the files modified and validation performed.
```

Exec mode workflow:

1. Check `git status` and relevant files first.
2. Provide the task with specific file paths or artifact names when possible.
3. When design assets, screenshots, or PDFs matter, tell Gemini exactly which files to use.
4. Re-check `git status` and `git diff`.
5. Run relevant tests or lint if the repository provides them.

Good Exec mode tasks:

- "Add input validation to the registration endpoint."
- "Refactor this module to share the parsing logic."
- "Generate tests for the new permission checks."
- "Implement the component shown in mockup.png using the patterns from src/components/."

Report:

- Files modified or created
- Summary of changes
- Validation performed
- Any remaining risks or follow-ups

## Review Mode

Use Review mode for read-only code review, security analysis, performance checks, and spec compliance.

Prompt template:

```text
Perform a comprehensive code review of [SCOPE].

Check for:
1. Critical issues: security vulnerabilities, runtime errors, data loss risks
2. Important issues: logic bugs, performance problems, type safety gaps
3. Suggestions: maintainability, patterns, documentation, or design/spec alignment improvements

For each issue, include:
- Severity
- File path and line number
- Why it matters
- How to fix it

If relevant, compare against these local artifacts: [IMAGE_OR_PDF_FILES].

Do NOT make any changes - this is review only.
```

Good Review mode tasks:

- "Review the staged changes before I commit."
- "Check this PR for security issues."
- "Compare the implementation to design-spec.pdf and call out mismatches."
- "What is wrong with this refactor?"

Present findings in severity order and keep the review read-only.

## Search Mode

Use Search mode for current external information.

### Important note

Gemini CLI has built-in Google Search grounding. For this mode:

- Ask Gemini to use Google Search and cite source URLs
- Prefer official documentation and primary sources
- Optionally follow up with Ask mode to connect the findings back to the local codebase

Search workflow:

1. Parse the research need and capture versions or framework context.
2. Ask Gemini to use Google Search grounding and cite URLs.
3. Prefer official documentation or authoritative standards when sources conflict.
4. If helpful, ask Gemini how the findings fit the current codebase.
5. Present results with citations and any local integration notes.

Example search prompt:

```text
Research [TOPIC] and use Google Search grounding.

Please provide:
- A direct answer or recommendation
- Official documentation links
- Key findings with citations
- Version-specific caveats
- Any relevant compatibility or security considerations

If local artifacts such as PDFs or screenshots matter, incorporate: [IMAGE_OR_PDF_FILES].
```

Search output should include:

- Direct answer or recommendation
- Official documentation links
- Key findings with citations
- Version-specific caveats
- Local codebase implications when relevant

## Gemini-Specific Strengths

Gemini CLI is especially helpful when the task benefits from:

- **Multimodal inputs**: analyze diagrams, screenshots, PDFs, wireframes, or design mockups alongside code
- **Built-in Google Search grounding**: research current documentation and standards without switching tools
- **Large-context analysis**: include multiple directories for complex, cross-cutting questions
- **Multi-step sessions**: preserve context across iterative prompts in an interactive Gemini session

Example multimodal prompt:

```text
Analyze architecture-diagram.png and requirements.pdf, then explain how the current codebase maps to the design and what gaps remain.

Do NOT make any changes - this is analysis only.
```

## Local Instructions

Before asking Gemini to change or review a project, inspect repository guidance such as:

- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md` if present

This keeps Gemini aligned with local conventions, testing expectations, and safety requirements.

## Error Handling

- If `gemini` is not available, install it per `README.md` and ensure it is in `PATH`.
- If authentication fails, run `gemini` and complete the sign-in flow or configure an API key.
- If results are vague, narrow the scope and include explicit file paths, directories, symbols, or artifact names.
- If multimodal analysis is weak, confirm the referenced files exist and are accessible from the workspace.
- If search results conflict, prefer official documentation and ask Gemini to cite version-aware sources.
- If the task is too broad, split it into phases and reuse the interactive session context.

## Limitations

- Gemini CLI is prompt-driven and may need multiple iterations for complex work
- Code changes still require human review and validation
- Search grounding depends on available online sources and cited material
- Multimodal analysis quality depends on the quality and availability of input files
- Large or ambiguous tasks may still need to be broken into smaller phases

---

**Remember**: Use Google Gemini CLI as the primary engine for Gemini-assisted work. Pick the correct mode first, gather context before prompting, and lean on multimodal inputs plus Google Search grounding when they add real value.
