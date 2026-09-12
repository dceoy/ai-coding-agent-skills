"""Tests for resumable, shard-level GitHub collection progress."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import collect_resumable
import ghapi
import pytest
import workdir

from tests.conftest import FakeGh, make_pr, make_repo

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

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

    def flaky_paginate(**kwargs: Any) -> Iterator[ghapi.GhApiResponse]:
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
        call
        for call in fake_gh.calls
        if call[1] == "/repos/acme/repo1/pulls"
    ]
    assert len(repo1_backfills) == 1
    committed = workdir.read_state(tmp_path)
    assert committed is not None
    assert committed["committed_run_id"] == second.run_id


def test_rate_limit_resumes_at_first_unfinished_pr_bundle(
    tmp_path: Path, fake_gh: FakeGh, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Completed PR bundles survive a pause inside the same repository."""
    fake_gh.set_list("/orgs/acme/repos", [[make_repo(1, "repo1")]])
    fake_gh.set_list(
        "/repos/acme/repo1/pulls",
        [[
            make_pr(2, "2026-01-10T00:00:00Z"),
            make_pr(1, "2026-01-09T00:00:00Z"),
        ]],
        sort="updated",
        direction="desc",
    )
    for number in (1, 2):
        fake_gh.set_object(
            f"/repos/acme/repo1/pulls/{number}",
            {"base": {"repo": {"id": 1}}, "number": number, "commits": 0},
        )

    delegate = ghapi.request
    failed = False

    def flaky_request(**kwargs: Any) -> ghapi.GhApiResponse:
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
        call
        for call in fake_gh.calls
        if call[1] == "/repos/acme/repo1/pulls/1"
    ]
    assert len(pr1_calls_after_pause) == 1

    second = collect_resumable.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert second.status == "complete"
    assert second.run_id == first.run_id
    pr1_calls_after_resume = [
        call
        for call in fake_gh.calls
        if call[1] == "/repos/acme/repo1/pulls/1"
    ]
    assert len(pr1_calls_after_resume) == 1
    assert second.manifest["repositories"]["1"]["touched_pr_numbers"] == [1, 2]

    raw_path = workdir.raw_dir(tmp_path, second.run_id) / "pulls.ndjson"
    rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert {row["provenance"]["run_id"] for row in rows} == {second.run_id}


def test_non_retryable_failure_finalizes_incomplete_generation(
    tmp_path: Path, fake_gh: FakeGh, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Permanent API errors preserve fail-closed manifest semantics."""
    fake_gh.set_list("/orgs/acme/repos", [[make_repo(1, "repo1")]])
    delegate = ghapi.paginate

    def failing_paginate(**kwargs: Any) -> Iterator[ghapi.GhApiResponse]:
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
