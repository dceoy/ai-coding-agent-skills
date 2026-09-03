"""Tests for the ``productivity.py`` CLI entry point."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import productivity
import pytest
import workdir

if TYPE_CHECKING:
    from pathlib import Path


def test_parse_boundary_converts_date_only_to_utc_midnight() -> None:
    """A date-only value converts deterministically to UTC midnight."""
    assert productivity.parse_boundary("2026-01-01") == datetime(2026, 1, 1, tzinfo=UTC)


def test_parse_boundary_accepts_zulu_timestamp() -> None:
    """A ``Z``-suffixed timestamp parses to the equivalent UTC datetime."""
    assert productivity.parse_boundary("2026-01-01T12:30:00Z") == datetime(
        2026, 1, 1, 12, 30, tzinfo=UTC
    )


def test_parse_boundary_rejects_naive_timestamp() -> None:
    """A timestamp with no UTC offset is rejected rather than silently assumed."""
    with pytest.raises(ValueError, match="UTC offset"):
        productivity.parse_boundary("2026-01-01T00:00:00")


def test_end_not_after_start_is_invalid_args(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--end`` at or before ``--start`` exits with the invalid-arguments code."""
    exit_code = productivity.main([
        "collect",
        "--org",
        "acme",
        "--workdir",
        str(tmp_path),
        "--start",
        "2026-01-01",
        "--end",
        "2026-01-01",
    ])
    assert exit_code == productivity.EXIT_INVALID_ARGS
    assert "--end must be strictly after --start" in capsys.readouterr().err


def test_negative_overlap_hours_is_invalid_args(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A negative ``--overlap-hours`` exits with the invalid-arguments code."""
    exit_code = productivity.main([
        "collect",
        "--org",
        "acme",
        "--workdir",
        str(tmp_path),
        "--start",
        "2026-01-01",
        "--end",
        "2026-02-01",
        "--overlap-hours",
        "-1",
    ])
    assert exit_code == productivity.EXIT_INVALID_ARGS
    assert "--overlap-hours must not be negative" in capsys.readouterr().err


def test_collect_command_dispatches_and_returns_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful ``collect`` run returns the OK exit code."""
    captured: dict[str, Any] = {}

    def fake_run_collect(**kwargs: Any) -> Any:  # noqa: ANN401
        captured.update(kwargs)
        return type(
            "Outcome", (), {"run_id": "run-1", "status": "complete", "manifest": {}}
        )()

    monkeypatch.setattr(productivity, "run_collect", fake_run_collect)
    exit_code = productivity.main([
        "collect",
        "--org",
        "acme",
        "--workdir",
        str(tmp_path),
        "--start",
        "2026-01-01",
        "--end",
        "2026-02-01",
    ])
    assert exit_code == productivity.EXIT_OK
    assert captured["org"] == "acme"
    assert captured["start"] == datetime(2026, 1, 1, tzinfo=UTC)
    assert captured["end"] == datetime(2026, 2, 1, tzinfo=UTC)


def test_collect_command_returns_incomplete_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An incomplete run returns the incomplete exit code."""

    def fake_run_collect(**_kwargs: Any) -> Any:  # noqa: ANN401
        return type(
            "Outcome",
            (),
            {"run_id": "run-1", "status": "incomplete", "manifest": {"failures": []}},
        )()

    monkeypatch.setattr(productivity, "run_collect", fake_run_collect)
    exit_code = productivity.main([
        "collect",
        "--org",
        "acme",
        "--workdir",
        str(tmp_path),
        "--start",
        "2026-01-01",
        "--end",
        "2026-02-01",
    ])
    assert exit_code == productivity.EXIT_INCOMPLETE


def test_collect_command_returns_locked_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A workdir already locked by another run returns the locked exit code."""

    def fake_run_collect(**_kwargs: Any) -> Any:  # noqa: ANN401
        msg = "already locked"
        raise workdir.WorkdirLockedError(msg)

    monkeypatch.setattr(productivity, "run_collect", fake_run_collect)
    exit_code = productivity.main([
        "collect",
        "--org",
        "acme",
        "--workdir",
        str(tmp_path),
        "--start",
        "2026-01-01",
        "--end",
        "2026-02-01",
    ])
    assert exit_code == productivity.EXIT_LOCKED


def test_collect_command_returns_invalid_args_exit_code_on_organization_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A workdir committed to a different organization returns the invalid-args code."""

    def fake_run_collect(**_kwargs: Any) -> Any:  # noqa: ANN401
        msg = "organization mismatch"
        raise workdir.OrganizationMismatchError(msg)

    monkeypatch.setattr(productivity, "run_collect", fake_run_collect)
    exit_code = productivity.main([
        "collect",
        "--org",
        "acme",
        "--workdir",
        str(tmp_path),
        "--start",
        "2026-01-01",
        "--end",
        "2026-02-01",
    ])
    assert exit_code == productivity.EXIT_INVALID_ARGS


def test_only_collect_subcommand_is_registered() -> None:
    """Follow-up subcommands are not registered until they are implemented."""
    with pytest.raises(SystemExit):
        productivity.main(["normalize"])
