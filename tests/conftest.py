"""Shared test fixtures, fakes, and entity builders for this skill's tests.

``FakeGh`` and the ``fake_gh`` fixture are a deterministic, no-network
stand-in for :mod:`ghapi`, used by ``test_collect.py`` and available to
any future test that drives ``collect``. ``test_normalize.py`` does not
use them -- it builds committed-lineage evidence on disk directly -- so
they live here rather than in ``test_collect.py`` only to keep one copy.

The ``write_state``/``write_normalized``/``*_row`` helpers below serve
``test_aggregate.py``/``test_analyze.py``/``test_report.py``: they build a
synthetic ``<workdir>/normalized/`` tree directly, bypassing
``collect``/``normalize`` entirely, since ``aggregate``/``analyze``/
``report`` only ever read normalized entity files and ``derivation.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import ghapi
import pytest
import workdir

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class FakeGh:
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


def make_repo(
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


def make_pr(number: int, updated_at: str, *, is_pr: bool = True) -> dict[str, Any]:
    """Build a minimal issues/pulls list item."""
    item: dict[str, Any] = {"number": number, "updated_at": updated_at}
    if is_pr:
        item["pull_request"] = {}
    return item


@pytest.fixture
def fake_gh(monkeypatch: pytest.MonkeyPatch) -> FakeGh:
    """Patch :mod:`ghapi` with a deterministic fake for one test."""
    fake = FakeGh()
    monkeypatch.setattr(ghapi, "paginate", fake.paginate)
    monkeypatch.setattr(ghapi, "request", fake.request)
    return fake


def write_state(
    workdir_path: Path,
    *,
    repository_ids: list[int],
    history_boundary: str = "2019-01-01T00:00:00Z",
    committed_run_id: str = "run1",
    organization: str = "acme",
) -> None:
    """Write a minimal committed ``state.json`` with permissive coverage.

    Args:
        workdir_path: The workdir root.
        repository_ids: Repository IDs to record committed coverage for.
        history_boundary: The committed historical coverage boundary
            recorded for every repository.
        committed_run_id: The committed run ID.
        organization: The bound organization login.
    """
    workdir.write_state(
        workdir_path,
        {
            "schema_version": workdir.SCHEMA_VERSION,
            "committed_run_id": committed_run_id,
            "organization": organization,
            "repositories": {
                str(repo_id): {
                    "name": f"repo{repo_id}",
                    "archived": False,
                    "fork": False,
                    "created_at": "2019-01-01T00:00:00Z",
                    "discovery_watermark": "2026-01-01T00:00:00Z",
                    "history_boundary": history_boundary,
                    "last_seen_in_enumeration_at": "2026-01-01T00:00:00Z",
                }
                for repo_id in repository_ids
            },
        },
    )


def repo_row(
    repo_id: int,
    *,
    name: str | None = None,
    fork: bool = False,
    created_at: str = "2019-01-01T00:00:00Z",
) -> dict[str, Any]:
    """Build one ``repositories.ndjson`` row."""
    return {
        "repository_id": repo_id,
        "name": name or f"repo{repo_id}",
        "archived": False,
        "fork": fork,
        "created_at": created_at,
        "last_seen_in_enumeration_at": "2026-01-01T00:00:00Z",
    }


def pr_row(
    repo_id: int,
    pr_number: int,
    *,
    author_id: int = 1,
    author_login: str = "alice",
    author_classification: str = "human",
    created_at: str,
    merged_at: str | None = None,
    size: tuple[int, int, int] = (3, 10, 5),
    commit_count: int = 1,
) -> dict[str, Any]:
    """Build one ``pull_requests.ndjson`` row.

    Args:
        repo_id: The repository ID.
        pr_number: The PR number.
        author_id: The author's actor ID.
        author_login: The author's login.
        author_classification: The author's actor classification.
        created_at: The PR's creation timestamp.
        merged_at: The PR's merge timestamp, or ``None`` if unmerged.
        size: ``(changed_files, additions, deletions)``.
        commit_count: The PR's total commit count.
    """
    changed_files, additions, deletions = size
    return {
        "repository_id": repo_id,
        "pr_number": pr_number,
        "source_run_id": "run1",
        "author_id": author_id,
        "author_login": author_login,
        "author_classification": author_classification,
        "draft": False,
        "state": "closed" if merged_at else "open",
        "created_at": created_at,
        "closed_at": merged_at,
        "merged_at": merged_at,
        "merge_commit_sha": "deadbeef" if merged_at else None,
        "head_sha": "head",
        "base_sha": "base",
        "additions": additions,
        "deletions": deletions,
        "changed_files": changed_files,
        "commit_count": commit_count,
    }


def review_row(
    repo_id: int,
    pr_number: int,
    review_id: int,
    *,
    reviewer_id: int = 2,
    reviewer_login: str = "bob",
    reviewer_classification: str = "human",
    state: str = "APPROVED",
    submitted_at: str,
    commit_id: str = "c1",
    independent: bool = True,
) -> dict[str, Any]:
    """Build one ``reviews.ndjson`` row."""
    return {
        "repository_id": repo_id,
        "pr_number": pr_number,
        "review_id": review_id,
        "reviewer_id": reviewer_id,
        "reviewer_login": reviewer_login,
        "reviewer_classification": reviewer_classification,
        "state": state,
        "submitted_at": submitted_at,
        "commit_id": commit_id,
        "independent": independent,
    }


def commit_rows(repo_id: int, pr_number: int, shas: list[str]) -> list[dict[str, Any]]:
    """Build ``pr_commits.ndjson`` rows for an ordered, available commit list."""
    return [
        {
            "repository_id": repo_id,
            "pr_number": pr_number,
            "source_run_id": "run1",
            "available": True,
            "position": position,
            "sha": sha,
        }
        for position, sha in enumerate(shas)
    ]


def unavailable_commit_row(repo_id: int, pr_number: int, reason: str) -> dict[str, Any]:
    """Build a single ``pr_commits.ndjson`` row marking a PR's commits unavailable."""
    return {
        "repository_id": repo_id,
        "pr_number": pr_number,
        "source_run_id": "run1",
        "available": False,
        "reason": reason,
    }


def draft_row(
    repo_id: int,
    pr_number: int,
    *,
    first_queue_entry: str | None,
    queue_entry_available: bool = True,
    initially_draft: bool = False,
    reason: str = "no_lifecycle_events_not_draft",
) -> dict[str, Any]:
    """Build one ``draft_lifecycle.ndjson`` row."""
    return {
        "repository_id": repo_id,
        "pr_number": pr_number,
        "source_run_id": "run1",
        "transitions": [],
        "initially_draft": initially_draft,
        "first_queue_entry": first_queue_entry,
        "queue_entry_available": queue_entry_available,
        "reason": reason,
    }


def dismissal_timeline_row(
    repo_id: int,
    pr_number: int,
    *,
    observed_index: int,
    review_id: int,
    pre_dismissal_state: str | None,
) -> dict[str, Any]:
    """Build one ``review_dismissed`` timeline row."""
    return {
        "repository_id": repo_id,
        "pr_number": pr_number,
        "observed_index": observed_index,
        "event": "review_dismissed",
        "created_at": "2026-01-01T00:00:00Z",
        "payload": {
            "event": "review_dismissed",
            "dismissed_review": {"review_id": review_id, "state": pre_dismissal_state},
        },
    }


def write_normalized(
    workdir_path: Path,
    *,
    repositories: list[dict[str, Any]],
    pull_requests: list[dict[str, Any]],
    reviews: list[dict[str, Any]] | None = None,
    pr_commits: list[dict[str, Any]] | None = None,
    timeline_events: list[dict[str, Any]] | None = None,
    draft_lifecycle: list[dict[str, Any]] | None = None,
    as_of: str = "2026-06-01T00:00:00Z",
    committed_run_id: str = "run1",
) -> None:
    """Write a synthetic ``<workdir>/normalized/`` tree directly.

    Bypasses ``collect``/``normalize`` entirely -- ``aggregate``/``analyze``/
    ``report`` only ever read the normalized entity files and
    ``derivation.json``, so tests build those directly for speed and
    clarity.
    """
    out = workdir_path / "normalized"
    workdir.atomic_write_ndjson(out / "repositories.ndjson", repositories)
    workdir.atomic_write_ndjson(out / "pull_requests.ndjson", pull_requests)
    workdir.atomic_write_ndjson(out / "reviews.ndjson", reviews or [])
    workdir.atomic_write_ndjson(out / "pr_commits.ndjson", pr_commits or [])
    workdir.atomic_write_ndjson(out / "timeline_events.ndjson", timeline_events or [])
    workdir.atomic_write_ndjson(out / "draft_lifecycle.ndjson", draft_lifecycle or [])
    workdir.atomic_write_json(
        out / "derivation.json",
        {
            "committed_run_id": committed_run_id,
            "source_run_ids": [committed_run_id],
            "as_of": as_of,
            "requested_interval": None,
            "schema_version": workdir.SCHEMA_VERSION,
            "normalizer_schema_version": 1,
            "actor_classification_fingerprint": "test",
            "actor_map": {"actor_ids": [], "logins": []},
            "normalizer_revision": "test",
        },
    )
