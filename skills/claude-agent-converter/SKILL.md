---
name: claude-agent-converter
description: Convert Claude Code subagents (.claude/agents/*.md) to standard Agent Skills (skills/*/SKILL.md). Use when migrating subagents to portable skill format, extracting reusable workflows from agents, or standardizing agent definitions across AI runtimes.
---

# Claude Agent Converter

Convert Claude Code subagents to standard Agent Skills format for portability across AI coding assistants.

## When to Use

- Migrating existing `.claude/agents/*.md` subagent files to `skills/*/SKILL.md` format.
- Extracting reusable workflows from subagent definitions.
- Creating portable skills from Claude Code-specific agents.
- Standardizing agent definitions for use with Claude Code, Codex CLI, Cursor CLI, and other runtimes.

## Inputs

- Source agent file path (e.g., `.claude/agents/my-agent.md`).
- Optional: target skill name (defaults to agent name from frontmatter).
- Optional: mode to extract (if agent supports multiple modes).

If input is missing, ask for the source agent file path.

## Format Differences

### Claude Code Subagent Format

Location: `.claude/agents/<agent-name>.md`

```yaml
---
name: agent-name
description: When Claude should delegate to this subagent
tools: Read, Grep, Glob, Bash
disallowedTools: Write, Edit
model: fast | default | advanced | inherit
permissionMode: default | acceptEdits | dontAsk | bypassPermissions | plan
skills: skill-1, skill-2
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate.sh"
---
[System prompt instructions for the subagent...]
```

### Standard Agent Skill Format

Location: `skills/<skill-name>/SKILL.md`

```yaml
---
name: skill-name
description: Complete description including what the skill does and when to use it.
---

# Skill Title

## When to Use

- Scenario 1
- Scenario 2

## Inputs

- Required input 1
- Optional input 2

## Workflow

1. Step 1
2. Step 2
...

## Outputs

- Output 1
- Output 2
```

## Conversion Workflow

1. **Read the source agent** from `.claude/agents/`.

2. **Analyze agent structure**:
   - Identify if agent has multiple modes (e.g., ask, exec, review, search).
   - Determine if agent should become one skill or multiple skills.
   - Note tool restrictions for skill documentation.

3. **Extract metadata**:
   - `name` from YAML frontmatter.
   - `description` for triggering context.
   - `tools` and `disallowedTools` for capability constraints.
   - `model` preference if specified.
   - `skills` dependencies to reference.
   - `hooks` for validation logic to document.

4. **Determine skill name(s)**:
   - Single-mode agent: use agent name directly.
   - Multi-mode agent: create separate skills per mode (e.g., `agent-ask`, `agent-exec`).
   - Use kebab-case for multi-word names.

5. **Create skill directory**: `skills/<skill-name>/`

6. **Transform content** to SKILL.md format:
   - **Frontmatter**: Keep only `name` and `description`.
   - **Enhance description**: Expand to include when to use the skill.
   - **Extract "When to Use"**: From mode selection criteria in agent prompt.
   - **Document Inputs**: What information the skill needs to operate.
   - **Structure Workflow**: Convert agent instructions to numbered steps.
   - **List Outputs**: Expected artifacts or results.
   - **Note Tool Usage**: Document which tools the workflow uses.
   - **Document Constraints**: Read-only modes, permission requirements.

7. **Handle multi-mode agents**:
   - If agent has distinct modes (ask/exec/review/search), create separate skills.
   - Each skill gets the mode-specific workflow and constraints.
   - Shared context (CLI usage, verification) goes in each skill as needed.

8. **Remove runtime-specific content**:
   - Remove `tools`, `disallowedTools`, `model`, `permissionMode` from frontmatter.
   - Remove `skills` and `hooks` from frontmatter.
   - Convert tool restrictions to prose documentation.
   - Replace runtime-specific variables with documented inputs.

9. **Extract helper scripts** (optional):
   - If agent uses hook scripts, consider including in `scripts/`.
   - If agent references validation logic, document or include it.

10. **Validate skill structure**:
    - Frontmatter has only `name` and `description`.
    - Body has clear sections (When to Use, Inputs, Workflow, Outputs).
    - No TODO placeholders remain.
    - No runtime-specific fields in frontmatter.

11. **Report conversion result**:
    - Source agent path.
    - Generated skill path(s).
    - Key transformations applied.
    - Multi-mode handling decisions.
    - Manual review recommendations.

## Transformation Rules

| Subagent Field          | Skill Transformation                                     |
| ----------------------- | -------------------------------------------------------- |
| `name`                  | `name` in frontmatter                                    |
| `description`           | `description` expanded with usage triggers               |
| `tools`                 | Documented in workflow (which tools are used)            |
| `disallowedTools`       | Documented as constraints (read-only, no modifications)  |
| `model`                 | Noted in workflow if relevant (e.g., "use a fast model") |
| `permissionMode`        | Documented as workflow constraints                       |
| `skills`                | Referenced in "Related Skills" or workflow               |
| `hooks`                 | Documented or extracted to `scripts/`                    |
| Mode sections           | Separate skills or workflow phases                       |
| CLI command patterns    | Included in workflow steps                               |
| Verification checklists | Included in workflow or outputs                          |

## Multi-Mode Agent Handling

When an agent has multiple modes (common pattern: ask, exec, review, search):

### Option A: Separate Skills (Recommended)

Create one skill per mode:

- `agent-ask` - Read-only Q&A
- `agent-exec` - Code generation/modification
- `agent-review` - Code review
- `agent-search` - Web research

Benefits:

- Clear, focused skills.
- Appropriate constraints per skill.
- Easier to discover and use.

### Option B: Single Skill with Modes

Keep as one skill if modes are tightly coupled:

- Document mode selection in workflow.
- Include all mode workflows.
- Clearly separate mode-specific sections.

## Example Conversion

### Input: `.claude/agents/code-reviewer.md`

```yaml
---
name: code-reviewer
description: Expert code review specialist. Proactively reviews code for quality, security, and maintainability.
tools: Read, Grep, Glob, Bash
model: inherit
---

You are a senior code reviewer ensuring high standards.

When invoked:
1. Run git diff to see recent changes
2. Focus on modified files
3. Begin review immediately

Review checklist:
- Code is clear and readable
- No exposed secrets or API keys
- Proper error handling
...
```

### Output: `skills/code-reviewer/SKILL.md`

```yaml
---
name: code-reviewer
description: Expert code review specialist for quality, security, and maintainability analysis. Use when reviewing code changes, checking for security vulnerabilities, validating before commits, or assessing code quality.
---

# Code Reviewer

Perform thorough code reviews focusing on quality, security, and maintainability.

## When to Use

- Review code changes before committing.
- Check for security vulnerabilities.
- Validate code quality and best practices.
- Assess maintainability of changes.

## Inputs

- Scope of review (uncommitted changes, specific commit, PR, or files).
- Focus area (comprehensive, security-focused, performance-focused).

If scope is unclear, default to reviewing uncommitted changes with `git diff`.

## Workflow

1. **Determine scope**:
   - Run `git diff` for uncommitted changes.
   - Run `git diff HEAD~1` for last commit.
   - Run `git diff main...branch` for PR.

2. **Gather context**:
   - Check `git status` for changed files.
   - Read modified files to understand changes.
   - Identify related code and patterns.

3. **Review for issues**:
   - **Critical**: Security vulnerabilities, runtime errors, data loss risks.
   - **Important**: Logic bugs, performance problems, error handling gaps.
   - **Suggestions**: Code quality, refactoring opportunities, documentation.

4. **Document findings**:
   - Prioritize by severity (Critical → Important → Suggestions).
   - Include file path and line numbers.
   - Provide specific fix examples.

5. **Include positive observations**:
   - Note well-implemented patterns.
   - Acknowledge good practices.

## Outputs

- Review summary with issue counts by severity.
- Detailed issue list with file:line references.
- Fix suggestions with code examples.
- Positive observations for reinforcement.

## Constraints

- **Read-only**: Do not modify code, only analyze and suggest.
- **Tools used**: Read, Grep, Glob, Bash (for git commands).

## Related Skills

- `code-exec` for implementing fixes.
- `code-ask` for understanding code before review.
```

## Multi-Mode Example

### Input: Multi-mode agent with ask/exec/review/search

Create four separate skills:

1. `skills/agent-ask/SKILL.md` - Q&A mode content
2. `skills/agent-exec/SKILL.md` - Execution mode content
3. `skills/agent-review/SKILL.md` - Review mode content
4. `skills/agent-search/SKILL.md` - Search mode content

Each skill includes:

- Mode-specific description and triggers.
- Mode-specific workflow from agent prompt.
- Mode-specific constraints (read-only for ask/review/search).
- CLI command patterns for that mode.

## Key Rules

- Preserve all workflow logic and instructions.
- Remove runtime-specific frontmatter fields (tools, model, permissions, hooks).
- Keep only `name` and `description` in skill frontmatter.
- Expand descriptions to include usage triggers.
- Use imperative voice in workflow steps.
- Convert tool restrictions to documented constraints.
- Keep skills self-contained and portable.
- Split multi-mode agents into focused skills.
- Don't add extraneous documentation files (README, CHANGELOG, etc.).

## Next Steps

After conversion:

- Review generated SKILL.md for completeness.
- Verify workflow steps are clear and actionable.
- Check that constraints are documented accurately.
- Delete unused example files in `scripts/`, `references/`, `assets/`.
- Update AGENTS.md/CLAUDE.md skill inventory if applicable.
- Create symlinks for runtime integration if needed.
