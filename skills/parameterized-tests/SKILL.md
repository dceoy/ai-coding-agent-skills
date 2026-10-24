---
name: parameterized-tests
description: Enforce native parameterized or table-driven tests when adding or modifying unit tests that exercise the same behavior with multiple data cases. Use whenever unit tests add repeated cases, edge-case matrices, or duplicated setup, execution, and assertions that differ only by case data.
---

# Parameterized Tests

Use data-driven tests whenever multiple unit-test cases exercise the same behavior with the same test logic.

## Core Rule

When adding or modifying unit tests, if two or more cases share the same setup, execution, and assertion semantics and differ only in inputs, expected outputs, expected errors, options, or equivalent case data, express them with the test framework's native parameterization mechanism.

If a new case would duplicate an existing standalone test with the same test logic, consolidate the touched group instead of adding another duplicated test.

## Workflow

1. Inspect nearby tests and repository guidance to identify the testing framework and established idioms.
2. Identify cases that share setup, execution, and assertion semantics.
3. Parameterize groups of two or more equivalent cases with the framework's native mechanism.
4. Keep each case independently identifiable in test output when the framework supports case names or IDs.
5. Prefer explicit case data over branching inside the shared test body.
6. Run the narrowest relevant test command after the change.

See [references/frameworks.md](./references/frameworks.md) for common framework idioms.

## Parameterize

Parameterize when cases differ only by data such as:

- Inputs or arguments.
- Expected return values.
- Expected errors or exception values when the assertion structure remains the same.
- Flags, options, environment values, or fixtures used uniformly by every case.
- Boundary, validation, or normalization examples that exercise the same behavior.

## Keep Separate

Keep tests separate when parameterization would require materially different:

- Setup or teardown.
- Execution paths or side effects.
- Assertion semantics.
- Behavior boundaries whose separation improves intent, such as success and failure behavior with different assertions.

Do not parameterize merely to reduce line count. If the shared test body needs case-specific `if`, `switch`, or equivalent branching to express substantially different behavior, separate tests are usually clearer.

## Constraints

- Prefer the framework's native parameterization or the language's established table-driven idiom over custom loops or helper abstractions.
- Do not add a testing dependency solely to obtain parameterization.
- Do not introduce a custom parameterization abstraction when the repository or framework already has an idiomatic mechanism.
- Preserve repository-specific conventions when they are stricter than this skill.
- Use descriptive case IDs or names when raw parameter values do not make failures obvious.
- Keep case tables focused; split unrelated behaviors into separate parameterized tests rather than building one universal matrix.
