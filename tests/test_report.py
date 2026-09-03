"""Tests for the fixed chart set and Markdown report generation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import aggregate
import analyze
import pytest
import report
import workdir

from tests.conftest import draft_row, pr_row, repo_row, write_normalized, write_state

if TYPE_CHECKING:
    from pathlib import Path


def _monday(index: int, base: datetime = datetime(2025, 1, 6, tzinfo=UTC)) -> datetime:
    return base + timedelta(days=7 * index)


def _build_workdir(tmp_path: Path) -> tuple[datetime, datetime, datetime]:
    write_state(tmp_path, repository_ids=[1])
    total_weeks = 26
    start = _monday(0)
    end = _monday(total_weeks)
    intervention_at = _monday(13)
    prs = []
    for week in range(total_weeks):
        week_start = _monday(week)
        merged_at = week_start + timedelta(days=1)
        for _ in range(3):
            prs.append(
                pr_row(
                    1,
                    len(prs) + 1,
                    created_at=week_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    merged_at=merged_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                )
            )
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=prs,
        draft_lifecycle=[
            draft_row(1, p["pr_number"], first_queue_entry=p["created_at"]) for p in prs
        ],
        as_of=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    return start, end, intervention_at


def test_report_generates_expected_sections_and_charts(tmp_path: Path) -> None:
    """report.md carries every required section and every fixed chart exists."""
    start, end, intervention_at = _build_workdir(tmp_path)
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)
    outcome = report.run_report(workdir_path=tmp_path)

    text = outcome.report_path.read_text(encoding="utf-8")
    for heading in (
        "## Collection freshness",
        "## Observed metrics",
        "## Data coverage",
        "## Modeled structural changes",
        "## Sensitivity results",
        "## Interpretation",
        "## Unsupported claims / limitations",
    ):
        assert heading in text
    assert "AI caused" not in text
    assert "Refresh status: no newer refresh attempt has failed" in text

    chart_names = {p.name for p in outcome.chart_paths}
    assert chart_names == {"delivery.svg", "review.svg", "rework.svg"}
    for path in outcome.chart_paths:
        assert path.exists()
        assert path.stat().st_size > 0


def test_report_is_deterministic_across_runs(tmp_path: Path) -> None:
    """Two report runs over identical input produce byte-identical output."""
    start, end, intervention_at = _build_workdir(tmp_path)
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)

    first = report.run_report(workdir_path=tmp_path)
    first_text = first.report_path.read_text(encoding="utf-8")
    first_charts = {p.name: p.read_bytes() for p in first.chart_paths}

    second = report.run_report(workdir_path=tmp_path)
    second_text = second.report_path.read_text(encoding="utf-8")
    second_charts = {p.name: p.read_bytes() for p in second.chart_paths}

    assert first_text == second_text
    assert first_charts == second_charts


def test_report_omits_ci_chart_when_ci_not_configured(tmp_path: Path) -> None:
    """No ci.svg is produced: CI metrics are out of scope for this PR."""
    start, end, intervention_at = _build_workdir(tmp_path)
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)
    outcome = report.run_report(workdir_path=tmp_path)
    assert not (tmp_path / "report" / "ci.svg").exists()
    assert all(p.name != "ci.svg" for p in outcome.chart_paths)


def test_report_surfaces_failed_refresh_attempt(tmp_path: Path) -> None:
    """A newer incomplete run after the committed one is surfaced in report.md."""
    start, end, intervention_at = _build_workdir(tmp_path)
    workdir.finalize_manifest(
        tmp_path,
        "run2",
        {
            "run_id": "run2",
            "status": "incomplete",
            "organization": "acme",
            "refresh_started_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)
    outcome = report.run_report(workdir_path=tmp_path)
    text = outcome.report_path.read_text(encoding="utf-8")
    assert "Refresh status: a newer refresh attempt failed" in text


def test_report_fails_closed_when_analysis_predates_a_rerun_aggregate(
    tmp_path: Path,
) -> None:
    """Report rejects an analysis.json derived from a different aggregate window."""
    start, end, intervention_at = _build_workdir(tmp_path)
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)
    # Simulate 'aggregate' being rerun with a narrower window after 'analyze'
    # already derived analysis.json from the original window.
    aggregate.run_aggregate(
        workdir_path=tmp_path, start=start + timedelta(days=7), end=end
    )
    with pytest.raises(report.ReportError, match="same derivation"):
        report.run_report(workdir_path=tmp_path)


def test_report_fails_closed_when_normalize_reran_with_new_actor_map(
    tmp_path: Path,
) -> None:
    """Report rejects a re-normalized entity tree it was not derived against."""
    start, end, intervention_at = _build_workdir(tmp_path)
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)
    # Re-run 'normalize' for the same committed run but a different actor map.
    prs = [
        pr_row(
            1,
            i + 1,
            created_at=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            merged_at=(start + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        for i in range(3)
    ]
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=prs,
        as_of=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        actor_classification_fingerprint="different",
    )
    with pytest.raises(report.ReportError, match="normalize"):
        report.run_report(workdir_path=tmp_path)


def test_report_renders_full_its_statistics_and_fitted_trend(tmp_path: Path) -> None:
    """report.md carries beta1/beta2/beta3 with CIs; charts overlay the fit."""
    start, end, intervention_at = _build_workdir(tmp_path)
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)
    outcome = report.run_report(workdir_path=tmp_path)

    text = outcome.report_path.read_text(encoding="utf-8")
    assert "beta1 (pre-trend) [95% CI]" in text
    assert "beta2 (level) [95% CI]" in text
    assert "beta3 (slope change) [95% CI]" in text
    assert "complete pre/post wks" in text
    # The fitted merged_prs row renders a bracketed 95% CI on each coefficient.
    merged_row = next(
        line for line in text.splitlines() if line.startswith("| `merged_prs`")
    )
    assert merged_row.count("[") >= 3
    assert merged_row.count("]") >= 3

    delivery_svg = next(p for p in outcome.chart_paths if p.name == "delivery.svg")
    svg_text = delivery_svg.read_text(encoding="utf-8")
    assert "merged_prs (fitted)" in svg_text
