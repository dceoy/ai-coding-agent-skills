---
name: code-simplifier
description: Simplifies and refines code for clarity, consistency, and maintainability while preserving all functionality. Use proactively after code changes and focus on recently modified code unless instructed otherwise.
---

# Code Simplifier

Simplify and refine code for clarity, consistency, and maintainability while preserving exact functionality.

## When to Use

- After writing or modifying code to ensure it meets quality standards.
- When code has become complex or hard to read.
- To apply project-specific coding standards consistently.
- When refactoring for maintainability without changing behavior.
- To reduce unnecessary complexity and nesting in existing code.

## Inputs

- Scope of code to simplify (recently modified files, specific files, or broader codebase).
- Project coding standards from CLAUDE.md, AGENTS.md, or similar files if available.

If scope is unclear, default to recently modified code using `git diff` or `git status`.

## Workflow

1. **Identify target code**:
   - Run `git status` and `git diff` to find recently modified files.
   - Focus on files changed in the current session unless instructed otherwise.

2. **Read project standards**:
   - Check CLAUDE.md, AGENTS.md, or similar for coding conventions.
   - Note language-specific patterns such as module style, import ordering, function syntax, type annotations, component patterns, error handling, and naming conventions.

3. **Analyze for simplification opportunities**:
   - Unnecessary complexity and deep nesting.
   - Redundant code and over-abstraction.
   - Unclear variable and function names.
   - Scattered related logic that could be consolidated.
   - Unnecessary comments describing obvious code.
   - Nested ternary operators (prefer switch/if-else).
   - Overly compact code sacrificing readability.

4. **Apply refinements** while preserving functionality:
   - **Preserve Functionality**: Never change what the code does, only how it does it.
   - **Apply Project Standards**: Follow established coding conventions.
   - **Enhance Clarity**: Simplify structure, improve naming, consolidate logic.
   - **Maintain Balance**: Avoid over-simplification that reduces maintainability.
   - **Respect Scope**: Refine only recently modified or explicitly requested code.

5. **Verify changes**:
   - Ensure all original features, outputs, and behaviors remain intact.
   - Confirm refined code is simpler and more maintainable.
   - Run tests if available to validate functionality is preserved.
   - If tests are expensive or unavailable, use focused static checks or explain what could not be verified.

6. **Document significant changes**:
   - Note only changes that affect understanding.
   - Skip obvious or trivial refinements.

## Guidelines

### Preserve Functionality

- Never change what the code does, only how it does it.
- All original features, outputs, and behaviors must remain intact.

### Enhance Clarity

- Reduce unnecessary complexity and nesting.
- Eliminate redundant code and abstractions.
- Improve readability through clear naming.
- Consolidate related logic.
- Remove unnecessary comments describing obvious code.
- Avoid nested ternary operators - prefer switch or if/else for multiple conditions.
- Choose clarity over brevity - explicit code is often better than compact code.
- Keep helpful abstractions that express domain concepts or reduce duplicated logic.

### Maintain Balance

Avoid over-simplification that could:

- Reduce code clarity or maintainability.
- Create overly clever solutions that are hard to understand.
- Combine too many concerns into single functions or components.
- Remove helpful abstractions that improve organization.
- Prioritize "fewer lines" over readability.
- Make the code harder to debug or extend.
- Drift into unrelated style rewrites outside the requested scope.

## Outputs

- Simplified code with preserved functionality.
- Summary of significant changes made.
- Notes on applied coding standards.

## Constraints

- **Functionality-preserving**: All original behavior must remain unchanged.
- **Scope-limited**: Focus on recently modified code unless explicitly directed otherwise.
- **Balance-aware**: Prefer readable, explicit code over overly compact solutions.
- **Autonomous but bounded**: Improve code when it is already in scope, but do not start broad refactors without direction.
