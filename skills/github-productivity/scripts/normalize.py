"""Deterministic normalization of committed collection runs into entities.

``normalize`` is a read-only derivation step. It reads exactly one pinned
``state.json`` snapshot, walks the committed run lineage
(:func:`workdir.resolve_committed_lineage`), and writes a deterministic set
of entity files under ``<workdir>/normalized/``:

- ``repositories.ndjson`` -- one row per committed repository ID.
- ``pull_requests.ndjson`` -- one row per ``(repository_id, pr_number)``,
  taken from the single newest committed snapshot bundle that touched the
  PR. Bundles are *replaced* whole, never unioned across runs.
- ``reviews.ndjson`` / ``timeline_events.ndjson`` / ``pr_commits.ndjson``
  -- child rows from that same winning bundle.
- ``draft_lifecycle.ndjson`` -- reconstructed first queue-entry per PR.
- ``actors.ndjson`` -- deduped actor registry with a deterministic
  classification (``human`` / ``bot`` / ``explicit-ai-agent`` /
  ``unknown``).
- ``derivation.json`` -- written last; the commit point that records what
  the tree was derived from, including the actor-classification
  fingerprint.

Output is a pure function of the committed lineage manifests, their raw
NDJSON evidence, the normalized actor map, and the module schema version:
running it twice on the same inputs produces a byte-identical tree. It
performs no GitHub access and acquires no collection lock.
"""

from __future__ import annotations

import hashlib
import json
import operator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import workdir

if TYPE_CHECKING:
    from pathlib import Path

#: Bump when the shape of anything under ``normalized/`` changes. Combined
#: with the committed run ID and the actor fingerprint to decide whether an
#: existing ``normalized/`` tree is still current.
NORMALIZE_SCHEMA_VERSION = 1

#: Timeline event names retained for downstream review/draft reconstruction.
_RETAINED_TIMELINE_EVENTS = frozenset({
    "reviewed",
    "review_dismissed",
    "ready_for_review",
    "convert_to_draft",
})
_DRAFT_EVENTS = ("ready_for_review", "convert_to_draft")

_CLASS_HUMAN = "human"
_CLASS_BOT = "bot"
_CLASS_AI = "explicit-ai-agent"
_CLASS_UNKNOWN = "unknown"


class NormalizeError(Exception):
    """Raised when normalization cannot proceed from committed evidence.

    Covers a workdir with nothing committed and an unreadable or
    malformed ``--actor-map`` file. A broken committed lineage raises
    :class:`workdir.CommittedLineageError` instead.
    """


@dataclass(slots=True)
class NormalizeOutcome:
    """The result of one ``normalize`` invocation."""

    committed_run_id: str
    status: str
    derivation: dict[str, Any]


@dataclass(slots=True)
class ActorMap:
    """A normalized, derivation-only explicit-AI-agent mapping."""

    actor_ids: frozenset[int]
    logins: frozenset[str]

    def canonical(self) -> dict[str, list[Any]]:
        """Return the canonical JSON-ready form used for fingerprinting.

        Returns:
            A dict with sorted ``actor_ids`` and ``logins`` lists.
        """
        return {
            "actor_ids": sorted(self.actor_ids),
            "logins": sorted(self.logins),
        }

    def fingerprint(self) -> str:
        """Return a stable hex digest over the canonical mapping.

        Returns:
            The SHA-256 digest of the canonical JSON form.
        """
        canonical = json.dumps(self.canonical(), sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_actor_map(path: Path | None) -> ActorMap:
    """Load and normalize the explicit-AI-agent mapping.

    Args:
        path: Path to a JSON file with an ``explicit_ai_agents`` list of
            ``{"actor_id": int}`` and/or ``{"login": str}`` entries, or
            ``None`` for an empty mapping.

    Returns:
        The normalized mapping.

    Raises:
        NormalizeError: If the file cannot be read, is not valid JSON, is
            not a JSON object, or ``explicit_ai_agents`` is not a list of
            ``actor_id``/``login`` objects.
    """
    if path is None:
        return ActorMap(frozenset(), frozenset())
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"actor map at {path} could not be read: {exc}"
        raise NormalizeError(msg) from exc
    try:
        content = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"actor map at {path} is not valid JSON: {exc}"
        raise NormalizeError(msg) from exc
    if not isinstance(content, dict):
        msg = f"actor map at {path} must be a JSON object"
        raise NormalizeError(msg)
    entries = content.get("explicit_ai_agents", [])
    if not isinstance(entries, list):
        msg = f"actor map at {path}: 'explicit_ai_agents' must be a list"
        raise NormalizeError(msg)
    ids: set[int] = set()
    logins: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not ({"actor_id", "login"} & entry.keys()):
            msg = (
                f"actor map at {path}: each entry needs an 'actor_id' or 'login' "
                f"key, got {entry!r}"
            )
            raise NormalizeError(msg)
        if isinstance(entry.get("actor_id"), int):
            ids.add(entry["actor_id"])
        if isinstance(entry.get("login"), str):
            logins.add(entry["login"].casefold())
    return ActorMap(frozenset(ids), frozenset(logins))


def classify_actor(
    actor: dict[str, Any] | None, actor_map: ActorMap
) -> tuple[str, str]:
    """Classify one GitHub-visible actor by explicit precedence.

    Args:
        actor: A GitHub user/actor object (``id``, ``login``, ``type``),
            or ``None`` for a deleted/absent identity.
        actor_map: The normalized explicit-AI-agent mapping.

    Returns:
        A ``(classification, reason)`` pair. ``classification`` is one of
        ``human``, ``bot``, ``explicit-ai-agent``, ``unknown``.
    """
    if not actor:
        return _CLASS_UNKNOWN, "missing"
    actor_id = actor.get("id")
    login = actor.get("login")
    login_cf = login.casefold() if isinstance(login, str) else None
    github_type = actor.get("type")
    if isinstance(actor_id, int) and actor_id in actor_map.actor_ids:
        return _CLASS_AI, "actor_map_actor_id"
    if login_cf is not None and login_cf in actor_map.logins:
        return _CLASS_AI, "actor_map_login"
    if github_type == "Bot" or (login_cf is not None and login_cf.endswith("[bot]")):
        return _CLASS_BOT, ("github_type_bot" if github_type == "Bot" else "bot_login")
    if github_type == "User" and login_cf is not None:
        return _CLASS_HUMAN, "user"
    known_unknown = {"Mannequin", "Organization"}
    reason = (
        github_type.casefold() if github_type in known_unknown else "unclassifiable"
    )
    return _CLASS_UNKNOWN, reason


def _parse_manifest_ts(manifest: dict[str, Any]) -> str:
    """Return a manifest's ``refresh_started_at`` for ordering.

    Args:
        manifest: A finalized run manifest.

    Returns:
        The ISO-8601 ``refresh_started_at`` string; empty if absent.
    """
    value = manifest.get("refresh_started_at")
    return value if isinstance(value, str) else ""


def _touched_prs(manifest: dict[str, Any]) -> set[tuple[int, int]]:
    """Return ``(repository_id, pr_number)`` pairs touched by one run.

    Args:
        manifest: A finalized run manifest.

    Returns:
        The set of touched PR identities recorded in the manifest.
    """
    pairs: set[tuple[int, int]] = set()
    repositories = manifest.get("repositories", {})
    if not isinstance(repositories, dict):
        return pairs
    for key, entry in repositories.items():
        try:
            repo_id = int(key)
        except (TypeError, ValueError):
            continue
        for number in entry.get("touched_pr_numbers", []):
            if isinstance(number, int):
                pairs.add((repo_id, number))
    return pairs


def _cap_exceeded(manifest: dict[str, Any], repo_id: int, pr_number: int) -> bool:
    """Report whether a PR's commit list was capped in the winning run.

    Args:
        manifest: The winning run's manifest.
        repo_id: The PR's repository ID.
        pr_number: The PR number.

    Returns:
        ``True`` if the manifest records a ``pr_commits_exceed_endpoint_cap``
        limitation for this PR.
    """
    for limitation in manifest.get("limitations", []):
        if (
            limitation.get("kind") == "pr_commits_exceed_endpoint_cap"
            and limitation.get("repository_id") == repo_id
            and limitation.get("pr_number") == pr_number
        ):
            return True
    return False


def _read_bundle_lines(raw_root: Path, filename: str, pr_number: int) -> list[Any]:
    """Read one raw NDJSON file's payloads for a single PR, in file order.

    Args:
        raw_root: The winning run's raw evidence directory.
        filename: The bundle file name (for example ``"reviews.ndjson"``).
        pr_number: The PR number whose records to keep.

    Returns:
        The ``payload`` of every line whose ``pr_number`` matches, in the
        order the lines appear on disk.
    """
    path = raw_root / filename
    if not path.exists():
        return []
    payloads: list[Any] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        record = json.loads(line)
        if record.get("pr_number") == pr_number:
            payloads.append(record.get("payload"))
    return payloads


def _flatten(payloads: list[Any]) -> list[dict[str, Any]]:
    """Flatten a list of page payloads into a single ordered record list.

    Args:
        payloads: Page payloads, each a list of records (or a single
            record).

    Returns:
        Every record, in page then in-page order.
    """
    records: list[dict[str, Any]] = []
    for payload in payloads:
        if isinstance(payload, list):
            records.extend(item for item in payload if isinstance(item, dict))
        elif isinstance(payload, dict):
            records.append(payload)
    return records


@dataclass(slots=True)
class _Bundle:
    """One PR's winning committed snapshot bundle."""

    repo_id: int
    pr_number: int
    source_run_id: str
    pr_object: dict[str, Any]
    reviews: list[dict[str, Any]]
    commits: list[dict[str, Any]]
    timeline: list[dict[str, Any]]
    commits_capped: bool


def _select_bundle(
    workdir_path: Path,
    repo_id: int,
    pr_number: int,
    ordered_runs: list[dict[str, Any]],
) -> _Bundle:
    """Select and read the newest committed bundle that touched a PR.

    Args:
        workdir_path: The skill's workdir root.
        repo_id: The PR's repository ID.
        pr_number: The PR number.
        ordered_runs: Lineage manifests sorted newest first by
            ``(refresh_started_at, run_id)``.

    Returns:
        The winning bundle.

    Raises:
        NormalizeError: If no committed run records this PR as touched
            (a committed-lineage invariant violation).
    """
    for manifest in ordered_runs:
        if (repo_id, pr_number) not in _touched_prs(manifest):
            continue
        run_id = manifest["run_id"]
        raw_root = workdir.raw_dir(workdir_path, run_id)
        pr_payloads = _read_bundle_lines(raw_root, "pulls.ndjson", pr_number)
        pr_object = next((p for p in reversed(pr_payloads) if isinstance(p, dict)), {})
        return _Bundle(
            repo_id=repo_id,
            pr_number=pr_number,
            source_run_id=run_id,
            pr_object=pr_object,
            reviews=_flatten(_read_bundle_lines(raw_root, "reviews.ndjson", pr_number)),
            commits=_flatten(_read_bundle_lines(raw_root, "commits.ndjson", pr_number)),
            timeline=_flatten(
                _read_bundle_lines(raw_root, "timeline.ndjson", pr_number)
            ),
            commits_capped=_cap_exceeded(manifest, repo_id, pr_number),
        )
    msg = (
        f"no committed run touched PR {repo_id}#{pr_number}; the committed "
        "lineage is inconsistent with its own manifests"
    )
    raise NormalizeError(msg)


def _actor_of(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return the GitHub actor object on a PR/review/timeline record.

    Args:
        record: A record that may carry a ``user`` or ``actor`` object.

    Returns:
        The ``user`` object if present, else the ``actor`` object, else
        ``None``.
    """
    for key in ("user", "actor"):
        value = record.get(key)
        if isinstance(value, dict):
            return value
    return None


def _pr_row(bundle: _Bundle, actor_map: ActorMap) -> dict[str, Any]:
    """Build the ``pull_requests.ndjson`` row for one bundle.

    Args:
        bundle: The PR's winning snapshot bundle.
        actor_map: The normalized explicit-AI-agent mapping.

    Returns:
        The normalized PR row.
    """
    pr = bundle.pr_object
    author = pr.get("user")
    author = author if isinstance(author, dict) else None
    classification = classify_actor(author, actor_map)[0]
    head = pr.get("head")
    head = head if isinstance(head, dict) else {}
    base = pr.get("base")
    base = base if isinstance(base, dict) else {}
    return {
        "repository_id": bundle.repo_id,
        "pr_number": bundle.pr_number,
        "source_run_id": bundle.source_run_id,
        "author_id": author.get("id") if author else None,
        "author_login": author.get("login") if author else None,
        "author_classification": classification,
        "draft": pr.get("draft"),
        "state": pr.get("state"),
        "created_at": pr.get("created_at"),
        "closed_at": pr.get("closed_at"),
        "merged_at": pr.get("merged_at"),
        "merge_commit_sha": pr.get("merge_commit_sha"),
        "head_sha": head.get("sha"),
        "base_sha": base.get("sha"),
        "additions": pr.get("additions"),
        "deletions": pr.get("deletions"),
        "changed_files": pr.get("changed_files"),
        "commit_count": pr.get("commits"),
    }


def _review_rows(bundle: _Bundle, actor_map: ActorMap) -> list[dict[str, Any]]:
    """Build the ``reviews.ndjson`` rows for one bundle.

    Args:
        bundle: The PR's winning snapshot bundle.
        actor_map: The normalized explicit-AI-agent mapping.

    Returns:
        Normalized review rows, one per formal review, sorted by review ID.
    """
    author = bundle.pr_object.get("user")
    author_id = author.get("id") if isinstance(author, dict) else None
    rows: list[dict[str, Any]] = []
    for review in bundle.reviews:
        reviewer = review.get("user")
        reviewer = reviewer if isinstance(reviewer, dict) else None
        classification = classify_actor(reviewer, actor_map)[0]
        reviewer_id = reviewer.get("id") if reviewer else None
        rows.append({
            "repository_id": bundle.repo_id,
            "pr_number": bundle.pr_number,
            "review_id": review.get("id"),
            "reviewer_id": reviewer_id,
            "reviewer_login": reviewer.get("login") if reviewer else None,
            "reviewer_classification": classification,
            "state": review.get("state"),
            "submitted_at": review.get("submitted_at"),
            "commit_id": review.get("commit_id"),
            "independent": reviewer_id is not None and reviewer_id != author_id,
        })
    rows.sort(key=lambda r: (r["review_id"] is None, r["review_id"] or 0))
    return rows


def _commit_rows(bundle: _Bundle) -> list[dict[str, Any]]:
    """Build the ``pr_commits.ndjson`` rows for one bundle.

    Args:
        bundle: The PR's winning snapshot bundle.

    Returns:
        Either one availability row (``available: false``) when the PR's
        commit list exceeded GitHub's endpoint cap, or one ``available``
        row per commit with its 0-based ordered position.
    """
    common = {
        "repository_id": bundle.repo_id,
        "pr_number": bundle.pr_number,
        "source_run_id": bundle.source_run_id,
    }
    if bundle.commits_capped:
        return [
            {**common, "available": False, "reason": "pr_commits_exceed_endpoint_cap"}
        ]
    return [
        {**common, "available": True, "position": position, "sha": commit.get("sha")}
        for position, commit in enumerate(bundle.commits)
    ]


def _timeline_rows(bundle: _Bundle) -> list[dict[str, Any]]:
    """Build the ``timeline_events.ndjson`` rows for one bundle.

    Args:
        bundle: The PR's winning snapshot bundle.

    Returns:
        One row per retained timeline event, in observed order, carrying
        the verbatim event payload.
    """
    rows: list[dict[str, Any]] = []
    for index, event in enumerate(bundle.timeline):
        name = event.get("event")
        if name not in _RETAINED_TIMELINE_EVENTS:
            continue
        rows.append({
            "repository_id": bundle.repo_id,
            "pr_number": bundle.pr_number,
            "observed_index": index,
            "event": name,
            "created_at": event.get("created_at"),
            "payload": event,
        })
    return rows


def _draft_lifecycle_row(bundle: _Bundle) -> dict[str, Any]:
    """Reconstruct one PR's first queue entry from draft-lifecycle events.

    Args:
        bundle: The PR's winning snapshot bundle.

    Returns:
        The ``draft_lifecycle.ndjson`` row: the ordered draft transitions
        plus the derived ``first_queue_entry`` / ``queue_entry_available``
        / ``reason``. v1 does not subtract later draft intervals.
    """
    created_at = bundle.pr_object.get("created_at")
    currently_draft = bool(bundle.pr_object.get("draft"))
    transitions = [
        {"event": e.get("event"), "created_at": e.get("created_at")}
        for e in bundle.timeline
        if e.get("event") in _DRAFT_EVENTS
    ]
    common = {
        "repository_id": bundle.repo_id,
        "pr_number": bundle.pr_number,
        "source_run_id": bundle.source_run_id,
        "transitions": transitions,
    }
    if any(not isinstance(t["created_at"], str) for t in transitions):
        return {
            **common,
            "initially_draft": None,
            "first_queue_entry": None,
            "queue_entry_available": False,
            "reason": "inconsistent_history",
        }
    if not transitions:
        if currently_draft:
            return {
                **common,
                "initially_draft": True,
                "first_queue_entry": None,
                "queue_entry_available": False,
                "reason": "still_draft_never_ready",
            }
        return {
            **common,
            "initially_draft": False,
            "first_queue_entry": created_at,
            "queue_entry_available": isinstance(created_at, str),
            "reason": "no_lifecycle_events_not_draft",
        }
    earliest = min(transitions, key=lambda t: str(t["created_at"]))
    if earliest["event"] == "ready_for_review":
        return {
            **common,
            "initially_draft": True,
            "first_queue_entry": earliest["created_at"],
            "queue_entry_available": True,
            "reason": "ready_for_review",
        }
    return {
        **common,
        "initially_draft": False,
        "first_queue_entry": created_at,
        "queue_entry_available": isinstance(created_at, str),
        "reason": "convert_to_draft",
    }


def _collect_actors(
    bundles: list[_Bundle], actor_map: ActorMap
) -> list[dict[str, Any]]:
    """Build the deduped actor registry across every winning bundle.

    Args:
        bundles: Every PR's winning snapshot bundle, in stable order.
        actor_map: The normalized explicit-AI-agent mapping.

    Returns:
        Actor rows sorted by ``(actor_id is None, actor_id, login)``. When
        one stable ``actor_id`` appears with more than one login, the
        first seen in this deterministic traversal wins.
    """
    registry: dict[str, dict[str, Any]] = {}
    for bundle in bundles:
        records: list[dict[str, Any]] = [bundle.pr_object, *bundle.reviews]
        records.extend(
            e for e in bundle.timeline if e.get("event") in _RETAINED_TIMELINE_EVENTS
        )
        for record in records:
            actor = _actor_of(record)
            if actor is None:
                continue
            actor_id = actor.get("id")
            login = actor.get("login")
            key = f"id:{actor_id}" if isinstance(actor_id, int) else f"login:{login}"
            if key in registry:
                continue
            classification, reason = classify_actor(actor, actor_map)
            registry[key] = {
                "actor_id": actor_id if isinstance(actor_id, int) else None,
                "login": login if isinstance(login, str) else None,
                "github_type": actor.get("type"),
                "classification": classification,
                "classification_reason": reason,
            }
    return sorted(
        registry.values(),
        key=lambda a: (a["actor_id"] is None, a["actor_id"] or 0, a["login"] or ""),
    )


def _repository_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the ``repositories.ndjson`` rows from committed state.

    Args:
        state: The pinned committed ``state.json`` snapshot.

    Returns:
        One row per committed repository ID, sorted by numeric ID. Forks
        and archived repositories are retained and flagged; cohort choices
        are a later aggregation-time decision.
    """
    rows: list[dict[str, Any]] = []
    for key, entry in state.get("repositories", {}).items():
        try:
            repo_id = int(key)
        except (TypeError, ValueError):
            continue
        rows.append({
            "repository_id": repo_id,
            "name": entry.get("name"),
            "archived": entry.get("archived"),
            "fork": entry.get("fork"),
            "created_at": entry.get("created_at"),
            "last_seen_in_enumeration_at": entry.get("last_seen_in_enumeration_at"),
        })
    rows.sort(key=operator.itemgetter("repository_id"))
    return rows


def _existing_is_current(
    workdir_path: Path, committed_run_id: str, fingerprint: str
) -> bool:
    """Report whether an existing ``normalized/`` tree is still current.

    Args:
        workdir_path: The skill's workdir root.
        committed_run_id: The currently committed run ID.
        fingerprint: The actor-classification fingerprint for this run.

    Returns:
        ``True`` if ``normalized/derivation.json`` exists and was derived
        from the same committed run, actor fingerprint, and normalizer
        schema version.
    """
    path = workdir_path / "normalized" / "derivation.json"
    try:
        derivation = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        derivation.get("committed_run_id") == committed_run_id
        and derivation.get("actor_classification_fingerprint") == fingerprint
        and derivation.get("normalizer_schema_version") == NORMALIZE_SCHEMA_VERSION
    )


def _write_entities(
    out_dir: Path,
    state: dict[str, Any],
    bundles: list[_Bundle],
    actor_map: ActorMap,
) -> None:
    """Write every entity NDJSON file (but not ``derivation.json``).

    Args:
        out_dir: The ``<workdir>/normalized`` directory.
        state: The pinned committed state snapshot.
        bundles: Every PR's winning snapshot bundle, in stable order.
        actor_map: The normalized explicit-AI-agent mapping.
    """
    pr_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    commit_rows: list[dict[str, Any]] = []
    timeline_rows: list[dict[str, Any]] = []
    draft_rows: list[dict[str, Any]] = []
    for bundle in bundles:
        pr_rows.append(_pr_row(bundle, actor_map))
        review_rows.extend(_review_rows(bundle, actor_map))
        commit_rows.extend(_commit_rows(bundle))
        timeline_rows.extend(_timeline_rows(bundle))
        draft_rows.append(_draft_lifecycle_row(bundle))
    workdir.atomic_write_ndjson(
        out_dir / "repositories.ndjson", _repository_rows(state)
    )
    workdir.atomic_write_ndjson(out_dir / "pull_requests.ndjson", pr_rows)
    workdir.atomic_write_ndjson(out_dir / "reviews.ndjson", review_rows)
    workdir.atomic_write_ndjson(out_dir / "pr_commits.ndjson", commit_rows)
    workdir.atomic_write_ndjson(out_dir / "timeline_events.ndjson", timeline_rows)
    workdir.atomic_write_ndjson(out_dir / "draft_lifecycle.ndjson", draft_rows)
    workdir.atomic_write_ndjson(
        out_dir / "actors.ndjson", _collect_actors(bundles, actor_map)
    )


def run_normalize(
    *,
    workdir_path: Path,
    actor_map_path: Path | None = None,
    force: bool = False,
) -> NormalizeOutcome:
    """Normalize the committed lineage into ``<workdir>/normalized/``.

    Propagates :class:`workdir.CommittedLineageError` when the committed
    run lineage cannot be resolved.

    Args:
        workdir_path: The skill's workdir root.
        actor_map_path: Optional path to the explicit-AI-agent mapping.
        force: Regenerate even if the existing tree is already current.

    Returns:
        The outcome, including whether files were rewritten and the
        derivation metadata.

    Raises:
        NormalizeError: If nothing is committed, or the actor map is
            unreadable or malformed.
    """
    state = workdir.read_state(workdir_path)
    if state is None or "committed_run_id" not in state:
        msg = f"workdir {workdir_path} has no committed collection state to normalize"
        raise NormalizeError(msg)
    actor_map = load_actor_map(actor_map_path)
    fingerprint = actor_map.fingerprint()
    committed_run_id = state["committed_run_id"]
    lineage = workdir.resolve_committed_lineage(workdir_path, state)
    ordered_runs = sorted(
        lineage, key=lambda m: (_parse_manifest_ts(m), m["run_id"]), reverse=True
    )
    newest = ordered_runs[0] if ordered_runs else {}
    derivation = {
        "committed_run_id": committed_run_id,
        "source_run_ids": [m["run_id"] for m in ordered_runs],
        "as_of": _parse_manifest_ts(newest),
        "requested_interval": newest.get("requested_interval"),
        "schema_version": workdir.SCHEMA_VERSION,
        "normalizer_schema_version": NORMALIZE_SCHEMA_VERSION,
        "actor_classification_fingerprint": fingerprint,
        "actor_map": actor_map.canonical(),
        "normalizer_revision": workdir.resolve_collector_revision() or "unavailable",
    }
    if not force and _existing_is_current(workdir_path, committed_run_id, fingerprint):
        return NormalizeOutcome(committed_run_id, "already-current", derivation)
    pr_ids = sorted({
        pair for manifest in ordered_runs for pair in _touched_prs(manifest)
    })
    bundles = [
        _select_bundle(workdir_path, repo_id, pr_number, ordered_runs)
        for repo_id, pr_number in pr_ids
    ]
    out_dir = workdir_path / "normalized"
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_entities(out_dir, state, bundles, actor_map)
    workdir.atomic_write_json(out_dir / "derivation.json", derivation)
    return NormalizeOutcome(committed_run_id, "written", derivation)
