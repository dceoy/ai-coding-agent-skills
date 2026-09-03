# Metrics, panel, and ITS design

This document pre-specifies every organization-week metric, the ITS-eligible
outcome list, and the statistical design **before** `aggregate`/`analyze`
inspect any data. `aggregate`/`analyze`/`report` implement exactly this
document; they do not choose metrics, models, denominators, or weights after
seeing results.

## Inputs

`aggregate` reads `<workdir>/normalized/*.ndjson` (written by `normalize`;
see [methodology.md](methodology.md)) and `<workdir>/normalized/derivation.json`
for `as_of`. It applies the requested `[--start, --end)` window and the
fork/cohort filters described below to build one **organization-week panel**:
one row per continuous UTC ISO week (Monday 00:00 UTC) in range.

`effective_observation_end = min(requested_end, derivation.json["as_of"])`.

A week is **complete** (`complete_week: true`) iff its whole half-open
`[week_start, week_end)` interval is inside `[requested_start, requested_end)`
and `week_end <= effective_observation_end`. Partial-boundary weeks, the
in-progress current week, and any week not fully covered by `as_of` are
descriptive-only: retained in `organization-week.csv` but excluded from
primary ITS and the symmetric-window sensitivities.

## Cohort

- Primary repository cohort: repositories with `fork == false` (`--include-forks`
  adds forked repositories back in as an explicit sensitivity/override).
- Primary author set for delivery/composition metrics: `human + explicit-ai-agent`.
- Human-review metrics use only `reviewer_classification == "human"` and
  `independent == true` (excludes an author's own review of their own PR,
  already computed by `normalize`).
- A PR qualifies for merged-PR metrics ("qualifying merged PR") when its
  repository is in the cohort, `merged_at` is non-null and falls in
  `[requested_start, effective_observation_end)`, and `author_classification`
  is `human` or `explicit-ai-agent`.

## Missingness conventions

- Count metrics (composition/scale, `opened_prs`, `merged_prs`, actor-class
  counts): zero-filled for weeks with no qualifying events.
- Rate/median metrics: `NA` when their denominator is zero or the underlying
  data is unavailable (never coerced to `0`).
- Every rate/median column has a companion `<metric>_n` (or documented
  coverage) column recording its denominator.

## Organization-week metrics

### Scale / composition diagnostics (descriptive only, never modeled)

| Metric                             | Definition                                                                                         |
| ---------------------------------- | -------------------------------------------------------------------------------------------------- |
| `active_repositories`              | Count of distinct `repository_id` with >=1 qualifying PR-authorship or merge event that week.      |
| `active_pr_authors`                | Count of distinct authors (`human`/`explicit-ai-agent`) with >=1 PR opened that week.              |
| `active_human_reviewers`           | Count of distinct `human`, `independent: true` reviewers with >=1 submitted review that week.      |
| `opened_prs`                       | Count of cohort PRs with `created_at` in week, author in `human + explicit-ai-agent`.              |
| `opened_prs_by_<class>` / `_share` | Count and share of opened PRs by each of `human`/`bot`/`explicit-ai-agent`/`unknown` author class. |
| `reviews_by_<class>` / `_share`    | Count and share of submitted reviews by each actor class.                                          |

These are workload/composition diagnostics, not productivity outcomes, and are
never fit with ITS.

### Delivery and size

| Metric                  | Definition                                                                                                                                                       | ITS-eligible    |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| `merged_prs`            | Count of qualifying merged PRs, assigned to the `merged_at` week.                                                                                                | yes             |
| `median_queue_to_merge` | Median hours from `first_queue_entry` (draft-lifecycle) to `merged_at`, over qualifying merged PRs with `queue_entry_available == true`. `NA` if none that week. | yes             |
| `median_changed_files`  | Median `changed_files` over qualifying merged PRs. `NA` if none.                                                                                                 | no (diagnostic) |
| `median_changed_lines`  | Median (`additions + deletions`) over qualifying merged PRs. `NA` if none.                                                                                       | no (diagnostic) |

`median_queue_to_merge` is queue-based, not creation-to-merge; PRs without a
reconstructed queue entry are excluded and counted in
`median_queue_to_merge_n` / total qualifying merged PRs as coverage.

### Review flow / burden (all ITS-eligible)

Let a qualifying merged PR's **first qualifying human review** be the
earliest `human`, `independent: true` review with
`submitted_at >= first_queue_entry` and `submitted_at <= merged_at` (requires
`queue_entry_available == true`; otherwise the PR has no first qualifying
human review for these metrics and is excluded, counted in coverage).

| Metric                               | Definition                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `human_review_coverage_rate`         | (qualifying merged PRs with >=1 independent human review `submitted_at <= merged_at`) / (qualifying merged PRs). `NA` if denominator 0.                                                                                                                                                                                                                                                                  |
| `median_time_to_first_human_review`  | Median hours from `first_queue_entry` to the first qualifying human review's `submitted_at`, over PRs with one. `NA` if none.                                                                                                                                                                                                                                                                            |
| `median_first_human_review_to_merge` | Median hours from that same first qualifying human review's `submitted_at` to `merged_at`. `NA` if none.                                                                                                                                                                                                                                                                                                 |
| `human_review_events_per_merged_pr`  | (independent human review submissions with `submitted_at <= merged_at`, across qualifying merged PRs) / (qualifying merged PRs). `NA` if denominator 0.                                                                                                                                                                                                                                                  |
| `changes_requested_rate`             | (human-reviewed qualifying merged PRs with >=1 reconstructed pre-merge independent human `CHANGES_REQUESTED` state) / (human-reviewed qualifying merged PRs with deterministically available historical review state). PRs whose dismissal history cannot be reconstructed are excluded from both numerator and denominator and counted in `changes_requested_rate_unavailable_n`, never treated as `0`. |

`changes_requested_rate`'s pre-merge state reconstruction: for each formal
review, replay `review_dismissed` timeline events carrying
`payload.dismissed_review.review_id == review_id`; the pre-dismissal state is
`payload.dismissed_review.state`. A review with no matching dismissal event
keeps its recorded `state`. If a review is dismissed and no
`dismissed_review.state` is present, that PR's historical state is
unavailable.

### Pre-merge rework (ITS-eligible)

| Metric                       | Definition                                                                                                                                                                                                                                                           |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `post_review_commits_per_pr` | Median, over qualifying merged PRs where the first qualifying human review's `commit_id` is locatable in that PR's ordered, `available: true` commit list, of the count of commits at a later `position` than the reviewed commit. `NA` if none available that week. |

A PR is **unavailable** for this metric (excluded from numerator/denominator,
counted in `post_review_commits_per_pr_unavailable_n`) when: it has no first
qualifying human review, its commits are `available: false` (>250-commit
endpoint cap), or the reviewed `commit_id` is not present in the PR's current
commit list (force-push/rebase). Never substituted with a timestamp
heuristic.

## Pre-specified ITS-eligible outcome metrics (fixed, exact)

```text
merged_prs
median_queue_to_merge
human_review_coverage_rate
median_time_to_first_human_review
median_first_human_review_to_merge
human_review_events_per_merged_pr
changes_requested_rate
post_review_commits_per_pr
```

No other metric is ever fit with ITS. `median_changed_files`,
`median_changed_lines`, and every composition/scale diagnostic are always
descriptive-only.

## Interrupted time-series (ITS) design

One segmented, unweighted OLS per eligible metric:

```text
y_t = β0 + β1*time_t + β2*post_t + β3*time_after_t + ε_t
```

- `time_t`: integer calendar-week offset from the first regression-eligible
  (complete, non-partial-boundary) ISO week. Fixed once; never renumbered
  after dropping a metric's `NA` rows.
- `p`: the `time_t` index of `first_complete_post_week`. If
  `--intervention-at` is exactly Monday 00:00 UTC, that week is
  `first_complete_post_week`. Otherwise the containing ISO week is partially
  exposed — excluded from regression and symmetric-window sensitivities,
  retained only in the descriptive panel — and `first_complete_post_week` is
  the next full ISO week.
- `post_t = 1` if `time_t >= p` else `0`.
- `time_after_t = max(0, time_t - p)`.
- Fit via `statsmodels.api.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 4, "use_correction": True})`
  over that metric's own ordered non-missing weekly rows (NA rows dropped
  before fitting). The HAC lag is fixed at `4` **observed weekly rows**, not
  necessarily 4 elapsed calendar weeks, when missing rows create gaps.
- Report `β1`, `β2`, `β3`, their 95% confidence intervals
  (`fit.conf_int(alpha=0.05)`), complete pre/post calendar-week counts, the
  metric's non-missing week count, and denominator/coverage diagnostics.

### Execution guard (per metric)

Fit a metric only when, after excluding partial-boundary/intervention weeks:

- > =12 non-missing complete weeks before `p` (`time_t < p`);
- > =12 non-missing complete weeks at/after `p` (`time_t >= p`); and
- the design matrix `[1, time_t, post_t, time_after_t]` has full column rank
  (`numpy.linalg.matrix_rank(X) == 4`).

Otherwise produce descriptive output only, with an explicit reason:
`insufficient_pre_weeks`, `insufficient_post_weeks`, or `rank_deficient`. This
guard is a minimum execution floor, not evidence of causal identification or
adequate statistical power.

### Interpretation

Report modeled changes as, e.g.:

> organization-level structural change associated with the intervention,
> conditional on the pre-specified time-series model

Never as "AI caused productivity to increase by X%". Seasonality,
contemporaneous non-AI organizational change, and unobserved non-GitHub work
are limitations, not covariates added post hoc.

## Required sensitivity analyses (fixed set of four)

1. **Window sensitivity.** Primary = full requested complete-week range.
   Additionally evaluate symmetric 26-week and 52-week pre/post windows,
   anchored on the last complete pre week and `first_complete_post_week`,
   only when both sides are fully available within the panel; otherwise
   report that window as unavailable. Truncates the existing panel; no
   entity recompute needed.
2. **Stable / two-sided repository cohort.** Repositories with
   `created_at < requested_start` and >=1 qualifying primary-cohort merged
   PR in both the complete-pre and complete-post periods. Recompute
   organization-week metrics from normalized entities restricted to this
   repository set (full recompute, not aggregate-level subtraction).
   Labeled explicitly as a post-period-conditioned sensitivity, not the
   primary estimand.
3. **Leave-one-repository-out.** For each repository ID in the primary
   cohort, recompute the full panel from entities excluding that repository,
   then refit ITS. Report the distribution (min/max) of `β2`/`β3` across
   runs, not a single re-estimate.
4. **Actor sensitivity.** Recompute the panel with the author set widened to
   `human + explicit-ai-agent + unknown` (the "not-known-bot" view) and
   report it alongside the primary `human + explicit-ai-agent` panel, plus
   the `explicit-ai-agent` and `unknown` shares of activity.

Placebo-date analysis and stable-workflow CI sensitivity are deferred to
later work; they are not required for v1.

## Determinism

- Median: Python's `statistics.median` (exact tie behavior, no numpy
  interpolation).
- Durations reported as float hours.
- `report` charts use a fixed `Agg` backend and strip timestamp/hash
  metadata so identical input produces byte-identical SVG output.

## Optional GitHub Actions (CI) metrics — out of scope for this PR

CI metrics require selected-workflow-run collection (workflow/run identity,
event, head SHA, status/conclusion) that `collect`/`ghapi` do not fetch. That
is a collection-affecting change to the already-reviewed collection surface,
not an aggregation/analysis addition, and the issue explicitly does not make
CI support a blocker for the core skill. `aggregate`/`analyze`/`report` in
this PR emit no CI metrics and no `ci.svg`; adding CI support is deferred to
a later change that also extends `collect`.
