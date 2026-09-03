"""Tests for workdir transaction, locking, and lineage primitives."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import workdir


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


def test_lock_exit_never_deletes_a_lock_it_no_longer_owns(tmp_path: Path) -> None:
    """Releasing a lock this instance no longer owns must not delete it.

    Simulates an operator manually clearing a stale lock (v1 has no
    automatic stale-lock recovery) followed by a different run acquiring
    it, then the original, now-stale ``CollectionLock`` instance exiting.
    """
    original = workdir.CollectionLock(tmp_path, "run-a")
    original.__enter__()  # noqa: PLC2801 -- exercising the protocol without exiting yet
    workdir.lock_path(tmp_path).unlink()
    with workdir.CollectionLock(tmp_path, "run-b"):
        original.__exit__(None, None, None)
        assert workdir.lock_path(tmp_path).exists()
        content = json.loads(workdir.lock_path(tmp_path).read_text(encoding="utf-8"))
        assert content["run_id"] == "run-b"
    assert not workdir.lock_path(tmp_path).exists()


@pytest.mark.parametrize("lock_content", ["null", "[]", '"x"'])
def test_lock_exit_does_not_raise_on_non_object_lock_content(
    tmp_path: Path, lock_content: str
) -> None:
    """A lock file holding valid, non-object JSON is treated as not-ours."""
    lock = workdir.CollectionLock(tmp_path, "run-a")
    lock.__enter__()  # noqa: PLC2801 -- exercising the protocol directly
    workdir.lock_path(tmp_path).write_text(lock_content, encoding="utf-8")
    lock.__exit__(None, None, None)
    assert workdir.lock_path(tmp_path).exists()


def test_lock_enter_cleans_up_touched_file_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write failure after acquiring the lock file does not leak an empty lock."""

    def fail_write(_self: Path, *_args: object, **_kwargs: object) -> int:
        msg = "simulated write failure"
        raise OSError(msg)

    monkeypatch.setattr(Path, "write_text", fail_write)
    with pytest.raises(OSError, match="simulated write failure"):
        workdir.CollectionLock(tmp_path, "run-a").__enter__()  # noqa: PLC2801
    assert not workdir.lock_path(tmp_path).exists()


def test_resolve_committed_lineage_rejects_cycle(tmp_path: Path) -> None:
    """A manifest chain that cycles back to an already-visited run is rejected."""
    workdir.finalize_manifest(
        tmp_path, "run-1", _base_manifest("run-1", previous="run-2")
    )
    workdir.finalize_manifest(
        tmp_path, "run-2", _base_manifest("run-2", previous="run-1")
    )
    with pytest.raises(workdir.CommittedLineageError, match="cycle"):
        workdir.resolve_committed_lineage(tmp_path, {"committed_run_id": "run-1"})
