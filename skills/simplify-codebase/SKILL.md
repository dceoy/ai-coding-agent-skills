---
name: simplify-codebase
description: Reduce a repository's maintenance surface across the whole codebase with KISS, DRY, and YAGNI while preserving required behavior. Use when asked to simplify, shrink, deduplicate, remove dead code, or refactor for maintainability, and proactively when the agent identifies clear, material simplification opportunities.
---

# Simplify Codebase

Reduce the repository to the smallest clear implementation that satisfies current requirements. Minimize maintenance surface, not line count.

## Rules

- Preserve required behavior, outputs, repository standards, and identified external contracts. No in-repository caller is not enough to remove a public API, CLI/configuration contract, data format, migration requirement, or supported platform.
- **KISS:** Prefer readable, explicit control and data flow, standard primitives, and the fewest useful layers over clever or dense code.
- **DRY:** Consolidate duplicated knowledge or equivalent logic only when one representation is clearer; do not merge distinct concerns or remove useful abstractions merely to reduce repetition.
- **YAGNI:** Remove functionality, flexibility, compatibility, configuration, or infrastructure without a current requirement.
- Simplify in this order: delete unused material, reuse existing code, inline needless indirection, consolidate equivalent paths, then abstract only stable repeated knowledge.
- Reduce unnecessary nesting, pass-through wrappers, redundant abstractions, weak naming, and comments that only restate obvious code when doing so improves clarity.
- Invoke proactively when high-confidence simplification would materially improve maintainability, but keep the scope proportional and do not displace the user's primary task with unrelated cleanup.
- Do not add features, dependencies, tools, speculative abstractions, or unrelated cleanup. Do not edit generated/vendor outputs directly or delete behavioral tests merely to shrink the repository.
- Preserve unrelated user changes; stop if the work cannot be isolated safely.

## Workflow

1. Read repository guidance, usage/architecture documentation, manifests, build configuration, and CI; check the worktree, normal validation commands, and compatibility constraints.
2. Scan the whole repository, excluding generated, vendored, cache, and build-output trees, for dead material, duplicated logic/declarations, needless indirection, speculative abstractions, obsolete compatibility paths, and redundant tests or documentation.
3. Prove removals by searching source, tests, docs, scripts, CI, packaging, configuration, and entry points; account for dynamic loading, reflection, plugin discovery, command names, serialized formats, environment variables, and external APIs. Keep uncertain contracts unless breaking them is explicitly allowed.
4. Apply only high-confidence simplifications using the order above. Prefer clear deletion or consolidation over broad rewrites or syntax compression; update documentation only when behavior, usage, configuration, or the source of truth changes.
5. Run focused checks while editing, then the repository's normal relevant tests, lint, type checks, builds, or equivalent validation. Review the final diff for preserved behavior/contracts, clearer code, and a net-smaller maintenance surface.

## Output

Report significant deletions/consolidations, preserved contracts, verification results, and valuable candidates left unchanged because safe removal could not be proven.
