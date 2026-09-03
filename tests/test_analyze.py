"""Tests for ITS fitting, guards, and required sensitivity analyses."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import aggregate
import analyze
import pytest

from tests.conftest import (
    draft_row,
    pr_row,
    repo_row,
    write_normalized,
    write_state,
)

if TYPE_CHECKING:
    from pathlib import Path


def _monday(index: int, base: datetime = datetime(2025, 1, 6, tzinfo=UTC)) -> datetime:
    """Return the ``index``-th Monday from a fixed base Monday."""
    return base + timedelta(days=7 * index)


def _synthetic_workdir(
    tmp_path: Path,
    *,
    n_pre_weeks: int,
    n_post_weeks: int,
    level_shift: int,
) -> tuple[Path, datetime, datetime, datetime]:
    """Build a workdir whose weekly ``merged_prs`` count jumps by ``level_shift``.

    Returns ``(workdir_path, start, end, intervention_at)``.
    """
    total_weeks = n_pre_weeks + n_post_weeks
    start = _monday(0)
    intervention_at = _monday(n_pre_weeks)
    end = _monday(total_weeks)
    prs = []
    pr_number = 1
    for week in range(total_weeks):
        week_start = _monday(week)
        count = 2 + (level_shift if week >= n_pre_weeks else 0)
        for _ in range(count):
            merged_at = week_start + timedelta(days=1)
            prs.append(
                pr_row(
                    1,
                    pr_number,
                    created_at=week_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    merged_at=merged_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                )
            )
            pr_number += 1
    write_state(tmp_path, repository_ids=[1])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=prs,
        draft_lifecycle=[
            draft_row(1, p["pr_number"], first_queue_entry=p["created_at"]) for p in prs
        ],
        as_of=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    return tmp_path, start, end, intervention_at


def test_its_recovers_known_level_shift(tmp_path: Path) -> None:
    """A synthetic level shift at the intervention is recovered by beta2."""
    workdir_path, start, end, intervention_at = _synthetic_workdir(
        tmp_path, n_pre_weeks=20, n_post_weeks=20, level_shift=5
    )
    entities = aggregate.load_entities(workdir_path)
    effective_end = aggregate.resolve_effective_observation_end(entities, end)
    panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=effective_end
    )
    time_index = analyze.build_time_index(panel, intervention_at)
    result = analyze.fit_its(panel, time_index, "merged_prs")
    assert result.fitted
    assert result.beta is not None
    assert result.beta["beta2"] == pytest.approx(5.0, abs=0.5)
    assert result.beta["beta3"] == pytest.approx(0.0, abs=0.5)


def test_guard_rejects_insufficient_pre_weeks(tmp_path: Path) -> None:
    """Fewer than 12 pre-intervention complete weeks skips the fit."""
    workdir_path, start, end, intervention_at = _synthetic_workdir(
        tmp_path, n_pre_weeks=5, n_post_weeks=20, level_shift=5
    )
    entities = aggregate.load_entities(workdir_path)
    effective_end = aggregate.resolve_effective_observation_end(entities, end)
    panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=effective_end
    )
    time_index = analyze.build_time_index(panel, intervention_at)
    result = analyze.fit_its(panel, time_index, "merged_prs")
    assert not result.fitted
    assert result.reason == "insufficient_pre_weeks"


def test_guard_rejects_insufficient_post_weeks(tmp_path: Path) -> None:
    """Fewer than 12 post-intervention complete weeks skips the fit."""
    workdir_path, start, end, intervention_at = _synthetic_workdir(
        tmp_path, n_pre_weeks=20, n_post_weeks=5, level_shift=5
    )
    entities = aggregate.load_entities(workdir_path)
    effective_end = aggregate.resolve_effective_observation_end(entities, end)
    panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=effective_end
    )
    time_index = analyze.build_time_index(panel, intervention_at)
    result = analyze.fit_its(panel, time_index, "merged_prs")
    assert not result.fitted
    assert result.reason == "insufficient_post_weeks"


def test_no_intervention_is_descriptive_only(tmp_path: Path) -> None:
    """Omitting --intervention-at never fits ITS for any metric."""
    workdir_path, start, end, _intervention_at = _synthetic_workdir(
        tmp_path, n_pre_weeks=20, n_post_weeks=20, level_shift=5
    )
    entities = aggregate.load_entities(workdir_path)
    effective_end = aggregate.resolve_effective_observation_end(entities, end)
    panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=effective_end
    )
    time_index = analyze.build_time_index(panel, None)
    result = analyze.fit_its(panel, time_index, "merged_prs")
    assert not result.fitted
    assert result.reason == "no_intervention_specified"


def test_mid_week_intervention_excludes_containing_week(tmp_path: Path) -> None:
    """A non-Monday intervention excludes its containing week and rolls p forward."""
    workdir_path, start, end, intervention_at = _synthetic_workdir(
        tmp_path, n_pre_weeks=20, n_post_weeks=20, level_shift=5
    )
    entities = aggregate.load_entities(workdir_path)
    effective_end = aggregate.resolve_effective_observation_end(entities, end)
    panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=effective_end
    )
    mid_week = intervention_at + timedelta(days=2)
    time_index = analyze.build_time_index(panel, mid_week)
    assert time_index.excluded_partial_week == intervention_at
    assert time_index.first_complete_post_week == intervention_at + timedelta(days=7)
    assert intervention_at not in time_index.weeks


def test_leave_one_repository_out_recomputes_from_entities(tmp_path: Path) -> None:
    """Leave-one-out drops a repo's PRs entirely, not by arithmetic subtraction."""
    write_state(tmp_path, repository_ids=[1, 2])
    total_weeks = 26
    start = _monday(0)
    end = _monday(total_weeks)
    intervention_at = _monday(13)
    prs = []
    for week in range(total_weeks):
        week_start = _monday(week)
        merged_at = week_start + timedelta(days=1)
        # Repo 1: steady 2/week. Repo 2: large post-only burst that a naive
        # subtraction of pre-computed aggregate numbers would not reproduce
        # the same way as a true from-entities recompute.
        for repo_id, count in ((1, 2), (2, 10 if week >= 13 else 0)):
            for _ in range(count):
                prs.append(
                    pr_row(
                        repo_id,
                        len(prs) + 1,
                        created_at=week_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        merged_at=merged_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    )
                )
    write_normalized(
        tmp_path,
        repositories=[repo_row(1), repo_row(2)],
        pull_requests=prs,
        draft_lifecycle=[
            draft_row(
                p["repository_id"], p["pr_number"], first_queue_entry=p["created_at"]
            )
            for p in prs
        ],
        as_of=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    entities = aggregate.load_entities(tmp_path)
    effective_end = aggregate.resolve_effective_observation_end(entities, end)
    panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=effective_end
    )
    time_index = analyze.build_time_index(panel, intervention_at)
    result = analyze._leave_one_out(  # pyright: ignore[reportPrivateUsage]
        entities,
        time_index,
        start=start,
        end=end,
        effective_end=effective_end,
        include_forks=False,
    )
    merged_prs = result["merged_prs"]
    assert merged_prs["runs"] == 2
    # Removing repo 2 (the whole post-period burst) must collapse beta2
    # toward zero; removing repo 1 (steady, no burst) leaves a large beta2.
    assert min(merged_prs["beta2_range"]) < 2 < max(merged_prs["beta2_range"])
