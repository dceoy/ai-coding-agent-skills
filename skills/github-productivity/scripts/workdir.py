"""Workdir layout, single-writer locking, and committed-state transactions.

This module owns the on-disk transaction model described in the
``github-productivity`` skill's methodology: append-only raw evidence per
run, write-once immutable manifests, and an atomically replaced
``state.json`` that is the sole acceptance frontier for committed
collection coverage. ``collect`` is the only writer; every other command
reads a single pinned ``state.json`` snapshot.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

#: Schema version for both run manifests and ``state.json``. Bump when the
#: on-disk shape changes in a way that is not backward compatible.
SCHEMA_VERSION = 1

_MANIFEST_STATUSES = frozenset({"complete", "incomplete"})

#: Bounds the local ``git rev-parse`` call used to resolve the collector's
#: own revision so a wedged or missing ``git`` cannot block a run.
_REVISION_TIMEOUT_SECONDS = 5


class WorkdirLockedError(Exception):
    """Raised when a collection lock is already held by another run."""


class ManifestAlreadyFinalizedError(Exception):
    """Raised when finalizing a run manifest that already exists on disk."""


class CommittedLineageError(Exception):
    """Raised when the committed run lineage cannot be resolved from disk."""


class OrganizationMismatchError(Exception):
    """Raised when a workdir's committed state belongs to a different org.

    A workdir is scoped to one organization. Reusing it for a different
    ``--org`` would silently carry the prior organization's repositories
    forward into state now labeled with the new one.
    """


def raw_dir(workdir: Path, run_id: str) -> Path:
    """Return the append-only raw evidence directory for one run.

    Args:
        workdir: The skill's workdir root.
        run_id: The collection run ID.

    Returns:
        The path ``<workdir>/raw/<run_id>``.
    """
    return workdir / "raw" / run_id


def manifests_dir(workdir: Path) -> Path:
    """Return the directory holding finalized run manifests.

    Args:
        workdir: The skill's workdir root.

    Returns:
        The path ``<workdir>/manifests``.
    """
    return workdir / "manifests"


def manifest_path(workdir: Path, run_id: str) -> Path:
    """Return the finalized manifest path for one run.

    Args:
        workdir: The skill's workdir root.
        run_id: The collection run ID.

    Returns:
        The path ``<workdir>/manifests/<run_id>.json``.
    """
    return manifests_dir(workdir) / f"{run_id}.json"


def state_path(workdir: Path) -> Path:
    """Return the path of the committed ``state.json``.

    Args:
        workdir: The skill's workdir root.

    Returns:
        The path ``<workdir>/state.json``.
    """
    return workdir / "state.json"


def lock_path(workdir: Path) -> Path:
    """Return the path of the single-writer collection lock file.

    Args:
        workdir: The skill's workdir root.

    Returns:
        The path ``<workdir>/.collect.lock``.
    """
    return workdir / ".collect.lock"


def organization_binding_path(workdir: Path) -> Path:
    """Return the path of the workdir's immutable organization binding.

    Args:
        workdir: The skill's workdir root.

    Returns:
        The path ``<workdir>/organization.json``.
    """
    return workdir / "organization.json"


def new_run_id() -> str:
    """Generate a new collection run ID.

    Returns:
        A run ID composed of the current UTC timestamp and a random
        suffix, safe to use as a filesystem path component.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(4)}"


def resolve_collector_revision() -> str | None:
    """Resolve the executing collector's own git commit revision.

    Recorded in every finalized manifest as ``collector_revision`` so a run
    can be traced back to the exact collector code that produced it, even
    for a behavior change that does not bump ``SCHEMA_VERSION``. Best
    effort: this skill can run from a checkout with no ``git`` binary
    available, or from a copy with no ``.git`` directory at all.

    Returns:
        The full commit SHA of the repository containing this script, or
        ``None`` if it cannot be resolved (``git`` is missing, this script
        is not inside a git working tree, the call times out, or any other
        failure).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=_REVISION_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    revision = result.stdout.strip()
    return revision or None


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON to ``path`` atomically via a temp file plus rename.

    Args:
        path: Destination path. Its parent directory must already exist.
        data: JSON-serializable data to write.
    """
    tmp_path = path.with_name(f"{path.name}.tmp.{secrets.token_hex(4)}")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    tmp_path.replace(path)


def append_ndjson(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON record as a line to an append-only NDJSON file.

    Args:
        path: The NDJSON file to append to. Created, along with its parent
            directory, if it does not already exist.
        record: JSON-serializable record to append.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True))
        handle.write("\n")


@dataclass(slots=True)
class CollectionLock:
    """An exclusive, single-writer lock over one workdir.

    Acquire before reading mutable committed state and hold through
    discovery, canonical refetches, manifest finalization, and the atomic
    state commit. Use as a context manager.
    """

    workdir: Path
    run_id: str
    _acquired: bool = False

    def __enter__(self) -> Self:
        """Acquire the lock, failing closed if already held.

        Returns:
            This lock instance.

        Raises:
            WorkdirLockedError: If another run already holds the lock.
            OSError: If the lock file is created but writing its content
                fails; the just-created file is removed before re-raising.
        """
        path = lock_path(self.workdir)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.touch(exist_ok=False)
        except FileExistsError as exc:
            msg = f"workdir {self.workdir} is already locked by another collection run"
            raise WorkdirLockedError(msg) from exc
        try:
            path.write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "run_id": self.run_id,
                        "acquired_at": datetime.now(UTC).isoformat(),
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        except OSError:
            path.unlink(missing_ok=True)
            raise
        self._acquired = True
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Release the lock if held, but only if it still names this run.

        A lock manually cleared by an operator (v1 has no automatic
        stale-lock recovery) could already have been re-acquired by a
        different run by the time this releases; unlinking unconditionally
        would delete that other run's lock instead of this one's.
        """
        if not self._acquired:
            return
        path = lock_path(self.workdir)
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._acquired = False
            return
        if isinstance(content, dict) and content.get("run_id") == self.run_id:
            path.unlink(missing_ok=True)
        self._acquired = False


def read_state(workdir: Path) -> dict[str, Any] | None:
    """Read and pin the current committed ``state.json`` snapshot.

    Args:
        workdir: The skill's workdir root.

    Returns:
        The committed state as a dict, or ``None`` if no collection has
        ever committed for this workdir.
    """
    path = state_path(workdir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(workdir: Path, state: dict[str, Any]) -> None:
    """Atomically replace the committed ``state.json``.

    Args:
        workdir: The skill's workdir root.
        state: The new committed state. Must already reflect a
            successfully finalized ``complete`` manifest.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(state_path(workdir), state)


def finalize_manifest(workdir: Path, run_id: str, manifest: dict[str, Any]) -> None:
    """Write a run manifest exactly once. Never overwrite an existing one.

    Args:
        workdir: The skill's workdir root.
        run_id: The collection run ID.
        manifest: The manifest body. Must include a ``status`` of either
            ``"complete"`` or ``"incomplete"``.

    Raises:
        ManifestAlreadyFinalizedError: If a manifest for this run ID
            already exists.
        ValueError: If ``manifest["status"]`` is not a recognized value.
    """
    if manifest.get("status") not in _MANIFEST_STATUSES:
        msg = f"manifest status must be one of {sorted(_MANIFEST_STATUSES)}"
        raise ValueError(msg)
    path = manifest_path(workdir, run_id)
    if path.exists():
        msg = f"manifest for run {run_id} is already finalized"
        raise ManifestAlreadyFinalizedError(msg)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, manifest)


def read_manifest(workdir: Path, run_id: str) -> dict[str, Any]:
    """Read one finalized run manifest.

    Args:
        workdir: The skill's workdir root.
        run_id: The collection run ID.

    Returns:
        The manifest body. The file must already exist.
    """
    return json.loads(manifest_path(workdir, run_id).read_text(encoding="utf-8"))


def manifest_organizations(workdir: Path) -> set[str]:
    """Collect every organization recorded across this workdir's manifests.

    Unlike :func:`read_state`, this looks at every manifest that exists,
    complete or incomplete, not just the committed lineage — a workdir
    should never mix evidence for more than one organization, even before
    its first successful commit.

    Args:
        workdir: The skill's workdir root.

    Returns:
        The set of ``organization`` values found. Empty if no manifest
        exists yet, or none records an organization.
    """
    directory = manifests_dir(workdir)
    if not directory.exists():
        return set()
    organizations: set[str] = set()
    for path in directory.glob("*.json"):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict):
            continue
        org = manifest.get("organization")
        if isinstance(org, str):
            organizations.add(org)
    return organizations


def read_organization_binding(workdir: Path) -> str | None:
    """Read the workdir's bound organization, if one has been recorded.

    Unlike :func:`manifest_organizations`, this binding is written before
    the first live API call of the workdir's first run — it is the only
    record of a workdir's organization when that first run is killed
    before any manifest, even an incomplete one, is ever finalized.

    Args:
        workdir: The skill's workdir root.

    Returns:
        The bound organization, or ``None`` if no binding has been
        recorded yet (the binding file does not exist).

    Raises:
        OrganizationMismatchError: If the binding file exists but is
            unreadable, not valid JSON, not a JSON object, or lacks a
            string ``organization`` field. A corrupted binding must never
            be treated the same as "no binding" — that would let a run
            for a different organization silently pass the guard this
            binding exists to enforce.
    """
    path = organization_binding_path(workdir)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        msg = f"organization binding at {path} exists but could not be read: {exc}"
        raise OrganizationMismatchError(msg) from exc
    try:
        content = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"organization binding at {path} exists but is not valid JSON: {exc}"
        raise OrganizationMismatchError(msg) from exc
    org = content.get("organization") if isinstance(content, dict) else None
    if not isinstance(org, str):
        msg = (
            f"organization binding at {path} exists but does not hold a JSON "
            "object with a string 'organization' field"
        )
        raise OrganizationMismatchError(msg)
    return org


def bind_organization(workdir: Path, org: str) -> None:
    """Record the workdir's organization binding, once, if not already set.

    Must be called under the collection lock, before the first live API
    call of the workdir's first run, so a process killed before any
    manifest is finalized still leaves a record of which organization owns
    this workdir's raw evidence. A no-op if a binding already exists — the
    binding is immutable for the life of the workdir.

    Args:
        workdir: The skill's workdir root.
        org: The organization login to bind this workdir to.
    """
    path = organization_binding_path(workdir)
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, {"organization": org})


def resolve_committed_lineage(
    workdir: Path, state: dict[str, Any]
) -> list[dict[str, Any]]:
    """Walk the committed run lineage from ``state["committed_run_id"]``.

    Args:
        workdir: The skill's workdir root.
        state: A pinned committed state snapshot, as returned by
            :func:`read_state`.

    Returns:
        Manifests on the committed lineage, newest first. A ``complete``
        manifest not reachable through this walk is uncommitted orphan
        evidence and must never be treated as canonical.

    Raises:
        CommittedLineageError: If the lineage chain is broken, for example
            a referenced manifest is missing, not ``complete``, or the
            chain cycles back to a run already visited.
    """
    lineage: list[dict[str, Any]] = []
    seen: set[str] = set()
    run_id = state.get("committed_run_id")
    while run_id is not None:
        if run_id in seen:
            msg = f"committed lineage cycles back to already-visited run {run_id}"
            raise CommittedLineageError(msg)
        seen.add(run_id)
        try:
            manifest = read_manifest(workdir, run_id)
        except FileNotFoundError as exc:
            msg = f"committed lineage references missing manifest {run_id}"
            raise CommittedLineageError(msg) from exc
        if manifest.get("status") != "complete":
            msg = f"committed lineage references non-complete manifest {run_id}"
            raise CommittedLineageError(msg)
        lineage.append(manifest)
        run_id = manifest.get("previous_committed_run_id")
    return lineage
