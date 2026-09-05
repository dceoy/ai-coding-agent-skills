# Finding Validation

Discovery proposes hypotheses; validation tries to disprove them before publication.

## Core rule

For each deduplicated candidate, reconstruct the changed behavior on the frozen snapshot, inspect only the surrounding code needed to establish reachability and constraints, search for counterevidence, and decide whether the claimed changed defect and impact are real.

Do not promote a finding because it matches a suspicious pattern, violates a generic best practice, or has high discovery confidence.

## Counterevidence

Check only what is relevant to the candidate, such as upstream validation, caller guards or authorization, framework guarantees, configuration, tests, retry/cleanup behavior, serialization contracts, prior behavior, or whether the alleged path is actually reachable.

A validator should be willing to reject a discovery finding.

## Dispositions

- `confirmed`: repository evidence supports a concrete PR-scoped root cause and credible impact with high confidence.
- `rejected`: a control, incorrect assumption, unreachable path, duplicate root cause, pre-existing unrelated behavior, or unsupported impact makes the candidate unsuitable for publication.
- `needs-human`: use sparingly when a material merge risk depends on one external fact the repository cannot resolve; name exactly what a human must verify.

## Publication gates

Apply the gate that matches the claim:

- security: establish the relevant trust-boundary/source-control-sink path and account for framework protections;
- correctness/reliability: identify a concrete input, state, or execution path that produces wrong behavior, loss, duplication, leak, or hidden failure;
- tests: name the important regression the current suite would fail to detect;
- performance: identify a credible workload, scale, call-frequency, or lifecycle condition with material impact;
- compatibility/docs: identify the concrete changed external contract or factual guidance mismatch;
- maintainability: require concrete complexity, duplication, or speculative flexibility introduced by the PR and keep remediation minimal under KISS/DRY/YAGNI.

## Deduplication and priority

Merge candidates when one changed root cause explains them. Keep separate failures only when independently reachable behavior or contracts require distinct fixes.

Severity expresses impact, not confidence: `critical`, `high`, `medium`, `low`. Normally suppress `low` findings.

A finding is publishable only when it is tied to changed behavior, has a concrete root cause and credible impact, survives relevant counterevidence, has proportional remediation, is accurately located when inline, is not already clearly covered by current feedback, and is strong enough to justify interrupting the author.
