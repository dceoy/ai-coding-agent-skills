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
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
from aggregate import (
    build_panel,
    load_entities,
    panel_to_rows,
    resolve_effective_observation_end,
)

if TYPE_CHECKING:
    from pathlib import Path

plt.rcParams["svg.hashsalt"] = "github-productivity"

#: Bump when the report/chart output shape changes.
REPORT_SCHEMA_VERSION = 1

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
) -> None:
    """Draw one fixed line chart and save it as a deterministic SVG.

    Args:
        path: Destination SVG path.
        weeks: Ordered week-start instants, the shared x-axis.
        series: Metric name -> parallel y-values (``None`` gaps allowed).
        title: The chart title.
        intervention_at: When given, drawn as a vertical marker line.
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
    fig.savefig(path, format="svg", metadata={"Date": None})
    plt.close(fig)


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
    """
    entities = load_entities(workdir_path)
    start = datetime.fromisoformat(meta["requested_start"])
    end = datetime.fromisoformat(meta["requested_end"])
    effective_end = resolve_effective_observation_end(entities, end)
    panel = build_panel(
        entities,
        start=start,
        end=end,
        effective_observation_end=effective_end,
        include_forks=bool(meta.get("include_forks")),
    )
    return panel_to_rows(panel), [w.week_start for w in panel.weeks]


def run_report(*, workdir_path: Path) -> ReportOutcome:
    """Generate the fixed chart set and Markdown report for a workdir.

    Propagates :class:`ReportError` if ``aggregate``/``analyze`` have not
    run for this workdir.

    Args:
        workdir_path: The skill's workdir root.

    Returns:
        The outcome: the report path and the chart paths written.
    """
    report_dir = workdir_path / "report"
    meta = _read_json(report_dir / "organization-week.meta.json", what="aggregate")
    analysis = _read_json(report_dir / "analysis.json", what="analyze")
    rows, weeks = _rebuild_panel_rows(workdir_path, meta)
    intervention_at = (
        datetime.fromisoformat(analysis["intervention_at"])
        if analysis.get("intervention_at")
        else None
    )

    chart_specs = (
        ("delivery.svg", "Delivery", _DELIVERY_METRICS),
        ("review.svg", "Review flow", _REVIEW_METRICS),
        ("rework.svg", "Review burden / rework", _REWORK_METRICS),
    )
    chart_paths: list[Path] = []
    for filename, title, metrics in chart_specs:
        path = report_dir / filename
        series = {m: _series_for(rows, m) for m in metrics}
        _draw_chart(path, weeks, series, title=title, intervention_at=intervention_at)
        chart_paths.append(path)

    report_path = report_dir / "report.md"
    report_path.write_text(_render_report(meta, analysis, rows), encoding="utf-8")
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


def _freshness_section(
    meta: dict[str, Any], complete_rows: list[dict[str, Any]], total: int
) -> str:
    """Render the collection-freshness section.

    Returns:
        The section's Markdown text.
    """
    return (
        "## Collection freshness\n\n"
        f"- Committed run: `{meta.get('committed_run_id')}`\n"
        f"- Data as-of: `{meta.get('as_of')}`\n"
        f"- Requested interval: `{meta.get('requested_start')}` .. "
        f"`{meta.get('requested_end')}` (effective end: "
        f"`{meta.get('effective_observation_end')}`)\n"
        f"- Complete weeks in panel: {len(complete_rows)} of {total}\n"
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
        body = "\n".join([intro, "", *_its_table(analysis.get("its", {}))])
    interpretation = (
        "> Interpretation: any fitted level/slope change reflects an "
        "organization-level structural change associated with the "
        "intervention, conditional on the pre-specified time-series model. "
        "It is not evidence that AI adoption caused a productivity change."
    )
    return f"## Modeled structural changes (ITS)\n\n{body}\n\n{interpretation}\n"


def _its_table(results: dict[str, Any]) -> list[str]:
    """Render a fitted/beta2/beta3/reason table for a set of ITS results.

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
    meta: dict[str, Any], analysis: dict[str, Any], rows: list[dict[str, Any]]
) -> str:
    """Render ``report.md``'s full content.

    Args:
        meta: The ``aggregate`` window sidecar.
        analysis: The full ``analyze`` output document.
        rows: The rendered organization-week panel rows.

    Returns:
        The complete Markdown document text.
    """
    complete_rows = [r for r in rows if r.get("complete_week")]
    sections = (
        _INTRO,
        _freshness_section(meta, complete_rows, len(rows)),
        _OBSERVED_METRICS_SECTION,
        _coverage_section(complete_rows),
        _its_section(analysis),
        _sensitivity_section(analysis, rows),
        _INTERPRETATION,
        _LIMITATIONS,
    )
    return "\n".join(sections)
