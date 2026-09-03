"""Organization-week panel construction from normalized entities.

``aggregate`` is a read-only derivation step: it reads exactly one pinned
committed ``state.json`` snapshot (for the per-repository history-coverage
gate) plus ``<workdir>/normalized/*.ndjson`` (written by ``normalize``), and
writes a continuous UTC-ISO-week organization-week panel to
``<workdir>/report/organization-week.csv`` with a sidecar
``organization-week.meta.json``.

:func:`build_panel` is a pure function of already-loaded entities (plus a
requested window and cohort filters) so it can be reused, unchanged, by
``analyze``'s required sensitivity analyses (window truncation aside, the
stable-cohort, leave-one-repository-out, and actor sensitivities all need a
full from-entities recompute over a different repository or author-class
set -- see references/metrics.md).
"""

from __future__ import annotations

import csv
import json
import operator
import secrets
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import workdir

if TYPE_CHECKING:
    from pathlib import Path

#: Bump when the panel's column set or derivation rules change.
AGGREGATE_SCHEMA_VERSION = 1

_HUMAN = "human"
_AI = "explicit-ai-agent"
_BOT = "bot"
_UNKNOWN = "unknown"
_ACTOR_CLASSES = (_HUMAN, _BOT, _AI, _UNKNOWN)

#: Primary delivery/composition author set.
PRIMARY_AUTHOR_CLASSES = frozenset({_HUMAN, _AI})
#: The "not-known-bot" actor-sensitivity author set.
NOT_KNOWN_BOT_AUTHOR_CLASSES = frozenset({_HUMAN, _AI, _UNKNOWN})

#: Organization-week metrics that are zero-filled counts rather than NA-able
#: rates/medians.
COUNT_METRICS = (
    "active_repositories",
    "active_pr_authors",
    "active_human_reviewers",
    "opened_prs",
    "merged_prs",
)

#: The fixed, pre-specified ITS-eligible weekly outcome metrics. See
#: references/metrics.md.
ITS_ELIGIBLE_METRICS = (
    "merged_prs",
    "median_queue_to_merge",
    "human_review_coverage_rate",
    "median_time_to_first_human_review",
    "median_first_human_review_to_merge",
    "human_review_events_per_merged_pr",
    "changes_requested_rate",
    "post_review_commits_per_pr",
)


class AggregateError(Exception):
    """Raised when the panel cannot be built from committed evidence."""


@dataclass(slots=True)
class Entities:
    """Normalized entities loaded from ``<workdir>/normalized/``."""

    repositories: dict[int, dict[str, Any]]
    pull_requests: dict[tuple[int, int], dict[str, Any]]
    reviews: dict[tuple[int, int], list[dict[str, Any]]]
    pr_commits: dict[tuple[int, int], list[dict[str, Any]]]
    timeline_events: dict[tuple[int, int], list[dict[str, Any]]]
    draft_lifecycle: dict[tuple[int, int], dict[str, Any]]
    derivation: dict[str, Any]


@dataclass(slots=True)
class WeekRow:
    """One organization-week panel row."""

    week_start: datetime
    complete_week: bool
    metrics: dict[str, float | int | None] = field(default_factory=dict)


@dataclass(slots=True)
class Panel:
    """A built organization-week panel plus the parameters that produced it."""

    weeks: list[WeekRow]
    start: datetime
    end: datetime
    effective_observation_end: datetime
    repository_ids: frozenset[int] | None
    author_classes: frozenset[str]
    include_forks: bool


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    """Read an NDJSON entity file.

    Args:
        path: The file to read.

    Returns:
        Every row, in file order.

    Raises:
        AggregateError: If the file is missing, unreadable, or a line is
            not a valid JSON object.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"normalized entity file {path} could not be read: {exc}"
        raise AggregateError(msg) from exc
    rows: list[dict[str, Any]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            msg = f"{path} line {lineno} is not valid JSON: {exc}"
            raise AggregateError(msg) from exc
        if not isinstance(row, dict):
            msg = f"{path} line {lineno} must be a JSON object, got {row!r}"
            raise AggregateError(msg)
        rows.append(row)
    return rows


def load_entities(workdir_path: Path) -> Entities:
    """Load every normalized entity file for one workdir.

    Args:
        workdir_path: The skill's workdir root.

    Returns:
        The loaded entity tables, keyed for efficient panel construction.

    Raises:
        AggregateError: If ``normalized/derivation.json`` does not exist
            (``normalize`` has never run) or any entity file is malformed.
    """
    normalized_dir = workdir_path / "normalized"
    derivation_path = normalized_dir / "derivation.json"
    try:
        derivation = json.loads(derivation_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        msg = f"{derivation_path} does not exist; run 'normalize' before 'aggregate'"
        raise AggregateError(msg) from exc
    except OSError as exc:
        msg = f"{derivation_path} could not be read: {exc}"
        raise AggregateError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"{derivation_path} is not valid JSON: {exc}"
        raise AggregateError(msg) from exc
    repositories = {
        row["repository_id"]: row
        for row in _read_ndjson(normalized_dir / "repositories.ndjson")
    }
    pull_requests = {
        (row["repository_id"], row["pr_number"]): row
        for row in _read_ndjson(normalized_dir / "pull_requests.ndjson")
    }
    reviews: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in _read_ndjson(normalized_dir / "reviews.ndjson"):
        reviews.setdefault((row["repository_id"], row["pr_number"]), []).append(row)
    pr_commits: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in _read_ndjson(normalized_dir / "pr_commits.ndjson"):
        pr_commits.setdefault((row["repository_id"], row["pr_number"]), []).append(row)
    timeline_events: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in _read_ndjson(normalized_dir / "timeline_events.ndjson"):
        timeline_events.setdefault((row["repository_id"], row["pr_number"]), []).append(
            row
        )
    draft_lifecycle = {
        (row["repository_id"], row["pr_number"]): row
        for row in _read_ndjson(normalized_dir / "draft_lifecycle.ndjson")
    }
    return Entities(
        repositories=repositories,
        pull_requests=pull_requests,
        reviews=reviews,
        pr_commits=pr_commits,
        timeline_events=timeline_events,
        draft_lifecycle=draft_lifecycle,
        derivation=derivation,
    )


def resolve_effective_observation_end(
    entities: Entities, requested_end: datetime
) -> datetime:
    """Return ``min(requested_end, as_of)`` from the normalized derivation.

    Args:
        entities: The loaded normalized entities.
        requested_end: The requested exclusive UTC interval end.

    Returns:
        The conservative data cutoff.

    Raises:
        AggregateError: If ``derivation.json`` lacks a valid ``as_of``.
    """
    as_of_raw = entities.derivation.get("as_of")
    if not isinstance(as_of_raw, str) or not as_of_raw:
        msg = "normalized/derivation.json is missing a valid 'as_of' timestamp"
        raise AggregateError(msg)
    try:
        as_of = datetime.fromisoformat(as_of_raw)
    except ValueError as exc:
        msg = f"normalized/derivation.json 'as_of' is not a valid timestamp: {exc}"
        raise AggregateError(msg) from exc
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)
    return min(requested_end, as_of)


def check_history_coverage(
    workdir_path: Path,
    *,
    start: datetime,
    overlap_hours: int,
    repository_ids: frozenset[int] | None,
) -> None:
    """Fail closed if committed state does not cover the requested window.

    Reads committed state fresh from disk. Callers that already hold a
    pinned ``state`` snapshot (matched against loaded entities) should use
    :func:`check_history_coverage_for_state` instead, so the coverage check
    and the loaded entities are guaranteed to reflect the same committed
    generation.

    Args:
        workdir_path: The skill's workdir root.
        start: The requested inclusive UTC interval start.
        overlap_hours: The deterministic overlap used at collection time.
        repository_ids: Restrict the check to this repository set, or
            ``None`` for every committed repository.

    Raises:
        AggregateError: If committed state does not exist, or any in-scope
            repository's ``history_boundary`` does not reach
            ``start - overlap_hours``.
    """
    state = workdir.read_state(workdir_path)
    if not state:
        msg = f"workdir {workdir_path} has no committed collection state"
        raise AggregateError(msg)
    check_history_coverage_for_state(
        state, start=start, overlap_hours=overlap_hours, repository_ids=repository_ids
    )


def check_history_coverage_for_state(
    state: dict[str, Any],
    *,
    start: datetime,
    overlap_hours: int,
    repository_ids: frozenset[int] | None,
) -> None:
    """Fail closed if a pinned committed-state snapshot does not cover the window.

    Mirrors the issue's "stale-state fallback only when the prior committed
    state fully covers the requested interval" rule, enforced here since
    ``normalize`` does not apply a requested window at all. Takes an
    already-read ``state`` snapshot rather than reading it from disk, so a
    caller can pin it to the same committed generation its loaded entities
    came from.

    Args:
        state: A pinned committed ``state.json`` snapshot.
        start: The requested inclusive UTC interval start.
        overlap_hours: The deterministic overlap used at collection time.
        repository_ids: Restrict the check to this repository set, or
            ``None`` for every committed repository.

    Raises:
        AggregateError: If any in-scope repository's ``history_boundary``
            does not reach ``start - overlap_hours``.
    """
    required_boundary = start - timedelta(hours=overlap_hours)
    repositories = state.get("repositories", {})
    for key, entry in repositories.items():
        repo_id = int(key)
        if repository_ids is not None and repo_id not in repository_ids:
            continue
        boundary_raw = entry.get("history_boundary")
        if not isinstance(boundary_raw, str):
            msg = f"repository {repo_id} has no committed 'history_boundary'"
            raise AggregateError(msg)
        boundary = datetime.fromisoformat(boundary_raw)
        if boundary.tzinfo is None:
            boundary = boundary.replace(tzinfo=UTC)
        if boundary > required_boundary:
            msg = (
                f"repository {repo_id} historical coverage ({boundary.isoformat()}) "
                f"does not reach the requested window's required boundary "
                f"({required_boundary.isoformat()}); run 'collect' with an earlier "
                "--start before aggregating"
            )
            raise AggregateError(msg)


def _week_start(instant: datetime) -> datetime:
    """Return the Monday 00:00 UTC start of the ISO week containing ``instant``."""
    day_start = instant.astimezone(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return day_start - timedelta(days=day_start.weekday())


def _week_starts(start: datetime, end: datetime) -> list[datetime]:
    """Return the continuous, ordered ISO week starts covering ``[start, end)``."""
    weeks: list[datetime] = []
    cur = _week_start(start)
    while cur < end:
        weeks.append(cur)
        cur += timedelta(days=7)
    return weeks


def _parse_ts(value: object) -> datetime | None:
    """Parse an ISO-8601 UTC timestamp field, or return ``None`` if absent/invalid.

    Returns:
        The parsed, timezone-aware UTC instant, or ``None``.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _median_or_na(values: list[float]) -> float | None:
    """Return the median of ``values``, or ``None`` if it is empty."""
    return statistics.median(values) if values else None


def _rate_or_na(numerator: int, denominator: int) -> float | None:
    """Return ``numerator / denominator``, or ``None`` if ``denominator`` is 0."""
    return numerator / denominator if denominator else None


@dataclass(slots=True)
class _PRMetrics:
    """Per-qualifying-merged-PR derived facts, ready for weekly aggregation."""

    merged_week: datetime
    changed_files: float | None
    changed_lines: float | None
    queue_to_merge_hours: float | None
    human_reviewed: bool
    time_to_first_human_review_hours: float | None
    first_human_review_to_merge_hours: float | None
    human_review_events: int
    changes_requested: str  # "no_human_review" | "unavailable" | "yes" | "no"
    post_review_commits: int | None
    post_review_commits_available: bool


def _reconstruct_review_states(
    reviews: list[dict[str, Any]], timeline: list[dict[str, Any]]
) -> dict[Any, str | None]:
    """Map each review ID to its pre-dismissal (or current) state.

    Args:
        reviews: A PR's normalized review rows.
        timeline: A PR's normalized timeline-event rows.

    Returns:
        ``review_id`` -> effective state, or ``None`` if the review was
        dismissed but its pre-dismissal state could not be reconstructed.
    """
    dismissed_state: dict[Any, str | None] = {}
    for row in timeline:
        if row.get("event") != "review_dismissed":
            continue
        payload = row.get("payload")
        dismissed_review = (
            payload.get("dismissed_review") if isinstance(payload, dict) else None
        )
        if not isinstance(dismissed_review, dict):
            continue
        review_id = dismissed_review.get("review_id")
        state = dismissed_review.get("state")
        if review_id is not None:
            dismissed_state[review_id] = state if isinstance(state, str) else None
    return {
        review["review_id"]: dismissed_state.get(
            review["review_id"], review.get("state")
        )
        for review in reviews
    }


def _first_qualifying_human_review(
    reviews: list[dict[str, Any]],
    *,
    queue_entry: datetime | None,
    merged_at: datetime,
) -> dict[str, Any] | None:
    """Return the earliest independent human review eligible for queue metrics.

    Args:
        reviews: A PR's normalized review rows.
        queue_entry: The PR's reconstructed first queue entry, or ``None``.
        merged_at: The PR's merge timestamp.

    Returns:
        The winning review row, or ``None`` if there is no independent
        human review with ``queue_entry <= submitted_at <= merged_at``.
    """
    if queue_entry is None:
        return None
    candidates = []
    for review in reviews:
        if review.get("reviewer_classification") != _HUMAN or not review.get(
            "independent"
        ):
            continue
        submitted_at = _parse_ts(review.get("submitted_at"))
        if submitted_at is None or not (queue_entry <= submitted_at <= merged_at):
            continue
        candidates.append((submitted_at, review.get("review_id") or 0, review))
    if not candidates:
        return None
    candidates.sort(key=operator.itemgetter(0, 1))
    return candidates[0][2]


def _pr_metrics(
    pr: dict[str, Any],
    reviews: list[dict[str, Any]],
    commits: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    draft: dict[str, Any] | None,
) -> _PRMetrics:
    """Derive one qualifying merged PR's weekly-metric inputs.

    Args:
        pr: The PR's normalized row (already known to be a qualifying
            merged PR).
        reviews: The PR's normalized review rows.
        commits: The PR's normalized ``pr_commits`` rows.
        timeline: The PR's normalized timeline-event rows.
        draft: The PR's ``draft_lifecycle`` row, or ``None``.

    Returns:
        The derived per-PR facts used to build every weekly review/rework
        metric.

    Raises:
        AggregateError: If the PR row lacks a ``merged_at`` timestamp --
            it must already be known to qualify as merged by the caller.
    """
    merged_at = _parse_ts(pr["merged_at"])
    if merged_at is None:
        msg = (
            f"qualifying merged PR {pr['repository_id']}#{pr['pr_number']} "
            "lacks merged_at"
        )
        raise AggregateError(msg)
    queue_entry = (
        _parse_ts(draft.get("first_queue_entry"))
        if draft and draft.get("queue_entry_available")
        else None
    )
    queue_to_merge_hours = (
        (merged_at - queue_entry).total_seconds() / 3600.0
        if queue_entry is not None and queue_entry <= merged_at
        else None
    )
    eligible_reviews = [
        r
        for r in reviews
        if r.get("reviewer_classification") == _HUMAN
        and r.get("independent")
        and (ts := _parse_ts(r.get("submitted_at"))) is not None
        and ts <= merged_at
    ]
    human_review_events = len(eligible_reviews)
    first_review = _first_qualifying_human_review(
        reviews, queue_entry=queue_entry, merged_at=merged_at
    )
    time_to_first_hours = None
    first_to_merge_hours = None
    if first_review is not None and queue_entry is not None:
        submitted_at = _parse_ts(first_review["submitted_at"])
        if submitted_at is not None:
            time_to_first_hours = (submitted_at - queue_entry).total_seconds() / 3600.0
            first_to_merge_hours = (merged_at - submitted_at).total_seconds() / 3600.0
    states = _reconstruct_review_states(reviews, timeline)
    if not eligible_reviews:
        changes_requested = "no_human_review"
    else:
        resolved = [states.get(r["review_id"]) for r in eligible_reviews]
        changes_requested = (
            "unavailable"
            if any(s is None for s in resolved)
            else ("yes" if "CHANGES_REQUESTED" in resolved else "no")
        )
    post_review_commits, post_review_available = _post_review_commits(
        first_review, commits
    )
    return _PRMetrics(
        merged_week=_week_start(merged_at),
        changed_files=(
            float(pr["changed_files"])
            if isinstance(pr.get("changed_files"), int)
            else None
        ),
        changed_lines=(
            float(pr["additions"] + pr["deletions"])
            if isinstance(pr.get("additions"), int)
            and isinstance(pr.get("deletions"), int)
            else None
        ),
        queue_to_merge_hours=queue_to_merge_hours,
        human_reviewed=bool(eligible_reviews),
        time_to_first_human_review_hours=time_to_first_hours,
        first_human_review_to_merge_hours=first_to_merge_hours,
        human_review_events=human_review_events,
        changes_requested=changes_requested,
        post_review_commits=post_review_commits,
        post_review_commits_available=post_review_available,
    )


def _post_review_commits(
    first_review: dict[str, Any] | None, commits: list[dict[str, Any]]
) -> tuple[int | None, bool]:
    """Count commits after the first qualifying human review's reviewed commit.

    Args:
        first_review: The PR's first qualifying human review, or ``None``.
        commits: The PR's normalized ``pr_commits`` rows.

    Returns:
        ``(count, available)``. ``available`` is ``False`` (count ``None``)
        when there is no first qualifying review, the commit list was
        capped, or the reviewed commit is not present in the current list.
    """
    if first_review is None:
        return None, False
    reviewed_sha = first_review.get("commit_id")
    if not reviewed_sha or any(not c.get("available", True) for c in commits):
        return None, False
    by_sha = {c["sha"]: c["position"] for c in commits if c.get("sha") is not None}
    if reviewed_sha not in by_sha:
        return None, False
    position = by_sha[reviewed_sha]
    return sum(1 for c in commits if c.get("position", -1) > position), True


def _in_cohort(
    entities: Entities,
    repo_id: int,
    *,
    repository_ids: frozenset[int] | None,
    include_forks: bool,
) -> bool:
    """Report whether a repository is in the requested aggregation cohort.

    Returns:
        ``True`` if the repository is in scope.
    """
    if repository_ids is not None:
        return repo_id in repository_ids
    repo = entities.repositories.get(repo_id)
    if repo is None:
        return False
    return include_forks or not repo.get("fork")


def _accumulate_pr(
    entities: Entities,
    counters: dict[int, dict[str, Any]],
    week_index: dict[datetime, int],
    repo_id: int,
    pr_number: int,
    pr: dict[str, Any],
    *,
    start: datetime,
    effective_observation_end: datetime,
    author_classes: frozenset[str],
) -> None:
    """Fold one cohort PR's opened/review/merged events into ``counters``.

    Args:
        entities: Loaded normalized entities.
        counters: Per-week accumulator dicts, mutated in place.
        week_index: Week-start instant -> index into ``counters``.
        repo_id: The PR's repository ID.
        pr_number: The PR number.
        pr: The PR's normalized row.
        start: Requested inclusive UTC interval start.
        effective_observation_end: ``min(end, as_of)``.
        author_classes: The author-classification set counted as
            delivery/review activity.
    """
    created_at = _parse_ts(pr.get("created_at"))
    author_class = pr.get("author_classification")
    if (
        created_at is not None
        and start <= created_at < effective_observation_end
        and (w := _week_start(created_at)) in week_index
    ):
        idx = week_index[w]
        counters[idx]["opened_by_class"][author_class] = (
            counters[idx]["opened_by_class"].get(author_class, 0) + 1
        )
        if author_class in author_classes:
            counters[idx]["opened_prs"] += 1
            counters[idx]["active_repositories"].add(repo_id)
            actor_key = (pr.get("author_id"), pr.get("author_login"))
            counters[idx]["active_pr_authors"].add(actor_key)
    for review in entities.reviews.get((repo_id, pr_number), []):
        submitted_at = _parse_ts(review.get("submitted_at"))
        if submitted_at is None or not (
            start <= submitted_at < effective_observation_end
        ):
            continue
        w = _week_start(submitted_at)
        if w not in week_index:
            continue
        idx = week_index[w]
        reviewer_class = review.get("reviewer_classification")
        counters[idx]["reviews_by_class"][reviewer_class] = (
            counters[idx]["reviews_by_class"].get(reviewer_class, 0) + 1
        )
        # Reviews are neither "PR-authorship" nor "merge" events, so they do
        # not count toward active_repositories (see references/metrics.md).
        if reviewer_class == _HUMAN and review.get("independent"):
            counters[idx]["active_human_reviewers"].add((
                review.get("reviewer_id"),
                review.get("reviewer_login"),
            ))
    merged_at = _parse_ts(pr.get("merged_at"))
    if (
        merged_at is not None
        and start <= merged_at < effective_observation_end
        and author_class in author_classes
        and (w := _week_start(merged_at)) in week_index
    ):
        idx = week_index[w]
        counters[idx]["active_repositories"].add(repo_id)
        metrics = _pr_metrics(
            pr,
            entities.reviews.get((repo_id, pr_number), []),
            entities.pr_commits.get((repo_id, pr_number), []),
            entities.timeline_events.get((repo_id, pr_number), []),
            entities.draft_lifecycle.get((repo_id, pr_number)),
        )
        counters[idx]["merged_pr_metrics"].append(metrics)


def build_panel(
    entities: Entities,
    *,
    start: datetime,
    end: datetime,
    effective_observation_end: datetime,
    repository_ids: frozenset[int] | None = None,
    include_forks: bool = False,
    author_classes: frozenset[str] = PRIMARY_AUTHOR_CLASSES,
) -> Panel:
    """Build a continuous organization-week panel from normalized entities.

    Pure function of ``entities`` and the given window/cohort parameters --
    no filesystem or workdir access. Reused by ``analyze``'s sensitivity
    analyses with a narrowed ``repository_ids`` or a widened
    ``author_classes``.

    Args:
        entities: Loaded normalized entities.
        start: Requested inclusive UTC interval start.
        end: Requested exclusive UTC interval end.
        effective_observation_end: ``min(end, as_of)``.
        repository_ids: Restrict the cohort to these repository IDs, or
            ``None`` to use every non-fork (or, with ``include_forks``,
            every) committed repository.
        include_forks: Include forked repositories in the default cohort.
            Ignored when ``repository_ids`` is given explicitly.
        author_classes: The author-classification set counted as
            delivery/review activity (see references/metrics.md).

    Returns:
        The built panel.
    """
    weeks = _week_starts(start, end)
    week_index = {w: i for i, w in enumerate(weeks)}
    rows = [
        WeekRow(
            week_start=w,
            complete_week=(
                w >= _week_start(start)
                and w + timedelta(days=7) <= end
                and w + timedelta(days=7) <= effective_observation_end
                and w >= start
            ),
        )
        for w in weeks
    ]

    counters: dict[int, dict[str, Any]] = {
        i: {
            "active_repositories": set(),
            "active_pr_authors": set(),
            "active_human_reviewers": set(),
            "opened_prs": 0,
            "opened_by_class": dict.fromkeys(_ACTOR_CLASSES, 0),
            "reviews_by_class": dict.fromkeys(_ACTOR_CLASSES, 0),
            "merged_pr_metrics": [],
        }
        for i in range(len(weeks))
    }

    for (repo_id, pr_number), pr in entities.pull_requests.items():
        if not _in_cohort(
            entities,
            repo_id,
            repository_ids=repository_ids,
            include_forks=include_forks,
        ):
            continue
        _accumulate_pr(
            entities,
            counters,
            week_index,
            repo_id,
            pr_number,
            pr,
            start=start,
            effective_observation_end=effective_observation_end,
            author_classes=author_classes,
        )

    for idx, row in enumerate(rows):
        c = counters[idx]
        merged: list[_PRMetrics] = c["merged_pr_metrics"]
        row.metrics.update(_composition_metrics(c))
        row.metrics.update(_delivery_metrics(merged))
        row.metrics.update(_review_metrics(merged))
        row.metrics.update(_rework_metrics(merged))

    return Panel(
        weeks=rows,
        start=start,
        end=end,
        effective_observation_end=effective_observation_end,
        repository_ids=repository_ids,
        author_classes=author_classes,
        include_forks=include_forks,
    )


def _composition_metrics(counter: dict[str, Any]) -> dict[str, float | int | None]:
    """Build one week's scale/composition diagnostic metrics.

    Returns:
        The metrics dict for this week.
    """
    metrics: dict[str, float | int | None] = {
        "active_repositories": len(counter["active_repositories"]),
        "active_pr_authors": len(counter["active_pr_authors"]),
        "active_human_reviewers": len(counter["active_human_reviewers"]),
        "opened_prs": counter["opened_prs"],
    }
    opened_total = sum(counter["opened_by_class"].values())
    review_total = sum(counter["reviews_by_class"].values())
    for cls in _ACTOR_CLASSES:
        metrics[f"opened_prs_by_{cls}"] = counter["opened_by_class"][cls]
        metrics[f"opened_prs_by_{cls}_share"] = _rate_or_na(
            counter["opened_by_class"][cls], opened_total
        )
        metrics[f"reviews_by_{cls}"] = counter["reviews_by_class"][cls]
        metrics[f"reviews_by_{cls}_share"] = _rate_or_na(
            counter["reviews_by_class"][cls], review_total
        )
    return metrics


def _delivery_metrics(merged: list[_PRMetrics]) -> dict[str, float | int | None]:
    """Build one week's delivery/size metrics from its qualifying merged PRs.

    Returns:
        The metrics dict for this week.
    """
    queue_values = [
        m.queue_to_merge_hours for m in merged if m.queue_to_merge_hours is not None
    ]
    files_values = [m.changed_files for m in merged if m.changed_files is not None]
    lines_values = [m.changed_lines for m in merged if m.changed_lines is not None]
    return {
        "merged_prs": len(merged),
        "median_queue_to_merge": _median_or_na(queue_values),
        "median_queue_to_merge_n": len(queue_values),
        "median_changed_files": _median_or_na(files_values),
        "median_changed_files_n": len(files_values),
        "median_changed_lines": _median_or_na(lines_values),
        "median_changed_lines_n": len(lines_values),
    }


def _review_metrics(merged: list[_PRMetrics]) -> dict[str, float | int | None]:
    """Build one week's review-flow/burden metrics from its qualifying merged PRs.

    Returns:
        The metrics dict for this week.
    """
    denom = len(merged)
    covered = sum(1 for m in merged if m.human_reviewed)
    time_to_first = [
        m.time_to_first_human_review_hours
        for m in merged
        if m.time_to_first_human_review_hours is not None
    ]
    first_to_merge = [
        m.first_human_review_to_merge_hours
        for m in merged
        if m.first_human_review_to_merge_hours is not None
    ]
    review_events = sum(m.human_review_events for m in merged)
    cr_known = [
        m.changes_requested for m in merged if m.changes_requested in {"yes", "no"}
    ]
    cr_unavailable = sum(1 for m in merged if m.changes_requested == "unavailable")
    return {
        "human_review_coverage_rate": _rate_or_na(covered, denom),
        "human_review_coverage_rate_n": denom,
        "median_time_to_first_human_review": _median_or_na(time_to_first),
        "median_time_to_first_human_review_n": len(time_to_first),
        "median_first_human_review_to_merge": _median_or_na(first_to_merge),
        "median_first_human_review_to_merge_n": len(first_to_merge),
        "human_review_events_per_merged_pr": _rate_or_na(review_events, denom),
        "human_review_events_per_merged_pr_n": denom,
        "changes_requested_rate": _rate_or_na(cr_known.count("yes"), len(cr_known)),
        "changes_requested_rate_n": len(cr_known),
        "changes_requested_rate_unavailable_n": cr_unavailable,
    }


def _rework_metrics(merged: list[_PRMetrics]) -> dict[str, float | int | None]:
    """Build one week's pre-merge rework metrics from its qualifying merged PRs.

    Returns:
        The metrics dict for this week.
    """
    available = [
        m.post_review_commits
        for m in merged
        if m.post_review_commits_available and m.post_review_commits is not None
    ]
    unavailable = sum(1 for m in merged if not m.post_review_commits_available)
    return {
        "post_review_commits_per_pr": _median_or_na([float(v) for v in available]),
        "post_review_commits_per_pr_n": len(available),
        "post_review_commits_per_pr_unavailable_n": unavailable,
    }


#: The ordered, fixed set of columns written to ``organization-week.csv``.
def panel_columns() -> list[str]:
    """Return the fixed, ordered CSV column set for the organization-week panel."""
    columns = ["week_start", "complete_week"]
    columns.extend(COUNT_METRICS)
    for cls in _ACTOR_CLASSES:
        columns.extend([
            f"opened_prs_by_{cls}",
            f"opened_prs_by_{cls}_share",
            f"reviews_by_{cls}",
            f"reviews_by_{cls}_share",
        ])
    columns.extend([
        "median_queue_to_merge",
        "median_queue_to_merge_n",
        "median_changed_files",
        "median_changed_files_n",
        "median_changed_lines",
        "median_changed_lines_n",
        "human_review_coverage_rate",
        "human_review_coverage_rate_n",
        "median_time_to_first_human_review",
        "median_time_to_first_human_review_n",
        "median_first_human_review_to_merge",
        "median_first_human_review_to_merge_n",
        "human_review_events_per_merged_pr",
        "human_review_events_per_merged_pr_n",
        "changes_requested_rate",
        "changes_requested_rate_n",
        "changes_requested_rate_unavailable_n",
        "post_review_commits_per_pr",
        "post_review_commits_per_pr_n",
        "post_review_commits_per_pr_unavailable_n",
    ])
    return columns


def panel_to_rows(panel: Panel) -> list[dict[str, Any]]:
    """Render a :class:`Panel` into ordered CSV-ready row dicts.

    Args:
        panel: The built panel.

    Returns:
        One dict per week, keyed by :func:`panel_columns`, with ``None``
        rendered as the empty string for NA cells.
    """
    columns = panel_columns()
    rows = []
    for week in panel.weeks:
        row: dict[str, Any] = {
            "week_start": week.week_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "complete_week": week.complete_week,
        }
        row.update(week.metrics)
        rows.append({
            col: row.get(col, "") if row.get(col) is not None else "" for col in columns
        })
    return rows


@dataclass(slots=True)
class AggregateOutcome:
    """The result of one ``aggregate`` invocation."""

    panel: Panel
    csv_path: Path
    meta_path: Path


def run_aggregate(
    *,
    workdir_path: Path,
    start: datetime,
    end: datetime,
    overlap_hours: int = 24,
    include_forks: bool = False,
) -> AggregateOutcome:
    """Build and persist the primary organization-week panel for a workdir.

    Args:
        workdir_path: The skill's workdir root.
        start: Requested inclusive UTC interval start.
        end: Requested exclusive UTC interval end.
        overlap_hours: The deterministic overlap used to check committed
            historical coverage against ``start``.
        include_forks: Include forked repositories in the primary cohort.

    Returns:
        The outcome: the built panel and the paths it was written to.

    Raises:
        AggregateError: If entities cannot be loaded, no committed state
            exists, committed state has advanced past the generation
            ``normalize`` derived entities from, or committed history does
            not cover the requested window.
    """
    entities = load_entities(workdir_path)
    state = workdir.read_state(workdir_path)
    if not state:
        msg = f"workdir {workdir_path} has no committed collection state"
        raise AggregateError(msg)
    if state.get("committed_run_id") != entities.derivation.get("committed_run_id"):
        msg = (
            f"committed state advanced to run {state.get('committed_run_id')!r} since "
            f"'normalize' derived entities from run "
            f"{entities.derivation.get('committed_run_id')!r}; run 'normalize' again "
            "before aggregating so entities and coverage reflect the same generation"
        )
        raise AggregateError(msg)
    check_history_coverage_for_state(
        state, start=start, overlap_hours=overlap_hours, repository_ids=None
    )
    effective_end = resolve_effective_observation_end(entities, end)
    panel = build_panel(
        entities,
        start=start,
        end=end,
        effective_observation_end=effective_end,
        include_forks=include_forks,
    )
    report_dir = workdir_path / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "organization-week.csv"
    _write_csv(csv_path, panel)
    meta_path = report_dir / "organization-week.meta.json"
    workdir.atomic_write_json(
        meta_path,
        {
            "schema_version": AGGREGATE_SCHEMA_VERSION,
            "requested_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "requested_end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "effective_observation_end": effective_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "overlap_hours": overlap_hours,
            "include_forks": include_forks,
            "committed_run_id": entities.derivation.get("committed_run_id"),
            "as_of": entities.derivation.get("as_of"),
        },
    )
    return AggregateOutcome(panel=panel, csv_path=csv_path, meta_path=meta_path)


def _write_csv(path: Path, panel: Panel) -> None:
    """Write a panel to CSV atomically via a temp file plus rename."""
    columns = panel_columns()
    tmp_path = path.with_name(f"{path.name}.tmp.{secrets.token_hex(4)}")
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(panel_to_rows(panel))
    tmp_path.replace(path)
