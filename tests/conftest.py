"""Shared test fixtures and fakes for the ``github-productivity`` skill.

``FakeGh`` and the ``fake_gh`` fixture are a deterministic, no-network
stand-in for :mod:`ghapi`, used by ``test_collect.py`` and available to
any future test that drives ``collect``. ``test_normalize.py`` does not
use them -- it builds committed-lineage evidence on disk directly -- so
they live here rather than in ``test_collect.py`` only to keep one copy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import ghapi
import pytest


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
