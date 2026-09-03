"""Tests for the ``gh api`` request seam."""

from __future__ import annotations

import json
import subprocess  # noqa: S404
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import ghapi
import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class _FakeCompletedProcess:
    """A stand-in for ``subprocess.CompletedProcess`` used in tests."""

    returncode: int
    stdout: str
    stderr: str = ""


def _stub_run(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[list[str]], _FakeCompletedProcess],
) -> list[list[str]]:
    """Replace ``subprocess.run`` with a fake, recording every invocation.

    Args:
        monkeypatch: The pytest monkeypatch fixture.
        handler: Produces a fake completed process for each argv.

    Returns:
        The list of argv calls made, appended to as they occur.
    """
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: object) -> _FakeCompletedProcess:
        calls.append(argv)
        return handler(argv)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_request_pins_api_version_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every request sends the pinned ``X-GitHub-Api-Version`` header."""
    calls = _stub_run(
        monkeypatch, lambda _argv: _FakeCompletedProcess(0, json.dumps({"id": 1}))
    )
    ghapi.request(endpoint="/repos/o/r", params={}, repository_id=1, run_id="run-1")
    assert f"X-GitHub-Api-Version: {ghapi.GITHUB_API_VERSION}" in calls[0]


def test_request_never_uses_paginate_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requests page explicitly and never rely on ``gh api --paginate``."""
    calls = _stub_run(
        monkeypatch, lambda _argv: _FakeCompletedProcess(0, json.dumps([]))
    )
    ghapi.request(
        endpoint="/orgs/o/repos", params={"page": 1}, repository_id=None, run_id="run-1"
    )
    assert "--paginate" not in calls[0]


def test_request_raises_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-zero ``gh`` exit raises ``GhApiError`` with a scrubbed message."""
    _stub_run(
        monkeypatch,
        lambda _argv: _FakeCompletedProcess(
            1, "", "error: Authorization: Bearer secret-token"
        ),
    )
    with pytest.raises(ghapi.GhApiError) as excinfo:
        ghapi.request(endpoint="/repos/o/r", params={}, repository_id=1, run_id="run-1")
    assert "secret-token" not in str(excinfo.value)


def test_request_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unparseable stdout raises ``GhApiError``."""
    _stub_run(monkeypatch, lambda _argv: _FakeCompletedProcess(0, "not json"))
    with pytest.raises(ghapi.GhApiError):
        ghapi.request(endpoint="/repos/o/r", params={}, repository_id=1, run_id="run-1")


def test_request_provenance_excludes_credential_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Serialized provenance never contains credential-shaped values."""
    _stub_run(monkeypatch, lambda _argv: _FakeCompletedProcess(0, json.dumps({})))
    response = ghapi.request(
        endpoint="/repos/o/r",
        params={"gh_token": "should-not-appear", "state": "all"},
        repository_id=1,
        run_id="run-1",
    )
    serialized = json.dumps(response.provenance)
    assert "should-not-appear" not in serialized
    assert "gh_token" not in serialized
    assert "state" in response.provenance["params"]


@pytest.mark.parametrize(
    ("record", "forbidden_key"),
    [
        ({"Authorization": "Bearer x", "endpoint": "/x"}, "Authorization"),
        ({"GH_TOKEN": "x", "endpoint": "/x"}, "GH_TOKEN"),
        ({"params": {"password": "x"}, "endpoint": "/x"}, "password"),
        ({"cookie": "x", "endpoint": "/x"}, "cookie"),
    ],
)
def test_scrub_provenance_removes_credential_keys(
    record: dict[str, Any], forbidden_key: str
) -> None:
    """``scrub_provenance`` removes every credential-shaped key, top-level or nested."""
    scrubbed = ghapi.scrub_provenance(record)
    assert forbidden_key not in json.dumps(scrubbed)


@pytest.mark.parametrize(
    "text",
    [
        'error: {"Authorization": "Bearer ghp_123456789012345678901234567890123456"}',
        "error: Authorization\tBearer ghp_123456789012345678901234567890123456",
        "Bad credentials (ghp_123456789012345678901234567890123456)",
        "Bad credentials (github_pat_1234567890123456789012345)",
    ],
)
def test_redact_secret_values_catches_shapes_the_key_pattern_misses(text: str) -> None:
    """A bare or unusually-delimited GitHub token is redacted independent of any key."""
    redacted = ghapi._redact_secret_values(text)  # pyright: ignore[reportPrivateUsage]
    assert "ghp_" not in redacted
    assert "github_pat_" not in redacted
    assert "[REDACTED]" in redacted, "the token must be replaced, not merely absent"


def test_paginate_stops_below_full_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pagination stops once a page returns fewer than ``per_page`` items."""
    pages = {1: [{"id": 1}, {"id": 2}], 2: [{"id": 3}]}

    def handler(argv: list[str]) -> _FakeCompletedProcess:
        url = argv[-1]
        page_number = int(url.split("page=")[1].split("&")[0])
        return _FakeCompletedProcess(0, json.dumps(pages[page_number]))

    calls = _stub_run(monkeypatch, handler)
    results = list(
        ghapi.paginate(
            endpoint="/repos/o/r/pulls",
            params={},
            repository_id=1,
            run_id="run-1",
            per_page=2,
        )
    )
    assert len(results) == 2
    assert len(calls) == 2
    assert [item["id"] for page in results for item in page.payload] == [1, 2, 3]


def test_paginate_raises_on_non_list_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-array page payload raises ``GhApiError``."""
    _stub_run(
        monkeypatch,
        lambda _argv: _FakeCompletedProcess(0, json.dumps({"not": "a list"})),
    )
    with pytest.raises(ghapi.GhApiError):
        list(
            ghapi.paginate(
                endpoint="/repos/o/r/pulls", params={}, repository_id=1, run_id="run-1"
            )
        )


def test_request_raises_gh_api_error_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wedged ``gh api`` call times out into ``GhApiError`` rather than hanging."""
    captured_kwargs: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        captured_kwargs.update(kwargs)
        raise subprocess.TimeoutExpired(cmd=argv, timeout=120.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ghapi.GhApiError, match="timed out"):
        ghapi.request(endpoint="/repos/o/r", params={}, repository_id=1, run_id="run-1")
    expected_timeout = ghapi._REQUEST_TIMEOUT_SECONDS  # pyright: ignore[reportPrivateUsage]
    assert captured_kwargs["timeout"] == expected_timeout
