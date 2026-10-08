"""Verify the Oracle PR sweep delegates non-blocking execution to Oracle."""

import os
import shutil
import subprocess  # noqa: S404 - invokes a fixed local mock command
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/oracle-pr-sweep.sh"


@pytest.mark.parametrize("exit_code", [0, 17])
def test_sweep_uses_native_no_wait(tmp_path: Path, exit_code: int) -> None:
    """Pass --no-wait to a Pro browser model and propagate dispatch failures."""
    bash = shutil.which("bash")
    assert bash is not None

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    oracle = bin_dir / "oracle"
    oracle.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "--version" ]]; then echo "oracle 0.20.0"; exit 0; fi\n'
        'if [[ "$1" == "bridge" && "$2" == "doctor" ]]; then exit 0; fi\n'
        'printf "%s\\n" "$@" > "${FAKE_ARGS:?}"\n'
        'cat > "${FAKE_PROMPT:?}"\n'
        'exit "${FAKE_EXIT_CODE:?}"\n',
        encoding="utf-8",
    )
    oracle.chmod(0o755)

    args_path = tmp_path / "args.txt"
    prompt_path = tmp_path / "prompt.txt"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_ARGS": str(args_path),
        "FAKE_PROMPT": str(prompt_path),
        "FAKE_EXIT_CODE": str(exit_code),
    }
    result = subprocess.run(  # noqa: S603 - fixed script path under test
        [bash, str(SCRIPT), "--max-count=3"],
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == exit_code
    assert args_path.read_text(encoding="utf-8").splitlines() == [
        "--no-wait",
        "--engine",
        "browser",
        "--model",
        "gpt-6-pro",
        "-p",
        "-",
    ]
    assert "at most 3 open" in prompt_path.read_text(encoding="utf-8")
