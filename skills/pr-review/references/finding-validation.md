# Finding Validation

Discovery produces hypotheses. Validation decides whether a hypothesis is strong enough to publish.

## Validation Principles

For every deduplicated candidate:

1. Reconstruct the changed behavior at the exact reviewed head SHA.
2. Trace enough surrounding code to establish reachability and constraints.
3. Search for counterevidence before accepting the claim.
4. Distinguish a defect introduced or exposed by the PR from unrelated pre-existing behavior.
5. Confirm the claimed impact and the smallest coherent remediation.

Do not promote a finding because it matches a suspicious pattern, violates a generic best practice, or received a high discovery confidence score.

## Counterevidence Checklist

Depending on the candidate, inspect:

- upstream input validation or normalization;
- caller-side guards and authorization;
- framework guarantees such as escaping, parameterization, lifecycle, or transaction semantics;
- configuration and deployment constraints;
- existing tests that prove the disputed behavior;
- retry, timeout, cancellation, and cleanup paths;
- serialization or compatibility guarantees;
- previous implementation behavior when the candidate may be pre-existing;
- whether the alleged failing path is actually reachable from the changed code.

A validator should be rewarded for rejecting a weak candidate, not for preserving discovery output.

## Dispositions

### `confirmed`

Use when repository evidence supports the root cause, changed reachability, concrete impact, and location with high confidence.

A confirmed finding must be actionable and scoped to the PR. Prefer confidence of at least 80/100 for publication unless explicit project policy requires otherwise.

### `rejected`

Use when validation finds a mitigating control, incorrect assumption, unreachable path, pre-existing unrelated behavior, unsupported impact, duplicate root cause, or other counterevidence that makes the candidate unsuitable for review feedback.

Rejected candidates are internal only.

### `needs-human`

Use sparingly when the candidate represents a material merge risk but repository evidence cannot resolve a necessary external fact, runtime property, rollout assumption, or operational dependency.

A `needs-human` result must state one exact verification target. Do not use it as a bucket for low confidence or incomplete investigation.

## Category-Specific Gates

### Security

Confirm attacker, tenant, or cross-trust-boundary control where applicable. Trace the relevant source, validation or authorization control, and sensitive sink or protected operation. Check framework protections and deployment configuration before claiming exploitability.

Do not publish theoretical defense-in-depth concerns as vulnerabilities.

### Correctness and reliability

Identify a concrete input, state, or execution path that produces the wrong result, loses work, duplicates work, leaks a resource, hides failure, or violates an established contract.

### Tests

A missing-test finding must identify a concrete important regression enabled by the changed implementation and explain why the current suite would not detect it. Do not request tests solely because production lines changed.

### Performance

Require a credible workload, data-size, call-frequency, or resource-lifecycle condition that makes the regression material. Avoid micro-optimization and benchmark speculation.

### Compatibility

Identify the exact existing consumer contract that changes: public API, configuration, CLI, data format, protocol, workflow input/output, or documented behavior. Do not demand backward compatibility without an actual requirement.

### Documentation

Confirm a factual mismatch or materially missing guidance caused by changed public or operational behavior. Suppress wording, formatting, and stylistic preferences.

### Maintainability

Require concrete duplication, unnecessary complexity, speculative flexibility, or an abstraction/infrastructure cost introduced by the PR. Apply KISS, DRY, and YAGNI and recommend the smallest coherent correction rather than broad refactoring.

## Deduplication

Candidates share one root cause when the same changed defect explains their impact, even if multiple reviewers noticed it. Merge supporting evidence into one finding.

Keep candidates separate when independently reachable operations, contracts, or trust boundaries can fail for different reasons and require distinct fixes.

## Severity

Use severity to express impact, not reviewer confidence:

- `critical`: severe security compromise, data loss, production outage, or broken core behavior with broad impact;
- `high`: important correctness, reliability, security, compatibility, or operational defect that should normally be fixed before merge;
- `medium`: real and actionable but narrower or non-blocking defect, meaningful regression-test gap, or material documentation/maintenance issue;
- `low`: minor cleanup, style, weak speculation, or optional improvement.

Normally suppress `low`. Confidence is tracked separately.

## Final Publishability Check

A finding is publishable only when all are true:

- it is tied to the PR's changed behavior;
- the root cause is concrete;
- the impact is specific and credible;
- relevant counterevidence was checked;
- remediation is actionable and proportional;
- the location is accurate when an inline comment is planned;
- it is not already clearly covered by current review feedback;
- confidence is high enough to justify interrupting the author.
