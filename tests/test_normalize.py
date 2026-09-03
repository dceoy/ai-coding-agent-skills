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
    workdir_path: Path,
    run_id: str,
    repo_id: int,
    pr_number: int,
    bundle: dict[str, Any],
) -> None:
    """Append one PR's raw snapshot bundle to a run's evidence directory.

    Mirrors ``collect``: one shared file per bundle type per run, every
    line carrying ``pr_number`` plus ``provenance.repository_id``.
    """
    raw_root = workdir.raw_dir(workdir_path, run_id)
    prov = {"repository_id": repo_id}
    workdir.append_ndjson(
        raw_root / "pulls.ndjson",
        {"pr_number": pr_number, "provenance": prov, "payload": bundle.get("pr", {})},
    )
    for name in ("reviews", "commits", "timeline"):
        workdir.append_ndjson(
            raw_root / f"{name}.ndjson",
            {
                "pr_number": pr_number,
                "provenance": prov,
                "payload": bundle.get(name, []),
            },
        )


def _repo_meta(repo_id: int, repo: dict[str, Any] | None) -> dict[str, Any]:
    """Default repository metadata for one repo entry."""
    return repo or {
        "name": f"repo{repo_id}",
        "archived": False,
        "fork": False,
        "created_at": "2020-01-01T00:00:00Z",
    }


def commit_run(
    workdir_path: Path,
    *,
    run_id: str,
    refresh_started_at: str,
    prs: dict[int, dict[str, Any]] | None = None,
    repo_id: int = 1,
    repo: dict[str, Any] | None = None,
    repos: dict[int, dict[int, dict[str, Any]]] | None = None,
    previous_committed_run_id: str | None = None,
    limitations: list[dict[str, Any]] | None = None,
    commit: bool = True,
) -> None:
    """Build one finalized ``complete`` run and optionally commit state to it.

    Args:
        workdir_path: The workdir root.
        run_id: The run ID.
        refresh_started_at: The manifest's ``refresh_started_at``.
        prs: Single-repo shorthand -- ``{pr_number: bundle}`` for
            ``repo_id``, where ``bundle`` is ``{"pr": {...}, "reviews":
            [...], "commits": [...], "timeline": [...]}``.
        repo_id: The repository ID ``prs`` belongs to.
        repo: Optional repository metadata for ``repo_id``.
        repos: Multi-repo form -- ``{repo_id: {pr_number: bundle}}``.
            Mutually exclusive with ``prs``.
        previous_committed_run_id: The prior committed run, recorded in the
            manifest and walked by the lineage resolver.
        limitations: Manifest ``limitations`` entries.
        commit: When ``True``, atomically point ``state.json`` at this run.
    """
    by_repo = repos if repos is not None else {repo_id: prs or {}}
    manifest_repos: dict[str, Any] = {}
    state_repos: dict[str, Any] = {}
    for rid, rprs in by_repo.items():
        meta = _repo_meta(rid, repo if rid == repo_id else None)
        for pr_number, bundle in rprs.items():
            _write_raw(workdir_path, run_id, rid, pr_number, bundle)
        manifest_repos[str(rid)] = {**meta, "touched_pr_numbers": sorted(rprs)}
        state_repos[str(rid)] = {
            **meta,
            "discovery_watermark": refresh_started_at,
            "history_boundary": "2020-01-01T00:00:00Z",
            "last_seen_in_enumeration_at": refresh_started_at,
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
        "repositories": manifest_repos,
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
                "repositories": state_repos,
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


def test_interrupted_regeneration_cannot_report_stale_already_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash mid-rewrite must not leave a marker attesting to the old tree."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    normalize.run_normalize(workdir_path=tmp_path)
    assert (tmp_path / "normalized" / "derivation.json").exists()

    real_atomic_write_ndjson = workdir.atomic_write_ndjson
    calls = {"count": 0}

    def _boom_after_first(path: Path, rows: list[dict[str, Any]]) -> None:
        calls["count"] += 1
        if calls["count"] == 2:
            msg = "simulated crash mid-regeneration"
            raise RuntimeError(msg)
        real_atomic_write_ndjson(path, rows)

    monkeypatch.setattr(normalize.workdir, "atomic_write_ndjson", _boom_after_first)
    with pytest.raises(RuntimeError, match="simulated crash"):
        normalize.run_normalize(workdir_path=tmp_path, force=True)
    assert not (tmp_path / "normalized" / "derivation.json").exists()

    monkeypatch.setattr(
        normalize.workdir, "atomic_write_ndjson", real_atomic_write_ndjson
    )
    outcome = normalize.run_normalize(workdir_path=tmp_path)
    assert outcome.status == "written"


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


def test_winner_ordering_uses_refresh_started_at_not_filesystem_order(
    tmp_path: Path,
) -> None:
    """The newest bundle wins by ``refresh_started_at``, not run-ID order.

    The run ID that sorts first (and would head a directory scan) is
    deliberately the *older* run, so a filesystem-order winner would pick
    the wrong bundle.
    """
    commit_run(
        tmp_path,
        run_id="aaa-early",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7, additions=1)}},
    )
    commit_run(
        tmp_path,
        run_id="zzz-late",
        refresh_started_at="2026-03-09T00:00:00Z",
        previous_committed_run_id="aaa-early",
        prs={7: {"pr": _pr_object(7, additions=99)}},
    )
    normalize.run_normalize(workdir_path=tmp_path)
    pr_rows = _rows(tmp_path, "pull_requests.ndjson")
    assert pr_rows[0]["source_run_id"] == "zzz-late"
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

    # Defense-in-depth: `normalize` does not import `ghapi` at all, so this
    # guard is structural today. It stays to catch a future regression that
    # adds a live call path.
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
        ({"id": 11, "login": "carol"}, [], "human"),
        (_user(None, "dependabot[bot]", "Bot"), [], "bot"),
        (_user(20, "renovate[bot]", "User"), [], "bot"),
        (_user(30, "ai-bot", "Bot"), [{"actor_id": 30}], "explicit-ai-agent"),
        (
            _user(40, "Claude-Agent", "User"),
            [{"login": "claude-agent"}],
            "explicit-ai-agent",
        ),
        (_user(50, "ghost", "Mannequin"), [], "unknown"),
        (_user(60, "org", "Organization"), [], "unknown"),
        ({"id": None, "login": None}, [], "unknown"),
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


@pytest.mark.parametrize(
    "entry",
    [
        {"actor_id": "500"},
        {"login": 500},
        {"actor_id": True},
        {"actor_id": 1.0},
    ],
)
def test_actor_map_rejects_wrong_typed_identity_fields(
    tmp_path: Path, entry: dict[str, Any]
) -> None:
    """A wrong-typed ``actor_id``/``login`` fails closed instead of being dropped."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    amap = tmp_path / "amap.json"
    amap.write_text(json.dumps({"explicit_ai_agents": [entry]}), encoding="utf-8")
    with pytest.raises(normalize.NormalizeError, match="must be a"):
        normalize.run_normalize(workdir_path=tmp_path, actor_map_path=amap)


def test_same_pr_number_in_two_repos_is_not_cross_contaminated(tmp_path: Path) -> None:
    """One run touching repo-a#1 and repo-b#1 keeps each PR's bundle separate."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        repos={
            1: {
                1: {
                    "pr": _pr_object(
                        1, additions=1, commits=1, user=_user(10, "alice")
                    ),
                    "reviews": [
                        {"id": 100, "user": _user(11, "bob"), "state": "APPROVED"}
                    ],
                    "commits": [{"sha": "a1"}],
                }
            },
            2: {
                1: {
                    "pr": _pr_object(
                        1, additions=99, commits=1, user=_user(20, "dave")
                    ),
                    "reviews": [
                        {"id": 200, "user": _user(21, "eve"), "state": "APPROVED"}
                    ],
                    "commits": [{"sha": "b1"}],
                }
            },
        },
    )
    normalize.run_normalize(workdir_path=tmp_path)
    prs = {
        (r["repository_id"], r["pr_number"]): r
        for r in _rows(tmp_path, "pull_requests.ndjson")
    }
    assert prs[1, 1]["additions"] == 1
    assert prs[1, 1]["author_login"] == "alice"
    assert prs[2, 1]["additions"] == 99
    assert prs[2, 1]["author_login"] == "dave"
    reviews = {
        (r["repository_id"], r["review_id"]) for r in _rows(tmp_path, "reviews.ndjson")
    }
    assert reviews == {(1, 100), (2, 200)}
    commits = {
        (r["repository_id"], r["sha"]) for r in _rows(tmp_path, "pr_commits.ndjson")
    }
    assert commits == {(1, "a1"), (2, "b1")}


def test_missing_bundle_file_in_committed_run_fails_closed(tmp_path: Path) -> None:
    """A committed run missing a bundle file is damaged evidence, not empty data."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    (workdir.raw_dir(tmp_path, "run-a") / "reviews.ndjson").unlink()
    with pytest.raises(normalize.NormalizeError, match="missing"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_corrupt_raw_bundle_line_fails_closed(tmp_path: Path) -> None:
    """A non-JSON line in a committed run's raw evidence raises rather than skips."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    commits = workdir.raw_dir(tmp_path, "run-a") / "commits.ndjson"
    with commits.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    with pytest.raises(normalize.NormalizeError, match="not valid JSON"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_corrupt_committed_state_fails_closed(tmp_path: Path) -> None:
    """An unreadable ``state.json`` raises instead of crashing with a traceback."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    workdir.state_path(tmp_path).write_text("{not json", encoding="utf-8")
    with pytest.raises(normalize.NormalizeError):
        normalize.run_normalize(workdir_path=tmp_path)


def test_null_committed_run_id_raises_rather_than_writing_empty_tree(
    tmp_path: Path,
) -> None:
    """A ``committed_run_id: null`` state is rejected, not silently normalized."""
    workdir.write_state(tmp_path, {"committed_run_id": None, "repositories": {}})
    with pytest.raises(normalize.NormalizeError):
        normalize.run_normalize(workdir_path=tmp_path)
    assert not (tmp_path / "normalized").exists()


def test_touched_prs_fails_closed_on_malformed_manifest_repositories(
    tmp_path: Path,
) -> None:
    """A non-int ``touched_pr_numbers`` entry raises instead of being dropped."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    manifest_path = workdir.manifest_path(tmp_path, "run-a")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["repositories"]["1"]["touched_pr_numbers"] = ["not-an-int"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(normalize.NormalizeError, match="touched_pr_numbers"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_repository_rows_fails_closed_on_malformed_state_repositories(
    tmp_path: Path,
) -> None:
    """A non-dict repository entry in committed state raises, not silently drops."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    state = json.loads(workdir.state_path(tmp_path).read_text(encoding="utf-8"))
    state["repositories"]["1"] = "not-a-dict"
    workdir.state_path(tmp_path).write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(normalize.NormalizeError, match="must be an object"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_repository_rows_fails_closed_on_non_numeric_key(tmp_path: Path) -> None:
    """A non-numeric repository key in committed state raises, not silently drops."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    state = json.loads(workdir.state_path(tmp_path).read_text(encoding="utf-8"))
    state["repositories"]["not-a-number"] = state["repositories"].pop("1")
    workdir.state_path(tmp_path).write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(normalize.NormalizeError, match="numeric repository ID"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_touched_prs_fails_closed_on_non_numeric_repository_key(
    tmp_path: Path,
) -> None:
    """A non-numeric repository key in a manifest raises, not silently drops PRs."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    manifest_path = workdir.manifest_path(tmp_path, "run-a")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["repositories"]["not-a-number"] = manifest["repositories"].pop("1")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(normalize.NormalizeError, match="numeric repository ID"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_cap_exceeded_fails_closed_on_non_list_limitations(tmp_path: Path) -> None:
    """A non-list ``limitations`` value raises instead of reading as "not capped"."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    manifest_path = workdir.manifest_path(tmp_path, "run-a")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["limitations"] = "not-a-list"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(normalize.NormalizeError, match="limitations"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_cap_exceeded_fails_closed_on_non_dict_limitation_entry(
    tmp_path: Path,
) -> None:
    """A non-object ``limitations`` entry raises instead of being skipped."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    manifest_path = workdir.manifest_path(tmp_path, "run-a")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["limitations"] = ["not-an-object"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(normalize.NormalizeError, match="limitations"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_raw_bundle_non_dict_record_fails_closed(tmp_path: Path) -> None:
    """A raw evidence line that is valid JSON but not an object raises."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    commits = workdir.raw_dir(tmp_path, "run-a") / "commits.ndjson"
    with commits.open("a", encoding="utf-8") as handle:
        handle.write("[1, 2, 3]\n")
    with pytest.raises(normalize.NormalizeError, match="must be an object"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_raw_bundle_wrong_typed_pr_identity_fails_closed(tmp_path: Path) -> None:
    """A raw evidence line with a non-int pr_number/repository_id raises."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    commits = workdir.raw_dir(tmp_path, "run-a") / "commits.ndjson"
    with commits.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({
                "pr_number": "not-an-int",
                "provenance": {"repository_id": 1},
                "payload": [{"sha": "z1"}],
            })
            + "\n"
        )
    with pytest.raises(normalize.NormalizeError, match="pr_number"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_manifest_ts_fails_closed_on_missing_refresh_started_at(
    tmp_path: Path,
) -> None:
    """A manifest missing ``refresh_started_at`` raises instead of sorting last."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    manifest_path = workdir.manifest_path(tmp_path, "run-a")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["refresh_started_at"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(normalize.NormalizeError, match="refresh_started_at"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_manifest_ts_fails_closed_on_non_string_refresh_started_at(
    tmp_path: Path,
) -> None:
    """A non-string ``refresh_started_at`` raises instead of sorting last."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    manifest_path = workdir.manifest_path(tmp_path, "run-a")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["refresh_started_at"] = 12345
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(normalize.NormalizeError, match="refresh_started_at"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_manifest_ts_fails_closed_on_invalid_timestamp_string(
    tmp_path: Path,
) -> None:
    """A non-empty but unparseable ``refresh_started_at`` raises."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    manifest_path = workdir.manifest_path(tmp_path, "run-a")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["refresh_started_at"] = "not-a-timestamp"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(normalize.NormalizeError, match="ISO-8601 timestamp"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_manifest_ts_fails_closed_on_missing_utc_offset(tmp_path: Path) -> None:
    """A ``refresh_started_at`` without a UTC offset raises.

    An offset-naive value would otherwise fail to compare against
    timezone-aware peers when sorting the lineage.
    """
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    manifest_path = workdir.manifest_path(tmp_path, "run-a")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["refresh_started_at"] = "2026-03-01T00:00:00"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(normalize.NormalizeError, match="UTC offset"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_commit_rows_fails_closed_on_commit_count_mismatch(tmp_path: Path) -> None:
    """An uncapped PR's flattened commit count must match the PR object's.

    A mismatch raises instead of publishing truncated commit data.
    """
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={
            7: {
                "pr": _pr_object(7, commits=3),
                "commits": [{"sha": "a"}, {"sha": "b"}],
            }
        },
    )
    with pytest.raises(normalize.NormalizeError, match="reports 3 commits"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_flatten_rejects_non_dict_page_element(tmp_path: Path) -> None:
    """A page payload list containing a non-object element raises."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    commits = workdir.raw_dir(tmp_path, "run-a") / "commits.ndjson"
    with commits.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({
                "pr_number": 7,
                "provenance": {"repository_id": 1},
                "payload": ["not-an-object"],
            })
            + "\n"
        )
    with pytest.raises(normalize.NormalizeError, match=r"commits\.ndjson"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_flatten_rejects_wrong_typed_page_payload(tmp_path: Path) -> None:
    """A page payload that is neither an object nor an array raises."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    commits = workdir.raw_dir(tmp_path, "run-a") / "commits.ndjson"
    with commits.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({
                "pr_number": 7,
                "provenance": {"repository_id": 1},
                "payload": "not-an-object-or-array",
            })
            + "\n"
        )
    with pytest.raises(normalize.NormalizeError, match=r"commits\.ndjson"):
        normalize.run_normalize(workdir_path=tmp_path)


def test_actors_registry_dedupes_by_id_first_login_wins(tmp_path: Path) -> None:
    """One actor ID under two logins keeps the first; login-only actors sort last."""
    commit_run(
        tmp_path,
        run_id="run-old",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7, user=_user(10, "alice"))}},
    )
    commit_run(
        tmp_path,
        run_id="run-new",
        refresh_started_at="2026-03-08T00:00:00Z",
        previous_committed_run_id="run-old",
        prs={
            8: {
                "pr": _pr_object(8, user=_user(10, "alice-renamed")),
                "reviews": [
                    {"id": 1, "user": _user(11, "bob"), "state": "APPROVED"},
                    {"id": 2, "user": {"login": "ghostonly"}, "state": "COMMENTED"},
                ],
            }
        },
    )
    normalize.run_normalize(workdir_path=tmp_path)
    actors = _rows(tmp_path, "actors.ndjson")
    by_id = {a["actor_id"]: a for a in actors}
    assert by_id[10]["login"] == "alice"  # first seen wins over "alice-renamed"
    assert actors[-1]["actor_id"] is None
    assert actors[-1]["login"] == "ghostonly"
    assert [a["actor_id"] for a in actors if a["actor_id"] is not None] == [10, 11]


def test_review_dismissed_event_is_carried_into_timeline_output(tmp_path: Path) -> None:
    """`review_dismissed` events (raw material for changes-requested) are retained."""
    commit_run(
        tmp_path,
        run_id="run-a",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={
            7: {
                "pr": _pr_object(7),
                "timeline": [
                    {"event": "labeled", "created_at": "2026-02-01T00:00:00Z"},
                    {
                        "event": "review_dismissed",
                        "created_at": "2026-02-02T00:00:00Z",
                        "dismissed_review": {
                            "review_id": 55,
                            "state": "changes_requested",
                        },
                    },
                ],
            }
        },
    )
    normalize.run_normalize(workdir_path=tmp_path)
    events = _rows(tmp_path, "timeline_events.ndjson")
    assert [e["event"] for e in events] == ["review_dismissed"]
    assert events[0]["payload"]["dismissed_review"] == {
        "review_id": 55,
        "state": "changes_requested",
    }


def test_derivation_json_records_freshness_provenance(tmp_path: Path) -> None:
    """`derivation.json` carries `as_of` and a newest-first `source_run_ids`."""
    commit_run(
        tmp_path,
        run_id="run-old",
        refresh_started_at="2026-03-01T00:00:00Z",
        prs={7: {"pr": _pr_object(7)}},
    )
    commit_run(
        tmp_path,
        run_id="run-new",
        refresh_started_at="2026-03-08T00:00:00Z",
        previous_committed_run_id="run-old",
        prs={7: {"pr": _pr_object(7)}},
    )
    outcome = normalize.run_normalize(workdir_path=tmp_path)
    derivation = json.loads(
        (tmp_path / "normalized" / "derivation.json").read_text(encoding="utf-8")
    )
    assert derivation["committed_run_id"] == "run-new"
    assert derivation["source_run_ids"] == ["run-new", "run-old"]
    assert derivation["as_of"] == "2026-03-08T00:00:00Z"
    assert derivation["requested_interval"] == {
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-07-01T00:00:00Z",
    }
    assert outcome.derivation["as_of"] == "2026-03-08T00:00:00Z"
