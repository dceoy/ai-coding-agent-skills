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


def test_atomic_write_ndjson_replaces_whole_file_deterministically(
    tmp_path: Path,
) -> None:
    """Each write fully replaces the file with sorted-key one-line-per-row JSON."""
    target = tmp_path / "nested" / "rows.ndjson"
    workdir.atomic_write_ndjson(target, [{"b": 2, "a": 1}, {"c": 3}])
    assert target.read_text(encoding="utf-8") == '{"a": 1, "b": 2}\n{"c": 3}\n'
    workdir.atomic_write_ndjson(target, [{"z": 9}])
    assert target.read_text(encoding="utf-8") == '{"z": 9}\n'
    workdir.atomic_write_ndjson(target, [])
    assert not target.read_text(encoding="utf-8")
    assert not any(
        p.name.startswith("rows.ndjson.tmp.") for p in target.parent.iterdir()
    )


def test_atomic_writers_clean_up_temp_file_on_serialization_failure(
    tmp_path: Path,
) -> None:
    """A non-serializable payload raises and leaves no orphan temp file behind."""
    ndjson_target = tmp_path / "rows.ndjson"
    with pytest.raises(TypeError):
        workdir.atomic_write_ndjson(ndjson_target, [{"ok": 1}, {"bad": object()}])
    assert not ndjson_target.exists()

    json_target = tmp_path / "doc.json"
    with pytest.raises(TypeError):
        workdir.atomic_write_json(json_target, {"bad": object()})
    assert not json_target.exists()
    assert list(tmp_path.iterdir()) == []


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
    with workdir.CollectionLock(tmp_path, "run-a"):
        workdir.lock_path(tmp_path).write_text(lock_content, encoding="utf-8")
    assert workdir.lock_path(tmp_path).exists()


def test_lock_enter_cleans_up_touched_file_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write failure after acquiring the lock file does not leak an empty lock."""

    def fail_write(_self: Path, *_args: object, **_kwargs: object) -> int:
        msg = "simulated write failure"
        raise OSError(msg)

    monkeypatch.setattr(Path, "write_text", fail_write)
    with (
        pytest.raises(OSError, match="simulated write failure"),
        workdir.CollectionLock(tmp_path, "run-a"),
    ):
        pass
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


def test_manifest_organizations_tolerates_non_object_manifest_json(
    tmp_path: Path,
) -> None:
    """A foreign or tampered manifest file that isn't a JSON object is skipped."""
    workdir.finalize_manifest(
        tmp_path, "run-1", {**_base_manifest("run-1"), "organization": "acme"}
    )
    (workdir.manifests_dir(tmp_path) / "not-a-manifest.json").write_text(
        "[]", encoding="utf-8"
    )
    assert workdir.manifest_organizations(tmp_path) == {"acme"}


def test_latest_manifest_run_id_and_status_returns_none_when_empty(
    tmp_path: Path,
) -> None:
    """No manifests yet means no latest run to report."""
    assert workdir.latest_manifest_run_id_and_status(tmp_path) is None


def test_latest_manifest_run_id_and_status_picks_highest_run_id(
    tmp_path: Path,
) -> None:
    """With no timestamps to compare, the run ID is the deterministic tiebreak."""
    workdir.finalize_manifest(tmp_path, "run-1", _base_manifest("run-1"))
    workdir.finalize_manifest(
        tmp_path, "run-2", _base_manifest("run-2", status="incomplete")
    )
    assert workdir.latest_manifest_run_id_and_status(tmp_path) == (
        "run-2",
        "incomplete",
    )


def test_latest_manifest_orders_by_refresh_started_at_not_run_id(
    tmp_path: Path,
) -> None:
    """Two runs started in the same second sort by refresh_started_at, not run ID.

    ``new_run_id`` is ``<second-resolution-timestamp>-<random-suffix>``, so
    the random suffix -- not chronology -- decides lexicographic order when
    two runs start in the same second. The run that actually started later
    must win even though its run ID sorts *first*.
    """
    earlier_by_clock_later_by_id = "20260301T120000Z-0000"
    later_by_clock_earlier_by_id = "20260301T120000Z-ffff"
    workdir.finalize_manifest(
        tmp_path,
        later_by_clock_earlier_by_id,
        {
            **_base_manifest(later_by_clock_earlier_by_id),
            "refresh_started_at": "2026-03-01T12:00:00.100000+00:00",
        },
    )
    workdir.finalize_manifest(
        tmp_path,
        earlier_by_clock_later_by_id,
        {
            **_base_manifest(earlier_by_clock_later_by_id, status="incomplete"),
            "refresh_started_at": "2026-03-01T12:00:00.900000+00:00",
        },
    )
    # Lexicographic run-id order would pick "...-ffff" ("complete"); the true
    # latest by wall clock is "...-0000" ("incomplete").
    assert workdir.latest_manifest_run_id_and_status(tmp_path) == (
        earlier_by_clock_later_by_id,
        "incomplete",
    )


def test_latest_manifest_skips_unreadable_manifest(tmp_path: Path) -> None:
    """One corrupt manifest is skipped, not fatal to the freshness signal."""
    workdir.finalize_manifest(
        tmp_path,
        "20260301T120000Z-aaaa",
        {
            **_base_manifest("20260301T120000Z-aaaa"),
            "refresh_started_at": "2026-03-01T12:00:00+00:00",
        },
    )
    (workdir.manifests_dir(tmp_path) / "20260302T120000Z-bbbb.json").write_text(
        "{ not json", encoding="utf-8"
    )
    assert workdir.latest_manifest_run_id_and_status(tmp_path) == (
        "20260301T120000Z-aaaa",
        "complete",
    )


def test_read_organization_binding_is_none_before_any_binding(
    tmp_path: Path,
) -> None:
    """A workdir with no binding yet reports no bound organization."""
    assert workdir.read_organization_binding(tmp_path) is None


def test_bind_organization_round_trips(tmp_path: Path) -> None:
    """A bound organization is readable back from a fresh workdir."""
    workdir.bind_organization(tmp_path, "acme")
    assert workdir.read_organization_binding(tmp_path) == "acme"


def test_bind_organization_is_immutable_once_set(tmp_path: Path) -> None:
    """A second bind call never overwrites the first-recorded organization.

    This is what protects a workdir even when the run that first bound it
    is killed before any manifest, even an incomplete one, is finalized.
    """
    workdir.bind_organization(tmp_path, "acme")
    workdir.bind_organization(tmp_path, "other-org")
    assert workdir.read_organization_binding(tmp_path) == "acme"


def test_read_organization_binding_fails_closed_on_non_object_json(
    tmp_path: Path,
) -> None:
    """A tampered binding file that isn't a JSON object must not read as unbound.

    Treating a corrupted binding the same as "no binding" would let a run
    for a different organization silently pass the guard this binding
    exists to enforce.
    """
    path = workdir.organization_binding_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(workdir.OrganizationMismatchError):
        workdir.read_organization_binding(tmp_path)


def test_read_organization_binding_fails_closed_on_malformed_json(
    tmp_path: Path,
) -> None:
    """A tampered binding file that isn't valid JSON must not read as unbound."""
    path = workdir.organization_binding_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(workdir.OrganizationMismatchError):
        workdir.read_organization_binding(tmp_path)


def test_resolve_collector_revision_returns_a_commit_sha_in_this_checkout() -> None:
    """Inside this git checkout, the collector's own HEAD SHA is resolvable."""
    revision = workdir.resolve_collector_revision()
    assert revision is not None
    assert len(revision) == 40
    assert all(char in "0123456789abcdef" for char in revision)


def test_resolve_collector_revision_tolerates_missing_git(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing ``git`` binary is a best-effort ``None``, not a crash."""

    def fake_run(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(workdir.subprocess, "run", fake_run)
    assert workdir.resolve_collector_revision() is None
