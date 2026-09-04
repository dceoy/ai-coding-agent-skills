"""Fixed chart set and Markdown report generation.

``report`` is a read-only derivation step. It rebuilds the primary
organization-week panel (see :mod:`aggregate`) and reads
``<workdir>/report/analysis.json`` (written by ``analyze``), then writes a
fixed, small chart set plus ``report.md`` under ``<workdir>/report/``. No
custom dashboard, no synthetic productivity score: dimension-wise
observations, coverage, modeled changes, sensitivities, interpretation, and
limitations are kept in clearly separated sections.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
import workdir
from aggregate import (
    AggregateError,
    build_panel,
    load_entities,
    normalized_derivation_identity,
    panel_to_rows,
    resolve_effective_observation_end,
)

if TYPE_CHECKING:
    from pathlib import Path

plt.rcParams["svg.hashsalt"] = "github-productivity"

#: Bump when the report/chart output shape changes.
#: v2 renders the full ITS statistics table (beta1/beta2/beta3 + 95% CIs +
#: pre/post week and coverage counts), overlays the persisted fitted ITS
#: trend on eligible chart series, and pins the report to the full
#: normalized-derivation identity.
REPORT_SCHEMA_VERSION = 2

_DELIVERY_METRICS = ("merged_prs", "median_queue_to_merge", "median_changed_lines")
_REVIEW_METRICS = (
    "median_time_to_first_human_review",
    "median_first_human_review_to_merge",
    "human_review_coverage_rate",
)
_REWORK_METRICS = (
    "human_review_events_per_merged_pr",
    "changes_requested_rate",
    "post_review_commits_per_pr",
)
_COVERAGE_COLUMNS = (
    "median_queue_to_merge_n",
    "human_review_coverage_rate_n",
    "changes_requested_rate_unavailable_n",
    "post_review_commits_per_pr_unavailable_n",
)


class ReportError(Exception):
    """Raised when the report cannot be generated from committed evidence."""


def _read_json(path: Path, *, what: str) -> dict[str, Any]:
    """Read one required JSON input.

    Args:
        path: The file to read.
        what: The subcommand that must run first, for the error message.

    Returns:
        The parsed JSON document.

    Raises:
        ReportError: If the file does not exist or cannot be read/parsed.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        msg = f"{path} does not exist; run '{what}' before 'report'"
        raise ReportError(msg) from exc
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"{path} could not be read: {exc}"
        raise ReportError(msg) from exc


def _draw_chart(
    path: Path,
    weeks: list[datetime],
    series: dict[str, list[float | None]],
    *,
    title: str,
    intervention_at: datetime | None,
    fitted: dict[str, list[float | None]] | None = None,
) -> None:
    """Draw one fixed line chart and save it as a deterministic SVG.

    Args:
        path: Destination SVG path.
        weeks: Ordered week-start instants, the shared x-axis.
        series: Metric name -> parallel y-values (``None`` gaps allowed).
        title: The chart title.
        intervention_at: When given, drawn as a vertical marker line.
        fitted: Optional label -> parallel fitted-trend y-values, drawn as a
            dashed overlay for the ITS-modeled series (``None`` gaps allowed).
    """
    fig, ax = plt.subplots(figsize=(8, 4))
    for name, values in series.items():
        xs = [w for w, v in zip(weeks, values, strict=True) if v is not None]
        ys = [v for v in values if v is not None]
        if xs:
            # matplotlib accepts datetime x-values at runtime via its date
            # unit converter; the stubs only type this as ArrayLike | float.
            ax.plot(
                xs,  # pyright: ignore[reportArgumentType]
                ys,
                marker="o",
                markersize=2,
                linewidth=1,
                label=name,
            )
    for name, values in (fitted or {}).items():
        xs = [w for w, v in zip(weeks, values, strict=True) if v is not None]
        ys = [v for v in values if v is not None]
        if xs:
            ax.plot(
                xs,  # pyright: ignore[reportArgumentType]
                ys,
                linestyle="--",
                linewidth=1,
                label=name,
            )
    if intervention_at is not None:
        ax.axvline(
            intervention_at,  # pyright: ignore[reportArgumentType]
            color="black",
            linestyle="--",
            linewidth=1,
            label="intervention",
        )
    ax.set_title(title)
    ax.legend(fontsize="small")
    fig.autofmt_xdate()
    fig.tight_layout()
    tmp_path = path.with_name(f"{path.name}.tmp.{secrets.token_hex(4)}")
    try:
        fig.savefig(tmp_path, format="svg", metadata={"Date": None})
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    finally:
        plt.close(fig)
    tmp_path.replace(path)


_CHART_SPECS = (
    ("delivery.svg", "Delivery", _DELIVERY_METRICS),
    ("review.svg", "Review flow", _REVIEW_METRICS),
    ("rework.svg", "Review burden / rework", _REWORK_METRICS),
)


def _draw_all_charts(
    report_dir: Path,
    rows: list[dict[str, Any]],
    weeks: list[datetime],
    analysis: dict[str, Any],
    *,
    intervention_at: datetime | None,
) -> list[Path]:
    """Draw the fixed chart set, overlaying each modeled series' fitted trend.

    Returns:
        The written chart paths, in fixed order.
    """
    fitted_by_metric = _fitted_trends(analysis.get("its", {}), weeks)
    chart_paths: list[Path] = []
    for filename, title, metrics in _CHART_SPECS:
        path = report_dir / filename
        _draw_chart(
            path,
            weeks,
            {m: _series_for(rows, m) for m in metrics},
            title=title,
            intervention_at=intervention_at,
            fitted={
                f"{m} (fitted)": fitted_by_metric[m]
                for m in metrics
                if m in fitted_by_metric
            },
        )
        chart_paths.append(path)
    return chart_paths


def _fitted_trends(
    its_results: dict[str, Any], weeks: list[datetime]
) -> dict[str, list[float | None]]:
    """Map each fitted metric's persisted ITS trend onto the panel's weeks.

    ``analyze`` writes ``fitted_series`` as ``[[week_start_iso, y_hat], ...]``
    for exactly the weekly rows it fit; ``report`` only aligns them to the
    x-axis so the modeled trend can be overlaid without re-fitting.

    Args:
        its_results: ``analysis["its"]`` -- metric -> result JSON.
        weeks: The ordered panel week-start instants (the chart x-axis).

    Returns:
        Metric -> parallel fitted y-values, ``None`` where no fit row exists.
        Only metrics with a non-empty ``fitted_series`` appear.
    """
    week_keys = [w.strftime("%Y-%m-%dT%H:%M:%SZ") for w in weeks]
    out: dict[str, list[float | None]] = {}
    for metric, result in its_results.items():
        series = (result or {}).get("fitted_series")
        if not series:
            continue
        by_week = {str(week): float(y_hat) for week, y_hat in series}
        out[metric] = [by_week.get(key) for key in week_keys]
    return out


def _series_for(panel_rows: list[dict[str, Any]], metric: str) -> list[float | None]:
    """Extract one metric's ordered, NA-aware series from rendered panel rows.

    Returns:
        Parallel values for each panel row, ``None`` where NA.
    """
    return [
        float(row[metric]) if row.get(metric) not in {None, ""} else None
        for row in panel_rows
    ]


@dataclass(slots=True)
class ReportOutcome:
    """The result of one ``report`` invocation."""

    report_path: Path
    chart_paths: list[Path]


def _rebuild_panel_rows(
    workdir_path: Path, meta: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[datetime]]:
    """Rebuild the primary panel from entities and render it to rows.

    Args:
        workdir_path: The skill's workdir root.
        meta: The ``aggregate`` window sidecar.

    Returns:
        ``(rendered_rows, week_starts)``.

    Raises:
        ReportError: If ``meta`` lacks a valid ``requested_start``/``requested_end``,
            or normalized-entity loading/rebuilding fails.
    """
    try:
        entities = load_entities(workdir_path)
    except AggregateError as exc:
        msg = str(exc)
        raise ReportError(msg) from exc
    entities_identity = normalized_derivation_identity(entities.derivation)
    if meta.get("normalized_derivation") != entities_identity:
        msg = (
            f"the aggregate window sidecar pins normalized derivation "
            f"{meta.get('normalized_derivation')!r} but the current normalized tree "
            f"is {entities_identity!r}; 'normalize' has re-run since 'aggregate'. "
            "Re-run 'aggregate' and 'analyze' so the report renders against one "
            "committed normalization"
        )
        raise ReportError(msg)
    try:
        start = datetime.fromisoformat(meta["requested_start"])
        end = datetime.fromisoformat(meta["requested_end"])
    except (KeyError, ValueError) as exc:
        msg = f"aggregate's window sidecar has an invalid requested_start/end: {exc}"
        raise ReportError(msg) from exc
    try:
        effective_end = resolve_effective_observation_end(entities, end)
        panel = build_panel(
            entities,
            start=start,
            end=end,
            effective_observation_end=effective_end,
            include_forks=bool(meta.get("include_forks")),
        )
    except AggregateError as exc:
        msg = str(exc)
        raise ReportError(msg) from exc
    return panel_to_rows(panel), [w.week_start for w in panel.weeks]


def run_report(*, workdir_path: Path) -> ReportOutcome:
    """Generate the fixed chart set and Markdown report for a workdir.

    Propagates :class:`ReportError` if ``aggregate``/``analyze`` have not
    run for this workdir.

    Args:
        workdir_path: The skill's workdir root.

    Returns:
        The outcome: the report path and the chart paths written.

    Raises:
        ReportError: If ``aggregate``/``analyze`` sidecars are missing or
            malformed.
    """
    report_dir = workdir_path / "report"
    meta = _read_json(report_dir / "organization-week.meta.json", what="aggregate")
    analysis = _read_json(report_dir / "analysis.json", what="analyze")
    expected = analysis.get("aggregate_derivation")
    actual = {
        "requested_start": meta.get("requested_start"),
        "requested_end": meta.get("requested_end"),
        "include_forks": meta.get("include_forks"),
        "normalized_derivation": meta.get("normalized_derivation"),
    }
    if expected != actual:
        msg = (
            f"analysis.json was derived from aggregate window {expected!r} but the "
            f"current aggregate sidecar is {actual!r}; run 'aggregate' and 'analyze' "
            "again so report reflects the same derivation"
        )
        raise ReportError(msg)
    rows, weeks = _rebuild_panel_rows(workdir_path, meta)
    try:
        intervention_at = (
            datetime.fromisoformat(analysis["intervention_at"])
            if analysis.get("intervention_at")
            else None
        )
    except ValueError as exc:
        msg = f"analyze's analysis.json has an invalid intervention_at: {exc}"
        raise ReportError(msg) from exc

    chart_paths = _draw_all_charts(
        report_dir, rows, weeks, analysis, intervention_at=intervention_at
    )

    report_path = report_dir / "report.md"
    report_tmp = report_path.with_name(f"{report_path.name}.tmp.{secrets.token_hex(4)}")
    try:
        report_tmp.write_text(
            _render_report(workdir_path, meta, analysis, rows), encoding="utf-8"
        )
    except BaseException:
        report_tmp.unlink(missing_ok=True)
        raise
    report_tmp.replace(report_path)
    return ReportOutcome(report_path=report_path, chart_paths=chart_paths)


def _fmt(value: object) -> str:
    """Format one panel/analysis value for Markdown.

    Returns:
        ``"NA"`` for ``None``/empty, else the formatted value.
    """
    if value in {None, ""}:
        return "NA"
    if isinstance(value, float):
        return f"{value:.3g}"
    return str(value)


def _current_refresh_failed(workdir_path: Path, meta: dict[str, Any]) -> bool:
    """Re-evaluate refresh-failure status against the manifests on disk.

    ``aggregate`` snapshots this status into ``meta`` at aggregate time, but a
    ``collect`` can fail after ``aggregate``/``analyze`` and before
    ``report``; re-scanning here (rather than trusting the snapshot) keeps
    the freshness statement current as of report generation.

    Returns:
        Whether the most recently started run is newer than the pinned
        ``committed_run_id`` and did not complete.
    """
    latest_run = workdir.latest_manifest_run_id_and_status(workdir_path)
    return bool(
        latest_run is not None
        and latest_run[0] != meta.get("committed_run_id")
        and latest_run[1] != "complete"
    )


def _freshness_section(
    workdir_path: Path,
    meta: dict[str, Any],
    complete_rows: list[dict[str, Any]],
    total: int,
) -> str:
    """Render the collection-freshness section.

    Returns:
        The section's Markdown text.
    """
    refresh_failed = _current_refresh_failed(workdir_path, meta)
    refresh_note = (
        "a newer refresh attempt failed; this report uses the prior committed state"
        if refresh_failed
        else "no newer refresh attempt has failed since this committed state"
    )
    return (
        "## Collection freshness\n\n"
        f"- Committed run: `{meta.get('committed_run_id')}`\n"
        f"- Data as-of: `{meta.get('as_of')}`\n"
        f"- Requested interval: `{meta.get('requested_start')}` .. "
        f"`{meta.get('requested_end')}` (effective end: "
        f"`{meta.get('effective_observation_end')}`)\n"
        f"- Complete weeks in panel: {len(complete_rows)} of {total}\n"
        f"- Refresh status: {refresh_note}\n"
    )


def _coverage_section(complete_rows: list[dict[str, Any]]) -> str:
    """Render the data coverage/composition section.

    Returns:
        The section's Markdown text.
    """
    lines = ["## Data coverage / composition\n"]
    for col in _COVERAGE_COLUMNS:
        total = sum(int(r[col]) for r in complete_rows if r.get(col) not in {None, ""})
        lines.append(f"- `{col}` total across complete weeks: {total}")
    return "\n".join(lines) + "\n"


def _its_section(analysis: dict[str, Any]) -> str:
    """Render the modeled-structural-changes (ITS) section.

    Returns:
        The section's Markdown text.
    """
    if analysis.get("intervention_at") is None:
        body = (
            "No `--intervention-at` was given to `analyze`; this run is "
            "descriptive-only, no ITS models were fit."
        )
    else:
        intro = (
            f"Intervention: `{analysis['intervention_at']}`, first complete "
            f"post week `{analysis.get('first_complete_post_week')}`. HAC lag "
            f"fixed at {analysis.get('hac_maxlags')} observed weekly rows; "
            f"minimum guard {analysis.get('min_guard_weeks')} non-missing "
            "complete weeks per side."
        )
        body = "\n".join([intro, "", *_its_primary_table(analysis.get("its", {}))])
    interpretation = (
        "> Interpretation: any fitted level/slope change reflects an "
        "organization-level structural change associated with the "
        "intervention, conditional on the pre-specified time-series model. "
        "It is not evidence that AI adoption caused a productivity change."
    )
    return f"## Modeled structural changes (ITS)\n\n{body}\n\n{interpretation}\n"


def _ci_cell(result: dict[str, Any], key: str) -> str:
    """Format ``beta<key> [lo, hi]`` for one coefficient, or ``NA``.

    Returns:
        The Markdown table cell text.
    """
    beta = (result.get("beta") or {}).get(f"beta{key}")
    if beta is None:
        return "NA"
    ci = (result.get("conf_int") or {}).get(f"beta{key}")
    if not ci:
        return _fmt(beta)
    return f"{_fmt(beta)} [{_fmt(ci[0])}, {_fmt(ci[1])}]"


def _its_primary_table(results: dict[str, Any]) -> list[str]:
    """Render the full pre-specified ITS statistics table for the primary fit.

    One row per eligible metric with the reporting fields Issue #98 requires:
    the pre-intervention trend ``beta1``, the immediate level change
    ``beta2``, the post-intervention trend change ``beta3``, each with its
    95% confidence interval, the complete pre/post calendar-week counts, the
    metric-specific non-missing week count actually fit, and the
    denominator/coverage totals over the fit weeks.

    Returns:
        Markdown table lines (header plus one row per metric), or an empty
        list if ``results`` is empty.
    """
    if not results:
        return []
    header = (
        "| metric | fitted | beta1 (pre-trend) [95% CI] | beta2 (level) [95% CI] "
        "| beta3 (slope change) [95% CI] | complete pre/post wks | non-missing rows "
        "| denominator (unavailable) | reason |"
    )
    rows = [header, "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for metric, result in results.items():
        denom = result.get("denominator_total")
        unavailable = result.get("unavailable_total")
        denom_cell = "NA" if denom is None else str(denom)
        if unavailable is not None:
            denom_cell = f"{denom_cell} ({unavailable})"
        rows.append(
            f"| `{metric}` | {result.get('fitted')} | "
            f"{_ci_cell(result, '1')} | {_ci_cell(result, '2')} | "
            f"{_ci_cell(result, '3')} | "
            f"{result.get('pre_complete_weeks')}/{result.get('post_complete_weeks')} | "
            f"{result.get('non_missing_weeks')} | {denom_cell} | "
            f"{result.get('reason') or ''} |"
        )
    return rows


def _its_table(results: dict[str, Any]) -> list[str]:
    """Render a compact fitted/beta2/beta3/reason table for sensitivity results.

    Returns:
        Markdown table lines (header plus one row per metric), or an
        empty list if ``results`` is empty.
    """
    if not results:
        return []
    return [
        "| metric | fitted | beta2 (level) | beta3 (slope) | reason |",
        "| --- | --- | --- | --- | --- |",
        *(
            f"| `{metric}` | {result.get('fitted')} | "
            f"{_fmt((result.get('beta') or {}).get('beta2'))} | "
            f"{_fmt((result.get('beta') or {}).get('beta3'))} | "
            f"{result.get('reason') or ''} |"
            for metric, result in results.items()
        ),
    ]


def _actor_totals(
    rows: list[dict[str, Any]],
) -> tuple[int, int, float | None, float | None]:
    """Sum opened-PR counts and average explicit-AI-agent/unknown shares.

    Returns:
        ``(opened_prs_total, merged_prs_total, avg_ai_share, avg_unknown_share)``,
        averaged over weeks where the share is available.
    """
    opened_total = sum(int(r.get("opened_prs") or 0) for r in rows)
    merged_total = sum(int(r.get("merged_prs") or 0) for r in rows)
    ai_shares = [
        float(r["opened_prs_by_explicit-ai-agent_share"])
        for r in rows
        if r.get("opened_prs_by_explicit-ai-agent_share") not in {None, ""}
    ]
    unknown_shares = [
        float(r["opened_prs_by_unknown_share"])
        for r in rows
        if r.get("opened_prs_by_unknown_share") not in {None, ""}
    ]
    avg_ai = sum(ai_shares) / len(ai_shares) if ai_shares else None
    avg_unknown = sum(unknown_shares) / len(unknown_shares) if unknown_shares else None
    return opened_total, merged_total, avg_ai, avg_unknown


def _window_sensitivity_block(sens: dict[str, Any]) -> list[str]:
    """Render the window-sensitivity lines.

    Returns:
        Markdown lines for the window-sensitivity subsection.
    """
    window_blocks: list[str] = []
    for weeks_key, result in sens.get("window", {}).items():
        available = result.get("available")
        window_blocks.append(
            f"**{weeks_key}-week symmetric window** (available: {available})"
        )
        window_blocks.extend(_its_table(result.get("results", {})))
        window_blocks.append("")
    return window_blocks


def _leave_one_out_block(sens: dict[str, Any]) -> list[str]:
    """Render the leave-one-repository-out lines.

    Returns:
        Markdown lines for the leave-one-out subsection.
    """
    loo_lines = []
    for metric, result in sens.get("leave_one_repository_out", {}).items():
        if result.get("runs"):
            loo_lines.append(
                f"- `{metric}`: beta2 range {result.get('beta2_range')}, "
                f"beta3 range {result.get('beta3_range')} across {result['runs']} runs"
            )
        else:
            loo_lines.append(f"- `{metric}`: no leave-one-out runs available")
    return loo_lines


def _actor_sensitivity_block(
    sens: dict[str, Any], primary_rows: list[dict[str, Any]]
) -> list[str]:
    """Render the actor-sensitivity lines, with primary-vs-widened totals/shares.

    Returns:
        Markdown lines for the actor-sensitivity subsection.
    """
    actor = sens.get("actor", {})
    primary_opened, primary_merged, _, _ = _actor_totals(primary_rows)
    widened_opened, widened_merged, ai_share, unknown_share = _actor_totals(
        actor.get("rows", [])
    )
    primary_totals = f"{primary_opened} / {primary_merged}"
    widened_totals = f"{widened_opened} / {widened_merged}"
    return [
        f"- Author classes included: {actor.get('author_classes')}",
        f"- Primary (human+explicit-ai-agent) opened/merged totals: {primary_totals}",
        f"- Widened (not-known-bot) opened/merged totals: {widened_totals}",
        f"- Mean weekly `explicit-ai-agent` share of opened PRs: {_fmt(ai_share)}",
        f"- Mean weekly `unknown` share of opened PRs: {_fmt(unknown_share)}",
    ]


def _sensitivity_section(
    analysis: dict[str, Any], primary_rows: list[dict[str, Any]]
) -> str:
    """Render the sensitivity-results section, with actual computed values.

    Args:
        analysis: The full ``analyze`` output document.
        primary_rows: The rendered primary organization-week panel rows,
            for the actor-sensitivity delta.

    Returns:
        The section's Markdown text.
    """
    sens = analysis.get("sensitivities", {})
    stable = sens.get("stable_cohort", {})
    stable_block = [
        f"- Repositories in cohort: {len(stable.get('repository_ids', []))}",
        "",
        *_its_table(stable.get("results", {})),
    ]
    return "\n".join([
        "## Sensitivity results",
        "",
        "### Window sensitivity",
        *_window_sensitivity_block(sens),
        "### Stable / two-sided repository cohort",
        *stable_block,
        "",
        "### Leave-one-repository-out",
        *_leave_one_out_block(sens),
        "",
        "### Actor sensitivity (not-known-bot)",
        *_actor_sensitivity_block(sens, primary_rows),
        "",
    ])


_INTERPRETATION = (
    "## Interpretation\n\n"
    "Read delivery, review-flow, and rework dimensions together, never "
    "as a single score. `merged_prs` alone is not productivity; "
    "queue/cycle time alone is not quality; review or comment counts "
    "alone are not review precision or accuracy.\n"
)

_LIMITATIONS = (
    "## Unsupported claims / limitations\n\n"
    "- No business value, developer-hours, or production-incident "
    "claims are made from GitHub data alone.\n"
    "- Local AI coding-agent use is never inferred from an ordinary "
    "human GitHub identity.\n"
    "- Repository organization-membership history before/after a "
    "transfer is not reconstructed; see methodology.md.\n"
    "- The 12-week guard is a minimum execution floor, not evidence of "
    "causal identification or adequate statistical power.\n"
    "- Optional GitHub Actions CI metrics are not implemented in this "
    "report.\n"
)

_OBSERVED_METRICS_SECTION = (
    "## Observed metrics (descriptive)\n\n"
    "See `organization-week.csv` for the full panel. Composition/scale "
    "diagnostics, PR-size medians, `active_*` counts, and actor-class "
    "shares are workload/composition diagnostics, never productivity "
    "outcomes on their own.\n"
)

_INTRO = (
    "# GitHub organization productivity report\n\n"
    "GitHub-observable delivery, review-flow, and rework activity for one "
    "organization, over UTC ISO weeks. This report never infers business "
    "value, developer hours, or production defects, and never attributes "
    "a productivity change to AI adoption as a causal fact.\n"
)


def _render_report(
    workdir_path: Path,
    meta: dict[str, Any],
    analysis: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    """Render ``report.md``'s full content.

    Args:
        workdir_path: The skill's workdir root.
        meta: The ``aggregate`` window sidecar.
        analysis: The full ``analyze`` output document.
        rows: The rendered organization-week panel rows.

    Returns:
        The complete Markdown document text.
    """
    complete_rows = [r for r in rows if r.get("complete_week")]
    sections = (
        _INTRO,
        _freshness_section(workdir_path, meta, complete_rows, len(rows)),
        _OBSERVED_METRICS_SECTION,
        _coverage_section(complete_rows),
        _its_section(analysis),
        _sensitivity_section(analysis, rows),
        _INTERPRETATION,
        _LIMITATIONS,
    )
    return "\n".join(sections)
