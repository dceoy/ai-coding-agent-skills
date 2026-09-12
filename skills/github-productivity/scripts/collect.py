# ruff: noqa: DOC201, DOC501
"""Repository, PR, review, timeline, and commit collection through ``gh api``.

Implements the collection half of the transaction contract in
``workdir.py``: single-writer locking, repository re-enumeration, initial or
incremental PR discovery with reconciliation, canonical per-PR snapshot
bundle refetch, resumable shard checkpoints, and fail-closed manifest/state
finalization.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
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
_CHECKPOINT_SCHEMA_VERSION = 1
_CHECKPOINT_FILENAME = ".collect.pending.json"
_RETRYABLE_FAILURE_PATTERN = re.compile(
    r"rate limit|secondary rate|abuse detection|http (?:429|5\d\d)|"
    r"timed out|temporarily unavailable|connection reset|"
    r"i/o timeout|context deadline exceeded|connection refused",
    re.IGNORECASE,
)


@dataclass(slots=True)
class CollectOutcome:
    """The result of one ``collect`` invocation."""

    run_id: str
    status: str
    manifest: dict[str, Any]


class _CollectionAbortedError(Exception):
    """Internal control flow used to stop after the first GitHub API failure."""


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


def _abort_collection(
    ctx: _RunContext,
    *,
    endpoint: str,
    repository_id: int | None,
    pr_number: int | None,
    exc: ghapi.GhApiError,
) -> None:
    """Record the first API failure and abort the remaining live collection.

    Once any endpoint fails, the transaction cannot commit its new state.
    Continuing to issue GitHub requests would only delay the inevitable
    ``incomplete`` result, and repeated per-call timeouts can otherwise keep
    a synchronous run alive for hours.

    Args:
        ctx: The active run context.
        endpoint: Stable endpoint-family tag recorded in the manifest.
        repository_id: Repository ID associated with the failed request.
        pr_number: PR number associated with the failed request, when any.
        exc: The underlying GitHub API failure.

    Raises:
        _CollectionAbortedError: Always, after persisting the failure in memory.
    """
    ctx.failures.append({
        "endpoint": endpoint,
        "repository_id": repository_id,
        "pr_number": pr_number,
        "reason": str(exc),
    })
    raise _CollectionAbortedError from exc


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
    """Parse a GitHub REST timestamp into an aware UTC datetime."""
    return workdir.parse_timestamp(value)


def _fmt_ts(value: datetime) -> str:
    """Format a datetime as a GitHub-compatible UTC timestamp."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt_ts_precise(value: datetime) -> str:
    """Format a datetime with microsecond precision, for run-ordering fields."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def fetch_organization_repositories(ctx: _RunContext) -> list[dict[str, Any]]:
    """Re-enumerate every repository visible to the caller in the org."""
    repositories: dict[int, dict[str, Any]] = {}
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
            for item in page.payload:
                _record_repository(repositories, item)
    except ghapi.GhApiError as exc:
        _abort_collection(
            ctx,
            endpoint="repos",
            repository_id=None,
            pr_number=None,
            exc=exc,
        )
    return [repositories[key] for key in sorted(repositories)]


def _record_repository(repositories: dict[int, dict[str, Any]], item: Any) -> None:  # noqa: ANN401
    """Retain an enumeration identity once, rejecting contradictory snapshots."""
    repo = _repository_summary(item)
    if repositories.setdefault(repo["id"], repo) != repo:
        msg = f"conflicting enumeration for repository {repo['id']}"
        raise ghapi.GhApiError(msg)


def _repository_summary(item: Any) -> dict[str, Any]:  # noqa: ANN401
    """Validate the repository fields that control identity and collection."""
    fields = {"id", "name", "full_name", "archived", "fork", "created_at"}
    if not isinstance(item, dict) or not fields <= item.keys():
        msg = "repository list item is missing required fields"
        raise ghapi.GhApiError(msg)
    expected_types = {
        "id": int,
        "archived": bool,
        "fork": bool,
        "name": str,
        "full_name": str,
    }
    if any(type(item[key]) is not expected for key, expected in expected_types.items()):
        msg = "repository list item has invalid identity or cohort fields"
        raise ghapi.GhApiError(msg)
    owner, separator, name = item["full_name"].partition("/")
    if (
        item["id"] <= 0
        or not owner
        or not separator
        or name != item["name"]
        or "/" in name
    ):
        msg = "repository list item has an invalid full_name or id"
        raise ghapi.GhApiError(msg)
    _api_timestamp(item["created_at"])
    return {key: item[key] for key in fields}


def _api_timestamp(value: Any) -> datetime:  # noqa: ANN401
    """Parse an API timestamp, translating malformed evidence to API failure."""
    try:
        return _parse_ts(value)
    except (TypeError, ValueError) as exc:
        msg = "API response has an invalid timestamp"
        raise ghapi.GhApiError(msg) from exc


def _discovered_number(item: Any) -> int:  # noqa: ANN401
    """Validate a discovery item and return its positive PR/issue number."""
    number = item.get("number") if isinstance(item, dict) else None
    if type(number) is not int or number <= 0:
        msg = "discovery item must have a positive integer number"
        raise ghapi.GhApiError(msg)
    return number


def _consume_backfill_page(
    page: ghapi.GhApiResponse, boundary: datetime, touched: set[int]
) -> bool:
    """Fold one backfill page's items into ``touched``."""
    for item in page.payload:
        number = _discovered_number(item)
        if _api_timestamp(item.get("updated_at")) < boundary:
            return True
        touched.add(number)
    return False


def _discover_backfill(
    ctx: _RunContext, repo: dict[str, Any], boundary: datetime
) -> set[int]:
    """Discover PR numbers via the ordered descending Pulls endpoint."""
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
        _abort_collection(
            ctx,
            endpoint="pulls-backfill",
            repository_id=repo["id"],
            pr_number=None,
            exc=exc,
        )
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
    """Discover PR numbers via the Issues endpoint, filtered to PR items."""
    touched: set[int] = set()
    owner, name = repo["full_name"].split("/", 1)
    raw_path = workdir.raw_dir(ctx.workdir, ctx.run_id) / "discovery.ndjson"
    try:
        for page in ghapi.paginate(
            endpoint=f"/repos/{owner}/{name}/issues",
            params={
                "state": "all",
                "since": _fmt_ts(since - timedelta(seconds=1)),
                "sort": sort,
                "direction": direction,
            },
            repository_id=repo["id"],
            run_id=ctx.run_id,
        ):
            workdir.append_ndjson(
                raw_path, {"provenance": page.provenance, "payload": page.payload}
            )
            for item in page.payload:
                number = _discovered_number(item)
                if "pull_request" in item:
                    touched.add(number)
    except ghapi.GhApiError as exc:
        _abort_collection(
            ctx,
            endpoint=endpoint_tag,
            repository_id=repo["id"],
            pr_number=None,
            exc=exc,
        )
    return touched


def _fetch_pr_bundle(ctx: _RunContext, repo: dict[str, Any], pr_number: int) -> None:
    """Refetch one PR's canonical snapshot bundle: PR, reviews, commits, timeline."""
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
            _abort_collection(
                ctx,
                endpoint=tag,
                repository_id=repo["id"],
                pr_number=pr_number,
                exc=exc,
            )


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
    """Fetch and append one bundle endpoint.

    Returns the PR payload to carry forward.
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
    _validate_pr_payload(response.payload, repo["id"], pr_number)
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


def _validate_pr_payload(payload: Any, repo_id: int, number: int) -> None:  # noqa: ANN401
    """Reject a malformed or mismatched PR detail before fetching its children."""
    if not isinstance(payload, dict):
        msg = "PR detail must be an object"
        raise ghapi.GhApiError(msg)
    base = payload.get("base")
    repository = base.get("repo") if isinstance(base, dict) else None
    if (
        type(payload.get("number")) is not int
        or payload["number"] != number
        or not isinstance(repository, dict)
        or type(repository.get("id")) is not int
        or repository["id"] != repo_id
    ):
        msg = f"PR detail identity does not match repository {repo_id} PR #{number}"
        raise ghapi.GhApiError(msg)
    expected = payload.get("commits")
    if type(expected) is not int or expected < 0:
        msg = f"could not read a non-negative integer commit count for PR #{number}"
        raise ghapi.GhApiError(msg)


def _check_commit_bundle_completeness(
    ctx: _RunContext,
    repo: dict[str, Any],
    pr_number: int,
    pr_payload: dict[str, Any] | None,
    collected: int,
) -> None:
    """Verify a PR's commit bundle against the PR's own commit count."""
    expected = pr_payload.get("commits") if pr_payload else None
    if type(expected) is not int or expected < 0:
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


def _ensure_matching_organization(org: str, workdir_path: Path) -> None:
    """Fail closed if this workdir already has evidence for a different org."""
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


def _validate_previous_state(
    state: dict[str, Any], org: str, path: Path, refresh_started_at: datetime
) -> None:
    """Check the acceptance frontier before issuing any successor-run requests."""
    recorded = state.get("organization")
    if not isinstance(recorded, str) or recorded.casefold() != org.casefold():
        msg = "committed state organization does not match --org"
        raise workdir.OrganizationMismatchError(msg)
    repositories = state.get("repositories")
    if not isinstance(repositories, dict):
        msg = "committed state repositories must be an object"
        raise workdir.WorkdirDataError(msg)
    lineage = workdir.resolve_committed_lineage(path, state)
    for manifest in lineage:
        started = workdir.parse_manifest_started_at(manifest)
        if started is None or started > refresh_started_at:
            msg = (
                "committed refresh timestamp is invalid or later than the current clock"
            )
            raise workdir.WorkdirDataError(msg)
    for key, entry in repositories.items():
        if (
            not key.isdecimal()
            or int(key) <= 0
            or str(int(key)) != key
            or not isinstance(entry, dict)
        ):
            msg = "committed state has an invalid repository identity or entry"
            raise workdir.WorkdirDataError(msg)
        _validate_watermarks(key, entry, refresh_started_at)


def _validate_watermarks(
    key: str, entry: dict[str, Any], refresh_started_at: datetime
) -> None:
    """Reject malformed or future incremental watermarks before any API access."""
    for name in ("history_boundary", "discovery_watermark"):
        value = entry.get(name)
        if value is None:
            continue
        try:
            instant = _parse_ts(value)
        except (TypeError, ValueError) as exc:
            msg = f"repository {key} has an invalid {name}"
            raise workdir.WorkdirDataError(msg) from exc
        if name == "discovery_watermark" and instant > refresh_started_at:
            msg = f"repository {key} watermark is later than the current clock"
            raise workdir.WorkdirDataError(msg)


def _checkpoint_path(workdir_path: Path) -> Path:
    """Return the durable pending-generation checkpoint path."""
    return workdir_path / _CHECKPOINT_FILENAME


def _delete_checkpoint(workdir_path: Path) -> None:
    """Remove a pending checkpoint after commit or deliberate abandonment."""
    path = _checkpoint_path(workdir_path)
    if not path.exists():
        return
    path.unlink()
    workdir.sync_directory(workdir_path)


def _write_checkpoint(workdir_path: Path, checkpoint: dict[str, Any]) -> None:
    """Atomically persist one pending generation checkpoint."""
    workdir_path.mkdir(parents=True, exist_ok=True)
    workdir.atomic_write_json(_checkpoint_path(workdir_path), checkpoint)


def _request_identity(
    *,
    org: str,
    start: datetime,
    end: datetime,
    overlap_hours: int,
    fingerprint: str,
) -> dict[str, Any]:
    """Return fields that must match before a checkpoint may be resumed."""
    return {
        "organization": org,
        "requested_interval": {
            "start": workdir.format_timestamp(start),
            "end": workdir.format_timestamp(end),
        },
        "overlap_hours": overlap_hours,
        "collection_affecting_fingerprint": fingerprint,
    }


def _checkpoint_matches(
    checkpoint: dict[str, Any],
    *,
    identity: dict[str, Any],
    previous_committed_run_id: str | None,
    workdir_path: Path,
) -> bool:
    """Return whether a pending checkpoint is safe to resume."""
    if (
        checkpoint.get("checkpoint_schema_version") != _CHECKPOINT_SCHEMA_VERSION
        or checkpoint.get("base_committed_run_id") != previous_committed_run_id
        or checkpoint.get("collector_revision") != workdir.resolve_collector_revision()
    ):
        return False
    checkpoint_org = checkpoint.get("organization")
    identity_org = identity.get("organization")
    if (
        not isinstance(checkpoint_org, str)
        or not isinstance(identity_org, str)
        or checkpoint_org.casefold() != identity_org.casefold()
    ):
        return False
    if any(
        checkpoint.get(key) != value
        for key, value in identity.items()
        if key != "organization"
    ):
        return False
    run_id = checkpoint.get("run_id")
    if not isinstance(run_id, str):
        return False
    try:
        workdir.validate_run_id(run_id)
    except workdir.WorkdirDataError:
        return False
    return not workdir.manifest_path(workdir_path, run_id).exists()


def _load_checkpoint(
    workdir_path: Path,
    *,
    identity: dict[str, Any],
    previous_committed_run_id: str | None,
) -> dict[str, Any] | None:
    """Load a compatible generation and abandon a stale checkpoint."""
    path = _checkpoint_path(workdir_path)
    if not path.exists():
        return None
    checkpoint = workdir.read_json_object(path)
    if _checkpoint_matches(
        checkpoint,
        identity=identity,
        previous_committed_run_id=previous_committed_run_id,
        workdir_path=workdir_path,
    ):
        return checkpoint
    _delete_checkpoint(workdir_path)
    return None


def _new_checkpoint(
    *,
    org: str,
    start: datetime,
    end: datetime,
    overlap_hours: int,
    fingerprint: str,
    previous_committed_run_id: str | None,
    refresh_started_at: datetime,
    ci_workflow_ids: list[int],
) -> dict[str, Any]:
    """Create an empty resumable collection generation."""
    return {
        "checkpoint_schema_version": _CHECKPOINT_SCHEMA_VERSION,
        "run_id": workdir.new_run_id(),
        "organization": org,
        "requested_interval": {
            "start": workdir.format_timestamp(start),
            "end": workdir.format_timestamp(end),
        },
        "overlap_hours": overlap_hours,
        "collection_affecting_config": {"ci_workflow_ids": sorted(ci_workflow_ids)},
        "collection_affecting_fingerprint": fingerprint,
        "base_committed_run_id": previous_committed_run_id,
        "collector_revision": workdir.resolve_collector_revision(),
        "refresh_started_at": _fmt_ts_precise(refresh_started_at),
        "repositories": None,
        "enumeration_shard_run_id": None,
        "repo_progress": {},
        "last_pause": None,
    }


def _attempt_run_id(generation_run_id: str, tag: str) -> str:
    """Return a unique raw-evidence run ID for one shard attempt."""
    safe_tag = re.sub(r"[^A-Za-z0-9_-]", "-", tag)
    return f"{generation_run_id}-{safe_tag}-{secrets.token_hex(3)}"


def _attempt_context(
    checkpoint: dict[str, Any], workdir_path: Path, run_id: str
) -> _RunContext:
    """Build a collector context pinned to the generation as-of instant."""
    return _RunContext(
        org=str(checkpoint["organization"]),
        workdir=workdir_path,
        run_id=run_id,
        refresh_started_at=workdir.parse_timestamp(checkpoint["refresh_started_at"]),
        overlap_hours=int(checkpoint["overlap_hours"]),
    )


def _last_failure(ctx: _RunContext) -> dict[str, Any]:
    """Return the failure recorded by the collector abort path."""
    if not ctx.failures:
        msg = "collection aborted without recording a GitHub API failure"
        raise workdir.WorkdirDataError(msg)
    return dict(ctx.failures[-1])


def _is_retryable_failure(failure: dict[str, Any]) -> bool:
    """Classify rate limits and transient transport/server errors."""
    reason = str(failure.get("reason", ""))
    return bool(_RETRYABLE_FAILURE_PATTERN.search(reason))


def _paused_outcome(
    checkpoint: dict[str, Any], failure: dict[str, Any]
) -> CollectOutcome:
    """Build a non-finalized outcome instructing a later resume."""
    checkpoint["last_pause"] = {
        "paused_at": workdir.format_timestamp(datetime.now(UTC)),
        "failure": failure,
    }
    return CollectOutcome(
        run_id=str(checkpoint["run_id"]),
        status="paused",
        manifest={
            "run_id": checkpoint["run_id"],
            "status": "paused",
            "organization": checkpoint["organization"],
            "refresh_started_at": checkpoint["refresh_started_at"],
            "failures": [failure],
            "resumable": True,
        },
    )


def _discover_repository(
    ctx: _RunContext,
    repo: dict[str, Any],
    repo_state: dict[str, Any] | None,
    *,
    start: datetime,
) -> dict[str, Any]:
    """Run discovery and reconciliation without fetching PR bundles."""
    overlap = timedelta(hours=ctx.overlap_hours)
    required_boundary = start - overlap
    previous_watermark = repo_state.get("discovery_watermark") if repo_state else None
    previous_boundary = repo_state.get("history_boundary") if repo_state else None
    needs_backfill = (
        previous_boundary is None
        or previous_watermark is None
        or _parse_ts(previous_boundary) > required_boundary
    )
    touched: set[int] = set()
    if needs_backfill:
        touched |= _discover_backfill(ctx, repo, required_boundary)
    else:
        if previous_watermark is None:
            msg = "incremental discovery requires a previously committed watermark"
            raise AssertionError(msg)
        touched |= _discover_issues(
            ctx,
            repo,
            since=_parse_ts(previous_watermark) - overlap,
            sort="created",
            direction="asc",
            endpoint_tag="issues-incremental",
        )
    touched |= _discover_issues(
        ctx,
        repo,
        since=ctx.refresh_started_at - overlap,
        sort="updated",
        direction="asc",
        endpoint_tag="issues-reconciliation",
    )
    return {
        "discovery_shard_run_id": ctx.run_id,
        "previous_watermark": previous_watermark,
        "previous_history_boundary": previous_boundary,
        "required_history_boundary": workdir.format_timestamp(required_boundary),
        "touched_pr_numbers": sorted(touched),
        "pr_shards": {},
        "manifest_entry": None,
        "state_entry": None,
    }


def _complete_repository_progress(
    checkpoint: dict[str, Any],
    repo: dict[str, Any],
    repo_state: dict[str, Any] | None,
    progress: dict[str, Any],
) -> None:
    """Derive manifest/state entries after all PR bundles complete."""
    required_boundary = _parse_ts(progress["required_history_boundary"])
    previous_boundary_raw = repo_state.get("history_boundary") if repo_state else None
    previous_boundary = (
        _parse_ts(previous_boundary_raw) if previous_boundary_raw else None
    )
    history_boundary = (
        min(previous_boundary, required_boundary)
        if previous_boundary is not None
        else required_boundary
    )
    refresh_started_at = workdir.parse_timestamp(checkpoint["refresh_started_at"])
    progress["manifest_entry"] = {
        "name": repo["name"],
        "archived": repo["archived"],
        "fork": repo["fork"],
        "created_at": repo["created_at"],
        "previous_watermark": progress["previous_watermark"],
        "previous_history_boundary": progress["previous_history_boundary"],
        "touched_pr_numbers": progress["touched_pr_numbers"],
        "required_history_boundary": progress["required_history_boundary"],
    }
    progress["state_entry"] = {
        "name": repo["name"],
        "archived": repo["archived"],
        "fork": repo["fork"],
        "created_at": repo["created_at"],
        "discovery_watermark": _fmt_ts_precise(refresh_started_at),
        "history_boundary": workdir.format_timestamp(history_boundary),
        "last_seen_in_enumeration_at": _fmt_ts_precise(refresh_started_at),
    }


def _ordered_source_run_ids(checkpoint: dict[str, Any]) -> list[str]:
    """Return completed raw shards in deterministic merge order."""
    sources: list[str] = []
    enumeration = checkpoint.get("enumeration_shard_run_id")
    if isinstance(enumeration, str):
        sources.append(enumeration)
    progress_map = checkpoint.get("repo_progress", {})
    if not isinstance(progress_map, dict):
        msg = "pending checkpoint repo_progress must be an object"
        raise workdir.WorkdirDataError(msg)
    for repo_key in sorted(progress_map, key=int):
        progress = progress_map[repo_key]
        if not isinstance(progress, dict):
            msg = f"pending checkpoint repository {repo_key} progress is invalid"
            raise workdir.WorkdirDataError(msg)
        discovery = progress.get("discovery_shard_run_id")
        if isinstance(discovery, str):
            sources.append(discovery)
        pr_shards = progress.get("pr_shards", {})
        if not isinstance(pr_shards, dict):
            msg = f"pending checkpoint repository {repo_key} pr_shards is invalid"
            raise workdir.WorkdirDataError(msg)
        for pr_key in sorted(pr_shards, key=int):
            shard = pr_shards[pr_key]
            if isinstance(shard, dict) and isinstance(shard.get("run_id"), str):
                sources.append(shard["run_id"])
    return sources


def _rewrite_run_id(row: Any, generation_run_id: str) -> dict[str, Any]:  # noqa: ANN401
    """Rewrite shard-local provenance to the sealed generation identity."""
    if not isinstance(row, dict):
        msg = "raw evidence row must be a JSON object"
        raise workdir.WorkdirDataError(msg)
    rewritten = dict(row)
    provenance = rewritten.get("provenance")
    if isinstance(provenance, dict):
        rewritten["provenance"] = {**provenance, "run_id": generation_run_id}
    return rewritten


def _materialize_generation_raw(workdir_path: Path, checkpoint: dict[str, Any]) -> None:
    """Seal the current completed-shard set into the canonical raw directory."""
    generation_run_id = str(checkpoint["run_id"])
    final_root = workdir.raw_dir(workdir_path, generation_run_id)
    source_ids = _ordered_source_run_ids(checkpoint)
    bucket_names: set[str] = set()
    for source_id in source_ids:
        source_root = workdir.raw_dir(workdir_path, source_id)
        if not source_root.exists():
            msg = f"pending raw shard {source_id} is missing"
            raise workdir.WorkdirDataError(msg)
        bucket_names.update(path.name for path in source_root.glob("*.ndjson"))

    seal_run_id = _attempt_run_id(generation_run_id, "seal")
    seal_root = workdir.raw_dir(workdir_path, seal_run_id)
    seal_root.mkdir(parents=True, exist_ok=False)
    for bucket_name in sorted(bucket_names):
        target = seal_root / bucket_name
        with target.open("w", encoding="utf-8") as output:
            for source_id in source_ids:
                source = workdir.raw_dir(workdir_path, source_id) / bucket_name
                if not source.exists():
                    continue
                with source.open(encoding="utf-8") as input_handle:
                    for line in input_handle:
                        row = _rewrite_run_id(json.loads(line), generation_run_id)
                        output.write(json.dumps(row, sort_keys=True))
                        output.write("\n")
            output.flush()
            os.fsync(output.fileno())
    workdir.sync_raw_evidence(workdir_path, seal_run_id)
    if final_root.exists():
        shutil.rmtree(final_root)
        workdir.sync_directory(final_root.parent)
    seal_root.replace(final_root)
    workdir.sync_directory(final_root.parent)


def _completed_entries(checkpoint: dict[str, Any], field: str) -> dict[str, Any]:
    """Collect completed repository entries for one checkpoint field."""
    entries: dict[str, Any] = {}
    progress_map = checkpoint.get("repo_progress", {})
    if not isinstance(progress_map, dict):
        return entries
    for key, progress in progress_map.items():
        if isinstance(progress, dict) and isinstance(progress.get(field), dict):
            entries[str(key)] = progress[field]
    return entries


def _limitations(checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect limitations from completed PR bundle shards."""
    limitations: list[dict[str, Any]] = []
    progress_map = checkpoint.get("repo_progress", {})
    if not isinstance(progress_map, dict):
        return limitations
    for progress in progress_map.values():
        if not isinstance(progress, dict):
            continue
        pr_shards = progress.get("pr_shards", {})
        if not isinstance(pr_shards, dict):
            continue
        for shard in pr_shards.values():
            if not isinstance(shard, dict):
                continue
            value = shard.get("limitations", [])
            if isinstance(value, list):
                limitations.extend(item for item in value if isinstance(item, dict))
    return limitations


def _finalize_generation(
    *,
    checkpoint: dict[str, Any],
    workdir_path: Path,
    previous_state: dict[str, Any] | None,
    status: str,
    failures: list[dict[str, Any]],
) -> CollectOutcome:
    """Seal raw shards and finalize one complete or incomplete generation."""
    _materialize_generation_raw(workdir_path, checkpoint)
    run_id = str(checkpoint["run_id"])
    manifest = {
        "schema_version": workdir.SCHEMA_VERSION,
        "run_id": run_id,
        "status": status,
        "previous_committed_run_id": checkpoint["base_committed_run_id"],
        "organization": checkpoint["organization"],
        "requested_interval": checkpoint["requested_interval"],
        "refresh_started_at": checkpoint["refresh_started_at"],
        "collection_ended_at": workdir.format_timestamp(datetime.now(UTC)),
        "github_api_version": ghapi.GITHUB_API_VERSION,
        "collector_revision": workdir.resolve_collector_revision() or "unavailable",
        "overlap_hours": checkpoint["overlap_hours"],
        "collection_affecting_config": checkpoint["collection_affecting_config"],
        "collection_affecting_fingerprint": checkpoint[
            "collection_affecting_fingerprint"
        ],
        "repositories": _completed_entries(checkpoint, "manifest_entry"),
        "failures": failures,
        "limitations": _limitations(checkpoint),
    }
    workdir.sync_raw_evidence(workdir_path, run_id)
    workdir.finalize_manifest(workdir_path, run_id, manifest)
    if status == "complete":
        previous_repositories = (
            previous_state.get("repositories", {}) if previous_state else {}
        )
        repositories = dict(previous_repositories)
        repositories.update(_completed_entries(checkpoint, "state_entry"))
        workdir.write_state(
            workdir_path,
            {
                "schema_version": workdir.SCHEMA_VERSION,
                "committed_run_id": run_id,
                "organization": checkpoint["organization"],
                "collection_affecting_config": checkpoint[
                    "collection_affecting_config"
                ],
                "collection_affecting_fingerprint": checkpoint[
                    "collection_affecting_fingerprint"
                ],
                "repositories": repositories,
            },
        )
    _delete_checkpoint(workdir_path)
    return CollectOutcome(run_id=run_id, status=status, manifest=manifest)


def _handle_abort(
    *,
    checkpoint: dict[str, Any],
    ctx: _RunContext,
    workdir_path: Path,
    previous_state: dict[str, Any] | None,
) -> CollectOutcome:
    """Pause retryable failures and finalize permanent failures."""
    failure = _last_failure(ctx)
    if _is_retryable_failure(failure):
        outcome = _paused_outcome(checkpoint, failure)
        _write_checkpoint(workdir_path, checkpoint)
        return outcome
    return _finalize_generation(
        checkpoint=checkpoint,
        workdir_path=workdir_path,
        previous_state=previous_state,
        status="incomplete",
        failures=[failure],
    )


def _enumerate_if_needed(
    *,
    checkpoint: dict[str, Any],
    workdir_path: Path,
    previous_state: dict[str, Any] | None,
) -> CollectOutcome | None:
    """Enumerate repositories once per pending generation."""
    if isinstance(checkpoint.get("repositories"), list):
        return None
    attempt_id = _attempt_run_id(str(checkpoint["run_id"]), "enumerate")
    ctx = _attempt_context(checkpoint, workdir_path, attempt_id)
    try:
        repositories = fetch_organization_repositories(ctx)
    except _CollectionAbortedError:
        return _handle_abort(
            checkpoint=checkpoint,
            ctx=ctx,
            workdir_path=workdir_path,
            previous_state=previous_state,
        )
    workdir.sync_raw_evidence(workdir_path, attempt_id)
    checkpoint["repositories"] = repositories
    checkpoint["enumeration_shard_run_id"] = attempt_id
    checkpoint["last_pause"] = None
    _write_checkpoint(workdir_path, checkpoint)
    return None


def _ensure_discovery(
    *,
    checkpoint: dict[str, Any],
    repo: dict[str, Any],
    repo_state: dict[str, Any] | None,
    start: datetime,
    workdir_path: Path,
    previous_state: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, CollectOutcome | None]:
    """Checkpoint repository discovery before any PR bundle work."""
    repo_key = str(repo["id"])
    progress_map = checkpoint["repo_progress"]
    progress = progress_map.get(repo_key)
    if isinstance(progress, dict) and isinstance(
        progress.get("discovery_shard_run_id"), str
    ):
        return progress, None
    attempt_id = _attempt_run_id(str(checkpoint["run_id"]), f"r{repo_key}-discover")
    ctx = _attempt_context(checkpoint, workdir_path, attempt_id)
    try:
        progress = _discover_repository(ctx, repo, repo_state, start=start)
    except _CollectionAbortedError:
        return None, _handle_abort(
            checkpoint=checkpoint,
            ctx=ctx,
            workdir_path=workdir_path,
            previous_state=previous_state,
        )
    workdir.sync_raw_evidence(workdir_path, attempt_id)
    progress_map[repo_key] = progress
    checkpoint["last_pause"] = None
    _write_checkpoint(workdir_path, checkpoint)
    return progress, None


def _collect_pr_bundles(
    *,
    checkpoint: dict[str, Any],
    repo: dict[str, Any],
    progress: dict[str, Any],
    workdir_path: Path,
    previous_state: dict[str, Any] | None,
) -> CollectOutcome | None:
    """Fetch each touched PR as an independently resumable shard."""
    pr_shards = progress["pr_shards"]
    for pr_number in progress["touched_pr_numbers"]:
        pr_key = str(pr_number)
        if pr_key in pr_shards:
            continue
        attempt_id = _attempt_run_id(
            str(checkpoint["run_id"]), f"r{repo['id']}-pr{pr_number}"
        )
        ctx = _attempt_context(checkpoint, workdir_path, attempt_id)
        try:
            _fetch_pr_bundle(ctx, repo, int(pr_number))
        except _CollectionAbortedError:
            return _handle_abort(
                checkpoint=checkpoint,
                ctx=ctx,
                workdir_path=workdir_path,
                previous_state=previous_state,
            )
        workdir.sync_raw_evidence(workdir_path, attempt_id)
        pr_shards[pr_key] = {
            "run_id": attempt_id,
            "limitations": list(ctx.limitations),
        }
        checkpoint["last_pause"] = None
        _write_checkpoint(workdir_path, checkpoint)
    return None


def _collect_repositories(
    *,
    checkpoint: dict[str, Any],
    previous_state: dict[str, Any] | None,
    start: datetime,
    workdir_path: Path,
) -> CollectOutcome | None:
    """Collect repositories serially and checkpoint each finished shard."""
    repositories = checkpoint.get("repositories")
    if not isinstance(repositories, list):
        msg = "pending checkpoint repositories must be a list after enumeration"
        raise workdir.WorkdirDataError(msg)
    previous_repositories = (
        previous_state.get("repositories", {}) if previous_state else {}
    )
    for repo in repositories:
        if not isinstance(repo, dict) or type(repo.get("id")) is not int:
            msg = "pending checkpoint contains an invalid repository summary"
            raise workdir.WorkdirDataError(msg)
        repo_key = str(repo["id"])
        existing = checkpoint["repo_progress"].get(repo_key)
        if isinstance(existing, dict) and isinstance(existing.get("state_entry"), dict):
            continue
        repo_state = previous_repositories.get(repo_key)
        progress, outcome = _ensure_discovery(
            checkpoint=checkpoint,
            repo=repo,
            repo_state=repo_state,
            start=start,
            workdir_path=workdir_path,
            previous_state=previous_state,
        )
        if outcome is not None:
            return outcome
        if progress is None:
            msg = f"repository {repo_key} discovery did not produce progress"
            raise workdir.WorkdirDataError(msg)
        outcome = _collect_pr_bundles(
            checkpoint=checkpoint,
            repo=repo,
            progress=progress,
            workdir_path=workdir_path,
            previous_state=previous_state,
        )
        if outcome is not None:
            return outcome
        _complete_repository_progress(checkpoint, repo, repo_state, progress)
        _write_checkpoint(workdir_path, checkpoint)
    return None


def run_collect(
    *,
    org: str,
    workdir_path: Path,
    start: datetime,
    end: datetime,
    overlap_hours: int = 24,
    ci_workflow_ids: list[int] | None = None,
) -> CollectOutcome:
    """Run or resume one transactionally committed collection generation.

    Returns a ``CollectOutcome`` with one of three statuses:

    - ``"complete"`` / ``"incomplete"``: a fully finalized, canonical manifest
      (``schema_version``, ``repositories``, and every other finalized field).
    - ``"paused"``: collection hit a retryable failure and produced a reduced
      manifest (``run_id``, ``status``, ``organization``, ``refresh_started_at``,
      ``failures``, ``resumable``) with no ``schema_version`` or
      ``repositories`` key. A later call with the same request resumes from
      the durable checkpoint.
    """
    lock_run_id = workdir.new_run_id()
    with workdir.CollectionLock(workdir_path, lock_run_id):
        _ensure_matching_organization(org, workdir_path)
        now = datetime.now(UTC)
        previous_state = workdir.read_state(workdir_path)
        if previous_state is not None:
            _validate_previous_state(previous_state, org, workdir_path, now)
        workdir.bind_organization(workdir_path, org)
        previous_committed_run_id = (
            previous_state.get("committed_run_id") if previous_state else None
        )
        config_ids = ci_workflow_ids or []
        fingerprint = collection_affecting_fingerprint(config_ids)
        identity = _request_identity(
            org=org,
            start=start,
            end=end,
            overlap_hours=overlap_hours,
            fingerprint=fingerprint,
        )
        checkpoint = _load_checkpoint(
            workdir_path,
            identity=identity,
            previous_committed_run_id=previous_committed_run_id,
        )
        if checkpoint is None:
            checkpoint = _new_checkpoint(
                org=org,
                start=start,
                end=end,
                overlap_hours=overlap_hours,
                fingerprint=fingerprint,
                previous_committed_run_id=previous_committed_run_id,
                refresh_started_at=now,
                ci_workflow_ids=config_ids,
            )
            _write_checkpoint(workdir_path, checkpoint)
        elif workdir.parse_timestamp(checkpoint["refresh_started_at"]) > now:
            msg = "pending collection refresh timestamp is later than the current clock"
            raise workdir.WorkdirDataError(msg)

        outcome = _enumerate_if_needed(
            checkpoint=checkpoint,
            workdir_path=workdir_path,
            previous_state=previous_state,
        )
        if outcome is not None:
            return outcome
        outcome = _collect_repositories(
            checkpoint=checkpoint,
            previous_state=previous_state,
            start=start,
            workdir_path=workdir_path,
        )
        if outcome is not None:
            return outcome
        repositories = checkpoint.get("repositories", [])
        completed = _completed_entries(checkpoint, "state_entry")
        if len(completed) != len(repositories):
            msg = "all enumerated repositories must complete before commit"
            raise workdir.WorkdirDataError(msg)
        return _finalize_generation(
            checkpoint=checkpoint,
            workdir_path=workdir_path,
            previous_state=previous_state,
            status="complete",
            failures=[],
        )
