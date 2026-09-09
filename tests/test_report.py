"""Tests for the fixed chart set and Markdown report generation."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import aggregate
import analyze
import collect
import normalize
import pytest
import report
import workdir
from matplotlib.figure import Figure

from tests.conftest import (
    FakeGh,
    draft_row,
    make_pr,
    make_repo,
    pr_row,
    repo_row,
    write_normalized,
    write_state,
)

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


def test_report_surfaces_orphan_complete_refresh_attempt(tmp_path: Path) -> None:
    """A newer completed-but-uncommitted run is surfaced as orphan, not clean."""
    start, end, intervention_at = _build_workdir(tmp_path)
    workdir.finalize_manifest(
        tmp_path,
        "run2",
        {
            "run_id": "run2",
            "status": "complete",
            "organization": "acme",
            "refresh_started_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)
    outcome = report.run_report(workdir_path=tmp_path)
    text = outcome.report_path.read_text(encoding="utf-8")
    assert "Refresh status: a newer refresh completed but was never committed" in text


def test_refresh_status_distinguishes_committed_successor_from_orphan(
    tmp_path: Path,
) -> None:
    """A newer run that is now the committed head is not mislabeled orphan.

    ``_current_refresh_status`` re-scans manifests on disk against the
    ``meta`` snapshot pinned at aggregate time. If a newer run both
    completed *and* was committed in the window between that pin and
    report generation, it is this workdir's actual committed successor,
    not orphan (finalized-but-uncommitted) evidence.
    """
    start, end, intervention_at = _build_workdir(tmp_path)
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)
    meta = workdir.read_json_object(tmp_path / "report" / "organization-week.meta.json")
    workdir.finalize_manifest(
        tmp_path,
        "run2",
        {
            "run_id": "run2",
            "status": "complete",
            "organization": "acme",
            "refresh_started_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )
    write_state(tmp_path, repository_ids=[1], committed_run_id="run2")
    assert (
        report._current_refresh_status(tmp_path, meta)  # pyright: ignore[reportPrivateUsage]
        == "advanced"
    )


def test_report_fails_closed_on_stale_analyze_schema_version(tmp_path: Path) -> None:
    """Report rejects an analysis.json written by an older analyze schema.

    A future incompatible ``ANALYZE_SCHEMA_VERSION`` bump must not let
    ``report`` silently consume an old-shaped ``analysis.json``.
    """
    start, end, intervention_at = _build_workdir(tmp_path)
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)
    analysis_path = tmp_path / "report" / "analysis.json"
    analysis = workdir.read_json_object(analysis_path)
    analysis["schema_version"] = analyze.ANALYZE_SCHEMA_VERSION - 1
    workdir.atomic_write_json(analysis_path, analysis)
    with pytest.raises(report.ReportError, match="schema_version"):
        report.run_report(workdir_path=tmp_path)


def test_report_fails_closed_on_stale_aggregate_schema_version(tmp_path: Path) -> None:
    """Report rejects an aggregate meta sidecar written by an older schema.

    A future incompatible ``AGGREGATE_SCHEMA_VERSION`` bump must not let
    ``report`` silently consume an old-shaped aggregate meta sidecar, even
    though ``analysis.json`` still matches ``ANALYZE_SCHEMA_VERSION``.
    """
    start, end, intervention_at = _build_workdir(tmp_path)
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)
    meta_path = tmp_path / "report" / "organization-week.meta.json"
    meta = workdir.read_json_object(meta_path)
    meta["schema_version"] = aggregate.AGGREGATE_SCHEMA_VERSION - 1
    workdir.atomic_write_json(meta_path, meta)
    with pytest.raises(report.ReportError, match="schema_version"):
        report.run_report(workdir_path=tmp_path)


def test_report_fails_closed_when_normalize_force_rewrites_entities_in_place(
    tmp_path: Path,
) -> None:
    """Reject a stale aggregate/analysis/report after a same-identity force-renormalize.

    Regression: ``normalized_derivation_identity()`` used to reduce identity
    to ``(committed_run_id, actor_classification_fingerprint,
    normalizer_schema_version)``, so ``normalize --force`` rewriting entity
    bytes under an otherwise-unchanged identity was indistinguishable from
    the prior generation -- ``report`` could rebuild a panel from the new
    entities while ``organization-week.csv``/``analysis.json`` still came
    from the old generation. Comparing ``entity_sha256`` closes that gap.
    """
    start, end, intervention_at = _build_workdir(tmp_path)
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)
    report.run_report(workdir_path=tmp_path)

    # Simulate 'normalize --force' rewriting entity bytes (an extra PR) while
    # keeping the committed run, actor fingerprint, and normalizer schema
    # version unchanged -- only entity_sha256 drifts.
    week0_created = _monday(0).strftime("%Y-%m-%dT%H:%M:%SZ")
    week0_merged = (_monday(0) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[
            *[
                pr_row(1, n + 1, created_at=week0_created, merged_at=week0_merged)
                for n in range(3)
            ],
            pr_row(1, 999, created_at=week0_created, merged_at=week0_merged),
        ],
        as_of=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    with pytest.raises(report.ReportError, match=re.escape("'normalize' has re-run")):
        report.run_report(workdir_path=tmp_path)


def test_report_invalidates_report_md_before_chart_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rerun that fails partway through chart drawing leaves no stale report.md.

    Regression: ``report.md`` previously stayed on disk from a prior
    successful run even when a rerun failed while replacing a later chart,
    leaving it pointing at a mixed old/new chart set. ``report.md`` is now
    unlinked before any chart is replaced, so a mid-generation failure
    leaves no report at all rather than one that misdescribes stale charts.
    """
    start, end, intervention_at = _build_workdir(tmp_path)
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)
    first = report.run_report(workdir_path=tmp_path)
    assert first.report_path.exists()

    calls = {"n": 0}
    original_draw_chart = report._draw_chart  # pyright: ignore[reportPrivateUsage]

    def _failing_draw_chart(*args: object, **kwargs: object) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            msg = "simulated chart failure"
            raise RuntimeError(msg)
        original_draw_chart(*args, **kwargs)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(report, "_draw_chart", _failing_draw_chart)
    with pytest.raises(RuntimeError, match="simulated chart failure"):
        report.run_report(workdir_path=tmp_path)

    assert not first.report_path.exists()


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


def test_report_fails_closed_when_state_advanced_past_aggregate(
    tmp_path: Path,
) -> None:
    """Report rejects a newer committed run 'collect' left unaggregated.

    Regression for a gap where ``report`` only compared ``analyze``'s
    recorded derivation against the current ``aggregate`` sidecar, and never
    re-pinned the currently committed ``state.json``. A successful
    ``collect`` that commits a newer run after ``analyze`` but before
    ``report`` must not be silently ignored.
    """
    start, end, intervention_at = _build_workdir(tmp_path)
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    analyze.run_analyze(workdir_path=tmp_path, intervention_at=intervention_at)
    # Simulate a later successful 'collect' committing a newer run before
    # 'aggregate'/'analyze' rerun.
    write_state(tmp_path, repository_ids=[1], committed_run_id="run2")
    with pytest.raises(report.ReportError, match="committed state advanced"):
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


def test_fractional_windows_round_trip_entire_pipeline(
    tmp_path: Path, fake_gh: FakeGh
) -> None:
    """API evidence yields identical half-open panels at every derivation stage."""
    start = datetime.fromisoformat("2026-01-05T00:00:00.500000Z")
    end = datetime.fromisoformat("2026-01-12T00:00:00.500000Z")
    fake_gh.set_list("/orgs/acme/repos", [[make_repo(1, "repo1")]])
    fake_gh.set_list(
        "/repos/acme/repo1/pulls",
        [[make_pr(n, "2026-01-20T00:00:00Z") for n in (1, 2)]],
    )
    for number, created in [(1, "2026-01-05T00:00:00Z"), (2, "2026-01-12T00:00:00Z")]:
        fake_gh.set_object(
            f"/repos/acme/repo1/pulls/{number}",
            {
                "number": number,
                "base": {"repo": {"id": 1}},
                "commits": 1,
                "created_at": created,
                "merged_at": "2026-01-06T00:00:00Z" if number == 1 else None,
                "draft": False,
                "state": "closed" if number == 1 else "open",
                "user": {"id": 1, "login": "alice", "type": "User"},
            },
        )
        fake_gh.set_list(f"/repos/acme/repo1/pulls/{number}/commits", [[{"sha": "c1"}]])
    collected = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=start, end=end
    )
    assert collected.status == "complete"
    assert (
        datetime.fromisoformat(collected.manifest["requested_interval"]["start"])
        == start
    )
    assert (
        datetime.fromisoformat(collected.manifest["requested_interval"]["end"]) == end
    )
    normalize.run_normalize(workdir_path=tmp_path)
    result = aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)
    expected = aggregate.panel_to_rows(result.panel)
    assert [row["opened_prs"] for row in expected] == [0, 1]
    assert [row["complete_week"] for row in expected] == [False, False]
    analysis = analyze.run_analyze(
        workdir_path=tmp_path, intervention_at=start
    ).analysis
    assert analysis["sensitivities"]["actor"]["rows"] == expected
    assert datetime.fromisoformat(analysis["intervention_at"]) == start
    meta = workdir.read_json_object(result.meta_path)
    assert report._rebuild_panel_rows(tmp_path, meta)[0] == expected  # pyright: ignore[reportPrivateUsage]
    generated = report.run_report(workdir_path=tmp_path).report_path.read_text(
        encoding="utf-8"
    )
    assert "post-period conditioned" in generated
    assert "not the primary estimand" in generated
    assert "no_qualifying_two_sided_repositories" in generated


def test_failed_aggregate_regeneration_invalidates_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interrupted CSV/meta replacement cannot advertise a mixed valid generation."""
    start, end, _ = _build_workdir(tmp_path)
    aggregate.run_aggregate(workdir_path=tmp_path, start=start, end=end)

    def fail_scan(_path: Path) -> None:
        msg = "simulated scan failure"
        raise OSError(msg)

    monkeypatch.setattr(workdir, "latest_manifest_run_id_and_status", fail_scan)
    with pytest.raises(OSError, match="simulated scan failure"):
        aggregate.run_aggregate(
            workdir_path=tmp_path, start=start + timedelta(days=7), end=end
        )
    assert not (tmp_path / "report" / "organization-week.meta.json").exists()
    with pytest.raises(analyze.AnalyzeError, match="aggregate"):
        analyze.run_analyze(workdir_path=tmp_path)


@pytest.mark.parametrize("values", [[1.0, None, 3.0], [None, None, None]])
def test_charts_preserve_missing_week_gaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: list[float | None]
) -> None:
    """Unavailable weeks stay as gaps on a calendar axis, not interpolated lines."""
    figures = []
    close = report.plt.close

    def record_close(figure: Figure | int | str | None) -> None:
        if isinstance(figure, Figure):
            figures.append(figure)
        close(figure)

    monkeypatch.setattr(report.plt, "close", record_close)
    weeks = [_monday(i) for i in range(3)]
    report._draw_chart(  # pyright: ignore[reportPrivateUsage]
        tmp_path / "chart.svg",
        weeks,
        {"metric": values},
        title="Test",
        intervention_at=None,
    )
    line = figures[-1].axes[0].lines[0]
    assert len(line.get_xdata()) == 3
    assert math.isnan(line.get_ydata()[1])
    assert (
        figures[-1].axes[0].get_xlim()[0] > 19000
    )  # Calendar dates, not default 0..1.
