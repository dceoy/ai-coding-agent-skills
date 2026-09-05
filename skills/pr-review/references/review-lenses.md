# Review Lenses

Lenses are analysis dimensions, not fixed reviewer identities. Select only what the changed behavior justifies, and require a concrete risk hypothesis for every dispatched task.

## Baseline

For an unscoped review, cover correctness and regression risk. Include tests and documentation when the changed behavior makes them relevant. A small change may combine baseline coverage into one task.

An explicit user scope overrides this baseline; do not dispatch or publish outside it.

## Conditional lenses

Activate only when the diff provides evidence for the corresponding risk:

- security / trust boundaries: authentication, authorization, secrets, untrusted input, serialization, file/process/network access, permissions, or CI/deployment credentials;
- reliability / I/O: exceptions, retries, fallbacks, cleanup, partial operations, external services, async failures, or operator-visible failure state;
- data / migrations: schemas, persistence formats, backfills, indexes, transactions, rollout/rollback, or old/new reader-writer compatibility;
- concurrency / lifecycle: shared state, queues, caches, locks, listeners, timers, cancellation, idempotency, leaks, or ordering assumptions;
- API / compatibility: public APIs, CLI flags, configuration, environment variables, file/protocol formats, workflow inputs/outputs, or externally consumed schemas;
- performance: unbounded loops, database/network round trips, batching, allocation-heavy paths, caching, pagination, startup cost, or long-lived resources;
- infrastructure / supply chain: GitHub Actions, containers, IaC, cloud IAM, dependencies, build/release configuration, artifact provenance, or deployment ordering;
- observability: critical background work, retries, recovery, state transitions, or failure paths where operators must distinguish success, failure, or partial completion;
- comments / documentation: changed behavior makes comments, examples, defaults, commands, APIs, permissions, or operational guidance materially false or incomplete;
- maintainability / simplification: changed code introduces concrete duplication, unnecessary complexity, speculative abstractions, redundant logic, or extension points without a current requirement.

For security, test-gap, performance, compatibility, documentation, and maintainability findings, apply the publication gates in `finding-validation.md` rather than expanding the discovery prompt with generic checklists.

## Selection rule

Use changed behavior rather than filenames alone. Prefer fewer broad-but-coherent tasks over one task per lens. Split only when distinct scopes or risk hypotheses benefit from independent analysis, and add another task later only when evidence reveals a previously hidden material boundary.
