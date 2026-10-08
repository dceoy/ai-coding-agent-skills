"""Verify that the Oracle PR sweep detaches without waiting for the review."""

import os
import shutil
import subprocess  # noqa: S404 - invokes a fixed local mock command
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/oracle-pr-sweep.sh"


def wait_for_file(path: Path) -> None:
    """Wait for a background worker to write a file."""
    for _ in range(100):
        if path.is_file():
            return
        time.sleep(0.1)
    msg = f"Timed out waiting for {path}"
    raise AssertionError(msg)


def test_sweep_returns_before_review_finishes(tmp_path: Path) -> None:
    """Ensure the detached worker completes independently without saving status."""
    bash = shutil.which("bash")
    assert bash is not None

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    oracle = bin_dir / "oracle"
    oracle.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "--version" ]]; then echo "oracle 0.20.0"; exit 0; fi\n'
        'if [[ "$1" == "bridge" && "$2" == "doctor" ]]; then exit 0; fi\n'
        'cat > "${FAKE_PROMPT:?}"\n'
        'touch "${FAKE_LAUNCHED:?}"\n'
        'while [[ ! -f "${FAKE_RELEASE:?}" ]]; do sleep 0.1; done\n'
        'touch "${FAKE_FINISHED:?}"\n'
        'echo "RESULT: success"\n',
        encoding="utf-8",
    )
    oracle.chmod(0o755)

    prompt = tmp_path / "prompt.txt"
    launched = tmp_path / "launched"
    release = tmp_path / "release"
    finished = tmp_path / "finished"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "FAKE_PROMPT": str(prompt),
        "FAKE_LAUNCHED": str(launched),
        "FAKE_RELEASE": str(release),
        "FAKE_FINISHED": str(finished),
    }
    try:
        result = subprocess.run(  # noqa: S603 - fixed script path under test
            [bash, str(SCRIPT), "--max-count=3"],
            env=env,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "started in background" in result.stdout
        wait_for_file(launched)
        assert not finished.exists()
        assert not (tmp_path / "state").exists()
        assert "at most 3 open" in prompt.read_text(encoding="utf-8")
    finally:
        release.touch()

    wait_for_file(finished)
    assert not (tmp_path / "state").exists()
