"""Single seam for GitHub REST calls through ``gh api``.

Every request is pinned to one supported REST API version and returns both
the parsed payload and a scrubbed provenance record safe to persist to raw
storage. No other module in this skill invokes ``gh`` or any HTTP client
directly.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The single GitHub REST API version pinned by this skill. Recorded in
#: every run manifest so collected data stays reproducible even as the
#: default GitHub API version changes over time.
GITHUB_API_VERSION = "2026-03-10"

_DEFAULT_PER_PAGE = 100

#: Bounds a single ``gh api`` call so a wedged process cannot block a
#: collection run (and the exclusive workdir lock it holds) indefinitely.
_REQUEST_TIMEOUT_SECONDS = 120

_SECRET_KEY_PATTERN = re.compile(
    r"authorization|token|password|secret|cookie", re.IGNORECASE
)

#: Matches credential-shaped ``key: value`` or ``key=value`` fragments inside
#: free text such as ``gh``'s stderr, which can otherwise echo request
#: headers back into error output.
_SECRET_VALUE_PATTERN = re.compile(
    r"(authorization|token|password|secret|cookie)(\s*[:=]\s*).+", re.IGNORECASE
)


class GhApiError(Exception):
    """Raised when a ``gh api`` invocation fails or returns unparseable JSON."""


@dataclass(frozen=True, slots=True)
class GhApiResponse:
    """One ``gh api`` call's parsed payload and scrubbed request provenance."""

    payload: Any
    provenance: dict[str, Any]


def scrub_provenance(record: dict[str, Any]) -> dict[str, Any]:
    """Remove any credential-shaped key from a provenance record.

    Args:
        record: A provenance mapping that may contain caller-supplied
            parameters.

    Returns:
        A shallow copy of ``record`` with any key matching a
        credential-shaped pattern (``authorization``, ``token``,
        ``password``, ``secret``, ``cookie``, case-insensitive) removed from
        the top level and from any nested ``params`` mapping.
    """
    scrubbed = {
        key: value
        for key, value in record.items()
        if not _SECRET_KEY_PATTERN.search(key)
    }
    params = scrubbed.get("params")
    if isinstance(params, dict):
        scrubbed["params"] = {
            key: value
            for key, value in params.items()
            if not _SECRET_KEY_PATTERN.search(str(key))
        }
    return scrubbed


def _redact_secret_values(text: str) -> str:
    """Redact credential-shaped values embedded in free text.

    Args:
        text: Free text that may echo a credential-bearing fragment, such
            as ``gh``'s stderr output.

    Returns:
        ``text`` with any ``key: value`` or ``key=value`` fragment whose
        key looks credential-shaped replaced by a redacted placeholder.
    """
    return _SECRET_VALUE_PATTERN.sub(r"\1\2[REDACTED]", text)


def request(
    *,
    endpoint: str,
    params: dict[str, str | int],
    repository_id: int | None,
    run_id: str,
) -> GhApiResponse:
    """Issue one GET request to the GitHub REST API through ``gh api``.

    Args:
        endpoint: The REST path, for example ``/repos/{owner}/{repo}/pulls``.
        params: Non-secret query parameters, for example pagination or
            filter parameters. Never pass credential-bearing values here.
        repository_id: The stable repository ID this call relates to, or
            ``None`` for organization-level endpoints such as repository
            enumeration.
        run_id: The collection run this call belongs to.

    Returns:
        The parsed JSON payload together with a scrubbed provenance record
        suitable for append-only raw persistence.

    Raises:
        GhApiError: If ``gh`` exits non-zero, times out, or its stdout is
            not valid JSON.
    """
    query = urlencode(sorted(params.items()))
    path = f"{endpoint}?{query}" if query else endpoint
    argv = [
        "gh",
        "api",
        "--method",
        "GET",
        "-H",
        f"X-GitHub-Api-Version: {GITHUB_API_VERSION}",
        "-H",
        "Accept: application/vnd.github+json",
        path,
    ]
    requested_at = datetime.now(UTC).isoformat()
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"gh api timed out for {endpoint} after {_REQUEST_TIMEOUT_SECONDS}s"
        raise GhApiError(msg) from exc
    provenance = scrub_provenance({
        "endpoint": endpoint,
        "repository_id": repository_id,
        "params": dict(params),
        "api_version": GITHUB_API_VERSION,
        "run_id": run_id,
        "requested_at": requested_at,
    })
    if result.returncode != 0:
        stderr_excerpt = _redact_secret_values(result.stderr)[:500]
        msg = (
            f"gh api failed for {endpoint} (exit {result.returncode}): {stderr_excerpt}"
        )
        raise GhApiError(msg)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        msg = f"gh api returned unparseable JSON for {endpoint}: {exc}"
        raise GhApiError(msg) from exc
    return GhApiResponse(payload=payload, provenance=provenance)


def paginate(
    *,
    endpoint: str,
    params: dict[str, str | int],
    repository_id: int | None,
    run_id: str,
    per_page: int = _DEFAULT_PER_PAGE,
) -> Iterator[GhApiResponse]:
    """Page through a GitHub REST list endpoint with explicit parameters.

    Args:
        endpoint: The REST path to page through.
        params: Non-secret query parameters shared by every page. Must not
            include ``page`` or ``per_page``; those are added per page.
        repository_id: The stable repository ID this call relates to, or
            ``None`` for organization-level endpoints.
        run_id: The collection run this call belongs to.
        per_page: Page size. Iteration stops once a page returns fewer
            items than this.

    Yields:
        One :class:`GhApiResponse` per page, each carrying that page's
        items as ``payload`` and page-scoped provenance.

    Raises:
        GhApiError: If any page request fails, or a page's payload is not a
            JSON array.
    """
    page = 1
    while True:
        page_params: dict[str, str | int] = {
            **params,
            "per_page": per_page,
            "page": page,
        }
        response = request(
            endpoint=endpoint,
            params=page_params,
            repository_id=repository_id,
            run_id=run_id,
        )
        if not isinstance(response.payload, list):
            msg = f"expected a JSON array from {endpoint}, got {type(response.payload)}"
            raise GhApiError(msg)
        yield response
        if len(response.payload) < per_page:
            return
        page += 1
