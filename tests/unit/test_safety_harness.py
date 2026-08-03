"""The negative-control harness must fail closed when pytest is unavailable."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _to_bash_path(cygpath: str, path: Path) -> str:
    return subprocess.check_output(  # noqa: S603 - fixed cygpath executable
        [cygpath, "-u", str(path)], text=True
    ).strip()


def test_missing_pytest_is_not_counted_as_a_caught_mutation(tmp_path):
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required to execute the CI harness")

    fake_python = tmp_path / "python-without-pytest"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'No module named pytest' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    script = Path(__file__).resolve().parents[2] / "lab" / "verify-safety-suite.sh"
    env = os.environ.copy()
    if os.name == "nt":
        cygpath = shutil.which("cygpath")
        if cygpath is None:
            pytest.skip("cygpath is required for Git Bash path conversion")
        env["PYTHON_BIN"] = _to_bash_path(cygpath, fake_python)
        script_arg = _to_bash_path(cygpath, script)
    else:
        env["PYTHON_BIN"] = str(fake_python)
        script_arg = str(script)

    result = subprocess.run(  # noqa: S603 - fixed bash script under test
        [bash, script_arg], capture_output=True, text=True, env=env
    )

    assert result.returncode == 2
    assert "pytest is unavailable" in result.stderr
