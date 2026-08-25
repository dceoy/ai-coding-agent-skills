---
name: simplify-codebase
description: Reduce a repository's maintenance surface across the whole codebase by applying KISS, DRY, and YAGNI while preserving required behavior. Use when asked to simplify, shrink, deduplicate, remove dead code, or refactor a repository for maintainability rather than add features.
---

# Simplify Codebase

Reduce the repository to the smallest coherent implementation that satisfies its current requirements. Prefer deleting code over replacing it with new infrastructure.

## Priorities

Apply these priorities in order:

1. Preserve required behavior, public contracts, and repository conventions.
2. Delete code, configuration, dependencies, and documentation that have no current use.
3. Reuse one existing implementation instead of maintaining equivalent implementations.
4. Inline or collapse indirection that has only one meaningful caller, implementation, or use case.
5. Keep or introduce an abstraction only when it represents stable repeated knowledge and materially reduces maintenance cost.
6. Keep tests and documentation aligned with the simplified implementation.

Do not optimize for line count alone. A shorter implementation that is harder to understand or verify is not a simplification.

## KISS, DRY, and YAGNI

- **KISS:** Prefer direct control flow, explicit data flow, standard library or framework primitives, and the fewest layers needed to express the behavior clearly.
- **DRY:** Remove duplicated knowledge and equivalent logic when one shared representation is clearer. Do not force superficially similar but semantically different code through one abstraction.
- **YAGNI:** Remove speculative flexibility, compatibility layers, extension points, feature flags, configuration, or infrastructure that serve no current requirement.

When the principles conflict, prefer the option with the smaller long-term maintenance surface rather than the smallest immediate diff.

## Workflow

1. **Establish the baseline.** Read repository guidance, architecture and usage documentation, dependency manifests, build configuration, and CI. Check the worktree before editing, identify the supported build/test/lint commands, and record any user constraints or required compatibility boundaries.
2. **Scan the whole repository.** Exclude generated, vendored, cache, and build-output trees unless their source definition requires a change. Look for:
   - unreachable or unused code, files, dependencies, scripts, configuration, environment variables, flags, and workflow steps;
   - duplicate implementations, constants, schemas, configuration, validation, parsing, or dependency declarations;
   - pass-through wrappers, one-use helpers, single-implementation interfaces, redundant adapters, and unnecessary layering;
   - generic frameworks or abstractions built for only one current use case;
   - obsolete compatibility shims, migration paths, fallbacks, feature flags, and deprecated aliases that are no longer required;
   - redundant tests or fixtures that can be consolidated without reducing behavioral coverage;
   - comments and documentation that describe paths being removed or duplicate a single authoritative source.
3. **Prove candidates before deleting them.** Search references across source, tests, documentation, scripts, CI, packaging, configuration, and entry points. Account for dynamic loading, reflection, plugin discovery, command names, serialized formats, environment variables, and externally consumed APIs. Treat uncertain external usage as a reason to keep the contract unless the user explicitly allows breaking it.
4. **Rank simplifications by value and risk.** Prefer high-confidence deletion and consolidation over broad rewrites. Reject changes that merely compress syntax, hide behavior behind metaprogramming, or add a new abstraction to remove a small amount of duplication.
5. **Implement in this order:** delete unused material; reuse an existing primitive; inline needless indirection; merge equivalent paths or representations; extract a shared abstraction only for stable, meaningful duplication that remains.
6. **Verify each coherent batch.** Run the narrowest relevant checks while editing, then the repository's normal test, lint, type-check, build, or validation commands appropriate to the changed areas. Distinguish pre-existing failures from regressions introduced by the simplification.
7. **Review the final diff.** Confirm that required behavior is preserved, the maintenance surface is net smaller, tests were not removed merely to reduce size, and no replacement machinery cancels out the simplification. Update documentation only where behavior, usage, configuration, or the source of truth changed.

For a large repository, scan independent areas in parallel when the active runtime provides safe read-only subagents, but keep candidate deduplication, implementation decisions, edits, and verification under the top-level agent. Parallelism is optional; repository-wide coverage is not.

## Constraints

- Do not add features, speculative generality, or unrelated cleanup.
- Do not add a dependency or tool solely to perform the simplification.
- Do not preserve backward compatibility unless the repository, user, or an identified external contract requires it.
- Do not remove a public API, data format, CLI/configuration contract, migration requirement, or supported platform based only on an absence of in-repository callers.
- Do not modify generated or vendored outputs directly when their source can be changed instead.
- Do not delete tests solely to make the repository smaller; consolidate genuinely duplicated tests only when behavioral coverage and failure clarity remain equivalent.
- Do not replace clear repeated code with a harder-to-understand abstraction solely to satisfy DRY.
- Preserve unrelated user changes and stop rather than mixing them into the refactor when the repository state makes safe isolation impossible.

## Output

Report:

- the main deletion and consolidation decisions;
- required behavior or contracts intentionally preserved;
- verification commands and results;
- remaining high-value candidates that were left unchanged because their usage or compatibility requirements could not be proven safely.
