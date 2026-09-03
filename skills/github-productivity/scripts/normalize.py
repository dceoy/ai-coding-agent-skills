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

The entity files are a deterministic function of the committed lineage
manifests, their raw NDJSON evidence, the normalized actor map, and the
module schema version: running it twice on the same inputs produces
byte-identical entity files. ``derivation.json`` additionally records the
normalizer's own git revision as provenance -- that field, and only that
field, can differ between two runs over identical inputs from different
checkouts. It performs no GitHub access and acquires no collection lock;
it must not be run concurrently with itself (the entity files are written
through independent atomic renames and could interleave).
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
            objects each carrying a valid integer ``actor_id`` and/or
            string ``login``. Wrong-typed identity fields fail closed
            rather than being silently dropped.
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
        _consume_actor_map_entry(path, entry, ids, logins)
    return ActorMap(frozenset(ids), frozenset(logins))


def _consume_actor_map_entry(
    path: Path, entry: object, ids: set[int], logins: set[str]
) -> None:
    """Validate one ``explicit_ai_agents`` entry into ``ids`` / ``logins``.

    Args:
        path: The actor-map path, for error messages.
        entry: One raw list element.
        ids: The accumulating explicit-AI-agent ``actor_id`` set.
        logins: The accumulating casefolded explicit-AI-agent login set.

    Raises:
        NormalizeError: If the entry is not an object with a valid integer
            ``actor_id`` and/or string ``login`` (JSON booleans are not
            valid IDs).
    """
    if not isinstance(entry, dict) or not ({"actor_id", "login"} & entry.keys()):
        msg = (
            f"actor map at {path}: each entry needs an 'actor_id' or 'login' "
            f"key, got {entry!r}"
        )
        raise NormalizeError(msg)
    if "actor_id" in entry:
        actor_id = entry["actor_id"]
        if isinstance(actor_id, bool) or not isinstance(actor_id, int):
            msg = (
                f"actor map at {path}: 'actor_id' must be an integer, got {actor_id!r}"
            )
            raise NormalizeError(msg)
        ids.add(actor_id)
    if "login" in entry:
        login = entry["login"]
        if not isinstance(login, str):
            msg = f"actor map at {path}: 'login' must be a string, got {login!r}"
            raise NormalizeError(msg)
        logins.add(login.casefold())


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
    if login_cf is not None and github_type in {None, "User"}:
        return _CLASS_HUMAN, "user"
    reason = (
        github_type.casefold()
        if github_type in {"Mannequin", "Organization"}
        else "unclassifiable"
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

    Raises:
        NormalizeError: If ``repositories`` is not a dict, a key is not a
            numeric repository ID, an entry is not a dict, or a
            ``touched_pr_numbers`` element is not an int -- a malformed
            committed manifest must fail closed rather than silently drop
            PR identities.
    """
    pairs: set[tuple[int, int]] = set()
    repositories = manifest.get("repositories", {})
    if not isinstance(repositories, dict):
        msg = f"manifest 'repositories' must be an object, got {repositories!r}"
        raise NormalizeError(msg)
    for key, entry in repositories.items():
        try:
            repo_id = int(key)
        except (TypeError, ValueError) as exc:
            msg = f"manifest repository key {key!r} must be a numeric repository ID"
            raise NormalizeError(msg) from exc
        if not isinstance(entry, dict):
            msg = f"manifest repository entry {key!r} must be an object, got {entry!r}"
            raise NormalizeError(msg)
        numbers = entry.get("touched_pr_numbers", [])
        for number in numbers:
            if isinstance(number, bool) or not isinstance(number, int):
                msg = (
                    f"manifest repository {key!r} 'touched_pr_numbers' entry "
                    f"must be an integer, got {number!r}"
                )
                raise NormalizeError(msg)
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

    Raises:
        NormalizeError: If ``limitations`` is not a list or an entry is not
            an object -- a malformed committed manifest must fail closed
            rather than being silently read as "this PR was not capped".
    """
    limitations = manifest.get("limitations", [])
    if not isinstance(limitations, list):
        msg = f"manifest 'limitations' must be an array, got {limitations!r}"
        raise NormalizeError(msg)
    for limitation in limitations:
        if not isinstance(limitation, dict):
            msg = f"manifest 'limitations' entry must be an object, got {limitation!r}"
            raise NormalizeError(msg)
        if (
            limitation.get("kind") == "pr_commits_exceed_endpoint_cap"
            and limitation.get("repository_id") == repo_id
            and limitation.get("pr_number") == pr_number
        ):
            return True
    return False


#: The four per-run raw bundle files every touched PR contributes to.
_BUNDLE_FILES = ("pulls.ndjson", "reviews.ndjson", "commits.ndjson", "timeline.ndjson")


def _read_run_bucket(raw_root: Path, filename: str) -> dict[tuple[int, int], list[Any]]:
    """Read one run's raw bundle file once, bucketed by ``(repo_id, pr)``.

    ``collect`` writes a single file per bundle type per run, with every
    touched PR from every repository interleaved. Records are keyed by
    ``pr_number`` plus ``provenance.repository_id`` -- filtering on
    ``pr_number`` alone would merge two repositories that happen to share a
    PR number.

    Args:
        raw_root: The winning run's raw evidence directory.
        filename: The bundle file name (for example ``"reviews.ndjson"``).

    Returns:
        ``payload`` lists keyed by ``(repository_id, pr_number)``, each in
        the order the lines appear on disk.

    Raises:
        NormalizeError: If the file does not exist or is unreadable -- a
            lineage-committed run is expected to hold every bundle endpoint
            -- or a line is not valid JSON, not an object, or missing a
            well-typed ``pr_number``/``provenance.repository_id`` -- a
            damaged committed record must fail closed rather than silently
            disappear.
    """
    path = raw_root / filename
    try:
        handle = path.open(encoding="utf-8")
    except FileNotFoundError as exc:
        msg = (
            f"committed run evidence file {path} is missing; the committed "
            "lineage points at incomplete or damaged evidence"
        )
        raise NormalizeError(msg) from exc
    except OSError as exc:
        msg = f"committed run evidence file {path} is unreadable: {exc}"
        raise NormalizeError(msg) from exc
    buckets: dict[tuple[int, int], list[Any]] = {}
    with handle:
        for lineno, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                msg = f"raw evidence in {path} line {lineno} is not valid JSON: {exc}"
                raise NormalizeError(msg) from exc
            if not isinstance(record, dict):
                msg = (
                    f"raw evidence in {path} line {lineno} must be an object, "
                    f"got {record!r}"
                )
                raise NormalizeError(msg)
            pr_number = record.get("pr_number")
            provenance = record.get("provenance")
            repo_id = (
                provenance.get("repository_id")
                if isinstance(provenance, dict)
                else None
            )
            if not isinstance(pr_number, int) or not isinstance(repo_id, int):
                msg = (
                    f"raw evidence in {path} line {lineno} must have an integer "
                    f"'pr_number' and 'provenance.repository_id', got "
                    f"pr_number={pr_number!r} provenance={provenance!r}"
                )
                raise NormalizeError(msg)
            buckets.setdefault((repo_id, pr_number), []).append(record.get("payload"))
    return buckets


def _flatten(payloads: list[Any], *, source: str) -> list[dict[str, Any]]:
    """Flatten a list of page payloads into a single ordered record list.

    Args:
        payloads: Page payloads, each a list of records (or a single
            record).
        source: A description of the payloads' origin, for error messages.

    Returns:
        Every record, in page then in-page order.

    Raises:
        NormalizeError: If a payload is neither a list nor an object, or a
            list element is not an object -- malformed committed page data
            must fail closed rather than being silently filtered out.
    """
    records: list[dict[str, Any]] = []
    for payload in payloads:
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    msg = f"{source} page element must be an object, got {item!r}"
                    raise NormalizeError(msg)
                records.append(item)
        elif isinstance(payload, dict):
            records.append(payload)
        else:
            msg = f"{source} page payload must be an object or array, got {payload!r}"
            raise NormalizeError(msg)
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


def _build_run_bundles(
    workdir_path: Path,
    manifest: dict[str, Any],
    pr_ids: list[tuple[int, int]],
) -> list[_Bundle]:
    """Read one winning run's four bundle files once and build its bundles.

    Args:
        workdir_path: The skill's workdir root.
        manifest: The winning run's finalized manifest.
        pr_ids: The ``(repository_id, pr_number)`` pairs whose winning run
            is this one.

    Returns:
        One :class:`_Bundle` per entry in ``pr_ids``.

    Raises:
        NormalizeError: If the manifest lacks a string ``run_id``, a bundle
            file is missing, or a touched PR has no PR object in its
            winning run -- all signs of damaged committed evidence.
    """
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str):
        msg = "a committed lineage manifest is missing a string 'run_id'"
        raise NormalizeError(msg)
    raw_root = workdir.raw_dir(workdir_path, run_id)
    files = {name: _read_run_bucket(raw_root, name) for name in _BUNDLE_FILES}
    bundles: list[_Bundle] = []
    for key in pr_ids:
        pr_payloads = files["pulls.ndjson"].get(key, [])
        pr_object = next(
            (p for p in reversed(pr_payloads) if isinstance(p, dict)), None
        )
        if pr_object is None:
            msg = (
                f"committed run {run_id} has no PR object for {key[0]}#{key[1]}; "
                "the committed lineage points at damaged evidence"
            )
            raise NormalizeError(msg)
        bundles.append(
            _Bundle(
                repo_id=key[0],
                pr_number=key[1],
                source_run_id=run_id,
                pr_object=pr_object,
                reviews=_flatten(
                    files["reviews.ndjson"].get(key, []), source="reviews.ndjson"
                ),
                commits=_flatten(
                    files["commits.ndjson"].get(key, []), source="commits.ndjson"
                ),
                timeline=_flatten(
                    files["timeline.ndjson"].get(key, []), source="timeline.ndjson"
                ),
                commits_capped=_cap_exceeded(manifest, key[0], key[1]),
            )
        )
    return bundles


def _select_winning_runs(
    ordered_runs: list[dict[str, Any]],
) -> dict[tuple[int, int], str]:
    """Map each touched PR to the newest committed run that touched it.

    Args:
        ordered_runs: Lineage manifests sorted newest first by
            ``(refresh_started_at, run_id)``.

    Returns:
        ``(repository_id, pr_number)`` -> winning ``run_id``. Whole-bundle
        replacement: a PR touched by several runs is served entirely from
        the newest one; mutable child rows are never unioned across runs.

    Raises:
        NormalizeError: If a lineage manifest lacks a string ``run_id`` --
            dropping its touched PRs silently would fail open.
    """
    winning: dict[tuple[int, int], str] = {}
    for manifest in ordered_runs:
        run_id = manifest.get("run_id")
        if not isinstance(run_id, str):
            msg = "a committed lineage manifest lacks a string 'run_id'"
            raise NormalizeError(msg)
        for pair in _touched_prs(manifest):
            winning.setdefault(pair, run_id)
    return winning


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

    Raises:
        NormalizeError: If ``repositories`` is not a dict, an entry is not a
            dict, or a key is not a numeric repository ID -- a malformed
            committed ``state.json`` must fail closed rather than silently
            drop repositories.
    """
    rows: list[dict[str, Any]] = []
    repositories = state.get("repositories", {})
    if not isinstance(repositories, dict):
        msg = f"state 'repositories' must be an object, got {repositories!r}"
        raise NormalizeError(msg)
    for key, entry in repositories.items():
        if not isinstance(entry, dict):
            msg = f"state repository entry {key!r} must be an object, got {entry!r}"
            raise NormalizeError(msg)
        try:
            repo_id = int(key)
        except (TypeError, ValueError) as exc:
            msg = f"state repository key {key!r} must be a numeric repository ID"
            raise NormalizeError(msg) from exc
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
        schema version. It trusts ``derivation.json`` alone -- an entity
        file deleted or truncated out of band is not detected here; rerun
        with ``force=True`` to rebuild the whole tree.
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


def _gather_bundles(
    workdir_path: Path, ordered_runs: list[dict[str, Any]]
) -> list[_Bundle]:
    """Resolve every touched PR to its winning bundle, in stable key order.

    Reads each winning run's four bundle files exactly once, so cost is
    linear in total evidence size rather than quadratic in PR count.

    Args:
        workdir_path: The skill's workdir root.
        ordered_runs: Lineage manifests, newest first.

    Returns:
        One :class:`_Bundle` per touched ``(repository_id, pr_number)``,
        sorted by that key.
    """
    winning_run = _select_winning_runs(ordered_runs)
    pr_ids = sorted(winning_run)
    runs_by_id = {
        m["run_id"]: m for m in ordered_runs if isinstance(m.get("run_id"), str)
    }
    by_run: dict[str, list[tuple[int, int]]] = {}
    for pair in pr_ids:
        by_run.setdefault(winning_run[pair], []).append(pair)
    built: dict[tuple[int, int], _Bundle] = {}
    for run_id, pairs in by_run.items():
        for bundle in _build_run_bundles(workdir_path, runs_by_id[run_id], pairs):
            built[bundle.repo_id, bundle.pr_number] = bundle
    return [built[pair] for pair in pr_ids]


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
        NormalizeError: If nothing is committed, the committed state or a
            lineage manifest is unreadable, or the actor map is unreadable
            or malformed.
    """
    try:
        state = workdir.read_state(workdir_path)
    except (json.JSONDecodeError, OSError) as exc:
        msg = f"committed state in {workdir_path} is unreadable: {exc}"
        raise NormalizeError(msg) from exc
    if not state or not state.get("committed_run_id"):
        msg = f"workdir {workdir_path} has no committed collection state to normalize"
        raise NormalizeError(msg)
    actor_map = load_actor_map(actor_map_path)
    fingerprint = actor_map.fingerprint()
    committed_run_id = state["committed_run_id"]
    try:
        lineage = workdir.resolve_committed_lineage(workdir_path, state)
    except json.JSONDecodeError as exc:
        msg = f"a committed lineage manifest in {workdir_path} is not valid JSON: {exc}"
        raise NormalizeError(msg) from exc
    if not lineage:
        msg = f"committed run {committed_run_id} resolves to an empty lineage"
        raise NormalizeError(msg)
    ordered_runs = sorted(
        lineage,
        key=lambda m: (_parse_manifest_ts(m), str(m.get("run_id") or "")),
        reverse=True,
    )
    newest = ordered_runs[0]
    derivation = {
        "committed_run_id": committed_run_id,
        "source_run_ids": [str(m.get("run_id") or "") for m in ordered_runs],
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
    bundles = _gather_bundles(workdir_path, ordered_runs)
    out_dir = workdir_path / "normalized"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "derivation.json").unlink(missing_ok=True)
    _write_entities(out_dir, state, bundles, actor_map)
    workdir.atomic_write_json(out_dir / "derivation.json", derivation)
    return NormalizeOutcome(committed_run_id, "written", derivation)
