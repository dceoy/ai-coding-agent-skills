"""Repository, PR, review, timeline, and commit collection through ``gh api``.

Implements the collection half of the transaction contract in
``workdir.py``: single-writer locking, repository re-enumeration, initial or
incremental PR discovery with reconciliation, canonical per-PR snapshot
bundle refetch, and fail-closed manifest/state finalization.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import ghapi
import workdir

if TYPE_CHECKING:
    from pathlib import Path

# GitHub's commits-on-a-pull-request endpoint returns at most this many results.
# A PR whose own commit count exceeds it cannot be paginated in full, so
# commit-order rework is defined as unavailable for it (issue #98).
_PR_COMMITS_ENDPOINT_CAP = 250


@dataclass(slots=True)
class CollectOutcome:
    """The result of one ``collect`` invocation."""

    run_id: str
    status: str
    manifest: dict[str, Any]


@dataclass(slots=True)
class _RunContext:
    """Mutable bookkeeping threaded through one collection run."""

    org: str
    workdir: Path
    run_id: str
    refresh_started_at: datetime
    overlap_hours: int
    failures: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[dict[str, Any]] = field(default_factory=list)


def collection_affecting_fingerprint(ci_workflow_ids: list[int]) -> str:
    """Fingerprint the configuration that changes what must be fetched.

    Args:
        ci_workflow_ids: Selected Actions workflow IDs, when CI metrics are
            enabled. Empty in this skill's current implementation.

    Returns:
        A stable hex digest over the canonical JSON form of the
        collection-affecting configuration.
    """
    canonical = json.dumps({"ci_workflow_ids": sorted(ci_workflow_ids)}, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_ts(value: str) -> datetime:
    """Parse a GitHub REST timestamp into an aware UTC datetime.

    Args:
        value: A timestamp such as ``"2026-01-01T00:00:00Z"``.

    Returns:
        The equivalent timezone-aware ``datetime`` in UTC.
    """
    return datetime.fromisoformat(value).astimezone(UTC)


def _fmt_ts(value: datetime) -> str:
    """Format a datetime as a GitHub-compatible UTC timestamp.

    Args:
        value: A datetime, converted to UTC if not already.

    Returns:
        A string such as ``"2026-01-01T00:00:00Z"``.
    """
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt_ts_precise(value: datetime) -> str:
    """Format a datetime with microsecond precision, for run-ordering fields.

    ``refresh_started_at`` (and the watermarks derived from it) must keep
    sub-second precision: two collection runs can start within the same
    second, and :func:`workdir.latest_manifest_run_id_and_status` breaks
    same-instant ties using ``run_id``, whose random suffix does not sort
    chronologically. Truncating to whole seconds, as :func:`_fmt_ts` does
    for GitHub API query parameters, would make such runs indistinguishable.

    Args:
        value: A datetime, converted to UTC if not already.

    Returns:
        A string such as ``"2026-01-01T00:00:00.123456Z"``.
    """
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def fetch_organization_repositories(ctx: _RunContext) -> list[dict[str, Any]]:
    """Re-enumerate every repository visible to the caller in the org.

    Args:
        ctx: The active run context.

    Returns:
        Repository summaries with ``id``, ``name``, ``full_name``,
        ``archived``, ``fork``, and ``created_at``, including archived
        repositories.
    """
    repositories: list[dict[str, Any]] = []
    raw_path = workdir.raw_dir(ctx.workdir, ctx.run_id) / "repos.ndjson"
    try:
        for page in ghapi.paginate(
            endpoint=f"/orgs/{ctx.org}/repos",
            params={"type": "all"},
            repository_id=None,
            run_id=ctx.run_id,
        ):
            workdir.append_ndjson(
                raw_path, {"provenance": page.provenance, "payload": page.payload}
            )
            repositories.extend(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "full_name": item["full_name"],
                    "archived": item["archived"],
                    "fork": item["fork"],
                    "created_at": item["created_at"],
                }
                for item in page.payload
            )
    except ghapi.GhApiError as exc:
        ctx.failures.append({
            "endpoint": "repos",
            "repository_id": None,
            "pr_number": None,
            "reason": str(exc),
        })
    return repositories


def _consume_backfill_page(
    page: ghapi.GhApiResponse, boundary: datetime, touched: set[int]
) -> bool:
    """Fold one backfill page's items into ``touched``.

    Args:
        page: One page of the descending-``updated_at`` Pulls scan.
        boundary: The earliest ``updated_at`` still required by this scan.
        touched: The accumulated set of touched PR numbers, updated in
            place.

    Returns:
        ``True`` once an item older than ``boundary`` is seen, signaling
        the caller to stop paging.
    """
    for item in page.payload:
        if _parse_ts(item["updated_at"]) < boundary:
            return True
        touched.add(item["number"])
    return False


def _discover_backfill(
    ctx: _RunContext, repo: dict[str, Any], boundary: datetime
) -> set[int]:
    """Discover PR numbers via the ordered descending Pulls endpoint.

    Stops once an item's ``updated_at`` is older than ``boundary``, per the
    initial/backward-backfill discovery contract.

    Args:
        ctx: The active run context.
        repo: The repository summary being discovered.
        boundary: The earliest ``updated_at`` still required by this scan.

    Returns:
        PR numbers whose ``updated_at`` was at or after ``boundary``.
    """
    touched: set[int] = set()
    owner, name = repo["full_name"].split("/", 1)
    raw_path = workdir.raw_dir(ctx.workdir, ctx.run_id) / "discovery.ndjson"
    try:
        pages = ghapi.paginate(
            endpoint=f"/repos/{owner}/{name}/pulls",
            params={"state": "all", "sort": "updated", "direction": "desc"},
            repository_id=repo["id"],
            run_id=ctx.run_id,
        )
        for page in pages:
            workdir.append_ndjson(
                raw_path, {"provenance": page.provenance, "payload": page.payload}
            )
            if _consume_backfill_page(page, boundary, touched):
                break
    except ghapi.GhApiError as exc:
        ctx.failures.append({
            "endpoint": "pulls-backfill",
            "repository_id": repo["id"],
            "pr_number": None,
            "reason": str(exc),
        })
    return touched


def _discover_issues(
    ctx: _RunContext,
    repo: dict[str, Any],
    *,
    since: datetime,
    sort: str,
    direction: str,
    endpoint_tag: str,
) -> set[int]:
    """Discover PR numbers via the Issues endpoint, filtered to PR items.

    Args:
        ctx: The active run context.
        repo: The repository summary being discovered.
        since: The lower bound passed as the Issues endpoint's ``since``.
        sort: The Issues endpoint ``sort`` parameter.
        direction: The Issues endpoint ``direction`` parameter.
        endpoint_tag: A label distinguishing this scan in raw evidence and
            failure records (for example ``"issues-incremental"``).

    Returns:
        PR numbers among the returned issues, identified by the presence
        of a ``pull_request`` key.
    """
    touched: set[int] = set()
    owner, name = repo["full_name"].split("/", 1)
    raw_path = workdir.raw_dir(ctx.workdir, ctx.run_id) / "discovery.ndjson"
    try:
        for page in ghapi.paginate(
            endpoint=f"/repos/{owner}/{name}/issues",
            params={
                "state": "all",
                "since": _fmt_ts(since),
                "sort": sort,
                "direction": direction,
            },
            repository_id=repo["id"],
            run_id=ctx.run_id,
        ):
            workdir.append_ndjson(
                raw_path, {"provenance": page.provenance, "payload": page.payload}
            )
            touched.update(
                item["number"] for item in page.payload if "pull_request" in item
            )
    except ghapi.GhApiError as exc:
        ctx.failures.append({
            "endpoint": endpoint_tag,
            "repository_id": repo["id"],
            "pr_number": None,
            "reason": str(exc),
        })
    return touched


def _fetch_pr_bundle(ctx: _RunContext, repo: dict[str, Any], pr_number: int) -> None:
    """Refetch one PR's canonical snapshot bundle: PR, reviews, commits, timeline.

    An unverifiable or truncated commits page for a PR with 250 or fewer
    commits (see ``_check_commit_bundle_completeness``) is recorded as a
    failure, making the run ``incomplete`` rather than silently committing
    a truncated bundle. A PR whose own commit count exceeds GitHub's
    250-result endpoint cap is instead recorded as a manifest limitation:
    the capped bundle is kept and the run still progresses, since
    commit-order rework is defined as unavailable for that PR.

    Args:
        ctx: The active run context.
        repo: The repository summary the PR belongs to.
        pr_number: The PR number to refetch.
    """
    owner, name = repo["full_name"].split("/", 1)
    raw_root = workdir.raw_dir(ctx.workdir, ctx.run_id)
    endpoints = (
        ("pulls", f"/repos/{owner}/{name}/pulls/{pr_number}", "pulls.ndjson", False),
        (
            "reviews",
            f"/repos/{owner}/{name}/pulls/{pr_number}/reviews",
            "reviews.ndjson",
            True,
        ),
        (
            "commits",
            f"/repos/{owner}/{name}/pulls/{pr_number}/commits",
            "commits.ndjson",
            True,
        ),
        (
            "timeline",
            f"/repos/{owner}/{name}/issues/{pr_number}/timeline",
            "timeline.ndjson",
            True,
        ),
    )
    pr_payload: dict[str, Any] | None = None
    for tag, endpoint, filename, paged in endpoints:
        try:
            pr_payload = _fetch_bundle_entry(
                ctx,
                repo,
                pr_number,
                tag,
                endpoint,
                filename,
                raw_root,
                paged,
                pr_payload,
            )
        except ghapi.GhApiError as exc:
            ctx.failures.append({
                "endpoint": tag,
                "repository_id": repo["id"],
                "pr_number": pr_number,
                "reason": str(exc),
            })


def _fetch_bundle_entry(
    ctx: _RunContext,
    repo: dict[str, Any],
    pr_number: int,
    tag: str,
    endpoint: str,
    filename: str,
    raw_root: Path,
    paged: bool,
    pr_payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Fetch and append one bundle endpoint, returning the PR payload to carry forward.

    Returns:
        ``pr_payload``, updated to the fetched payload when ``tag`` is
        ``"pulls"``; otherwise unchanged.
    """
    if paged:
        collected = 0
        for page in ghapi.paginate(
            endpoint=endpoint, params={}, repository_id=repo["id"], run_id=ctx.run_id
        ):
            collected += len(page.payload)
            workdir.append_ndjson(
                raw_root / filename,
                {
                    "pr_number": pr_number,
                    "provenance": page.provenance,
                    "payload": page.payload,
                },
            )
        if tag == "commits":
            _check_commit_bundle_completeness(
                ctx, repo, pr_number, pr_payload, collected
            )
        return pr_payload
    response = ghapi.request(
        endpoint=endpoint, params={}, repository_id=repo["id"], run_id=ctx.run_id
    )
    workdir.append_ndjson(
        raw_root / filename,
        {
            "pr_number": pr_number,
            "provenance": response.provenance,
            "payload": response.payload,
        },
    )
    if tag == "pulls" and isinstance(response.payload, dict):
        return response.payload
    return pr_payload


def _check_commit_bundle_completeness(
    ctx: _RunContext,
    repo: dict[str, Any],
    pr_number: int,
    pr_payload: dict[str, Any] | None,
    collected: int,
) -> None:
    """Verify a PR's commit bundle against the PR's own commit count.

    The collected commits are compared with the PR object's ``commits``
    field to tell a naturally short final page apart from a truncated one:

    - An unreadable expected count (a missing ``pulls`` fetch, or a
      payload without an integer ``commits`` field) fails closed -- it
      cannot be verified complete, so it must not be committed as if it
      were.
    - ``expected > 250`` is GitHub's documented commits-on-a-pull-request
      endpoint cap. Per issue #98, commit-order-based rework is simply
      unavailable for such a PR; the capped bundle is retained as
      evidence and the limitation is recorded, but the run is **not**
      failed. Failing here would leave the PR permanently inside the
      discovery window (an unadvanced watermark is retried every run),
      stalling every future refresh of the workdir.
    - Otherwise (``expected <= 250``) any mismatch -- short or over-count
      -- fails closed, since either means the commits list and the PR's
      own count were not observed as one coherent snapshot (for example a
      commit pushed between the two fetches).

    Raises:
        ghapi.GhApiError: If the PR's commit count cannot be read, or is
            ``<= 250`` and does not exactly match the number collected.
    """
    expected = pr_payload.get("commits") if pr_payload else None
    if not isinstance(expected, int):
        msg = (
            f"could not read an integer commit count for PR #{pr_number}; "
            "the commits bundle cannot be verified complete"
        )
        raise ghapi.GhApiError(msg)
    if expected > _PR_COMMITS_ENDPOINT_CAP:
        ctx.limitations.append({
            "kind": "pr_commits_exceed_endpoint_cap",
            "repository_id": repo["id"],
            "pr_number": pr_number,
            "expected_commits": expected,
            "collected_commits": collected,
        })
        return
    if collected != expected:
        msg = (
            f"expected {expected} commits for PR #{pr_number} but collected "
            f"{collected}; the commit bundle is truncated or was not observed "
            "as a coherent snapshot"
        )
        raise ghapi.GhApiError(msg)


def _collect_repository(
    ctx: _RunContext,
    repo: dict[str, Any],
    repo_state: dict[str, Any] | None,
    *,
    start: datetime,
) -> dict[str, Any]:
    """Discover, reconcile, and refetch bundles for one repository.

    Args:
        ctx: The active run context.
        repo: The repository summary being collected.
        repo_state: The repository's previously committed state, or
            ``None`` if this is a newly discovered repository.
        start: The requested observation interval's inclusive UTC start.

    Returns:
        The manifest entry describing this repository's collection
        outcome, including its touched PR numbers.

    Raises:
        AssertionError: If incremental discovery is selected but no prior
            committed watermark exists, which would indicate a broken
            committed-state invariant.
    """
    overlap = timedelta(hours=ctx.overlap_hours)
    required_boundary = start - overlap
    previous_watermark = repo_state.get("discovery_watermark") if repo_state else None
    previous_boundary = repo_state.get("history_boundary") if repo_state else None
    needs_backfill = (
        previous_boundary is None or _parse_ts(previous_boundary) > required_boundary
    )
    touched: set[int] = set()
    if needs_backfill:
        touched |= _discover_backfill(ctx, repo, required_boundary)
    else:
        if previous_watermark is None:
            msg = "incremental discovery requires a previously committed watermark"
            raise AssertionError(msg)
        since = _parse_ts(previous_watermark) - overlap
        touched |= _discover_issues(
            ctx,
            repo,
            since=since,
            sort="created",
            direction="asc",
            endpoint_tag="issues-incremental",
        )
    reconcile_since = ctx.refresh_started_at - overlap
    touched |= _discover_issues(
        ctx,
        repo,
        since=reconcile_since,
        sort="updated",
        direction="asc",
        endpoint_tag="issues-reconciliation",
    )
    for pr_number in sorted(touched):
        _fetch_pr_bundle(ctx, repo, pr_number)
    return {
        "name": repo["name"],
        "archived": repo["archived"],
        "fork": repo["fork"],
        "created_at": repo["created_at"],
        "previous_watermark": previous_watermark,
        "previous_history_boundary": previous_boundary,
        "touched_pr_numbers": sorted(touched),
        "required_history_boundary": _fmt_ts(required_boundary),
    }


def _process_repo(
    ctx: _RunContext,
    repo: dict[str, Any],
    previous_repositories: dict[str, Any],
    *,
    start: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Collect one repository and derive its manifest and state entries.

    Args:
        ctx: The active run context.
        repo: The repository summary being collected.
        previous_repositories: Previously committed per-repository state,
            keyed by stable repository ID.
        start: The requested observation interval's inclusive UTC start.

    Returns:
        A ``(manifest_entry, state_entry)`` pair for this repository.
    """
    key = str(repo["id"])
    repo_state = previous_repositories.get(key)
    entry = _collect_repository(ctx, repo, repo_state, start=start)
    required_boundary = _parse_ts(entry["required_history_boundary"])
    previous_boundary_raw = repo_state.get("history_boundary") if repo_state else None
    previous_boundary = (
        _parse_ts(previous_boundary_raw) if previous_boundary_raw else None
    )
    history_boundary = (
        min(previous_boundary, required_boundary)
        if previous_boundary is not None
        else required_boundary
    )
    state_entry = {
        "name": repo["name"],
        "archived": repo["archived"],
        "fork": repo["fork"],
        "created_at": repo["created_at"],
        "discovery_watermark": _fmt_ts_precise(ctx.refresh_started_at),
        "history_boundary": _fmt_ts(history_boundary),
        "last_seen_in_enumeration_at": _fmt_ts_precise(ctx.refresh_started_at),
    }
    return entry, state_entry


def _ensure_matching_organization(org: str, workdir_path: Path) -> None:
    """Fail closed if this workdir already has evidence for a different org.

    Checks every manifest that exists, complete or incomplete, plus the
    workdir's organization binding (see :func:`workdir.bind_organization`)
    — the binding covers a run killed before any manifest, even an
    incomplete one, was ever finalized, so a failed or crashed run for one
    organization can't be silently followed by a successful run for
    another on the same workdir. Comparison is case-insensitive, since
    GitHub organization logins are.

    Args:
        org: The requested organization login.
        workdir_path: The skill's workdir root.

    Raises:
        workdir.OrganizationMismatchError: If any existing manifest or the
            organization binding in this workdir names a different
            organization than ``org``, or if the organization binding
            exists but is corrupted (see
            :func:`workdir.read_organization_binding`).
    """
    recorded = workdir.manifest_organizations(workdir_path)
    bound = workdir.read_organization_binding(workdir_path)
    if bound is not None:
        recorded |= {bound}
    mismatched = {o for o in recorded if o.casefold() != org.casefold()}
    if not mismatched:
        return
    msg = (
        f"workdir {workdir_path} already has evidence for organization(s) "
        f"{sorted(mismatched)!r}, not {org!r}; use a different --workdir per org"
    )
    raise workdir.OrganizationMismatchError(msg)


def run_collect(
    *,
    org: str,
    workdir_path: Path,
    start: datetime,
    end: datetime,
    overlap_hours: int = 24,
    ci_workflow_ids: list[int] | None = None,
) -> CollectOutcome:
    """Run one collection attempt against a workdir for an organization.

    Args:
        org: The GitHub organization login to collect.
        workdir_path: The skill's workdir root.
        start: The requested observation interval's inclusive UTC start.
        end: The requested observation interval's exclusive UTC end.
        overlap_hours: Deterministic overlap applied to discovery
            boundaries and watermarks.
        ci_workflow_ids: Selected Actions workflow IDs. Unused by this
            skill's current implementation; recorded for forward
            compatibility with optional CI metrics.

    Returns:
        The outcome of this run: its ID, ``"complete"`` or ``"incomplete"``
        status, and finalized manifest.
    """
    run_id = workdir.new_run_id()
    with workdir.CollectionLock(workdir_path, run_id):
        _ensure_matching_organization(org, workdir_path)
        workdir.bind_organization(workdir_path, org)
        refresh_started_at = datetime.now(UTC)
        previous_state = workdir.read_state(workdir_path)
        previous_committed_run_id = (
            previous_state.get("committed_run_id") if previous_state else None
        )
        fingerprint = collection_affecting_fingerprint(ci_workflow_ids or [])
        ctx = _RunContext(
            org=org,
            workdir=workdir_path,
            run_id=run_id,
            refresh_started_at=refresh_started_at,
            overlap_hours=overlap_hours,
        )
        repositories = fetch_organization_repositories(ctx)
        previous_repositories: dict[str, Any] = (
            previous_state.get("repositories", {}) if previous_state else {}
        )
        manifest_repositories: dict[str, Any] = {}
        new_state_repositories: dict[str, Any] = dict(previous_repositories)
        for repo in repositories:
            entry, state_entry = _process_repo(
                ctx, repo, previous_repositories, start=start
            )
            key = str(repo["id"])
            manifest_repositories[key] = entry
            new_state_repositories[key] = state_entry
        status = "incomplete" if ctx.failures else "complete"
        manifest = {
            "schema_version": workdir.SCHEMA_VERSION,
            "run_id": run_id,
            "status": status,
            "previous_committed_run_id": previous_committed_run_id,
            "organization": org,
            "requested_interval": {"start": _fmt_ts(start), "end": _fmt_ts(end)},
            "refresh_started_at": _fmt_ts_precise(refresh_started_at),
            "collection_ended_at": _fmt_ts(datetime.now(UTC)),
            "github_api_version": ghapi.GITHUB_API_VERSION,
            "collector_revision": workdir.resolve_collector_revision() or "unavailable",
            "overlap_hours": overlap_hours,
            "collection_affecting_config": {
                "ci_workflow_ids": sorted(ci_workflow_ids or [])
            },
            "collection_affecting_fingerprint": fingerprint,
            "repositories": manifest_repositories,
            "failures": ctx.failures,
            "limitations": ctx.limitations,
        }
        workdir.finalize_manifest(workdir_path, run_id, manifest)
        if status == "complete":
            workdir.write_state(
                workdir_path,
                {
                    "schema_version": workdir.SCHEMA_VERSION,
                    "committed_run_id": run_id,
                    "organization": org,
                    "collection_affecting_config": {
                        "ci_workflow_ids": sorted(ci_workflow_ids or [])
                    },
                    "collection_affecting_fingerprint": fingerprint,
                    "repositories": new_state_repositories,
                },
            )
        return CollectOutcome(run_id=run_id, status=status, manifest=manifest)
