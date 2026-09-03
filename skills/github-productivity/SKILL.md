---
name: github-productivity
description: Collect and retain GitHub organization repository/PR/review/timeline/commit data through `gh api`, with immutable run provenance and committed-state transaction semantics, for retrospective delivery-productivity analysis.
---

# GitHub Productivity

Retrospectively analyze GitHub-observable organization delivery activity. This skill currently implements **collection only**: repository/PR/review/timeline/commit data retrieval through `gh api`, with append-only raw retention, immutable run manifests, and a committed `state.json` that is the sole acceptance frontier for what counts as canonical evidence.

Normalization (actor classification, draft-lifecycle reconstruction, canonical PR snapshot-bundle selection), the organization-week metrics panel, interrupted time-series analysis, sensitivity analyses, charts, and the Markdown report are **not implemented yet**. They land in follow-up work. Do not run `aggregate`, `analyze`, or `report` subcommands — they do not exist.

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

- `--start` / `--end` accept either a date-only value (`YYYY-MM-DD`, converted to UTC midnight) or a timestamp with an explicit UTC offset. The interval is half-open `[start, end)`; `--end` must be strictly after `--start`.
- `--overlap-hours` (default `24`) is the deterministic overlap applied to discovery boundaries and watermarks.
- Exit codes: `0` success, `1` the run was incomplete (fail closed; committed state is unchanged), `2` invalid arguments — including reusing a `--workdir` for a different `--org` than it already has evidence for — `3` the workdir is already locked by another collection run.

Re-running `collect` against the same `--workdir` incrementally extends coverage. Requesting an earlier `--start` than previously covered triggers a bounded backward backfill before that range counts as covered. See [references/methodology.md](references/methodology.md) for the full transaction, discovery, and time-semantics contract.

## Workdir layout

```text
<workdir>/
├── .collect.lock          # held while a run is in progress; see methodology.md if it outlives one
├── raw/<run-id>/...       # append-only NDJSON per endpoint family
├── manifests/<run-id>.json  # finalized, immutable run provenance
└── state.json              # committed_run_id + per-repository coverage
```

`collect` is single-writer per workdir: a second concurrent `collect` invocation is rejected before it performs any live collection. Read-only consumers (once implemented) pin one committed `state.json` snapshot at start and never read a half-committed mixture of old and new coverage.

## Interpretation contract

This skill produces GitHub-observable collection data only. Anyone deriving metrics or conclusions from it — in this skill or downstream — must:

- never call merged PR count productivity by itself;
- never call queue/cycle time a quality metric;
- never call review count or comment count review precision or quality;
- never infer production defects or incidents without an explicit GitHub-observable proxy;
- never infer local AI coding-agent use (Claude Code, Codex, Cursor, or similar) from an ordinary human GitHub identity;
- distinguish descriptive observations, model-associated changes, and causal claims;
- surface missingness and coverage rather than coercing unavailable data to zero or success;
- follow pre-specified metric, model, workflow, and actor rules rather than choosing them after inspecting results.

## References

- [references/methodology.md](references/methodology.md) — the transaction model, time semantics, discovery/watermark contract, repository inclusion rules, and known limitations for the collection implemented so far.

`references/metrics.md` (exact metric formulas and the pre-specified ITS design) is deferred to the follow-up PR that implements normalization and analysis — pre-specifying metrics ahead of the aggregation code that would be checked against them is not meaningfully reviewable.
