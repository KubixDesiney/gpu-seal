#!/usr/bin/env python3
"""Run the repository liveness scorecard.

The scorecard deliberately executes the machinery behind the project's
claims. It is not a replacement for the tests or mutation battery: it is a
small, repeatable check that those checks can start, that probe modules import,
and that the policy matrix is loadable.

    python3 lab/scorecard.py
    python3 lab/scorecard.py --history /tmp/scorecard.jsonl
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import pkgutil
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE_ROOT = ROOT / "probe"
BATTERY = ROOT / "lab" / "verify-safety-suite.sh"
DEFAULT_HISTORY = ROOT / ".provenance" / "scorecard-history.jsonl"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _bash_command() -> str | None:
    """Return a Bash executable that can actually start on this host."""
    candidates: list[str] = []
    discovered = shutil.which("bash")
    if discovered:
        candidates.append(discovered)
    if os.name == "nt":
        candidates.extend(
            path
            for path in (
                r"C:\Program Files\Git\bin\bash.exe",
                r"C:\Program Files\Git\usr\bin\bash.exe",
            )
            if Path(path).is_file()
        )
    for candidate in dict.fromkeys(candidates):
        try:
            result = subprocess.run(  # noqa: S603 - known Bash executable
                [candidate, "-c", "exit 0"],
                capture_output=True,
                check=False,
            )
        except OSError:
            continue
        if result.returncode == 0:
            return candidate
    return None


def _bash_python(bash: str) -> str:
    """Choose a Python command that the selected bash environment can run."""
    if os.name != "nt":
        return sys.executable
    bash_path = bash.lower().replace("/", "\\")
    if "\\system32\\bash.exe" in bash_path:
        # WSL can invoke Windows' Python through interop, but cannot execute a
        # Windows path passed as a POSIX command name.
        return "python.exe"
    cygpath = shutil.which("cygpath")
    if cygpath is None and os.name == "nt":
        candidate = Path(r"C:\Program Files\Git\usr\bin\cygpath.exe")
        cygpath = str(candidate) if candidate.is_file() else None
    if cygpath is not None:
        result = subprocess.run(  # noqa: S603 - cygpath resolved above
            [cygpath, "-u", sys.executable],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    return "python"


def _repository_scripts() -> list[Path]:
    ignored = {".git", ".venv", "venv", "node_modules", "__pycache__"}
    return sorted(
        path
        for path in ROOT.rglob("*.sh")
        if not ignored.intersection(path.parts)
    )


def _short_output(result: subprocess.CompletedProcess[str]) -> str:
    output = (result.stdout + result.stderr).strip()
    if not output:
        return "no output"
    lines = output.splitlines()
    if len(lines) > 4:
        lines = [*lines[:3], "…", lines[-1]]
    return " | ".join(lines)


def check_shell_syntax() -> CheckResult:
    bash = _bash_command()
    scripts = _repository_scripts()
    if bash is None:
        return CheckResult("shell syntax", False, "bash is unavailable")
    failures: list[str] = []
    for script in scripts:
        result = subprocess.run(  # noqa: S603 - bash resolved above
            [bash, "-n", script.relative_to(ROOT).as_posix()],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
        if result.returncode:
            failures.append(f"{script.relative_to(ROOT)}: {_short_output(result)}")
    if failures:
        return CheckResult("shell syntax", False, "; ".join(failures))
    return CheckResult(
        "shell syntax", True, f"bash -n passed for {len(scripts)} scripts"
    )


def check_probe_imports() -> CheckResult:
    sys.path.insert(0, str(PROBE_ROOT))
    try:
        import gpu_seal

        modules = sorted(
            module.name
            for module in pkgutil.walk_packages(
                gpu_seal.__path__, prefix=f"{gpu_seal.__name__}."
            )
        )
        for module in modules:
            importlib.import_module(module)
    except Exception as exc:  # noqa: BLE001 - scorecard must report the module
        return CheckResult("probe imports", False, f"{type(exc).__name__}: {exc}")
    return CheckResult(
        "probe imports", True, f"imported {len(modules)} gpu_seal modules"
    )


def check_battery_preflight() -> CheckResult:
    bash = _bash_command()
    if bash is None:
        return CheckResult("battery preflight", False, "bash is unavailable")

    relative_battery = BATTERY.relative_to(ROOT).as_posix()
    if os.name == "nt" and "\\system32\\bash.exe" in bash.lower():
        command = (
            f"PYTHON_BIN={shlex.quote(_bash_python(bash))} "
            f"exec bash {shlex.quote(relative_battery)} --preflight"
        )
        result = subprocess.run(  # noqa: S603 - bash and repo path are fixed
            [bash, "-c", command],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
    else:
        env = os.environ.copy()
        env["PYTHON_BIN"] = _bash_python(bash)
        result = subprocess.run(  # noqa: S603 - bash and repo path are fixed
            [bash, relative_battery, "--preflight"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=env,
            check=False,
        )
    if result.returncode:
        return CheckResult("battery preflight", False, _short_output(result))
    return CheckResult(
        "battery preflight", True, "pytest version and collection succeeded"
    )


def check_provider_matrix() -> CheckResult:
    sys.path.insert(0, str(PROBE_ROOT))
    try:
        from gpu_seal.controller.policy_matrix import load_policy_matrix

        matrix = load_policy_matrix(ROOT / "docs" / "provider-policy-review")
    except Exception as exc:  # noqa: BLE001 - scorecard must report the loader
        return CheckResult("provider matrix", False, f"{type(exc).__name__}: {exc}")
    return CheckResult(
        "provider matrix",
        True,
        f"loaded {len(matrix)} reviewed provider record(s): "
        f"{', '.join(matrix.provider_codes) or 'none'}",
    )


def _git_commit() -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    result = subprocess.run(  # noqa: S603 - git resolved above
        [git, "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def append_history(path: Path, results: list[CheckResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": _git_commit(),
        "checks": [asdict(result) for result in results],
        "ok": all(result.ok for result in results),
    }
    with path.open("a", encoding="utf-8", newline="\n") as history:
        history.write(json.dumps(record, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history",
        type=Path,
        default=DEFAULT_HISTORY,
        help=f"JSONL history path (default: {DEFAULT_HISTORY.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="do not append this run to the history file",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = [
        check_shell_syntax(),
        check_probe_imports(),
        check_battery_preflight(),
        check_provider_matrix(),
    ]
    print("GPU-SEAL liveness scorecard")
    print("=" * 30)
    for result in results:
        marker = "PASS" if result.ok else "FAIL"
        print(f"[{marker}] {result.name}: {result.detail}")
    if not args.no_history:
        append_history(args.history, results)
        print(f"history: {args.history}")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
