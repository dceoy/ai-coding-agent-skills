"""Regression tests for fail-fast GitHub collection behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import collect
import workdir

from tests.conftest import FakeGh, make_pr, make_repo

if TYPE_CHECKING:
    from pathlib import Path

_START = datetime(2026, 1, 8, tzinfo=UTC)
_END = datetime(2026, 2, 1, tzinfo=UTC)


def test_bundle_failure_aborts_later_endpoints_and_repositories(
    tmp_path: Path, fake_gh: FakeGh
) -> None:
    """The first failed bundle endpoint stops all remaining live collection."""
    fake_gh.set_list(
        "/orgs/acme/repos", [[make_repo(1, "repo1"), make_repo(2, "repo2")]]
    )
    fake_gh.set_list(
        "/repos/acme/repo1/pulls",
        [[make_pr(7, "2026-01-10T00:00:00Z")]],
        sort="updated",
        direction="desc",
    )
    fake_gh.set_object(
        "/repos/acme/repo1/pulls/7",
        {"base": {"repo": {"id": 1}}, "number": 7, "commits": 0},
    )
    fake_gh.fail("/reviews")

    outcome = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )

    endpoints = [endpoint for _, endpoint, _ in fake_gh.calls]
    assert outcome.status == "incomplete"
    assert outcome.manifest["failures"] == [
        {
            "endpoint": "reviews",
            "repository_id": 1,
            "pr_number": 7,
            "reason": "forced failure for /repos/acme/repo1/pulls/7/reviews",
        }
    ]
    assert "/repos/acme/repo1/pulls/7/reviews" in endpoints
    assert "/repos/acme/repo1/pulls/7/commits" not in endpoints
    assert "/repos/acme/repo1/issues/7/timeline" not in endpoints
    assert not any(endpoint.startswith("/repos/acme/repo2/") for endpoint in endpoints)
    assert workdir.read_state(tmp_path) is None


def test_discovery_failure_aborts_reconciliation_and_later_repositories(
    tmp_path: Path, fake_gh: FakeGh
) -> None:
    """A failed primary discovery scan stops reconciliation and later repos."""
    fake_gh.set_list(
        "/orgs/acme/repos", [[make_repo(1, "repo1"), make_repo(2, "repo2")]]
    )
    fake_gh.fail("/repos/acme/repo1/pulls")

    outcome = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )

    endpoints = [endpoint for _, endpoint, _ in fake_gh.calls]
    assert outcome.status == "incomplete"
    assert outcome.manifest["failures"] == [
        {
            "endpoint": "pulls-backfill",
            "repository_id": 1,
            "pr_number": None,
            "reason": "forced failure for /repos/acme/repo1/pulls",
        }
    ]
    assert "/repos/acme/repo1/pulls" in endpoints
    assert "/repos/acme/repo1/issues" not in endpoints
    assert not any(endpoint.startswith("/repos/acme/repo2/") for endpoint in endpoints)
    assert workdir.read_state(tmp_path) is None
