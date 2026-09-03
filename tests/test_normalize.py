"""Tests for deterministic normalization of committed collection runs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import ghapi
import normalize
import pytest
import workdir

if TYPE_CHECKING:
    from pathlib import Path


def _write_raw(
    workdir_path: Path, run_id: str, pr_number: int, bundle: dict[str, Any]
) -> None:
    """Append one PR's raw snapshot bundle to a run's evidence directory."""
    raw_root = workdir.raw_dir(workdir_path, run_id)
    workdir.append_ndjson(
        raw_root / "pulls.ndjson",
        {"pr_number": pr_number, "provenance": {}, "payload": bundle.get("pr", {})},
    )
    for name in ("reviews", "commits", "timeline"):
        workdir.append_ndjson(
            raw_root / f"{name}.ndjson",
            {
                "pr_number": pr_number,
                "provenance": {},
                "payload": bundle.get(name, []),
            },
        )


def commit_run(
    workdir_path: Path,
    *,
    run_id: str,
    refresh_started_at: str,
    prs: dict[int, dict[str, Any]],
    repo_id: int = 1,
    repo: dict[str, Any] | None = None,
    previous_committed_run_id: str | None = None,
    limitations: list[dict[str, Any]] | None = None,
    commit: bool = True,
) -> None:
    """Build one finalized ``complete`` run and optionally commit state to it.

    Args:
        workdir_path: The workdir root.
        run_id: The run ID.
        refresh_started_at: The manifest's ``refresh_started_at``.
        prs: ``{pr_number: {"pr": {...}, "reviews": [...], "commits": [...],
            "timeline": [...]}}`` bundles to write as raw evidence and mark
            touched.
        repo_id: The repository ID the PRs belong to.
        repo: Optional repository metadata for ``state.json``.
        previous_committed_run_id: The prior committed run, recorded in the
            manifest and walked by the lineage resolver.
        limitations: Manifest ``limitations`` entries.
        commit: When ``True``, atomically point ``state.json`` at this run.
    """
    for pr_number, bundle in prs.items():
        _write_raw(workdir_path, run_id, pr_number, bundle)
    repo_meta = repo or {
        "name": "repo1",
        "archived": False,
        "fork": False,
        "created_at": "2020-01-01T00:00:00Z",
    }
    manifest = {
        "schema_version": workdir.SCHEMA_VERSION,
        "run_id": run_id,
        "status": "complete",
        "previous_committed_run_id": previous_committed_run_id,
        "organization": "acme",
        "requested_interval": {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-07-01T00:00:00Z",
        },
        "refresh_started_at": refresh_started_at,
        "repositories": {
            str(repo_id): {**repo_meta, "touched_pr_numbers": sorted(prs)}
        },
        "failures": [],
        "limitations": limitations or [],
    }
    workdir.finalize_manifest(workdir_path, run_id, manifest)
    if commit:
        workdir.write_state(
            workdir_path,
            {
                "schema_version": workdir.SCHEMA_VERSION,
                "committed_run_id": run_id,
                "organization": "acme",
                "repositories": {
                    str(repo_id): {
                        **repo_meta,
                        "discovery_watermark": refresh_started_at,
                        "history_boundary": "2020-01-01T00:00:00Z",
                        "last_seen_in_enumeration_at": refresh_started_at,
                    }
                },
            },
        )


def _rows(workdir_path: Path, name: str) -> list[dict[str, Any]]:
    """Read one normalized NDJSON file into a list of rows."""
    path = workdir_path / "normalized" / name
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _user(
    actor_id: int | None, login: str | None, actor_type: str = "User"
) -> dict[str, Any]:
    """Build a minimal GitHub actor object."""
    return {"id": actor_id, "login": login, "type": actor_type}


def _pr_object(number: int, **overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """Build a minimal PR object with sensible defaults."""
    base = {
        "number": number,
        "user": _user(10, "alice"),
        "draft": False,
        "state": "closed",
        "created_at": "2026-02-01T00:00:00Z",
        "merged_at": "2026-02-03T00:00:00Z",
        "commits": 0,
    }
    base.update(overrides)
    return base


def test_no_committed_state_raises_normalize_error(tmp_path: Path) -> None:
    """A workdir with nothing committed cannot be normalized."""
    with pytest.raises(normalize.NormalizeError, match="no committed"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_normalize_is_byte_identical_on_repeated_runs(tmp_path: Path) -> None:
    """Running normalize twice on identical inputs rewrites an identical tree."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={
            7: {
                "pr": _pr_object(7, commits=2),
                "reviews": [
                    {
                        "id": 200,
                        "user": _user(11, "bob"),
                        "state": "APPROVED",
                        "submitted_at": "2026-02-02T00:00:00Z",
                        "commit_id": "c1",
                    }
                ],
                "commits": [{"sha": "c1"}, {"sha": "c2"}],
                "timeline": [
                    {
                        "event": "reviewed",
                        "created_at": "2026-02-02T00:00:00Z",
                        "user": _user(11, "bob"),
                    }
                ],
            }
        },
    )
    first = normalize.run_normalize(workdir_path=tmp_path)
    assert first.status == "written"
    tree_a = {
        p.name: p.read_bytes() for p in sorted((tmp_path / "normalized").iterdir())
    }
    normalize.run_normalize(workdir_path=tmp_path, force=True)
    tree_b = {
        p.name: p.read_bytes() for p in sorted((tmp_path / "normalized").iterdir())
    }
    assert tree_a == tree_b


def test_already_current_tree_is_not_rewritten(tmp_path: Path) -> None:
    """A second normalize with the same inputs reports already-current."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    normalize.run_normalize(workdir_path=tmp_path)
    outcome = normalize.run_normalize(workdir_path=tmp_path)
    assert outcome.status == "already-current"


def test_newer_bundle_replaces_earlier_one_wholesale(tmp_path: Path) -> None:
    """A later run touching a PR wins for the PR object, reviews, and timeline."""
    commit_run(
        tmp_path,
        run_id="run-old",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={
            7: {
                "pr": _pr_object(7, state="open", merged_at=None),
                "reviews": [{"id": 1, "user": _user(11, "bob"), "state": "COMMENTED"}],
                "timeline": [
                    {
                        "event": "reviewed",
                        "created_at": "2026-02-02T00:00:00Z",
                        "user": _user(11, "bob"),
                    }
                ],
            }
        },
    )
    commit_run(
        tmp_path,
        run_id="run-new",
        refresh_started_at="2026-03-08T00:00:00Z",
        previous_committed_run_id="run-old",
        prs={
            7: {
                "pr": _pr_object(7, state="closed", merged_at="2026-03-05T00:00:00Z"),
                "reviews": [{"id": 2, "user": _user(11, "bob"), "state": "APPROVED"}],
                "timeline": [
                    {
                        "event": "reviewed",
                        "created_at": "2026-03-04T00:00:00Z",
                        "user": _user(11, "bob"),
                    }
                ],
            }
        },
    )
    normalize.run_normalize(workdir_path=tmp_path)
    pr_rows = _rows(tmp_path, "pull_requests.ndjson")
    assert len(pr_rows) == 1
    assert pr_rows[0]["source_run_id"] == "run-new"
    assert pr_rows[0]["merged_at"] == "2026-03-05T00:00:00Z"
    assert [r["review_id"] for r in _rows(tmp_path, "reviews.ndjson")] == [2]
    tl = _rows(tmp_path, "timeline_events.ndjson")
    assert [e["created_at"] for e in tl] == ["2026-03-04T00:00:00Z"]


def test_force_push_removing_a_commit_is_not_unioned(tmp_path: Path) -> None:
    """Canonical commits exactly match the newest bundle, never a union."""
    commit_run(
        tmp_path,
        run_id="run-old",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={
            7: {
                "pr": _pr_object(7, commits=3),
                "commits": [{"sha": "a"}, {"sha": "b"}, {"sha": "c"}],
            }
        },
    )
    commit_run(
        tmp_path,
        run_id="run-new",
        refresh_started_at="2026-03-08T00:00:00Z",
        previous_committed_run_id="run-old",
        prs={
            7: {
                "pr": _pr_object(7, commits=2),
                "commits": [{"sha": "a2"}, {"sha": "b2"}],
            }
        },
    )
    normalize.run_normalize(workdir_path=tmp_path)
    commit_rows = _rows(tmp_path, "pr_commits.ndjson")
    assert [(r["position"], r["sha"]) for r in commit_rows] == [(0, "a2"), (1, "b2")]


def test_winner_ordering_uses_refresh_started_at_not_run_id_lexical(
    tmp_path: Path,
) -> None:
    """The newest bundle wins by refresh time even if its run ID sorts first."""
    commit_run(
        tmp_path,
        run_id="zzz-early",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7, additions=1)}},
    )
    commit_run(
        tmp_path,
        run_id="aaa-late",
        refresh_started_at="2026-03-09T00:00:00Z",
        previous_committed_run_id="zzz-early",
        prs={7: {"pr": _pr_object(7, additions=99)}},
    )
    normalize.run_normalize(workdir_path=tmp_path)
    pr_rows = _rows(tmp_path, "pull_requests.ndjson")
    assert pr_rows[0]["source_run_id"] == "aaa-late"
    assert pr_rows[0]["additions"] == 99


def test_pr_commits_endpoint_cap_yields_unavailable_row(tmp_path: Path) -> None:
    """A capped commit list is marked unavailable rather than truncated."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={
            7: {
                "pr": _pr_object(7, commits=400),
                "commits": [{"sha": f"c{i}"} for i in range(250)],
            }
        },
        limitations=[
            {
                "kind": "pr_commits_exceed_endpoint_cap",
                "repository_id": 1,
                "pr_number": 7,
                "expected_commits": 400,
                "collected_commits": 250,
            }
        ],
    )
    normalize.run_normalize(workdir_path=tmp_path)
    rows = _rows(tmp_path, "pr_commits.ndjson")
    assert rows == [
        {
            "repository_id": 1,
            "pr_number": 7,
            "source_run_id": "run-a",
            "available": False,
            "reason": "pr_commits_exceed_endpoint_cap",
        }
    ]


def test_orphan_complete_run_is_excluded(tmp_path: Path) -> None:
    """A finalized complete run not on the committed lineage is never canonical."""
    commit_run(
        tmp_path,
        run_id="committed",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7, additions=1)}},
    )
    # Orphan: finalized complete, raw evidence written, but state.json not moved.
    commit_run(
        tmp_path,
        run_id="orphan",
        refresh_started_at="2026-03-08T00:00:00Z",
        previous_committed_run_id="committed",
        prs={
            7: {"pr": _pr_object(7, additions=999)},
            8: {"pr": _pr_object(8, additions=5)},
        },
        commit=False,
    )
    normalize.run_normalize(workdir_path=tmp_path)
    pr_rows = _rows(tmp_path, "pull_requests.ndjson")
    assert [r["pr_number"] for r in pr_rows] == [7]
    assert pr_rows[0]["additions"] == 1
    assert pr_rows[0]["source_run_id"] == "committed"


def test_normalize_takes_no_collection_lock(tmp_path: Path) -> None:
    """Read-only derivation never creates the single-writer lock file."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    normalize.run_normalize(workdir_path=tmp_path)
    assert not workdir.lock_path(tmp_path).exists()


def test_actor_map_change_renormalizes_without_github_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changing the derivation-only actor map re-normalizes retained raw data."""

    def _boom(**_kwargs: Any) -> Any:  # noqa: ANN401
        msg = "normalize must not touch GitHub"
        raise AssertionError(msg)

    monkeypatch.setattr(ghapi, "request", _boom)
    monkeypatch.setattr(ghapi, "paginate", _boom)
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7, user=_user(500, "agent-account", "User"))}},
    )
    normalize.run_normalize(workdir_path=tmp_path)
    state_before = workdir.state_path(tmp_path).read_bytes()
    base_fingerprint = json.loads(
        (tmp_path / "normalized" / "derivation.json").read_text(encoding="utf-8")
    )["actor_classification_fingerprint"]

    actor_map = tmp_path / "actor-map.json"
    actor_map.write_text(
        json.dumps({"explicit_ai_agents": [{"actor_id": 500}]}), encoding="utf-8"
    )
    outcome = normalize.run_normalize(workdir_path=tmp_path, actor_map_path=actor_map)
    assert outcome.status == "written"
    assert workdir.state_path(tmp_path).read_bytes() == state_before
    derivation = json.loads(
        (tmp_path / "normalized" / "derivation.json").read_text(encoding="utf-8")
    )
    assert derivation["actor_classification_fingerprint"] != base_fingerprint
    pr_rows = _rows(tmp_path, "pull_requests.ndjson")
    assert pr_rows[0]["author_classification"] == "explicit-ai-agent"


@pytest.mark.parametrize(
    ("actor", "entries", "expected"),
    [
        (_user(10, "alice", "User"), [], "human"),
        (_user(None, "dependabot[bot]", "Bot"), [], "bot"),
        (_user(20, "renovate[bot]", "User"), [], "bot"),
        (_user(30, "ai-bot", "Bot"), [{"actor_id": 30}], "explicit-ai-agent"),
        (
            _user(40, "Claude-Agent", "User"),
            [{"login": "claude-agent"}],
            "explicit-ai-agent",
        ),
        (_user(50, "ghost", "Mannequin"), [], "unknown"),
        (None, [], "unknown"),
    ],
)
def test_actor_classification_precedence(
    actor: dict[str, Any] | None, entries: list[dict[str, Any]], expected: str
) -> None:
    """Actor classification follows the issue's explicit precedence order."""
    actor_map = normalize.ActorMap(
        frozenset(e["actor_id"] for e in entries if "actor_id" in e),
        frozenset(e["login"].casefold() for e in entries if "login" in e),
    )
    assert normalize.classify_actor(actor, actor_map)[0] == expected


def test_self_review_is_not_independent(tmp_path: Path) -> None:
    """A PR author's own formal review is retained but flagged non-independent."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={
            7: {
                "pr": _pr_object(7, user=_user(10, "alice")),
                "reviews": [
                    {"id": 1, "user": _user(10, "alice"), "state": "APPROVED"},
                    {"id": 2, "user": _user(11, "bob"), "state": "APPROVED"},
                ],
            }
        },
    )
    normalize.run_normalize(workdir_path=tmp_path)
    rows = {r["review_id"]: r["independent"] for r in _rows(tmp_path, "reviews.ndjson")}
    assert rows == {1: False, 2: True}


@pytest.mark.parametrize(
    ("draft", "timeline", "expected_available", "expected_reason", "expected_entry"),
    [
        (
            True,
            [{"event": "ready_for_review", "created_at": "2026-02-02T00:00:00Z"}],
            True,
            "ready_for_review",
            "2026-02-02T00:00:00Z",
        ),
        (
            False,
            [{"event": "convert_to_draft", "created_at": "2026-02-02T00:00:00Z"}],
            True,
            "convert_to_draft",
            "2026-02-01T00:00:00Z",
        ),
        (False, [], True, "no_lifecycle_events_not_draft", "2026-02-01T00:00:00Z"),
        (True, [], False, "still_draft_never_ready", None),
        (
            True,
            [{"event": "ready_for_review", "created_at": None}],
            False,
            "inconsistent_history",
            None,
        ),
    ],
)
def test_draft_lifecycle_reconstruction(
    tmp_path: Path,
    draft: bool,
    timeline: list[dict[str, Any]],
    expected_available: bool,
    expected_reason: str,
    expected_entry: str | None,
) -> None:
    """First queue entry is reconstructed from draft-lifecycle history."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={
            7: {
                "pr": _pr_object(7, draft=draft, created_at="2026-02-01T00:00:00Z"),
                "timeline": timeline,
            }
        },
    )
    normalize.run_normalize(workdir_path=tmp_path)
    row = _rows(tmp_path, "draft_lifecycle.ndjson")[0]
    assert row["queue_entry_available"] is expected_available
    assert row["reason"] == expected_reason
    assert row["first_queue_entry"] == expected_entry


def test_repositories_row_retains_archived_and_fork_flags(tmp_path: Path) -> None:
    """Archived and fork repositories are retained and flagged, not dropped."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        repo_id=42,
        repo={
            "name": "legacy",
            "archived": True,
            "fork": True,
            "created_at": "2019-01-01T00:00:00Z",
        },
        prs={7: {"pr": _pr_object(7)}},
    )
    normalize.run_normalize(workdir_path=tmp_path)
    rows = _rows(tmp_path, "repositories.ndjson")
    assert rows == [
        {
            "repository_id": 42,
            "name": "legacy",
            "archived": True,
            "fork": True,
            "created_at": "2019-01-01T00:00:00Z",
            "last_seen_in_enumeration_at": "2026-03-01T00:00:00Z",
        }
    ]


def test_malformed_actor_map_raises_normalize_error(tmp_path: Path) -> None:
    """An actor map that is not the expected shape fails closed."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"explicit_ai_agents": [{"name": "x"}]}), encoding="utf-8"
    )
    with pytest.raises(normalize.NormalizeError, match="actor_id"):
        normalize.run_normalize(workdir_path=tmp_path, actor_map_path=bad)
