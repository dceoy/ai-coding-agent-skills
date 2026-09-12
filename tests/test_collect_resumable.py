# pyright: reportArgumentType=false, reportPrivateUsage=false
"""Tests for resumable, shard-level GitHub collection progress."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import collect_resumable
import ghapi
import workdir

from tests.conftest import FakeGh, make_pr, make_repo

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    import pytest

_START = datetime(2026, 1, 8, tzinfo=UTC)
_END = datetime(2026, 2, 1, tzinfo=UTC)


def test_rate_limit_resumes_at_first_unfinished_repository(
    tmp_path: Path, fake_gh: FakeGh, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A later repository rate limit does not replay completed repositories."""
    fake_gh.set_list(
        "/orgs/acme/repos",
        [[make_repo(1, "repo1"), make_repo(2, "repo2")]],
    )
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]])
    fake_gh.set_list("/repos/acme/repo2/pulls", [[]])

    delegate = ghapi.paginate
    failed = False

    def flaky_paginate(**kwargs: object) -> Iterator[ghapi.GhApiResponse]:
        nonlocal failed
        endpoint = str(kwargs["endpoint"])
        if endpoint == "/repos/acme/repo2/pulls" and not failed:
            failed = True
            msg = "API rate limit exceeded (HTTP 403)"
            raise ghapi.GhApiError(msg)
        return delegate(**kwargs)

    monkeypatch.setattr(ghapi, "paginate", flaky_paginate)

    first = collect_resumable.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert first.status == "paused"
    assert workdir.read_state(tmp_path) is None
    assert not workdir.manifest_path(tmp_path, first.run_id).exists()
    assert (tmp_path / ".collect.pending.json").exists()

    second = collect_resumable.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert second.status == "complete"
    assert second.run_id == first.run_id
    repo1_backfills = [
        call for call in fake_gh.calls if call[1] == "/repos/acme/repo1/pulls"
    ]
    assert len(repo1_backfills) == 1
    committed = workdir.read_state(tmp_path)
    assert committed is not None
    assert committed["committed_run_id"] == second.run_id


def test_rate_limit_resumes_at_first_unfinished_pr_bundle(
    tmp_path: Path, fake_gh: FakeGh, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Completed PR bundles survive a pause inside the same repository."""
    _configure_two_pr_repository(fake_gh)
    delegate = ghapi.request
    failed = False

    def flaky_request(**kwargs: object) -> ghapi.GhApiResponse:
        nonlocal failed
        endpoint = str(kwargs["endpoint"])
        if endpoint == "/repos/acme/repo1/pulls/2" and not failed:
            failed = True
            msg = "You have exceeded a secondary rate limit (HTTP 403)"
            raise ghapi.GhApiError(msg)
        return delegate(**kwargs)

    monkeypatch.setattr(ghapi, "request", flaky_request)

    first = collect_resumable.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert first.status == "paused"
    pr1_calls_after_pause = [
        call for call in fake_gh.calls if call[1] == "/repos/acme/repo1/pulls/1"
    ]
    assert len(pr1_calls_after_pause) == 1

    second = collect_resumable.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert second.status == "complete"
    assert second.run_id == first.run_id
    pr1_calls_after_resume = [
        call for call in fake_gh.calls if call[1] == "/repos/acme/repo1/pulls/1"
    ]
    assert len(pr1_calls_after_resume) == 1
    assert second.manifest["repositories"]["1"]["touched_pr_numbers"] == [1, 2]

    raw_path = workdir.raw_dir(tmp_path, second.run_id) / "pulls.ndjson"
    rows = [
        json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 2
    assert {row["provenance"]["run_id"] for row in rows} == {second.run_id}


def test_resume_rebuilds_stale_seal_after_new_shards_complete(
    tmp_path: Path, fake_gh: FakeGh, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-manifest stale seal cannot hide shards completed on resume."""
    _configure_two_pr_repository(fake_gh)
    delegate = ghapi.request
    failed = False

    def flaky_request(**kwargs: object) -> ghapi.GhApiResponse:
        nonlocal failed
        endpoint = str(kwargs["endpoint"])
        if endpoint == "/repos/acme/repo1/pulls/2" and not failed:
            failed = True
            msg = "API rate limit exceeded (HTTP 403)"
            raise ghapi.GhApiError(msg)
        return delegate(**kwargs)

    monkeypatch.setattr(ghapi, "request", flaky_request)
    first = collect_resumable.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert first.status == "paused"

    checkpoint = workdir.read_json_object(tmp_path / ".collect.pending.json")
    collect_resumable._materialize_generation_raw(tmp_path, checkpoint)
    stale_path = workdir.raw_dir(tmp_path, first.run_id) / "pulls.ndjson"
    stale_rows = stale_path.read_text(encoding="utf-8").splitlines()
    assert len(stale_rows) == 1

    second = collect_resumable.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert second.status == "complete"
    final_rows = stale_path.read_text(encoding="utf-8").splitlines()
    assert len(final_rows) == 2


def test_completed_shards_are_synced_before_checkpoint(
    tmp_path: Path, fake_gh: FakeGh, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Durable shard markers are never written ahead of their raw evidence."""
    fake_gh.set_list("/orgs/acme/repos", [[make_repo(1, "repo1")]])
    fake_gh.set_list(
        "/repos/acme/repo1/pulls",
        [[make_pr(1, "2026-01-09T00:00:00Z")]],
        sort="updated",
        direction="desc",
    )
    fake_gh.set_object(
        "/repos/acme/repo1/pulls/1",
        {"base": {"repo": {"id": 1}}, "number": 1, "commits": 0},
    )

    synced: set[str] = set()
    real_sync = workdir.sync_raw_evidence
    real_write = collect_resumable._write_checkpoint

    def recording_sync(workdir_path: Path, run_id: str) -> None:
        real_sync(workdir_path, run_id)
        synced.add(run_id)

    def checked_write(workdir_path: Path, checkpoint: dict[str, object]) -> None:
        _assert_completed_shards_synced(checkpoint, synced)
        real_write(workdir_path, checkpoint)

    monkeypatch.setattr(workdir, "sync_raw_evidence", recording_sync)
    monkeypatch.setattr(collect_resumable, "_write_checkpoint", checked_write)

    outcome = collect_resumable.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert outcome.status == "complete"


def test_case_only_organization_change_resumes_checkpoint(
    tmp_path: Path, fake_gh: FakeGh, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GitHub login casing does not discard resumable progress."""
    fake_gh.set_list(
        "/orgs/acme/repos",
        [[make_repo(1, "repo1"), make_repo(2, "repo2")]],
    )
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]])
    fake_gh.set_list("/repos/acme/repo2/pulls", [[]])
    delegate = ghapi.paginate
    failed = False

    def flaky_paginate(**kwargs: object) -> Iterator[ghapi.GhApiResponse]:
        nonlocal failed
        endpoint = str(kwargs["endpoint"])
        if endpoint == "/repos/acme/repo2/pulls" and not failed:
            failed = True
            msg = "API rate limit exceeded (HTTP 403)"
            raise ghapi.GhApiError(msg)
        return delegate(**kwargs)

    monkeypatch.setattr(ghapi, "paginate", flaky_paginate)
    first = collect_resumable.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert first.status == "paused"

    second = collect_resumable.run_collect(
        org="ACME", workdir_path=tmp_path, start=_START, end=_END
    )
    assert second.status == "complete"
    assert second.run_id == first.run_id
    repo1_calls = [
        call for call in fake_gh.calls if call[1] == "/repos/acme/repo1/pulls"
    ]
    assert len(repo1_calls) == 1


def test_non_retryable_failure_finalizes_incomplete_generation(
    tmp_path: Path, fake_gh: FakeGh, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Permanent API errors preserve fail-closed manifest semantics."""
    fake_gh.set_list("/orgs/acme/repos", [[make_repo(1, "repo1")]])
    delegate = ghapi.paginate

    def failing_paginate(**kwargs: object) -> Iterator[ghapi.GhApiResponse]:
        if kwargs["endpoint"] == "/repos/acme/repo1/pulls":
            msg = "gh api failed (HTTP 404): Not Found"
            raise ghapi.GhApiError(msg)
        return delegate(**kwargs)

    monkeypatch.setattr(ghapi, "paginate", failing_paginate)

    outcome = collect_resumable.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert outcome.status == "incomplete"
    assert workdir.manifest_path(tmp_path, outcome.run_id).exists()
    assert not (tmp_path / ".collect.pending.json").exists()
    assert workdir.read_state(tmp_path) is None


def _assert_completed_shards_synced(
    checkpoint: dict[str, object], synced: set[str]
) -> None:
    """Assert that every shard referenced by a checkpoint is already durable."""
    enumeration = checkpoint.get("enumeration_shard_run_id")
    if isinstance(enumeration, str):
        assert enumeration in synced
    progress_map = checkpoint.get("repo_progress")
    if not isinstance(progress_map, dict):
        return
    for progress in progress_map.values():
        if not isinstance(progress, dict):
            continue
        discovery = progress.get("discovery_shard_run_id")
        if isinstance(discovery, str):
            assert discovery in synced
        pr_shards = progress.get("pr_shards")
        if not isinstance(pr_shards, dict):
            continue
        for shard in pr_shards.values():
            if isinstance(shard, dict) and isinstance(shard.get("run_id"), str):
                assert shard["run_id"] in synced


def _configure_two_pr_repository(fake_gh: FakeGh) -> None:
    """Configure one repository with two touched, zero-commit PRs."""
    fake_gh.set_list("/orgs/acme/repos", [[make_repo(1, "repo1")]])
    fake_gh.set_list(
        "/repos/acme/repo1/pulls",
        [
            [
                make_pr(2, "2026-01-10T00:00:00Z"),
                make_pr(1, "2026-01-09T00:00:00Z"),
            ]
        ],
        sort="updated",
        direction="desc",
    )
    for number in (1, 2):
        fake_gh.set_object(
            f"/repos/acme/repo1/pulls/{number}",
            {"base": {"repo": {"id": 1}}, "number": number, "commits": 0},
        )
