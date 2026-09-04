---
name: github-productivity
description: Collect, retain, normalize, and analyze GitHub organization repository/PR/review/timeline/commit data through `gh api` into an organization-week delivery panel with a pre-specified interrupted time-series model, required sensitivities, fixed charts, and a Markdown report.
---

# GitHub Productivity

Retrospectively analyze GitHub-observable organization delivery activity.

- `collect` — repository/PR/review/timeline/commit retrieval through `gh api`, with append-only raw retention, immutable run manifests, and a committed `state.json` that is the sole acceptance frontier for what counts as canonical evidence.
- `normalize` — deterministic derivation of canonical entities from the committed run lineage: newest-committed PR snapshot-bundle selection (whole-bundle replacement, never child-row union), actor classification, draft-lifecycle reconstruction, and an idempotent, filesystem-order-independent tree under `<workdir>/normalized/`.
- `aggregate` — builds a continuous UTC-ISO-week organization-week panel (delivery, review-flow, review-burden, rework, size, and composition metrics) from normalized entities, applying the `[--start, --end)` window and the `as_of` data cutoff.
- `analyze` — fits the pre-specified interrupted time-series (ITS) model for the fixed eligible-metric list, when `--intervention-at` and the metric-specific 12-week/full-rank guard are satisfied, plus the four required sensitivity analyses (window, stable cohort, leave-one-repository-out, actor).
- `report` — writes the fixed chart set (`delivery.svg`, `review.svg`, `rework.svg`) and `report.md`, separating observed metrics, coverage, modeled changes, sensitivities, interpretation, and limitations.

Optional GitHub Actions CI metrics are **not implemented**: they require extending `collect` to fetch selected workflow runs, which is out of scope here (see [references/metrics.md](references/metrics.md)).

## Prerequisites

- `gh` authenticated with read access to the target organization's repositories.
- Python 3.11+ available through `uv` (this repository's standard toolchain).

## Usage

```bash
uv run skills/github-productivity/scripts/productivity.py collect \
  --org <organization-login> \
  --workdir <path-to-workdir> \
  --start 2026-01-01 \
  --end 2026-07-01 \
  --overlap-hours 24
```

- `--start` / `--end` accept either a date-only value (`YYYY-MM-DD`, converted to UTC midnight) or a timestamp with an explicit UTC offset. The requested interval is half-open `[start, end)`; `--end` must be strictly after `--start`. `--start` bounds how far back discovery/backfill looks; `--end` is validated and recorded as provenance for the follow-up derivation work, but does **not** stop `collect` from fetching evidence past it — collection always discovers through "now" so a later re-run with a later `--end` never needs to recollect. Event-level filtering by `end` happens at derivation time (not yet implemented — see the top of this document); see [Observation-range semantics](references/methodology.md#observation-range-semantics).
- `--overlap-hours` (default `24`, must be non-negative) is the deterministic overlap applied to discovery boundaries and watermarks.
- Exit codes: `0` success, `1` the run was incomplete (fail closed; committed state is unchanged), `2` invalid arguments — including a negative `--overlap-hours` or reusing a `--workdir` for a different `--org` than it already has evidence for — `3` the workdir is already locked by another collection run, including by a since-killed process (see [Known limitations](references/methodology.md#known-limitations) for recovery).

Re-running `collect` against the same `--workdir` incrementally extends coverage. Requesting an earlier `--start` than previously covered triggers a bounded backward backfill before that range counts as covered. See [references/methodology.md](references/methodology.md) for the full transaction, discovery, and time-semantics contract.

```bash
uv run skills/github-productivity/scripts/productivity.py normalize \
  --workdir <path-to-workdir> \
  --actor-map <path-to-actor-map.json> \
  --force
```

- `normalize` reads exactly one pinned `state.json` snapshot and the committed run lineage it points to, then writes deterministic entities to `<workdir>/normalized/`. It performs no GitHub access and takes no collection lock, so it is safe to run while a `collect` is in progress.
- `--actor-map` (optional) is a JSON file `{"explicit_ai_agents": [{"actor_id": 123}, {"login": "some-agent[bot]"}]}` mapping identities to the `explicit-ai-agent` class. It is **derivation-only**: changing it re-normalizes retained raw data without recollecting GitHub history, and its fingerprint is recorded in `normalized/derivation.json`.
- `--force` regenerates even when `normalized/` is already current for the committed run and actor-map fingerprint; without it an already-current tree is left untouched.
- Exit codes: `0` success, `2` invalid arguments, `4` derivation failed (nothing committed to normalize, an unreadable or malformed `--actor-map`, or a broken committed lineage).

```bash
uv run skills/github-productivity/scripts/productivity.py aggregate \
  --workdir <path-to-workdir> \
  --start 2026-01-01 \
  --end 2026-07-01 \
  --overlap-hours 24
```

- `aggregate` reads normalized entities and writes `<workdir>/report/organization-week.csv` plus a `organization-week.meta.json` sidecar (the window `analyze`/`report` reuse). It fails closed (exit `4`) if committed historical coverage does not reach `--start - --overlap-hours` for any in-scope repository — run `collect` with an earlier `--start` first.
- `--include-forks` adds forked repositories to the primary cohort (excluded by default).
- See [references/metrics.md](references/metrics.md) for the exact metric formulas, denominators, and missingness rules.

```bash
uv run skills/github-productivity/scripts/productivity.py analyze \
  --workdir <path-to-workdir> \
  --intervention-at 2026-04-06
```

- `analyze` rebuilds the panel from entities, fits the pre-specified ITS model for each eligible metric (skipped with an explicit reason when the 12-complete-week or full-rank guard fails), and runs the four required sensitivities. Omitting `--intervention-at` produces a descriptive-only `analysis.json` with no fitted models. Output: `<workdir>/report/analysis.json`.

```bash
uv run skills/github-productivity/scripts/productivity.py report \
  --workdir <path-to-workdir>
```

- `report` writes `<workdir>/report/{delivery,review,rework}.svg` and `report.md`. Deterministic: identical committed input produces byte-identical output.
- Exit codes for `aggregate`/`analyze`/`report`: `0` success, `2` invalid arguments, `4` derivation failed (required upstream output missing, or coverage/window validation failed).

## Workdir layout

```text
<workdir>/
├── .collect.lock          # held while a run is in progress; see methodology.md if it outlives one
├── organization.json      # immutable org binding, written before the first live API call
├── raw/<run-id>/...       # append-only NDJSON per endpoint family
├── manifests/<run-id>.json  # finalized, immutable run provenance
├── state.json              # committed_run_id + per-repository coverage
├── normalized/             # deterministic entities from the committed lineage
│   ├── repositories.ndjson
│   ├── pull_requests.ndjson
│   ├── reviews.ndjson
│   ├── pr_commits.ndjson
│   ├── timeline_events.ndjson
│   ├── draft_lifecycle.ndjson
│   ├── actors.ndjson
│   └── derivation.json      # written last; records what the tree was derived from
└── report/                  # aggregate/analyze/report output
    ├── organization-week.csv
    ├── organization-week.meta.json
    ├── analysis.json
    ├── report.md
    ├── delivery.svg
    ├── review.svg
    └── rework.svg
```

`collect` is single-writer per workdir: a second concurrent `collect` invocation is rejected before it performs any live collection. `normalize` is a lock-free reader: it pins one committed `state.json` snapshot at start and never reads a half-committed mixture of old and new coverage. `derivation.json` is written last, so a crash mid-regeneration leaves a mismatched fingerprint that the next `normalize` fully rewrites.

## Interpretation contract

This skill produces GitHub-observable collection and normalized-entity data only. Anyone deriving metrics or conclusions from it — in this skill or downstream — must:

- never call merged PR count productivity by itself;
- never call queue/cycle time a quality metric;
- never call review count or comment count review precision or quality;
- never infer production defects or incidents without an explicit GitHub-observable proxy;
- never infer local AI coding-agent use (Claude Code, Codex, Cursor, or similar) from an ordinary human GitHub identity;
- distinguish descriptive observations, model-associated changes, and causal claims;
- surface missingness and coverage rather than coercing unavailable data to zero or success;
- follow pre-specified metric, model, workflow, and actor rules rather than choosing them after inspecting results.

## References

- [references/methodology.md](references/methodology.md) — the transaction model, time semantics, discovery/watermark contract, repository inclusion rules, and the normalization contract.
- [references/metrics.md](references/metrics.md) — exact organization-week metric formulas, denominators, missingness rules, the pre-specified ITS-eligible outcome list, the ITS design, and the four required sensitivity analyses.
