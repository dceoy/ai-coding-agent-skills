"""Tests for workdir transaction, locking, and lineage primitives."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import workdir

if TYPE_CHECKING:
    from pathlib import Path


def _base_manifest(
    run_id: str, *, status: str = "complete", previous: str | None = None
) -> dict[str, object]:
    """Build a minimal well-formed manifest for lineage tests.

    Args:
        run_id: The run ID this manifest belongs to.
        status: The manifest status.
        previous: The prior committed run ID, if any.

    Returns:
        A manifest dict sufficient for lineage-resolution tests.
    """
    return {
        "schema_version": workdir.SCHEMA_VERSION,
        "run_id": run_id,
        "status": status,
        "previous_committed_run_id": previous,
    }


def test_lock_rejects_second_collector_before_any_work(tmp_path: Path) -> None:
    """A second collector is rejected immediately, without touching state."""
    with (
        workdir.CollectionLock(tmp_path, "run-a"),
        pytest.raises(workdir.WorkdirLockedError),
        workdir.CollectionLock(tmp_path, "run-b"),
    ):
        pytest.fail("second lock must never be acquired")
    assert workdir.read_state(tmp_path) is None


def test_lock_is_released_on_exit(tmp_path: Path) -> None:
    """The lock file is removed once the context manager exits normally."""
    with workdir.CollectionLock(tmp_path, "run-a"):
        assert workdir.lock_path(tmp_path).exists()
    assert not workdir.lock_path(tmp_path).exists()


def test_lock_is_released_on_exception(tmp_path: Path) -> None:
    """The lock file is removed even when the body raises."""
    boom = RuntimeError("boom")
    with pytest.raises(RuntimeError), workdir.CollectionLock(tmp_path, "run-a"):
        raise boom
    assert not workdir.lock_path(tmp_path).exists()


def test_atomic_write_json_round_trips(tmp_path: Path) -> None:
    """Data written atomically reads back unchanged."""
    target = tmp_path / "nested" / "file.json"
    target.parent.mkdir(parents=True)
    workdir.atomic_write_json(target, {"a": 1})
    assert target.read_text(encoding="utf-8").strip().endswith("}")
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}


def test_finalize_manifest_is_write_once(tmp_path: Path) -> None:
    """A finalized manifest can never be silently overwritten."""
    workdir.finalize_manifest(tmp_path, "run-a", _base_manifest("run-a"))
    with pytest.raises(workdir.ManifestAlreadyFinalizedError):
        workdir.finalize_manifest(tmp_path, "run-a", _base_manifest("run-a"))


def test_finalize_manifest_rejects_unknown_status(tmp_path: Path) -> None:
    """A manifest with an unrecognized status is rejected before writing."""
    with pytest.raises(ValueError, match="status"):
        workdir.finalize_manifest(
            tmp_path, "run-a", _base_manifest("run-a", status="bogus")
        )


def test_state_round_trips(tmp_path: Path) -> None:
    """``write_state`` followed by ``read_state`` returns the same data."""
    assert workdir.read_state(tmp_path) is None
    workdir.write_state(tmp_path, {"committed_run_id": "run-a"})
    assert workdir.read_state(tmp_path) == {"committed_run_id": "run-a"}


def test_resolve_committed_lineage_walks_previous_ids(tmp_path: Path) -> None:
    """Lineage resolution follows ``previous_committed_run_id`` back to the root."""
    workdir.finalize_manifest(tmp_path, "run-1", _base_manifest("run-1"))
    workdir.finalize_manifest(
        tmp_path, "run-2", _base_manifest("run-2", previous="run-1")
    )
    workdir.finalize_manifest(
        tmp_path, "run-3", _base_manifest("run-3", previous="run-2")
    )
    lineage = workdir.resolve_committed_lineage(tmp_path, {"committed_run_id": "run-3"})
    assert [m["run_id"] for m in lineage] == ["run-3", "run-2", "run-1"]


def test_resolve_committed_lineage_excludes_orphan_complete_run(tmp_path: Path) -> None:
    """A complete manifest not reachable from committed state is never canonical."""
    workdir.finalize_manifest(tmp_path, "run-1", _base_manifest("run-1"))
    workdir.finalize_manifest(tmp_path, "run-orphan", _base_manifest("run-orphan"))
    lineage = workdir.resolve_committed_lineage(tmp_path, {"committed_run_id": "run-1"})
    assert [m["run_id"] for m in lineage] == ["run-1"]


def test_resolve_committed_lineage_rejects_incomplete_link(tmp_path: Path) -> None:
    """A lineage chain through a non-complete manifest is a broken invariant."""
    workdir.finalize_manifest(
        tmp_path, "run-1", _base_manifest("run-1", status="incomplete")
    )
    with pytest.raises(workdir.CommittedLineageError):
        workdir.resolve_committed_lineage(tmp_path, {"committed_run_id": "run-1"})


def test_resolve_committed_lineage_rejects_missing_manifest(tmp_path: Path) -> None:
    """A committed run ID with no manifest on disk is a broken invariant."""
    with pytest.raises(workdir.CommittedLineageError):
        workdir.resolve_committed_lineage(
            tmp_path, {"committed_run_id": "does-not-exist"}
        )


def test_coverage_gaps_empty_state_is_never_covered() -> None:
    """No committed state means no coverage."""
    gaps = workdir.coverage_gaps(
        None,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
        overlap_hours=24,
        collection_affecting_fingerprint="fp",
    )
    assert gaps


def test_coverage_gaps_fingerprint_mismatch() -> None:
    """A collection-affecting configuration change is an uncovered gap."""
    state = {
        "collection_affecting_fingerprint": "old-fp",
        "repositories": {},
    }
    gaps = workdir.coverage_gaps(
        state,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
        overlap_hours=24,
        collection_affecting_fingerprint="new-fp",
    )
    assert any("configuration" in gap for gap in gaps)


def test_coverage_gaps_fully_covered_repository_has_no_gaps() -> None:
    """A repository whose boundary/watermark fully bracket the interval has no gaps."""
    state = {
        "collection_affecting_fingerprint": "fp",
        "repositories": {
            "1": {
                "history_boundary": datetime(2025, 1, 1, tzinfo=UTC).timestamp(),
                "discovery_watermark": datetime(2026, 3, 1, tzinfo=UTC).timestamp(),
            }
        },
    }
    gaps = workdir.coverage_gaps(
        state,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
        overlap_hours=24,
        collection_affecting_fingerprint="fp",
    )
    assert gaps == []


def test_coverage_gaps_reports_insufficient_history_and_stale_watermark() -> None:
    """A repository behind on either boundary or watermark reports a gap for each."""
    state = {
        "collection_affecting_fingerprint": "fp",
        "repositories": {
            "1": {
                "history_boundary": datetime(2026, 1, 15, tzinfo=UTC).timestamp(),
                "discovery_watermark": datetime(2026, 1, 15, tzinfo=UTC).timestamp(),
            }
        },
    }
    gaps = workdir.coverage_gaps(
        state,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
        overlap_hours=24,
        collection_affecting_fingerprint="fp",
    )
    assert len(gaps) == 2
