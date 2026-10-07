"""Run credential-free native Node tests for the deployment wrapper."""

import os
import shutil
import subprocess  # noqa: S404 - invokes a fixed credential-free native test runner
from pathlib import Path


def test_mocked_gas_deployment() -> None:
    """Exercise packaging, remote preservation and deployment failure boundaries."""
    node = shutil.which("node")
    assert node is not None, "Node.js >=20 is required for mocked deployment tests"
    result = subprocess.run(  # noqa: S603
        [node, "--test", "tests/gas-html-artifact.test.mjs"],
        cwd=Path(__file__).resolve().parents[1],
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
