#!/usr/bin/env python3
"""CLI entry point for the ``github-productivity`` skill.

Registers the ``collect``, ``normalize``, ``aggregate``, ``analyze``, and
``report`` subcommands.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import workdir
from aggregate import AggregateError, run_aggregate
from analyze import AnalyzeError, run_analyze
from collect import run_collect
from normalize import NormalizeError, run_normalize
from report import ReportError, run_report

#: Exit codes returned by :func:`main`.
EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_INVALID_ARGS = 2
EXIT_LOCKED = 3
EXIT_DERIVATION_FAILED = 4


def parse_boundary(value: str) -> datetime:
    """Parse a CLI-supplied interval boundary into a UTC datetime.

    A date-only value such as ``"2026-01-01"`` converts deterministically
    to ``2026-01-01T00:00:00Z``. Any other value must be a timestamp with
    an explicit UTC offset (for example a trailing ``Z``).

    Args:
        value: The raw CLI argument.

    Returns:
        The equivalent timezone-aware UTC datetime.

    Raises:
        ValueError: If ``value`` is not a valid date-only or timezone-aware
            timestamp.
    """
    if len(value) == len("YYYY-MM-DD") and value[4] == "-" and value[7] == "-":
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        msg = f"timestamp {value!r} must include a UTC offset, or use date-only form"
        raise ValueError(msg)
    return parsed.astimezone(UTC)


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser.

    Returns:
        A parser with the ``collect``, ``normalize``, ``aggregate``,
        ``analyze``, and ``report`` subcommands registered.
    """
    parser = argparse.ArgumentParser(prog="productivity.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser(
        "collect",
        help="Collect GitHub organization repository/PR/review/timeline/commit data.",
    )
    collect_parser.add_argument(
        "--org", required=True, help="GitHub organization login."
    )
    collect_parser.add_argument(
        "--workdir",
        required=True,
        type=Path,
        help="Workdir root for raw/manifest/state storage.",
    )
    collect_parser.add_argument(
        "--start",
        required=True,
        help="Inclusive UTC interval start (date-only or timestamp).",
    )
    collect_parser.add_argument(
        "--end",
        required=True,
        help="Exclusive UTC interval end (date-only or timestamp).",
    )
    collect_parser.add_argument(
        "--overlap-hours",
        type=int,
        default=24,
        help="Deterministic overlap applied to discovery boundaries and watermarks.",
    )

    normalize_parser = subparsers.add_parser(
        "normalize",
        help="Derive deterministic entities from the committed collection lineage.",
    )
    normalize_parser.add_argument(
        "--workdir",
        required=True,
        type=Path,
        help="Workdir root holding committed collection state.",
    )
    normalize_parser.add_argument(
        "--actor-map",
        type=Path,
        default=None,
        help="Optional JSON file mapping explicit AI coding-agent identities.",
    )
    normalize_parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate normalized/ even if it is already current.",
    )

    aggregate_parser = subparsers.add_parser(
        "aggregate",
        help="Build the organization-week panel from normalized entities.",
    )
    aggregate_parser.add_argument(
        "--workdir",
        required=True,
        type=Path,
        help="Workdir root holding normalized entities.",
    )
    aggregate_parser.add_argument(
        "--start",
        required=True,
        help="Inclusive UTC interval start (date-only or timestamp).",
    )
    aggregate_parser.add_argument(
        "--end",
        required=True,
        help="Exclusive UTC interval end (date-only or timestamp).",
    )
    aggregate_parser.add_argument(
        "--overlap-hours",
        type=int,
        default=24,
        help="Overlap used to check committed historical coverage against --start.",
    )
    aggregate_parser.add_argument(
        "--include-forks",
        action="store_true",
        help="Include forked repositories in the primary cohort.",
    )

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Fit the pre-specified ITS models and required sensitivities.",
    )
    analyze_parser.add_argument(
        "--workdir",
        required=True,
        type=Path,
        help="Workdir root holding an 'aggregate' panel.",
    )
    analyze_parser.add_argument(
        "--intervention-at",
        default=None,
        help="UTC intervention timestamp; omit for a descriptive-only run.",
    )

    report_parser = subparsers.add_parser(
        "report",
        help="Generate the fixed chart set and Markdown report.",
    )
    report_parser.add_argument(
        "--workdir",
        required=True,
        type=Path,
        help="Workdir root holding an 'analyze' output.",
    )
    return parser


def _validate_collect_args(args: argparse.Namespace) -> tuple[datetime, datetime] | int:
    """Parse and validate the ``collect`` subcommand's arguments.

    Args:
        args: Parsed CLI arguments for the ``collect`` subcommand.

    Returns:
        The parsed ``(start, end)`` boundaries if valid, otherwise the
        exit code to return for the first validation failure found.
    """
    try:
        start = parse_boundary(args.start)
        end = parse_boundary(args.end)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID_ARGS
    if end <= start:
        print("error: --end must be strictly after --start", file=sys.stderr)
        return EXIT_INVALID_ARGS
    if args.overlap_hours < 0:
        print("error: --overlap-hours must not be negative", file=sys.stderr)
        return EXIT_INVALID_ARGS
    return start, end


def _run_collect_command(args: argparse.Namespace) -> int:
    """Handle a parsed ``collect`` invocation.

    Args:
        args: Parsed CLI arguments for the ``collect`` subcommand.

    Returns:
        The process exit code.
    """
    validated = _validate_collect_args(args)
    if isinstance(validated, int):
        return validated
    start, end = validated
    try:
        outcome = run_collect(
            org=args.org,
            workdir_path=args.workdir,
            start=start,
            end=end,
            overlap_hours=args.overlap_hours,
        )
    except workdir.WorkdirLockedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_LOCKED
    except workdir.OrganizationMismatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID_ARGS
    if outcome.status != "complete":
        print(
            f"run {outcome.run_id} incomplete: {outcome.manifest['failures']}",
            file=sys.stderr,
        )
        return EXIT_INCOMPLETE
    print(f"run {outcome.run_id} complete")
    return EXIT_OK


def _run_normalize_command(args: argparse.Namespace) -> int:
    """Handle a parsed ``normalize`` invocation.

    Args:
        args: Parsed CLI arguments for the ``normalize`` subcommand.

    Returns:
        The process exit code.
    """
    try:
        outcome = run_normalize(
            workdir_path=args.workdir,
            actor_map_path=args.actor_map,
            force=args.force,
        )
    except (
        NormalizeError,
        workdir.CommittedLineageError,
        json.JSONDecodeError,
        OSError,
        AttributeError,
        TypeError,
    ) as exc:
        # AttributeError/TypeError are a backstop for committed evidence
        # corrupted out of band into an unexpected shape: fail closed with
        # exit 4 rather than surfacing a raw traceback.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DERIVATION_FAILED
    print(f"normalized {outcome.committed_run_id} ({outcome.status})")
    return EXIT_OK


def _validate_window_args(args: argparse.Namespace) -> tuple[datetime, datetime] | int:
    """Parse and validate a subcommand's shared ``--start``/``--end`` window.

    Args:
        args: Parsed CLI arguments carrying ``start``/``end`` strings.

    Returns:
        The parsed ``(start, end)`` boundaries if valid, otherwise the
        exit code to return for the first validation failure found.
    """
    try:
        start = parse_boundary(args.start)
        end = parse_boundary(args.end)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID_ARGS
    if end <= start:
        print("error: --end must be strictly after --start", file=sys.stderr)
        return EXIT_INVALID_ARGS
    return start, end


def _run_aggregate_command(args: argparse.Namespace) -> int:
    """Handle a parsed ``aggregate`` invocation.

    Args:
        args: Parsed CLI arguments for the ``aggregate`` subcommand.

    Returns:
        The process exit code.
    """
    validated = _validate_window_args(args)
    if isinstance(validated, int):
        return validated
    start, end = validated
    if args.overlap_hours < 0:
        print("error: --overlap-hours must not be negative", file=sys.stderr)
        return EXIT_INVALID_ARGS
    try:
        outcome = run_aggregate(
            workdir_path=args.workdir,
            start=start,
            end=end,
            overlap_hours=args.overlap_hours,
            include_forks=args.include_forks,
        )
    except AggregateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DERIVATION_FAILED
    print(f"aggregated {len(outcome.panel.weeks)} weeks to {outcome.csv_path}")
    return EXIT_OK


def _run_analyze_command(args: argparse.Namespace) -> int:
    """Handle a parsed ``analyze`` invocation.

    Args:
        args: Parsed CLI arguments for the ``analyze`` subcommand.

    Returns:
        The process exit code.
    """
    intervention_at = None
    if args.intervention_at is not None:
        try:
            intervention_at = parse_boundary(args.intervention_at)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_INVALID_ARGS
    try:
        outcome = run_analyze(
            workdir_path=args.workdir, intervention_at=intervention_at
        )
    except AnalyzeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DERIVATION_FAILED
    print(f"analyzed to {outcome.path}")
    return EXIT_OK


def _run_report_command(args: argparse.Namespace) -> int:
    """Handle a parsed ``report`` invocation.

    Args:
        args: Parsed CLI arguments for the ``report`` subcommand.

    Returns:
        The process exit code.
    """
    try:
        outcome = run_report(workdir_path=args.workdir)
    except ReportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DERIVATION_FAILED
    print(f"reported to {outcome.report_path}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Argument vector, or ``None`` to use ``sys.argv[1:]``.

    Returns:
        The process exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "collect":
        return _run_collect_command(args)
    if args.command == "normalize":
        return _run_normalize_command(args)
    if args.command == "aggregate":
        return _run_aggregate_command(args)
    if args.command == "analyze":
        return _run_analyze_command(args)
    if args.command == "report":
        return _run_report_command(args)
    parser.error(f"unknown command {args.command!r}")
    return EXIT_INVALID_ARGS


if __name__ == "__main__":
    raise SystemExit(main())
