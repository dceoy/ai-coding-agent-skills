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


@pytest.mark.parametrize("command", ["aggregate", "analyze", "report"])
def test_followup_subcommands_are_registered(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """All documented subcommands expose help with their required workdir option."""
    with pytest.raises(SystemExit) as caught:
        productivity.main([command, "--help"])
    assert caught.value.code == 0
    assert "--workdir" in capsys.readouterr().out


def test_normalize_command_dispatches_and_returns_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful ``normalize`` run returns the OK exit code."""
    captured: dict[str, Any] = {}

    def fake_run_normalize(**kwargs: Any) -> Any:  # noqa: ANN401
        captured.update(kwargs)
        return type("Outcome", (), {"committed_run_id": "run-1", "status": "written"})()

    monkeypatch.setattr(productivity, "run_normalize", fake_run_normalize)
    exit_code = productivity.main(["normalize", "--workdir", str(tmp_path)])
    assert exit_code == productivity.EXIT_OK
    assert captured["workdir_path"] == tmp_path
    assert captured["actor_map_path"] is None
    assert captured["force"] is False


def test_normalize_command_returns_derivation_failed_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A normalization error maps to the derivation-failed exit code."""

    def fake_run_normalize(**_kwargs: Any) -> Any:  # noqa: ANN401
        msg = "nothing committed"
        raise productivity.NormalizeError(msg)

    monkeypatch.setattr(productivity, "run_normalize", fake_run_normalize)
    exit_code = productivity.main(["normalize", "--workdir", str(tmp_path)])
    assert exit_code == productivity.EXIT_DERIVATION_FAILED


@pytest.mark.parametrize(
    ("command", "filename", "expected"),
    [
        ("collect", "state.json", productivity.EXIT_INVALID_ARGS),
        ("normalize", "state.json", productivity.EXIT_DERIVATION_FAILED),
        (
            "analyze",
            "report/organization-week.meta.json",
            productivity.EXIT_DERIVATION_FAILED,
        ),
        (
            "report",
            "report/organization-week.meta.json",
            productivity.EXIT_DERIVATION_FAILED,
        ),
    ],
)
@pytest.mark.parametrize("content", ["[]", "null", "{invalid"])
def test_malformed_documents_return_expected_exit_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
    filename: str,
    expected: int,
    content: str,
) -> None:
    """User/data failures produce a concise error rather than an internal traceback."""
    path = tmp_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    args = [command, "--workdir", str(tmp_path)]
    if command == "collect":
        args.extend(["--org", "acme", "--start", "2026-01-01", "--end", "2026-02-01"])
    assert productivity.main(args) == expected
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["collect", "aggregate"])
def test_overlap_overflow_is_invalid_args(tmp_path: Path, command: str) -> None:
    """Huge overlap values are rejected before datetime arithmetic can crash."""
    args = [
        command,
        "--workdir",
        str(tmp_path),
        "--start",
        "2026-01-01",
        "--end",
        "2026-02-01",
        "--overlap-hours",
        "999999999999999999999",
    ]
    if command == "collect":
        args.extend(["--org", "acme"])
    assert productivity.main(args) == productivity.EXIT_INVALID_ARGS


def test_programming_errors_are_not_hidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Arbitrary implementation TypeError must not become a data error."""

    def fail(**_kwargs: object) -> None:
        raise TypeError

    monkeypatch.setattr(productivity, "run_normalize", fail)
    with pytest.raises(TypeError):
        productivity.main(["normalize", "--workdir", str(tmp_path)])
