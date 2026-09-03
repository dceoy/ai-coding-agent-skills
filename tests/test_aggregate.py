"""Tests for organization-week panel construction."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

import aggregate
import pytest
import workdir

from tests.conftest import (
    commit_rows,
    dismissal_timeline_row,
    draft_row,
    pr_row,
    repo_row,
    review_row,
    unavailable_commit_row,
    write_normalized,
    write_state,
)

if TYPE_CHECKING:
    from pathlib import Path


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_zero_fills_count_metrics_for_inactive_weeks(tmp_path: Path) -> None:
    """A week with no qualifying events reports zero counts, not NA."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[],
    )
    entities = aggregate.load_entities(tmp_path)
    panel = aggregate.build_panel(
        entities,
        start=_ts("2026-01-05T00:00:00Z"),
        end=_ts("2026-01-19T00:00:00Z"),
        effective_observation_end=_ts("2026-01-19T00:00:00Z"),
    )
    assert len(panel.weeks) == 2
    for week in panel.weeks:
        assert week.metrics["opened_prs"] == 0
        assert week.metrics["merged_prs"] == 0


def test_na_for_zero_denominator_rates_and_medians(tmp_path: Path) -> None:
    """A week with no merged PRs reports NA (None), not zero, for rates/medians."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(tmp_path, repositories=[repo_row(1)], pull_requests=[])
    entities = aggregate.load_entities(tmp_path)
    panel = aggregate.build_panel(
        entities,
        start=_ts("2026-01-05T00:00:00Z"),
        end=_ts("2026-01-12T00:00:00Z"),
        effective_observation_end=_ts("2026-01-12T00:00:00Z"),
    )
    metrics = panel.weeks[0].metrics
    assert metrics["median_queue_to_merge"] is None
    assert metrics["human_review_coverage_rate"] is None
    assert metrics["changes_requested_rate"] is None


def test_complete_week_flag_respects_boundaries_and_as_of(tmp_path: Path) -> None:
    """Only weeks fully inside [start, end) and before as_of are complete."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[],
        as_of="2026-01-13T00:00:00Z",
    )
    entities = aggregate.load_entities(tmp_path)
    start = _ts("2026-01-08T00:00:00Z")  # mid-week (Thursday)
    end = _ts("2026-01-26T00:00:00Z")
    effective_end = aggregate.resolve_effective_observation_end(entities, end)
    panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=effective_end
    )
    # Week 1 (Jan 5-12): partial boundary (start mid-week) -> incomplete.
    # Week 2 (Jan 12-19): as_of cutoff (Jan 13) falls inside it -> incomplete.
    # Week 3 (Jan 19-26) is entirely beyond effective_observation_end (Jan 13),
    # so the panel doesn't materialize it at all.
    assert [w.complete_week for w in panel.weeks] == [False, False]


def test_half_open_interval_excludes_end_boundary_event(tmp_path: Path) -> None:
    """A PR created exactly at --end is excluded; one created at --start is included."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[
            pr_row(1, 1, created_at="2026-01-05T00:00:00Z"),
            pr_row(1, 2, created_at="2026-01-12T00:00:00Z"),
        ],
    )
    entities = aggregate.load_entities(tmp_path)
    panel = aggregate.build_panel(
        entities,
        start=_ts("2026-01-05T00:00:00Z"),
        end=_ts("2026-01-12T00:00:00Z"),
        effective_observation_end=_ts("2026-01-12T00:00:00Z"),
    )
    assert len(panel.weeks) == 1
    assert panel.weeks[0].metrics["opened_prs"] == 1


def test_fork_excluded_by_default_included_with_flag(tmp_path: Path) -> None:
    """Forked repositories are excluded from the primary cohort by default."""
    write_state(tmp_path, repository_ids=[1, 2])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1, fork=False), repo_row(2, fork=True)],
        pull_requests=[
            pr_row(1, 1, created_at="2026-01-05T00:00:00Z"),
            pr_row(2, 1, created_at="2026-01-05T00:00:00Z"),
        ],
    )
    entities = aggregate.load_entities(tmp_path)
    start, end = _ts("2026-01-05T00:00:00Z"), _ts("2026-01-12T00:00:00Z")
    default_panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=end
    )
    assert default_panel.weeks[0].metrics["opened_prs"] == 1
    with_forks = aggregate.build_panel(
        entities,
        start=start,
        end=end,
        effective_observation_end=end,
        include_forks=True,
    )
    assert with_forks.weeks[0].metrics["opened_prs"] == 2


def test_actor_class_filter_widens_opened_pr_count(tmp_path: Path) -> None:
    """The 'not-known-bot' author-class set includes unknown-authored PRs."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[
            pr_row(
                1, 1, created_at="2026-01-05T00:00:00Z", author_classification="human"
            ),
            pr_row(
                1, 2, created_at="2026-01-05T00:00:00Z", author_classification="unknown"
            ),
        ],
    )
    entities = aggregate.load_entities(tmp_path)
    start, end = _ts("2026-01-05T00:00:00Z"), _ts("2026-01-12T00:00:00Z")
    primary = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=end
    )
    assert primary.weeks[0].metrics["opened_prs"] == 1
    widened = aggregate.build_panel(
        entities,
        start=start,
        end=end,
        effective_observation_end=end,
        author_classes=aggregate.NOT_KNOWN_BOT_AUTHOR_CLASSES,
    )
    assert widened.weeks[0].metrics["opened_prs"] == 2


def test_history_coverage_gate_fails_closed(tmp_path: Path) -> None:
    """A requested start earlier than committed history_boundary fails closed."""
    write_state(tmp_path, repository_ids=[1], history_boundary="2026-01-01T00:00:00Z")
    write_normalized(tmp_path, repositories=[repo_row(1)], pull_requests=[])
    with pytest.raises(aggregate.AggregateError, match="historical"):
        aggregate.check_history_coverage(
            tmp_path,
            start=_ts("2020-01-01T00:00:00Z"),
            overlap_hours=24,
            repository_ids=None,
        )


def test_changes_requested_reconstructs_pre_dismissal_state(tmp_path: Path) -> None:
    """A dismissed CHANGES_REQUESTED review still counts via timeline replay."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[
            pr_row(
                1,
                1,
                created_at="2026-01-01T00:00:00Z",
                merged_at="2026-01-05T12:00:00Z",
            )
        ],
        reviews=[
            review_row(
                1,
                1,
                101,
                state="DISMISSED",
                submitted_at="2026-01-02T00:00:00Z",
                commit_id="c1",
            )
        ],
        timeline_events=[
            dismissal_timeline_row(
                1,
                1,
                observed_index=0,
                review_id=101,
                pre_dismissal_state="CHANGES_REQUESTED",
            )
        ],
        pr_commits=commit_rows(1, 1, ["c1"]),
        draft_lifecycle=[draft_row(1, 1, first_queue_entry="2026-01-01T00:00:00Z")],
    )
    entities = aggregate.load_entities(tmp_path)
    start, end = _ts("2026-01-01T00:00:00Z"), _ts("2026-01-08T00:00:00Z")
    panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=end
    )
    week = next(w for w in panel.weeks if w.metrics["merged_prs"] == 1)
    assert week.metrics["changes_requested_rate"] == pytest.approx(1.0)


def test_changes_requested_unavailable_when_dismissal_unreconstructable(
    tmp_path: Path,
) -> None:
    """A dismissed review with no recorded pre-dismissal state is unavailable."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[
            pr_row(
                1,
                1,
                created_at="2026-01-01T00:00:00Z",
                merged_at="2026-01-05T12:00:00Z",
            )
        ],
        reviews=[
            review_row(
                1,
                1,
                101,
                state="DISMISSED",
                submitted_at="2026-01-02T00:00:00Z",
                commit_id="c1",
            )
        ],
        timeline_events=[
            dismissal_timeline_row(
                1, 1, observed_index=0, review_id=101, pre_dismissal_state=None
            )
        ],
        pr_commits=commit_rows(1, 1, ["c1"]),
        draft_lifecycle=[draft_row(1, 1, first_queue_entry="2026-01-01T00:00:00Z")],
    )
    entities = aggregate.load_entities(tmp_path)
    start, end = _ts("2026-01-01T00:00:00Z"), _ts("2026-01-08T00:00:00Z")
    panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=end
    )
    week = next(w for w in panel.weeks if w.metrics["merged_prs"] == 1)
    assert week.metrics["changes_requested_rate"] is None
    assert week.metrics["changes_requested_rate_unavailable_n"] == 1


def test_rework_unavailable_when_commits_capped(tmp_path: Path) -> None:
    """A >250-commit-capped PR is excluded from rework, not treated as zero."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[
            pr_row(
                1,
                1,
                created_at="2026-01-01T00:00:00Z",
                merged_at="2026-01-05T12:00:00Z",
            )
        ],
        reviews=[
            review_row(1, 1, 101, submitted_at="2026-01-02T00:00:00Z", commit_id="c1")
        ],
        pr_commits=[unavailable_commit_row(1, 1, "pr_commits_exceed_endpoint_cap")],
        draft_lifecycle=[draft_row(1, 1, first_queue_entry="2026-01-01T00:00:00Z")],
    )
    entities = aggregate.load_entities(tmp_path)
    start, end = _ts("2026-01-01T00:00:00Z"), _ts("2026-01-08T00:00:00Z")
    panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=end
    )
    week = next(w for w in panel.weeks if w.metrics["merged_prs"] == 1)
    assert week.metrics["post_review_commits_per_pr"] is None
    assert week.metrics["post_review_commits_per_pr_unavailable_n"] == 1


def test_rework_unavailable_when_reviewed_commit_missing_after_force_push(
    tmp_path: Path,
) -> None:
    """A reviewed commit no longer present in the PR's commit list is unavailable."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[
            pr_row(
                1,
                1,
                created_at="2026-01-01T00:00:00Z",
                merged_at="2026-01-05T12:00:00Z",
            )
        ],
        reviews=[
            review_row(
                1, 1, 101, submitted_at="2026-01-02T00:00:00Z", commit_id="stale-sha"
            )
        ],
        pr_commits=commit_rows(1, 1, ["new-sha-1", "new-sha-2"]),
        draft_lifecycle=[draft_row(1, 1, first_queue_entry="2026-01-01T00:00:00Z")],
    )
    entities = aggregate.load_entities(tmp_path)
    start, end = _ts("2026-01-01T00:00:00Z"), _ts("2026-01-08T00:00:00Z")
    panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=end
    )
    week = next(w for w in panel.weeks if w.metrics["merged_prs"] == 1)
    assert week.metrics["post_review_commits_per_pr"] is None


def test_queue_latency_never_negative_for_pre_queue_review(tmp_path: Path) -> None:
    """A review submitted before queue entry is not the 'first qualifying' one."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[
            pr_row(
                1,
                1,
                created_at="2026-01-01T00:00:00Z",
                merged_at="2026-01-10T00:00:00Z",
            )
        ],
        reviews=[
            review_row(1, 1, 101, submitted_at="2026-01-01T06:00:00Z", commit_id="c1"),
            review_row(1, 1, 102, submitted_at="2026-01-04T00:00:00Z", commit_id="c1"),
        ],
        pr_commits=commit_rows(1, 1, ["c1"]),
        draft_lifecycle=[draft_row(1, 1, first_queue_entry="2026-01-03T00:00:00Z")],
    )
    entities = aggregate.load_entities(tmp_path)
    start, end = _ts("2026-01-01T00:00:00Z"), _ts("2026-01-12T00:00:00Z")
    panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=end
    )
    week = next(w for w in panel.weeks if w.metrics["merged_prs"] == 1)
    assert week.metrics["median_time_to_first_human_review"] == pytest.approx(24.0)


def test_load_entities_requires_normalize_to_have_run(tmp_path: Path) -> None:
    """Loading entities from a workdir with no normalized/ tree fails closed."""
    with pytest.raises(aggregate.AggregateError):
        aggregate.load_entities(tmp_path)


def test_load_entities_retries_on_concurrent_normalize_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A derivation marker that changes mid-read is retried, not trusted."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(tmp_path, repositories=[repo_row(1)], pull_requests=[])
    monkeypatch.setattr(aggregate.time, "sleep", lambda _seconds: None)
    derivation_reads = iter([
        '{"committed_run_id": "run1"}',
        '{"committed_run_id": "run2"}',
        '{"committed_run_id": "run2"}',
    ])
    monkeypatch.setattr(
        aggregate, "_read_derivation_text", lambda _path: next(derivation_reads)
    )
    entities = aggregate.load_entities(tmp_path)
    assert entities.derivation == {"committed_run_id": "run2"}
    with pytest.raises(StopIteration):
        next(derivation_reads)


def test_load_entities_fails_closed_on_persistent_concurrent_normalize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A derivation marker that never stabilizes fails closed after retries."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(tmp_path, repositories=[repo_row(1)], pull_requests=[])
    monkeypatch.setattr(aggregate.time, "sleep", lambda _seconds: None)
    counter = iter(range(1_000))
    monkeypatch.setattr(
        aggregate,
        "_read_derivation_text",
        lambda _path: f'{{"committed_run_id": "run{next(counter)}"}}',
    )
    with pytest.raises(aggregate.AggregateError, match="running concurrently"):
        aggregate.load_entities(tmp_path)


def test_repository_id_filter_overrides_fork_default(tmp_path: Path) -> None:
    """An explicit repository_ids cohort is used verbatim, ignoring fork status."""
    write_state(tmp_path, repository_ids=[1, 2])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1, fork=False), repo_row(2, fork=True)],
        pull_requests=[pr_row(2, 1, created_at="2026-01-05T00:00:00Z")],
    )
    entities = aggregate.load_entities(tmp_path)
    start, end = _ts("2026-01-05T00:00:00Z"), _ts("2026-01-12T00:00:00Z")
    panel = aggregate.build_panel(
        entities,
        start=start,
        end=end,
        effective_observation_end=end,
        repository_ids=frozenset({2}),
    )
    assert panel.weeks[0].metrics["opened_prs"] == 1


def test_active_repositories_excludes_non_qualifying_activity(tmp_path: Path) -> None:
    """A repo with only bot-authored PRs and only reviews is not counted active."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[
            pr_row(
                1,
                1,
                created_at="2026-01-05T00:00:00Z",
                author_classification="bot",
            )
        ],
        reviews=[review_row(1, 1, 101, submitted_at="2026-01-06T00:00:00Z")],
    )
    entities = aggregate.load_entities(tmp_path)
    panel = aggregate.build_panel(
        entities,
        start=_ts("2026-01-05T00:00:00Z"),
        end=_ts("2026-01-12T00:00:00Z"),
        effective_observation_end=_ts("2026-01-12T00:00:00Z"),
    )
    assert panel.weeks[0].metrics["active_repositories"] == 0


def test_active_repositories_counts_qualifying_open_and_merge(tmp_path: Path) -> None:
    """A qualifying opened PR and a qualifying merge both count as active."""
    write_state(tmp_path, repository_ids=[1, 2])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1), repo_row(2)],
        pull_requests=[
            pr_row(1, 1, created_at="2026-01-05T00:00:00Z"),
            pr_row(
                2,
                1,
                created_at="2026-01-01T00:00:00Z",
                merged_at="2026-01-06T00:00:00Z",
            ),
        ],
        draft_lifecycle=[draft_row(2, 1, first_queue_entry="2026-01-01T00:00:00Z")],
    )
    entities = aggregate.load_entities(tmp_path)
    panel = aggregate.build_panel(
        entities,
        start=_ts("2026-01-05T00:00:00Z"),
        end=_ts("2026-01-12T00:00:00Z"),
        effective_observation_end=_ts("2026-01-12T00:00:00Z"),
    )
    assert panel.weeks[0].metrics["active_repositories"] == 2


def test_queue_to_merge_excludes_out_of_order_queue_entry(tmp_path: Path) -> None:
    """A queue entry reconstructed after merged_at is excluded, not negative."""
    write_state(tmp_path, repository_ids=[1])
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[
            pr_row(
                1,
                1,
                created_at="2026-01-01T00:00:00Z",
                merged_at="2026-01-02T00:00:00Z",
            )
        ],
        draft_lifecycle=[
            draft_row(1, 1, first_queue_entry="2026-01-05T00:00:00Z")  # after merge
        ],
    )
    entities = aggregate.load_entities(tmp_path)
    start, end = _ts("2026-01-01T00:00:00Z"), _ts("2026-01-08T00:00:00Z")
    panel = aggregate.build_panel(
        entities, start=start, end=end, effective_observation_end=end
    )
    week = next(w for w in panel.weeks if w.metrics["merged_prs"] == 1)
    assert week.metrics["median_queue_to_merge"] is None
    assert week.metrics["median_queue_to_merge_n"] == 0


def test_run_aggregate_fails_closed_on_advanced_committed_state(tmp_path: Path) -> None:
    """Aggregate fails closed if state.json advances past normalize's generation."""
    write_state(tmp_path, repository_ids=[1], committed_run_id="run1")
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[],
        committed_run_id="run1",
    )
    # Simulate a concurrent 'collect' committing a newer run after
    # 'normalize' derived entities from run1.
    write_state(tmp_path, repository_ids=[1], committed_run_id="run2")
    with pytest.raises(aggregate.AggregateError, match="advanced"):
        aggregate.run_aggregate(
            workdir_path=tmp_path,
            start=_ts("2026-01-05T00:00:00Z"),
            end=_ts("2026-01-12T00:00:00Z"),
        )


def test_meta_flags_last_refresh_attempt_failed(tmp_path: Path) -> None:
    """A newer incomplete run after the committed one is surfaced in meta.json."""
    write_state(tmp_path, repository_ids=[1], committed_run_id="run1")
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[],
        committed_run_id="run1",
    )
    workdir.finalize_manifest(
        tmp_path,
        "run2",
        {
            "run_id": "run2",
            "status": "incomplete",
            "organization": "acme",
            "refresh_started_at": "2026-01-10T00:00:00Z",
        },
    )
    outcome = aggregate.run_aggregate(
        workdir_path=tmp_path,
        start=_ts("2026-01-05T00:00:00Z"),
        end=_ts("2026-01-12T00:00:00Z"),
    )
    meta = json.loads(outcome.meta_path.read_text(encoding="utf-8"))
    assert meta["last_refresh_attempt_failed"] is True


def test_meta_does_not_flag_failure_when_committed_run_is_latest(
    tmp_path: Path,
) -> None:
    """No newer manifest after the committed run means no failure to surface."""
    write_state(tmp_path, repository_ids=[1], committed_run_id="run1")
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[],
        committed_run_id="run1",
    )
    workdir.finalize_manifest(
        tmp_path,
        "run1",
        {
            "run_id": "run1",
            "status": "complete",
            "organization": "acme",
            "refresh_started_at": "2026-01-05T00:00:00Z",
        },
    )
    outcome = aggregate.run_aggregate(
        workdir_path=tmp_path,
        start=_ts("2026-01-05T00:00:00Z"),
        end=_ts("2026-01-12T00:00:00Z"),
    )
    meta = json.loads(outcome.meta_path.read_text(encoding="utf-8"))
    assert meta["last_refresh_attempt_failed"] is False


def test_meta_records_full_normalized_derivation_identity(tmp_path: Path) -> None:
    """meta.json pins committed run + actor fingerprint + normalizer schema."""
    write_state(tmp_path, repository_ids=[1], committed_run_id="run1")
    write_normalized(
        tmp_path,
        repositories=[repo_row(1)],
        pull_requests=[],
        committed_run_id="run1",
        actor_classification_fingerprint="fp-xyz",
    )
    outcome = aggregate.run_aggregate(
        workdir_path=tmp_path,
        start=_ts("2026-01-05T00:00:00Z"),
        end=_ts("2026-01-12T00:00:00Z"),
    )
    meta = json.loads(outcome.meta_path.read_text(encoding="utf-8"))
    assert meta["normalized_derivation"] == {
        "committed_run_id": "run1",
        "actor_classification_fingerprint": "fp-xyz",
        "normalizer_schema_version": 1,
    }


def test_history_coverage_gate_ignores_excluded_forks(tmp_path: Path) -> None:
    """A fork's insufficient history doesn't block aggregating the non-fork cohort."""
    workdir.write_state(
        tmp_path,
        {
            "schema_version": workdir.SCHEMA_VERSION,
            "committed_run_id": "run1",
            "organization": "acme",
            "repositories": {
                "1": {
                    "name": "repo1",
                    "archived": False,
                    "fork": False,
                    "created_at": "2019-01-01T00:00:00Z",
                    "discovery_watermark": "2026-01-01T00:00:00Z",
                    "history_boundary": "2019-01-01T00:00:00Z",
                    "last_seen_in_enumeration_at": "2026-01-01T00:00:00Z",
                },
                "2": {
                    "name": "repo2",
                    "archived": False,
                    "fork": True,
                    "created_at": "2019-01-01T00:00:00Z",
                    "discovery_watermark": "2026-01-01T00:00:00Z",
                    "history_boundary": "2026-01-08T00:00:00Z",
                    "last_seen_in_enumeration_at": "2026-01-01T00:00:00Z",
                },
            },
        },
    )
    write_normalized(
        tmp_path,
        repositories=[repo_row(1), repo_row(2, fork=True)],
        pull_requests=[],
    )
    outcome = aggregate.run_aggregate(
        workdir_path=tmp_path,
        start=_ts("2026-01-05T00:00:00Z"),
        end=_ts("2026-01-12T00:00:00Z"),
    )
    assert outcome.panel is not None


def test_history_coverage_gate_still_checks_included_forks(tmp_path: Path) -> None:
    """--include-forks widens the coverage gate to match the widened cohort."""
    workdir.write_state(
        tmp_path,
        {
            "schema_version": workdir.SCHEMA_VERSION,
            "committed_run_id": "run1",
            "organization": "acme",
            "repositories": {
                "1": {
                    "name": "repo1",
                    "archived": False,
                    "fork": False,
                    "created_at": "2019-01-01T00:00:00Z",
                    "discovery_watermark": "2026-01-01T00:00:00Z",
                    "history_boundary": "2019-01-01T00:00:00Z",
                    "last_seen_in_enumeration_at": "2026-01-01T00:00:00Z",
                },
                "2": {
                    "name": "repo2",
                    "archived": False,
                    "fork": True,
                    "created_at": "2019-01-01T00:00:00Z",
                    "discovery_watermark": "2026-01-01T00:00:00Z",
                    "history_boundary": "2026-01-08T00:00:00Z",
                    "last_seen_in_enumeration_at": "2026-01-01T00:00:00Z",
                },
            },
        },
    )
    write_normalized(
        tmp_path,
        repositories=[repo_row(1), repo_row(2, fork=True)],
        pull_requests=[],
    )
    with pytest.raises(aggregate.AggregateError, match="historical"):
        aggregate.run_aggregate(
            workdir_path=tmp_path,
            start=_ts("2026-01-05T00:00:00Z"),
            end=_ts("2026-01-12T00:00:00Z"),
            include_forks=True,
        )
