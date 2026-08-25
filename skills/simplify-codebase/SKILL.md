---
name: simplify-codebase
description: Reduce a repository's maintenance surface across the whole codebase by applying KISS, DRY, and YAGNI while preserving required behavior. Use when asked to simplify, shrink, deduplicate, remove dead code, or refactor a repository for maintainability rather than add features.
---

# Simplify Codebase

Reduce the repository to the smallest coherent implementation that satisfies its current requirements. Minimize maintenance surface, not line count.

## Rules

- **KISS:** Prefer direct control and data flow, standard primitives, and the fewest useful layers.
- **DRY:** Consolidate duplicated knowledge or equivalent logic only when one representation is clearer.
- **YAGNI:** Remove functionality, flexibility, compatibility, configuration, or infrastructure without a current requirement.
- Simplify in this order: delete unused material, reuse existing code, inline needless indirection, consolidate equivalent paths, then extract an abstraction only for stable repeated knowledge.
- Preserve required behavior, repository conventions, and identified external contracts. Absence of in-repository callers is not enough to remove a public API, CLI/configuration contract, data format, migration requirement, or supported platform.
- Do not add features, dependencies, tools, speculative abstractions, or unrelated cleanup to accomplish the simplification.
- Do not modify generated or vendored outputs directly, delete tests merely to reduce size, or replace clear repetition with a harder abstraction.
- Preserve unrelated user changes; stop if the work cannot be isolated safely.

## Workflow

1. **Establish the baseline.** Read repository guidance, architecture/usage documentation, manifests, build configuration, and CI. Check the worktree, identify normal validation commands, and record compatibility or user constraints.
2. **Scan the whole repository.** Exclude generated, vendored, cache, and build-output trees. Find dead code/files/dependencies/configuration, duplicated logic or declarations, pass-through wrappers and unnecessary layers, speculative abstractions, obsolete compatibility paths, and redundant tests or documentation.
3. **Prove removal candidates.** Search source, tests, documentation, scripts, CI, packaging, configuration, and entry points. Account for dynamic loading, reflection, plugin discovery, command names, serialized formats, environment variables, and external APIs. Keep uncertain contracts unless breaking them is explicitly allowed.
4. **Implement high-confidence simplifications** using the order above. Prefer deletion and consolidation over broad rewrites or syntax compression.
5. **Verify coherent batches.** Run the narrowest relevant checks while editing, then the repository's normal tests, lint, type checks, builds, or equivalent validation for the changed areas. Distinguish pre-existing failures from regressions.
6. **Review the final diff.** Confirm required behavior and contracts remain intact, maintenance surface is net smaller, and tests/documentation still match the implementation.

## Output

Report the main deletions and consolidations, preserved contracts, verification results, and any valuable candidates left unchanged because safe removal could not be proven.
