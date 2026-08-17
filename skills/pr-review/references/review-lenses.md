# Review Lenses

Use this catalog to construct PR-specific review tasks. Lenses are analysis dimensions, not fixed subagent identities. Select only lenses justified by the diff and repository context.

## Baseline

Every review must cover:

- correctness and changed control flow;
- regression risk and edge cases;
- whether tests and documentation match changed behavior.

For a small change, combine these into one or two tasks. For a larger change, split them only where separate scopes or risk hypotheses improve depth.

## Conditional Lenses

### Security and authorization

Activate when the PR changes authentication, authorization, sessions, tokens, secrets, untrusted input, serialization, file handling, subprocesses, network requests, templates, queries, cryptography, permissions, CI credentials, or deployment boundaries.

Check attacker or tenant control, trust boundaries, source-to-control-to-sink flow, fail-open behavior, least privilege, sensitive-data exposure, and whether framework protections actually apply.

### Error handling and reliability

Activate for changed exceptions, result types, retries, fallbacks, defaults on failure, logging-and-continue behavior, cleanup, external I/O, async failures, or partial operations.

Look for swallowed failures, incorrect retries, hidden partial success, unsafe fallback behavior, double processing, missing cleanup, and operator-invisible failures.

### Types and invariants

Activate when public types, schemas, models, enums, validators, constructors, serialization contracts, or domain entities change.

Identify invariants, invalid states, construction and mutation boundaries, defaults, narrowing, exhaustiveness, and serialization compatibility.

### Concurrency and lifecycle

Activate for async coordination, threads, goroutines, queues, caches, shared mutable state, locks, listeners, timers, subscriptions, worker pools, or resource lifecycle changes.

Check races, deadlocks, ordering assumptions, cancellation, idempotency, leaks, stale state, cleanup, and duplicate work.

### Performance and scalability

Activate when the diff changes loops over unbounded inputs, database access, network round trips, allocation-heavy paths, caching, batching, pagination, retry behavior, startup cost, or long-lived resources.

Require a credible workload or resource impact. Do not report micro-optimizations without evidence.

### Data and migrations

Activate for schemas, migrations, persistence formats, data transforms, backfills, indexes, or compatibility between old and new readers and writers.

Check data loss, irreversible transforms, partial rollout, downgrade/rollback behavior, null/default semantics, uniqueness, transaction boundaries, and operational sequencing.

### API and compatibility

Activate for public APIs, CLI flags, configuration, environment variables, file formats, protocol behavior, action inputs/outputs, reusable workflows, package exports, or externally consumed schemas.

Check backward compatibility only where the repository or user requires it. Otherwise apply YAGNI and avoid speculative compatibility layers.

### Tests

Activate focused test review whenever behavior changes materially or the diff changes test infrastructure.

Review behavioral coverage rather than raw line coverage. Prioritize regressions in core behavior, public contracts, negative/error paths, validation boundaries, concurrency, migrations, and integration points. A test-gap finding must name the concrete regression that would escape detection.

### Documentation

Activate when public behavior, installation, configuration, commands, examples, APIs, defaults, permissions, operational steps, or release-facing behavior changes.

Report factual mismatch or materially missing user/operator guidance. Do not report prose style preferences.

### Infrastructure and supply chain

Activate for GitHub Actions, Docker, Kubernetes, Terraform, cloud IAM, build/release configuration, package metadata, dependency changes, or generated artifacts.

Check permissions, trust boundaries, pinning policy, artifact provenance, secrets exposure, deployment ordering, destructive defaults, environment assumptions, and reproducibility where relevant.

### Observability

Activate when the change introduces or alters critical operational paths, background work, retries, recovery, state transitions, or failure handling.

Check whether operators can distinguish success, failure, partial completion, and retry exhaustion. Avoid generic requests for more logging.

### Maintainability and simplification

Activate when the diff introduces material complexity, duplication, speculative abstractions, compatibility layers, extension points, or infrastructure without a current requirement.

Apply KISS, DRY, and YAGNI. Report only concrete maintainability cost tied to the changed code. Prefer the smallest coherent existing abstraction and avoid style-only simplification suggestions.

## Activation Hints

Use the changed behavior rather than filenames alone. Typical mappings include:

- auth/session/permission changes -> security, authorization, tests;
- parser/file/network/subprocess/query changes -> security, error handling;
- async/shared-state/cache changes -> concurrency, lifecycle, tests;
- schema/SQL/migration changes -> data integrity, compatibility, performance;
- public API/config/CLI changes -> compatibility, tests, documentation;
- retry/catch/fallback/default changes -> error handling, observability;
- workflow/Docker/Terraform/Kubernetes changes -> infrastructure, permissions, supply chain;
- large abstraction or framework changes -> correctness, maintainability, compatibility.

Do not launch a lens merely because it exists in this catalog. The parent must be able to state a concrete risk hypothesis for every dispatched task.
