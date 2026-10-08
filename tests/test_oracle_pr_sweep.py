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
    """Ensure the detached worker survives its parent and stores its result."""
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
        'echo "RESULT: success"\n',
        encoding="utf-8",
    )
    oracle.chmod(0o755)

    prompt = tmp_path / "prompt.txt"
    launched = tmp_path / "launched"
    release = tmp_path / "release"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "FAKE_PROMPT": str(prompt),
        "FAKE_LAUNCHED": str(launched),
        "FAKE_RELEASE": str(release),
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
        wait_for_file(launched)
        run_dirs = list((tmp_path / "state" / "oracle-pr-sweep").glob("run.*"))
        assert len(run_dirs) == 1
        run_dir = run_dirs[0]
        assert (run_dir / "started").is_file()
        assert not (run_dir / "exit-code").exists()
        assert "at most 3 open" in prompt.read_text(encoding="utf-8")
    finally:
        release.touch()

    wait_for_file(run_dir / "exit-code")
    assert (run_dir / "exit-code").read_text(encoding="utf-8").strip() == "0"
    assert "RESULT: success" in (run_dir / "output.log").read_text(encoding="utf-8")
