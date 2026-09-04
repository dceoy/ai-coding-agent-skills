"""Pre-specified interrupted time-series (ITS) analysis and sensitivities.

``analyze`` is a read-only derivation step. It rebuilds the primary
organization-week panel from normalized entities (see :mod:`aggregate`),
fits one segmented OLS ITS model per pre-specified eligible outcome metric
(references/metrics.md), and runs the four required sensitivity analyses.
Every design choice -- the eligible-metric list, the HAC lag, the
guard thresholds, and the sensitivity definitions -- is fixed in
``references/metrics.md`` and never chosen after inspecting results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import numpy as np
import statsmodels.api as sm
import workdir
from aggregate import (
    ITS_ELIGIBLE_METRICS,
    NOT_KNOWN_BOT_AUTHOR_CLASSES,
    PRIMARY_AUTHOR_CLASSES,
    AggregateError,
    build_panel,
    load_entities,
    normalized_derivation_identity,
    panel_to_rows,
    parse_ts,
    resolve_effective_observation_end,
)

if TYPE_CHECKING:
    from pathlib import Path

    from aggregate import Entities, Panel

#: Bump when the analysis output shape changes.
#: v2 adds per-metric ``beta1``/``conf_int`` reporting fields, the persisted
#: ``fitted_series`` ITS trend, denominator/coverage totals, and the full
#: normalized-derivation identity in ``aggregate_derivation``.
ANALYZE_SCHEMA_VERSION = 2

#: Fixed HAC/Newey-West lag, in observed (non-missing) weekly rows.
HAC_MAXLAGS = 4
#: Minimum non-missing complete weeks required on each side of the
#: intervention before a metric is fit.
MIN_GUARD_WEEKS = 12
_WINDOW_SENSITIVITIES = (26, 52)


class AnalyzeError(Exception):
    """Raised when analysis cannot proceed from committed evidence."""


def _read_meta(workdir_path: Path) -> dict[str, Any]:
    """Read the ``aggregate``-written window sidecar.

    Args:
        workdir_path: The skill's workdir root.

    Returns:
        The parsed ``organization-week.meta.json`` contents.

    Raises:
        AnalyzeError: If the sidecar does not exist or is unreadable --
            ``aggregate`` must run before ``analyze``.
    """
    path = workdir_path / "report" / "organization-week.meta.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        msg = f"{path} does not exist; run 'aggregate' before 'analyze'"
        raise AnalyzeError(msg) from exc
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"{path} could not be read: {exc}"
        raise AnalyzeError(msg) from exc


def _week_start(instant: datetime) -> datetime:
    """Return the Monday 00:00 UTC start of the ISO week containing ``instant``."""
    day_start = instant.astimezone(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return day_start - timedelta(days=day_start.weekday())


@dataclass(slots=True)
class TimeIndex:
    """The fixed calendar-week ``time_t`` index over every complete ISO week.

    ``weeks`` is the ordered list of every complete week in the panel;
    ``time_t`` for a week is its position in this list, so it is always a
    true calendar-week offset. ``excluded_partial_week``, when set, marks a
    week that must never contribute a data row to any fit (its slot is
    still counted for ``time_t`` purposes, so later weeks are not shifted).
    ``p`` is ``None`` when no intervention was given (descriptive-only run)
    or when the intervention's first complete post week falls outside the
    panel's complete weeks; ``intervention_given`` disambiguates the two.
    """

    weeks: list[datetime]
    p: int | None
    first_complete_post_week: datetime | None
    excluded_partial_week: datetime | None
    intervention_given: bool


def build_time_index(panel: Panel, intervention_at: datetime | None) -> TimeIndex:
    """Build the fixed calendar-week ``time_t`` index over complete weeks.

    Args:
        panel: The primary organization-week panel.
        intervention_at: The intervention instant, or ``None`` for a
            descriptive-only run.

    Returns:
        The fixed week/``time_t``/``p`` index. ``weeks`` always retains
        every complete week, including a mid-week intervention's excluded
        containing week, so that ``time_t`` never gets renumbered around a
        gap -- only :func:`fit_its` drops that week's data row.
    """
    complete_weeks = [w.week_start for w in panel.weeks if w.complete_week]
    if intervention_at is None:
        return TimeIndex(complete_weeks, None, None, None, intervention_given=False)
    containing = _week_start(intervention_at)
    exact_monday = intervention_at == containing
    if exact_monday:
        first_post = containing
        excluded = None
    else:
        first_post = containing + timedelta(days=7)
        excluded = containing
    p = complete_weeks.index(first_post) if first_post in complete_weeks else None
    return TimeIndex(complete_weeks, p, first_post, excluded, intervention_given=True)


@dataclass(slots=True)
class ITSResult:
    """The result of fitting (or skipping) one metric's ITS model.

    ``pre_complete_weeks``/``post_complete_weeks`` count every complete
    calendar week on each side of ``p`` (the excluded partial intervention
    week, when there is one, is not counted). ``non_missing_weeks`` is the
    number of weekly rows actually fit after dropping this metric's ``NA``
    weeks. ``fitted_series`` is ``[(week_start_iso, y_hat), ...]`` for exactly
    those fit rows, so ``report`` can overlay the modeled trend without
    re-fitting. ``denominator_total``/``unavailable_total`` sum this metric's
    rate/median denominator and unavailable counts over the fit weeks.
    """

    metric: str
    fitted: bool
    reason: str | None
    beta: dict[str, float] | None
    conf_int: dict[str, tuple[float, float]] | None
    pre_complete_weeks: int
    post_complete_weeks: int
    non_missing_weeks: int
    fitted_series: list[tuple[str, float]] | None = None
    denominator_total: int | None = None
    unavailable_total: int | None = None


#: The design matrix's fixed column count: intercept, time_t, post_t,
#: time_after_t.
_DESIGN_COLUMNS = 4

#: Per ITS-eligible metric, the organization-week panel column holding its
#: rate/median denominator (``None`` for a raw count outcome), and the column
#: holding its explicit "unavailable" count where one exists. Used only for
#: the ITS report's denominator/coverage diagnostics.
_METRIC_DENOMINATOR_COLUMN: dict[str, str | None] = {
    "merged_prs": None,
    "median_queue_to_merge": "median_queue_to_merge_n",
    "human_review_coverage_rate": "human_review_coverage_rate_n",
    "median_time_to_first_human_review": "median_time_to_first_human_review_n",
    "median_first_human_review_to_merge": "median_first_human_review_to_merge_n",
    "human_review_events_per_merged_pr": "human_review_events_per_merged_pr_n",
    "changes_requested_rate": "changes_requested_rate_n",
    "post_review_commits_per_pr": "post_review_commits_per_pr_n",
}
_METRIC_UNAVAILABLE_COLUMN: dict[str, str] = {
    "changes_requested_rate": "changes_requested_rate_unavailable_n",
    "post_review_commits_per_pr": "post_review_commits_per_pr_unavailable_n",
}


def its_design_matrix(time_ts: list[int], p: int) -> np.ndarray:
    """Build the segmented-OLS design matrix ``[1, time_t, post_t, time_after_t]``.

    The single source of the ITS design. Extracted so the full-rank guard
    (``numpy.linalg.matrix_rank(X) == 4``) can be exercised directly against a
    degenerate ``(time_ts, p)`` -- after the 12/12 non-missing-week guard the
    ``rank_deficient`` branch of :func:`fit_its` is unreachable from any panel
    :func:`aggregate.build_panel` can produce, so it is defense-in-depth that
    is only testable at this level.

    Args:
        time_ts: The ordered calendar-week ``time_t`` offsets of the fit rows.
        p: The ``time_t`` index of ``first_complete_post_week``.

    Returns:
        An ``(len(time_ts), 4)`` float array.
    """
    return np.array([
        [1.0, float(t), 1.0 if t >= p else 0.0, float(max(0, t - p))] for t in time_ts
    ])


def _skip(
    metric: str, reason: str, *, pre_complete: int, post_complete: int, non_missing: int
) -> ITSResult:
    """Build an unfitted :class:`ITSResult` with the given skip reason.

    Returns:
        The unfitted result.
    """
    return ITSResult(
        metric=metric,
        fitted=False,
        reason=reason,
        beta=None,
        conf_int=None,
        pre_complete_weeks=pre_complete,
        post_complete_weeks=post_complete,
        non_missing_weeks=non_missing,
    )


def fit_its(panel: Panel, time_index: TimeIndex, metric: str) -> ITSResult:
    """Fit one metric's segmented OLS ITS model, or report why it was skipped.

    Args:
        panel: The panel to read ``metric`` values from.
        time_index: The fixed ``time_t``/``p`` index.
        metric: One of :data:`aggregate.ITS_ELIGIBLE_METRICS`.

    Returns:
        The fit result, or a descriptive skip reason.
    """
    by_week = {w.week_start: w.metrics.get(metric) for w in panel.weeks}
    excluded = time_index.excluded_partial_week
    if time_index.p is None:
        reason = (
            "intervention_outside_panel"
            if time_index.intervention_given
            else "no_intervention_specified"
        )
        return _skip(
            metric,
            reason,
            pre_complete=0,
            post_complete=0,
            non_missing=0,
        )
    pre_complete = sum(
        1 for t, w in enumerate(time_index.weeks) if t < time_index.p and w != excluded
    )
    post_complete = sum(
        1 for t, w in enumerate(time_index.weeks) if t >= time_index.p and w != excluded
    )
    rows: list[tuple[int, float]] = [
        (t, float(value))
        for t, w in enumerate(time_index.weeks)
        if w != excluded and (value := by_week.get(w)) is not None
    ]
    pre_n = sum(1 for t, _ in rows if t < time_index.p)
    post_n = sum(1 for t, _ in rows if t >= time_index.p)
    if pre_n < MIN_GUARD_WEEKS:
        return _skip(
            metric,
            "insufficient_pre_weeks",
            pre_complete=pre_complete,
            post_complete=post_complete,
            non_missing=len(rows),
        )
    if post_n < MIN_GUARD_WEEKS:
        return _skip(
            metric,
            "insufficient_post_weeks",
            pre_complete=pre_complete,
            post_complete=post_complete,
            non_missing=len(rows),
        )
    p = time_index.p
    design = its_design_matrix([t for t, _ in rows], p)
    if np.linalg.matrix_rank(design) < _DESIGN_COLUMNS:
        return _skip(
            metric,
            "rank_deficient",
            pre_complete=pre_complete,
            post_complete=post_complete,
            non_missing=len(rows),
        )
    return _fit_result(
        design,
        panel,
        time_index,
        metric,
        rows,
        pre_complete=pre_complete,
        post_complete=post_complete,
        excluded=excluded,
    )


def _fit_result(
    design: np.ndarray,
    panel: Panel,
    time_index: TimeIndex,
    metric: str,
    rows: list[tuple[int, float]],
    *,
    pre_complete: int,
    post_complete: int,
    excluded: datetime | None,
) -> ITSResult:
    """Fit the OLS/HAC model for a full-rank design and build the result.

    Split out of :func:`fit_its` so the guard-and-skip logic there stays flat.

    Returns:
        The fitted :class:`ITSResult`, including the persisted ``fitted_series``
        trend and the denominator/coverage totals over the fit weeks.
    """
    names = ("beta0", "beta1", "beta2", "beta3")
    fit = sm.OLS(np.array([v for _, v in rows]), design).fit(
        cov_type="HAC", cov_kwds={"maxlags": HAC_MAXLAGS, "use_correction": True}
    )
    ci = fit.conf_int(alpha=0.05)
    denom_total, unavailable_total = _coverage_totals(
        panel, time_index, metric, rows, excluded=excluded
    )
    return ITSResult(
        metric=metric,
        fitted=True,
        reason=None,
        beta=dict(zip(names, (float(v) for v in fit.params), strict=True)),
        conf_int={
            name: (float(ci[i][0]), float(ci[i][1])) for i, name in enumerate(names)
        },
        pre_complete_weeks=pre_complete,
        post_complete_weeks=post_complete,
        non_missing_weeks=len(rows),
        fitted_series=[
            (time_index.weeks[t].strftime("%Y-%m-%dT%H:%M:%SZ"), float(y_hat))
            for (t, _), y_hat in zip(
                rows, np.asarray(design @ fit.params).ravel(), strict=True
            )
        ],
        denominator_total=denom_total,
        unavailable_total=unavailable_total,
    )


def _coverage_totals(
    panel: Panel,
    time_index: TimeIndex,
    metric: str,
    rows: list[tuple[int, float]],
    *,
    excluded: datetime | None,
) -> tuple[int | None, int | None]:
    """Sum ``metric``'s denominator and unavailable counts over the fit weeks.

    Args:
        panel: The panel the fit read from.
        time_index: The fixed ``time_t``/``p`` index.
        metric: The ITS-eligible metric.
        rows: The ``(time_t, value)`` rows actually fit.
        excluded: The excluded partial intervention week, if any.

    Returns:
        ``(denominator_total, unavailable_total)``. ``denominator_total`` is
        ``None`` for a raw count outcome with no separate denominator; the
        unavailable total is ``None`` when the metric has no explicit
        "unavailable" column.
    """
    denom_col = _METRIC_DENOMINATOR_COLUMN.get(metric)
    unavailable_col = _METRIC_UNAVAILABLE_COLUMN.get(metric)
    fit_weeks = {time_index.weeks[t] for t, _ in rows}
    metrics_by_week = {
        w.week_start: w.metrics
        for w in panel.weeks
        if w.week_start in fit_weeks and w.week_start != excluded
    }
    denom_total = (
        sum(int(m.get(denom_col) or 0) for m in metrics_by_week.values())
        if denom_col is not None
        else None
    )
    unavailable_total = (
        sum(int(m.get(unavailable_col) or 0) for m in metrics_by_week.values())
        if unavailable_col is not None
        else None
    )
    return denom_total, unavailable_total


def _primary_cohort_repository_ids(
    entities: Entities, *, include_forks: bool
) -> frozenset[int]:
    """Return the primary-cohort repository ID set (fork-filtered)."""
    return frozenset(
        repo_id
        for repo_id, repo in entities.repositories.items()
        if include_forks or not repo.get("fork")
    )


def _stable_cohort_repository_ids(
    entities: Entities,
    time_index: TimeIndex,
    *,
    requested_start: datetime,
    include_forks: bool,
) -> frozenset[int]:
    """Return repositories qualifying for the stable/two-sided cohort sensitivity.

    A repository qualifies when it was created before ``requested_start``
    and has at least one qualifying primary-cohort merged PR in both the
    complete-pre and complete-post periods.

    Args:
        entities: Loaded normalized entities.
        time_index: The fixed ``time_t``/``p`` index.
        requested_start: The requested inclusive UTC interval start.
        include_forks: Whether forks are eligible for the primary cohort.

    Returns:
        The qualifying repository ID set. Empty if ``time_index.p`` is
        ``None`` (no intervention).
    """
    if time_index.p is None:
        return frozenset()
    pre_weeks = set(time_index.weeks[: time_index.p]) - {
        time_index.excluded_partial_week
    }
    post_weeks = set(time_index.weeks[time_index.p :]) - {
        time_index.excluded_partial_week
    }
    primary_ids = _primary_cohort_repository_ids(entities, include_forks=include_forks)
    pre_repos: set[int] = set()
    post_repos: set[int] = set()
    for (repo_id, _pr_number), pr in entities.pull_requests.items():
        if (
            repo_id not in primary_ids
            or pr.get("author_classification") not in PRIMARY_AUTHOR_CLASSES
        ):
            continue
        merged = parse_ts(pr.get("merged_at"))
        if merged is None:
            continue
        w = _week_start(merged)
        if w in pre_weeks:
            pre_repos.add(repo_id)
        if w in post_weeks:
            post_repos.add(repo_id)
    created_ok = {
        repo_id
        for repo_id in primary_ids
        if (dt := parse_ts(entities.repositories[repo_id].get("created_at")))
        is not None
        and dt < requested_start
    }
    return frozenset(created_ok & pre_repos & post_repos)


def _window_sensitivity(
    entities: Entities, panel: Panel, time_index: TimeIndex, *, weeks: int
) -> dict[str, Any]:
    """Compute the symmetric ``weeks``-pre/post window ITS sensitivity.

    The pre/post window bounds are chosen from eligible complete weeks --
    excluding a mid-week intervention's excluded partial week from the
    ``weeks`` budget on each side -- while the excluded week's slot, when it
    falls inside the resulting bounds, is kept in the truncated regression
    index so ``time_t`` still reflects the true calendar gap.

    Args:
        entities: Unused directly (kept for a uniform sensitivity-function
            signature); the window sensitivity truncates the existing
            panel rather than recomputing from entities.
        panel: The primary panel.
        time_index: The fixed ``time_t``/``p`` index.
        weeks: The symmetric window size (26 or 52) of eligible complete
            weeks on each side of the intervention.

    Returns:
        Either ``{"available": True, "results": {...}}`` or
        ``{"available": False, "reason": ...}``.
    """
    del entities
    if time_index.p is None:
        return {"available": False, "reason": "insufficient_symmetric_coverage"}
    excluded = time_index.excluded_partial_week
    eligible_before = [
        i for i, w in enumerate(time_index.weeks[: time_index.p]) if w != excluded
    ]
    eligible_after = [
        i for i, w in enumerate(time_index.weeks) if i >= time_index.p and w != excluded
    ]
    if len(eligible_before) < weeks or len(eligible_after) < weeks:
        return {"available": False, "reason": "insufficient_symmetric_coverage"}
    lo = eligible_before[-weeks]
    hi = eligible_after[weeks - 1] + 1
    truncated = TimeIndex(
        time_index.weeks[lo:hi],
        time_index.p - lo,
        time_index.first_complete_post_week,
        excluded,
        intervention_given=True,
    )
    results = {
        m: _result_to_json(fit_its(panel, truncated, m)) for m in ITS_ELIGIBLE_METRICS
    }
    return {"available": True, "results": results}


def _result_to_json(result: ITSResult) -> dict[str, Any]:
    """Render an :class:`ITSResult` into JSON-ready form.

    Returns:
        The JSON-ready dict.
    """
    return {
        "metric": result.metric,
        "fitted": result.fitted,
        "reason": result.reason,
        "beta": result.beta,
        "conf_int": (
            {k: list(v) for k, v in result.conf_int.items()}
            if result.conf_int
            else None
        ),
        "pre_complete_weeks": result.pre_complete_weeks,
        "post_complete_weeks": result.post_complete_weeks,
        "non_missing_weeks": result.non_missing_weeks,
        "denominator_total": result.denominator_total,
        "unavailable_total": result.unavailable_total,
        "fitted_series": (
            [[week, y_hat] for week, y_hat in result.fitted_series]
            if result.fitted_series is not None
            else None
        ),
    }


def _leave_one_out(
    entities: Entities,
    time_index: TimeIndex,
    *,
    start: datetime,
    end: datetime,
    effective_end: datetime,
    include_forks: bool,
) -> dict[str, Any]:
    """Recompute the panel with each repository removed in turn and refit ITS.

    Args:
        entities: Loaded normalized entities.
        time_index: The fixed ``time_t``/``p`` index (reused across runs;
            the panel's week structure does not depend on repository set).
        start: Requested inclusive UTC interval start.
        end: Requested exclusive UTC interval end.
        effective_end: ``min(end, as_of)``.
        include_forks: Whether forks are eligible for the primary cohort.

    Returns:
        Per-metric ``{"beta2_range": [min, max], "beta3_range": [min, max],
        "runs": N}`` across every leave-one-out repository, using only
        successfully fitted runs.
    """
    primary_ids = _primary_cohort_repository_ids(entities, include_forks=include_forks)
    if time_index.p is None or not primary_ids:
        return {m: {"runs": 0} for m in ITS_ELIGIBLE_METRICS}
    per_metric: dict[str, list[dict[str, float]]] = {
        m: [] for m in ITS_ELIGIBLE_METRICS
    }
    for repo_id in sorted(primary_ids):
        subset_panel = build_panel(
            entities,
            start=start,
            end=end,
            effective_observation_end=effective_end,
            repository_ids=frozenset(primary_ids - {repo_id}),
        )
        for metric in ITS_ELIGIBLE_METRICS:
            fit = fit_its(subset_panel, time_index, metric)
            if fit.fitted and fit.beta is not None:
                per_metric[metric].append(fit.beta)
    out: dict[str, Any] = {}
    for metric, betas in per_metric.items():
        if not betas:
            out[metric] = {"runs": 0}
            continue
        beta2s = [b["beta2"] for b in betas]
        beta3s = [b["beta3"] for b in betas]
        out[metric] = {
            "runs": len(betas),
            "beta2_range": [min(beta2s), max(beta2s)],
            "beta3_range": [min(beta3s), max(beta3s)],
        }
    return out


def _actor_sensitivity(
    entities: Entities,
    *,
    start: datetime,
    end: datetime,
    effective_end: datetime,
    include_forks: bool,
) -> dict[str, Any]:
    """Recompute the panel with the widened "not-known-bot" author set.

    Args:
        entities: Loaded normalized entities.
        start: Requested inclusive UTC interval start.
        end: Requested exclusive UTC interval end.
        effective_end: ``min(end, as_of)``.
        include_forks: Whether forks are eligible for the primary cohort.

    Returns:
        The alternate panel's rows plus explicit-AI-agent/unknown activity
        shares, for descriptive side-by-side reporting.
    """
    alt_panel = build_panel(
        entities,
        start=start,
        end=end,
        effective_observation_end=effective_end,
        include_forks=include_forks,
        author_classes=NOT_KNOWN_BOT_AUTHOR_CLASSES,
    )
    return {
        "author_classes": sorted(NOT_KNOWN_BOT_AUTHOR_CLASSES),
        "rows": panel_to_rows(alt_panel),
    }


@dataclass(slots=True)
class AnalyzeOutcome:
    """The result of one ``analyze`` invocation."""

    analysis: dict[str, Any]
    path: Path


def run_analyze(
    *, workdir_path: Path, intervention_at: datetime | None = None
) -> AnalyzeOutcome:
    """Fit the pre-specified ITS models and required sensitivities.

    Args:
        workdir_path: The skill's workdir root.
        intervention_at: The UTC intervention instant, or ``None`` for a
            descriptive-only run with no ITS fitting.

    Returns:
        The outcome: the full analysis document and the path it was
        written to.

    Raises:
        AnalyzeError: If ``aggregate`` has not run for this workdir, entities
            cannot be loaded, or ``normalize`` has advanced to a different
            committed generation than the one ``aggregate`` derived its
            window sidecar from.
    """
    meta = _read_meta(workdir_path)
    try:
        entities = load_entities(workdir_path)
    except AggregateError as exc:
        msg = str(exc)
        raise AnalyzeError(msg) from exc
    meta_identity = meta.get("normalized_derivation")
    if meta_identity != normalized_derivation_identity(entities.derivation):
        msg = (
            f"normalized entities are derivation "
            f"{normalized_derivation_identity(entities.derivation)!r} but 'aggregate' "
            f"derived its window from {meta_identity!r}; re-run 'aggregate' before "
            "analyzing so the panel, ITS models, and coverage all reflect one "
            "committed normalization (committed run + actor-classification "
            "fingerprint + normalizer schema version)"
        )
        raise AnalyzeError(msg)
    try:
        start = datetime.fromisoformat(meta["requested_start"])
        end = datetime.fromisoformat(meta["requested_end"])
    except (KeyError, ValueError) as exc:
        msg = f"aggregate's window sidecar has an invalid requested_start/end: {exc}"
        raise AnalyzeError(msg) from exc
    effective_end = resolve_effective_observation_end(entities, end)
    include_forks = bool(meta.get("include_forks", False))
    panel = build_panel(
        entities,
        start=start,
        end=end,
        effective_observation_end=effective_end,
        include_forks=include_forks,
    )
    time_index = build_time_index(panel, intervention_at)
    primary_results = {
        m: _result_to_json(fit_its(panel, time_index, m)) for m in ITS_ELIGIBLE_METRICS
    }
    stable_ids = _stable_cohort_repository_ids(
        entities, time_index, requested_start=start, include_forks=include_forks
    )
    stable_panel = (
        build_panel(
            entities,
            start=start,
            end=end,
            effective_observation_end=effective_end,
            repository_ids=stable_ids,
        )
        if stable_ids
        else None
    )
    analysis = {
        "schema_version": ANALYZE_SCHEMA_VERSION,
        "aggregate_derivation": {
            "requested_start": meta.get("requested_start"),
            "requested_end": meta.get("requested_end"),
            "include_forks": meta.get("include_forks"),
            "normalized_derivation": meta_identity,
        },
        "intervention_at": intervention_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        if intervention_at
        else None,
        "first_complete_post_week": (
            time_index.first_complete_post_week.strftime("%Y-%m-%dT%H:%M:%SZ")
            if time_index.first_complete_post_week
            else None
        ),
        "excluded_partial_intervention_week": (
            time_index.excluded_partial_week.strftime("%Y-%m-%dT%H:%M:%SZ")
            if time_index.excluded_partial_week
            else None
        ),
        "hac_maxlags": HAC_MAXLAGS,
        "min_guard_weeks": MIN_GUARD_WEEKS,
        "its": primary_results,
        "sensitivities": {
            "window": {
                str(w): _window_sensitivity(entities, panel, time_index, weeks=w)
                for w in _WINDOW_SENSITIVITIES
            },
            "stable_cohort": {
                "repository_ids": sorted(stable_ids),
                "results": (
                    {
                        m: _result_to_json(fit_its(stable_panel, time_index, m))
                        for m in ITS_ELIGIBLE_METRICS
                    }
                    if stable_panel is not None
                    else {}
                ),
            },
            "leave_one_repository_out": _leave_one_out(
                entities,
                time_index,
                start=start,
                end=end,
                effective_end=effective_end,
                include_forks=include_forks,
            ),
            "actor": _actor_sensitivity(
                entities,
                start=start,
                end=end,
                effective_end=effective_end,
                include_forks=include_forks,
            ),
        },
    }
    path = workdir_path / "report" / "analysis.json"
    workdir.atomic_write_json(path, analysis)
    return AnalyzeOutcome(analysis=analysis, path=path)
