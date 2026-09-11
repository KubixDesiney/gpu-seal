"""The negative-control harness must fail closed when pytest is unavailable."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _to_bash_path(cygpath: str, path: Path) -> str:
    return subprocess.check_output(  # noqa: S603 - fixed cygpath executable
        [cygpath, "-u", str(path)], text=True
    ).strip()


def _cygpath_command() -> str | None:
    value = shutil.which("cygpath")
    if value is None and os.name == "nt":
        candidate = Path(r"C:\Program Files\Git\usr\bin\cygpath.exe")
        value = str(candidate) if candidate.is_file() else None
    return value


def _is_wsl_bash(bash: str) -> bool:
    return os.name == "nt" and "\\system32\\bash.exe" in bash.lower()


def _to_wsl_path(bash: str, path: Path) -> str:
    result = subprocess.run(  # noqa: S603 - known Bash executable
        [bash, "-c", 'wslpath -u -- "$1"', "wslpath", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _usable_bash() -> str | None:
    candidates = [shutil.which("bash")]
    if os.name == "nt":
        candidates.extend(
            path
            for path in (
                r"C:\Program Files\Git\bin\bash.exe",
                r"C:\Program Files\Git\usr\bin\bash.exe",
            )
            if Path(path).is_file()
        )
    for candidate in dict.fromkeys(path for path in candidates if path):
        try:
            result = subprocess.run(  # noqa: S603 - known Bash executable
                [candidate, "-c", "exit 0"], capture_output=True, check=False
            )
        except OSError:
            continue
        if result.returncode == 0:
            return candidate
    return None


def test_missing_pytest_is_not_counted_as_a_caught_mutation(tmp_path):
    bash = _usable_bash()
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
    if _is_wsl_bash(bash):
        env["PYTHON_BIN"] = _to_wsl_path(bash, fake_python)
        result = subprocess.run(  # noqa: S603 - fixed bash harness
            [
                bash,
                "-c",
                'PYTHON_BIN="$1" exec bash lab/verify-safety-suite.sh',
                "gpu-seal-harness",
                env["PYTHON_BIN"],
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=script.parents[1],
        )
    elif os.name == "nt":
        cygpath = _cygpath_command()
        if cygpath is None:
            pytest.skip("cygpath is required for Git Bash path conversion")
        env["PYTHON_BIN"] = _to_bash_path(cygpath, fake_python)
        script_arg = _to_bash_path(cygpath, script)
    else:
        env["PYTHON_BIN"] = str(fake_python)
        script_arg = str(script)

    if not _is_wsl_bash(bash):
        result = subprocess.run(  # noqa: S603 - fixed bash script under test
            [bash, script_arg], capture_output=True, text=True, env=env
        )

    assert result.returncode == 2
    assert "pytest is unavailable" in result.stderr


def test_battery_preflight_collects_without_mutating_the_tree():
    bash = _usable_bash()
    if bash is None:
        pytest.skip("bash is required to execute the CI harness")

    script = Path(__file__).resolve().parents[2] / "lab" / "verify-safety-suite.sh"
    env = os.environ.copy()
    if _is_wsl_bash(bash):
        result = subprocess.run(  # noqa: S603 - fixed bash harness
            [
                bash,
                "-c",
                "PYTHON_BIN=python.exe exec bash "
                "lab/verify-safety-suite.sh --preflight",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
    else:
        cygpath = _cygpath_command()
        env["PYTHON_BIN"] = (
            _to_bash_path(cygpath, Path(sys.executable))
            if cygpath is not None
            else sys.executable
        )
        script_arg = str(script)
        result = subprocess.run(  # noqa: S603 - fixed bash harness
            [bash, script_arg, "--preflight"],
            capture_output=True,
            text=True,
            env=env,
        )

    assert result.returncode == 0, result.stderr
    assert "collected" in result.stdout
