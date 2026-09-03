"""Tests for repository/PR discovery, reconciliation, and bundle collection."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import collect
import ghapi
import pytest
import workdir

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _FakeGh:
    """Deterministic stand-in for :mod:`ghapi`'s ``paginate``/``request``."""

    list_pages: dict[tuple[str, str | None, str | None], list[list[dict[str, Any]]]] = (
        field(default_factory=dict)
    )
    objects: dict[str, Any] = field(default_factory=dict)
    failing_substrings: set[str] = field(default_factory=set)
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def set_list(
        self,
        endpoint: str,
        pages: list[list[dict[str, Any]]],
        *,
        sort: str | None = None,
        direction: str | None = None,
    ) -> None:
        """Register the pages a matching paginated call should return."""
        self.list_pages[endpoint, sort, direction] = pages

    def set_object(self, endpoint: str, payload: Any) -> None:  # noqa: ANN401
        """Register the payload a non-paginated call should return."""
        self.objects[endpoint] = payload

    def fail(self, substring: str) -> None:
        """Force any call whose endpoint contains ``substring`` to error."""
        self.failing_substrings.add(substring)

    def paginate(
        self,
        *,
        endpoint: str,
        params: dict[str, Any],
        repository_id: int | None,  # noqa: ARG002
        run_id: str,  # noqa: ARG002
        per_page: int = 100,  # noqa: ARG002
    ) -> Any:  # noqa: ANN401
        """Fake replacement for ``ghapi.paginate``."""
        self.calls.append(("paginate", endpoint, dict(params)))
        if any(tag in endpoint for tag in self.failing_substrings):
            msg = f"forced failure for {endpoint}"
            raise ghapi.GhApiError(msg)
        key = (endpoint, params.get("sort"), params.get("direction"))
        pages = self.list_pages.get(
            key, self.list_pages.get((endpoint, None, None), [[]])
        )
        return (
            ghapi.GhApiResponse(
                payload=page, provenance={"endpoint": endpoint, "params": dict(params)}
            )
            for page in pages
        )

    def request(
        self,
        *,
        endpoint: str,
        params: dict[str, Any],
        repository_id: int | None,  # noqa: ARG002
        run_id: str,  # noqa: ARG002
    ) -> ghapi.GhApiResponse:
        """Fake replacement for ``ghapi.request``."""
        self.calls.append(("request", endpoint, dict(params)))
        if any(tag in endpoint for tag in self.failing_substrings):
            msg = f"forced failure for {endpoint}"
            raise ghapi.GhApiError(msg)
        return ghapi.GhApiResponse(
            payload=self.objects.get(endpoint, {}), provenance={"endpoint": endpoint}
        )


def _repo(
    repo_id: int, name: str, *, archived: bool = False, fork: bool = False
) -> dict[str, Any]:
    """Build a minimal repository enumeration item."""
    return {
        "id": repo_id,
        "name": name,
        "full_name": f"acme/{name}",
        "archived": archived,
        "fork": fork,
        "created_at": "2020-01-01T00:00:00Z",
    }


def _pr(number: int, updated_at: str, *, is_pr: bool = True) -> dict[str, Any]:
    """Build a minimal issues/pulls list item."""
    item: dict[str, Any] = {"number": number, "updated_at": updated_at}
    if is_pr:
        item["pull_request"] = {}
    return item


@pytest.fixture
def fake_gh(monkeypatch: pytest.MonkeyPatch) -> _FakeGh:
    """Patch :mod:`ghapi` with a deterministic fake for one test."""
    fake = _FakeGh()
    monkeypatch.setattr(ghapi, "paginate", fake.paginate)
    monkeypatch.setattr(ghapi, "request", fake.request)
    return fake


_START = datetime(2026, 1, 8, tzinfo=UTC)
_END = datetime(2026, 2, 1, tzinfo=UTC)


def test_initial_backfill_stops_at_boundary_via_descending_sort(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """Backfill discovery pages newest-first and stops below the required boundary."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list(
        "/repos/acme/repo1/pulls",
        [[_pr(5, "2026-01-10T00:00:00Z"), _pr(4, "2026-01-06T00:00:00Z")]],
        sort="updated",
        direction="desc",
    )
    fake_gh.set_object("/repos/acme/repo1/pulls/5", {"number": 5, "commits": 0})
    outcome = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert outcome.status == "complete"
    assert outcome.manifest["repositories"]["1"]["touched_pr_numbers"] == [5]
    pulls_calls = [c for c in fake_gh.calls if c[1] == "/repos/acme/repo1/pulls"]
    assert pulls_calls[0][2]["sort"] == "updated"
    assert pulls_calls[0][2]["direction"] == "desc"


def test_backward_range_expansion_triggers_backfill(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """A committed boundary newer than the newly requested start triggers backfill."""
    workdir.write_state(
        tmp_path,
        {
            "committed_run_id": "prior",
            "organization": "acme",
            "collection_affecting_fingerprint": (
                collect.collection_affecting_fingerprint([])
            ),
            "repositories": {
                "1": {
                    "name": "repo1",
                    "archived": False,
                    "fork": False,
                    "created_at": "2020-01-01T00:00:00Z",
                    "discovery_watermark": "2026-01-20T00:00:00Z",
                    "history_boundary": "2026-01-15T00:00:00Z",
                }
            },
        },
    )
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]], sort="updated", direction="desc")
    collect.run_collect(org="acme", workdir_path=tmp_path, start=_START, end=_END)
    pulls_calls = [c for c in fake_gh.calls if c[1] == "/repos/acme/repo1/pulls"]
    assert pulls_calls, (
        "backfill must run because the requested start precedes the committed boundary"
    )


def test_incremental_discovery_uses_created_ascending_since_watermark(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """Incremental discovery pages Issues since the watermark, ascending by creation."""
    workdir.write_state(
        tmp_path,
        {
            "committed_run_id": "prior",
            "organization": "acme",
            "collection_affecting_fingerprint": (
                collect.collection_affecting_fingerprint([])
            ),
            "repositories": {
                "1": {
                    "name": "repo1",
                    "archived": False,
                    "fork": False,
                    "created_at": "2020-01-01T00:00:00Z",
                    "discovery_watermark": "2026-01-05T00:00:00Z",
                    "history_boundary": "2020-01-01T00:00:00Z",
                }
            },
        },
    )
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list(
        "/repos/acme/repo1/issues",
        [[_pr(9, "2026-01-06T00:00:00Z")]],
        sort="created",
        direction="asc",
    )
    outcome = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    incremental_calls = [
        c
        for c in fake_gh.calls
        if c[1] == "/repos/acme/repo1/issues" and c[2].get("sort") == "created"
    ]
    assert incremental_calls[0][2]["since"] == "2026-01-04T00:00:00Z"
    assert 9 in outcome.manifest["repositories"]["1"]["touched_pr_numbers"]


def test_reconciliation_adds_pr_missed_by_incremental_scan(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """The always-run reconciliation pass unions in PRs the primary scan missed."""
    workdir.write_state(
        tmp_path,
        {
            "committed_run_id": "prior",
            "organization": "acme",
            "collection_affecting_fingerprint": (
                collect.collection_affecting_fingerprint([])
            ),
            "repositories": {
                "1": {
                    "name": "repo1",
                    "archived": False,
                    "fork": False,
                    "created_at": "2020-01-01T00:00:00Z",
                    "discovery_watermark": "2026-01-05T00:00:00Z",
                    "history_boundary": "2020-01-01T00:00:00Z",
                }
            },
        },
    )
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list(
        "/repos/acme/repo1/issues",
        [[_pr(10, "2026-01-06T00:00:00Z")]],
        sort="created",
        direction="asc",
    )
    fake_gh.set_list(
        "/repos/acme/repo1/issues",
        [[_pr(7, "2026-01-06T00:00:00Z")]],
        sort="updated",
        direction="asc",
    )
    outcome = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert set(outcome.manifest["repositories"]["1"]["touched_pr_numbers"]) == {7, 10}


def test_non_pr_issues_are_filtered_out(tmp_path: Path, fake_gh: _FakeGh) -> None:
    """Issues without a ``pull_request`` key are never treated as touched PRs."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]], sort="updated", direction="desc")
    fake_gh.set_list(
        "/repos/acme/repo1/issues",
        [
            [
                _pr(11, "2026-01-08T00:00:00Z", is_pr=False),
                _pr(12, "2026-01-08T00:00:00Z"),
            ]
        ],
        sort="updated",
        direction="asc",
    )
    outcome = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert outcome.manifest["repositories"]["1"]["touched_pr_numbers"] == [12]


def test_failed_bundle_fetch_leaves_committed_state_unchanged(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """A failed refresh leaves state.json unchanged and excluded from lineage."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]], sort="updated", direction="desc")
    first = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert first.status == "complete"
    committed_before = workdir.read_state(tmp_path)

    fake_gh.set_list(
        "/repos/acme/repo1/issues",
        [[_pr(20, "2026-01-15T00:00:00Z")]],
        sort="created",
        direction="asc",
    )
    fake_gh.fail("/reviews")
    second = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert second.status == "incomplete"
    assert second.manifest["failures"]
    assert workdir.read_state(tmp_path) == committed_before


def test_interruption_before_manifest_finalization_leaves_no_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_gh: _FakeGh
) -> None:
    """A crash before finalization leaves no manifest and releases the lock."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])

    def _boom(_ctx: object) -> None:
        msg = "simulated crash"
        raise RuntimeError(msg)

    monkeypatch.setattr(collect, "fetch_organization_repositories", _boom)
    with pytest.raises(RuntimeError, match="simulated crash"):
        collect.run_collect(org="acme", workdir_path=tmp_path, start=_START, end=_END)
    assert not list(workdir.manifests_dir(tmp_path).glob("*.json"))
    assert not workdir.lock_path(tmp_path).exists()


def test_crash_after_finalization_before_state_commit_leaves_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_gh: _FakeGh
) -> None:
    """A crash after finalization but before the state commit leaves an orphan run."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]], sort="updated", direction="desc")
    original_write_state = workdir.write_state

    def _boom(*_args: object, **_kwargs: object) -> None:
        msg = "simulated crash before state commit"
        raise RuntimeError(msg)

    monkeypatch.setattr(workdir, "write_state", _boom)
    with pytest.raises(RuntimeError, match="simulated crash before state commit"):
        collect.run_collect(org="acme", workdir_path=tmp_path, start=_START, end=_END)
    orphan_manifests = list(workdir.manifests_dir(tmp_path).glob("*.json"))
    assert len(orphan_manifests) == 1
    assert workdir.read_state(tmp_path) is None

    monkeypatch.setattr(workdir, "write_state", original_write_state)
    second = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert second.status == "complete"
    assert second.manifest["previous_committed_run_id"] is None
    committed = workdir.read_state(tmp_path)
    assert committed is not None
    assert committed["committed_run_id"] == second.run_id


def test_archived_and_fork_repositories_are_retained(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """Archived repositories and forks are both enumerated and collected."""
    fake_gh.set_list(
        "/orgs/acme/repos",
        [[_repo(1, "archived-repo", archived=True), _repo(2, "fork-repo", fork=True)]],
    )
    fake_gh.set_list(
        "/repos/acme/archived-repo/pulls", [[]], sort="updated", direction="desc"
    )
    fake_gh.set_list(
        "/repos/acme/fork-repo/pulls", [[]], sort="updated", direction="desc"
    )
    outcome = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert outcome.manifest["repositories"]["1"]["archived"] is True
    assert outcome.manifest["repositories"]["2"]["fork"] is True
    repos_call = next(c for c in fake_gh.calls if c[1] == "/orgs/acme/repos")
    assert repos_call[2]["type"] == "all", (
        "enumeration must not filter out archived/forks"
    )


def test_repository_rename_preserves_single_state_entry(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """A repository rename updates the existing state entry, never duplicates it."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "old-name")]])
    fake_gh.set_list(
        "/repos/acme/old-name/pulls", [[]], sort="updated", direction="desc"
    )
    collect.run_collect(org="acme", workdir_path=tmp_path, start=_START, end=_END)

    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "new-name")]])
    fake_gh.set_list(
        "/repos/acme/new-name/pulls", [[]], sort="updated", direction="desc"
    )
    collect.run_collect(org="acme", workdir_path=tmp_path, start=_START, end=_END)

    state = workdir.read_state(tmp_path)
    assert state is not None
    assert list(state["repositories"].keys()) == ["1"]
    assert state["repositories"]["1"]["name"] == "new-name"


def test_repository_missing_from_enumeration_keeps_prior_evidence(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """A repository that later disappears from enumeration keeps its retained state."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1"), _repo(2, "repo2")]])
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]], sort="updated", direction="desc")
    fake_gh.set_list("/repos/acme/repo2/pulls", [[]], sort="updated", direction="desc")
    collect.run_collect(org="acme", workdir_path=tmp_path, start=_START, end=_END)

    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    collect.run_collect(org="acme", workdir_path=tmp_path, start=_START, end=_END)

    state = workdir.read_state(tmp_path)
    assert state is not None
    assert set(state["repositories"].keys()) == {"1", "2"}


def test_watermark_advances_to_refresh_started_at_not_max_updated_at(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """The watermark is refresh_started_at, never the max observed updated_at."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list(
        "/repos/acme/repo1/pulls",
        [[_pr(1, "2030-06-15T00:00:00Z")]],
        sort="updated",
        direction="desc",
    )
    fake_gh.set_object("/repos/acme/repo1/pulls/1", {"number": 1, "commits": 0})
    outcome = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    state = workdir.read_state(tmp_path)
    assert state is not None
    watermark = state["repositories"]["1"]["discovery_watermark"]
    assert watermark == outcome.manifest["refresh_started_at"]
    assert watermark != "2030-06-15T00:00:00Z"


def test_second_concurrent_collector_is_rejected(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """A concurrent collector cannot advance state while another run holds the lock."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]], sort="updated", direction="desc")
    with (
        workdir.CollectionLock(tmp_path, "outside-run"),
        pytest.raises(workdir.WorkdirLockedError),
    ):
        collect.run_collect(org="acme", workdir_path=tmp_path, start=_START, end=_END)
    assert workdir.read_state(tmp_path) is None
    assert fake_gh.calls == [], "rejection must happen before any live collection call"


def test_touched_pr_bundle_is_written_to_raw_evidence(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """Each touched PR's bundle is appended to that run's raw NDJSON evidence."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list(
        "/repos/acme/repo1/pulls",
        [[_pr(7, "2026-01-10T00:00:00Z")]],
        sort="updated",
        direction="desc",
    )
    fake_gh.set_object(
        "/repos/acme/repo1/pulls/7", {"number": 7, "id": 700, "commits": 1}
    )
    fake_gh.set_list(
        "/repos/acme/repo1/pulls/7/reviews", [[{"id": 1, "state": "APPROVED"}]]
    )
    fake_gh.set_list("/repos/acme/repo1/pulls/7/commits", [[{"sha": "abc123"}]])
    fake_gh.set_list("/repos/acme/repo1/issues/7/timeline", [[{"event": "reviewed"}]])
    outcome = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    raw_root = workdir.raw_dir(tmp_path, outcome.run_id)
    expected_payloads = {
        "pulls.ndjson": {"number": 7, "id": 700, "commits": 1},
        "reviews.ndjson": [{"id": 1, "state": "APPROVED"}],
        "commits.ndjson": [{"sha": "abc123"}],
        "timeline.ndjson": [{"event": "reviewed"}],
    }
    for filename, expected_payload in expected_payloads.items():
        lines = (raw_root / filename).read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines]
        matching = [record for record in records if record["pr_number"] == 7]
        assert matching, f"{filename} must retain a record for the touched PR"
        assert matching[0]["payload"] == expected_payload, (
            f"{filename} must retain the actual fetched bundle content"
        )


def _commit_pages(total: int) -> list[list[dict[str, Any]]]:
    """Split ``total`` fake commits into GitHub-style pages of up to 100."""
    return [
        [{"sha": str(i)} for i in range(offset, min(offset + 100, total))]
        for offset in range(0, max(total, 1), 100)
    ]


@pytest.mark.parametrize(
    ("pr_object", "commit_total", "expect_status", "expect_limitation"),
    [
        pytest.param(
            {"number": 7, "commits": 400}, 250, "complete", True, id="exceeds-250-cap"
        ),
        pytest.param(
            {"number": 7, "commits": 250}, 250, "complete", False, id="at-250-boundary"
        ),
        pytest.param(
            {"number": 7, "commits": 200}, 150, "incomplete", False, id="sub-250-short"
        ),
        pytest.param(
            {"number": 7}, 1, "incomplete", False, id="unreadable-count"
        ),
    ],
)
def test_commit_bundle_completeness_check(
    tmp_path: Path,
    fake_gh: _FakeGh,
    pr_object: dict[str, Any],
    commit_total: int,
    expect_status: str,
    expect_limitation: bool,
) -> None:
    """The collected commit list is verified against the PR's own count.

    A PR whose own count exceeds GitHub's 250-result endpoint cap is a
    documented availability case (issue #98): the capped bundle is kept,
    a manifest ``limitations`` entry is recorded, and the run still
    commits so the PR's watermark advances instead of pinning it inside
    the discovery window forever. Any other unverifiable or truncated
    bundle (``expected <= 250`` mismatch, or an unreadable count) fails
    closed with a ``commits`` failure and no state commit.
    """
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list(
        "/repos/acme/repo1/pulls",
        [[_pr(7, "2026-01-10T00:00:00Z")]],
        sort="updated",
        direction="desc",
    )
    fake_gh.set_object("/repos/acme/repo1/pulls/7", pr_object)
    fake_gh.set_list("/repos/acme/repo1/pulls/7/reviews", [[]])
    fake_gh.set_list("/repos/acme/repo1/pulls/7/commits", _commit_pages(commit_total))
    fake_gh.set_list("/repos/acme/repo1/issues/7/timeline", [[]])
    outcome = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert outcome.status == expect_status
    commits_failures = [
        f for f in outcome.manifest["failures"] if f["endpoint"] == "commits"
    ]
    limitations = [
        limitation
        for limitation in outcome.manifest["limitations"]
        if limitation["kind"] == "pr_commits_exceed_endpoint_cap"
    ]
    state = workdir.read_state(tmp_path)
    if expect_status == "complete":
        assert commits_failures == []
        assert state is not None
        assert (
            state["repositories"]["1"]["discovery_watermark"]
            == outcome.manifest["refresh_started_at"]
        )
    else:
        assert commits_failures[0]["pr_number"] == 7
        assert state is None
    if expect_limitation:
        assert limitations == [
            {
                "kind": "pr_commits_exceed_endpoint_cap",
                "repository_id": 1,
                "pr_number": 7,
                "expected_commits": 400,
                "collected_commits": 250,
            }
        ]
    else:
        assert limitations == []


def test_history_boundary_is_never_pulled_forward(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """A later --start after an earlier committed boundary keeps that boundary."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]], sort="updated", direction="desc")
    first = collect.run_collect(
        org="acme",
        workdir_path=tmp_path,
        start=datetime(2020, 1, 8, tzinfo=UTC),
        end=_END,
    )
    first_boundary = first.manifest["repositories"]["1"]["required_history_boundary"]

    fake_gh.set_list("/repos/acme/repo1/issues", [[]], sort="created", direction="asc")
    second = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    state = workdir.read_state(tmp_path)
    assert state is not None
    assert state["repositories"]["1"]["history_boundary"] == first_boundary
    assert (
        second.manifest["repositories"]["1"]["required_history_boundary"]
        != first_boundary
    )


def test_organization_mismatch_is_rejected_before_live_collection(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """Reusing a workdir for a different org fails closed before any collection."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]], sort="updated", direction="desc")
    collect.run_collect(org="acme", workdir_path=tmp_path, start=_START, end=_END)
    committed_before = workdir.read_state(tmp_path)
    calls_before = len(fake_gh.calls)

    with pytest.raises(workdir.OrganizationMismatchError):
        collect.run_collect(
            org="other-org", workdir_path=tmp_path, start=_START, end=_END
        )
    assert len(fake_gh.calls) == calls_before, (
        "rejection must happen before any live collection call"
    )
    assert workdir.read_state(tmp_path) == committed_before


def test_organization_mismatch_is_rejected_even_before_first_commit(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """An incomplete first run still blocks a different org on the same workdir.

    A workdir with only a failed (incomplete) run has no committed state
    yet, so this must not rely on ``state.json`` alone -- otherwise a
    failed run for one org could be silently followed by a successful run
    for a different org on the same workdir.
    """
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]], sort="updated", direction="desc")
    fake_gh.fail("/orgs/acme/repos")
    first = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert first.status == "incomplete"
    assert workdir.read_state(tmp_path) is None

    with pytest.raises(workdir.OrganizationMismatchError):
        collect.run_collect(
            org="other-org", workdir_path=tmp_path, start=_START, end=_END
        )
    assert workdir.read_state(tmp_path) is None


def test_organization_comparison_is_case_insensitive(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """GitHub org logins are case-insensitive, so the guard must be too."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]], sort="updated", direction="desc")
    collect.run_collect(org="acme", workdir_path=tmp_path, start=_START, end=_END)

    outcome = collect.run_collect(
        org="ACME", workdir_path=tmp_path, start=_START, end=_END
    )
    assert outcome.status == "complete"


def test_organization_binding_rejects_mismatch_before_any_manifest_exists(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """A crash-before-finalize workdir still blocks a different org.

    Simulates a run for org A that was killed after writing raw evidence
    but before ``finalize_manifest`` ever ran: no manifest exists yet, only
    the organization binding written before the first live API call. A
    different org must still be rejected, since ``manifest_organizations``
    alone would see nothing here.
    """
    workdir.bind_organization(tmp_path, "acme")
    assert workdir.manifest_organizations(tmp_path) == set()

    with pytest.raises(workdir.OrganizationMismatchError):
        collect.run_collect(
            org="other-org", workdir_path=tmp_path, start=_START, end=_END
        )
    assert fake_gh.calls == []


def test_organization_binding_rejects_run_when_binding_is_corrupted(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """A corrupted binding file must fail closed, not read as unbound.

    Simulates a workdir whose ``organization.json`` exists but is not a
    JSON object with a string ``organization`` field (e.g. truncated by a
    crash mid-write, outside the atomic replace). Treating that the same
    as "no binding" would let this run start writing live evidence for a
    possibly different organization into a workdir another organization
    may already own.
    """
    path = workdir.organization_binding_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(workdir.OrganizationMismatchError):
        collect.run_collect(org="acme", workdir_path=tmp_path, start=_START, end=_END)
    assert fake_gh.calls == []
    assert workdir.read_state(tmp_path) is None
    assert workdir.manifest_organizations(tmp_path) == set()


def test_organization_binding_is_written_before_first_live_api_call(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """The binding exists even if collection never reaches a manifest."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]], sort="updated", direction="desc")
    collect.run_collect(org="acme", workdir_path=tmp_path, start=_START, end=_END)
    assert workdir.read_organization_binding(tmp_path) == "acme"


def test_manifest_records_collector_revision(tmp_path: Path, fake_gh: _FakeGh) -> None:
    """Every finalized manifest records the collector's own revision."""
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]], sort="updated", direction="desc")
    outcome = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert outcome.manifest["collector_revision"]


def test_process_repo_tolerates_missing_history_boundary_field(
    tmp_path: Path, fake_gh: _FakeGh
) -> None:
    """A repo state entry missing history_boundary does not crash the run.

    Simulates an older-schema or hand-edited ``state.json`` entry. Using
    ``repo_state["history_boundary"]`` instead of ``.get()`` here would
    raise ``KeyError`` before any manifest could record the failure.
    """
    workdir.write_state(
        tmp_path,
        {
            "committed_run_id": "prior",
            "organization": "acme",
            "collection_affecting_fingerprint": (
                collect.collection_affecting_fingerprint([])
            ),
            "repositories": {
                "1": {
                    "name": "repo1",
                    "archived": False,
                    "fork": False,
                    "created_at": "2020-01-01T00:00:00Z",
                    "discovery_watermark": "2026-01-05T00:00:00Z",
                }
            },
        },
    )
    fake_gh.set_list("/orgs/acme/repos", [[_repo(1, "repo1")]])
    fake_gh.set_list("/repos/acme/repo1/pulls", [[]], sort="updated", direction="desc")
    outcome = collect.run_collect(
        org="acme", workdir_path=tmp_path, start=_START, end=_END
    )
    assert outcome.status == "complete"
