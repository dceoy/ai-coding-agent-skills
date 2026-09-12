# ruff: noqa: DOC201, DOC501, PLR0911, SLF001
"""Resumable, rate-limit-tolerant GitHub collection orchestration.

The canonical acceptance frontier remains ``state.json``. Live work is split
into repository-discovery and per-PR shards, and only completed shards are
checkpointed. Retryable API failures therefore pause a pending generation
without making partial data visible to normalization or reporting.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import collect as base_collect
import ghapi
import workdir

if TYPE_CHECKING:
    from pathlib import Path

_CHECKPOINT_SCHEMA_VERSION = 1
_CHECKPOINT_FILENAME = ".collect.pending.json"
_RETRYABLE_FAILURE_PATTERN = re.compile(
    r"rate limit|secondary rate|abuse detection|http (?:429|5\d\d)|"
    r"timed out|temporarily unavailable|connection reset",
    re.IGNORECASE,
)


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
    if checkpoint.get("checkpoint_schema_version") != _CHECKPOINT_SCHEMA_VERSION:
        return False
    if checkpoint.get("base_committed_run_id") != previous_committed_run_id:
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
        "refresh_started_at": base_collect._fmt_ts_precise(refresh_started_at),
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
) -> base_collect._RunContext:
    """Build a collector context pinned to the generation as-of instant."""
    return base_collect._RunContext(
        org=str(checkpoint["organization"]),
        workdir=workdir_path,
        run_id=run_id,
        refresh_started_at=workdir.parse_timestamp(checkpoint["refresh_started_at"]),
        overlap_hours=int(checkpoint["overlap_hours"]),
    )


def _last_failure(ctx: base_collect._RunContext) -> dict[str, Any]:
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
) -> base_collect.CollectOutcome:
    """Build a non-finalized outcome instructing a later resume."""
    checkpoint["last_pause"] = {
        "paused_at": workdir.format_timestamp(datetime.now(UTC)),
        "failure": failure,
    }
    return base_collect.CollectOutcome(
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
    ctx: base_collect._RunContext,
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
        or base_collect._parse_ts(previous_boundary) > required_boundary
    )
    touched: set[int] = set()
    if needs_backfill:
        touched |= base_collect._discover_backfill(ctx, repo, required_boundary)
    else:
        if previous_watermark is None:
            msg = "incremental discovery requires a previously committed watermark"
            raise AssertionError(msg)
        touched |= base_collect._discover_issues(
            ctx,
            repo,
            since=base_collect._parse_ts(previous_watermark) - overlap,
            sort="created",
            direction="asc",
            endpoint_tag="issues-incremental",
        )
    touched |= base_collect._discover_issues(
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
    required_boundary = base_collect._parse_ts(progress["required_history_boundary"])
    previous_boundary_raw = repo_state.get("history_boundary") if repo_state else None
    previous_boundary = (
        base_collect._parse_ts(previous_boundary_raw) if previous_boundary_raw else None
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
        "discovery_watermark": base_collect._fmt_ts_precise(refresh_started_at),
        "history_boundary": workdir.format_timestamp(history_boundary),
        "last_seen_in_enumeration_at": base_collect._fmt_ts_precise(refresh_started_at),
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
) -> base_collect.CollectOutcome:
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
    return base_collect.CollectOutcome(run_id=run_id, status=status, manifest=manifest)


def _handle_abort(
    *,
    checkpoint: dict[str, Any],
    ctx: base_collect._RunContext,
    workdir_path: Path,
    previous_state: dict[str, Any] | None,
) -> base_collect.CollectOutcome:
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
) -> base_collect.CollectOutcome | None:
    """Enumerate repositories once per pending generation."""
    if isinstance(checkpoint.get("repositories"), list):
        return None
    attempt_id = _attempt_run_id(str(checkpoint["run_id"]), "enumerate")
    ctx = _attempt_context(checkpoint, workdir_path, attempt_id)
    try:
        repositories = base_collect.fetch_organization_repositories(ctx)
    except base_collect._CollectionAbortedError:
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
) -> tuple[dict[str, Any] | None, base_collect.CollectOutcome | None]:
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
    except base_collect._CollectionAbortedError:
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
) -> base_collect.CollectOutcome | None:
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
            base_collect._fetch_pr_bundle(ctx, repo, int(pr_number))
        except base_collect._CollectionAbortedError:
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
) -> base_collect.CollectOutcome | None:
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
) -> base_collect.CollectOutcome:
    """Run or resume one transactionally committed collection generation."""
    lock_run_id = workdir.new_run_id()
    with workdir.CollectionLock(workdir_path, lock_run_id):
        base_collect._ensure_matching_organization(org, workdir_path)
        now = datetime.now(UTC)
        previous_state = workdir.read_state(workdir_path)
        if previous_state is not None:
            base_collect._validate_previous_state(
                previous_state, org, workdir_path, now
            )
        workdir.bind_organization(workdir_path, org)
        previous_committed_run_id = (
            previous_state.get("committed_run_id") if previous_state else None
        )
        config_ids = ci_workflow_ids or []
        fingerprint = base_collect.collection_affecting_fingerprint(config_ids)
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
