#!/usr/bin/env python3
"""Aggregate the sharded mutation-battery logs into one machine-readable summary.

Each suite-negative-control matrix job runs a subset of lab/verify-safety-suite.sh
(selected by CASE_FILTER) and uploads its raw stdout/stderr as a build artifact.
This script downloads those shard logs (see the mutation-summary job in
.github/workflows/safety.yml), matches each of the battery's run_case
invocations against them by name, and writes one JSON document recording
whether every injected policy violation was actually caught -- so the
"injected violations caught" claim in README.md can be generated from a real
CI result instead of hand-typed.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATTERY = ROOT / "lab" / "verify-safety-suite.sh"
# The same two directories lab/check-mutation-coverage.py resolves a case's
# expected test against; run_case runs both, so a case can land in either.
TEST_DIRS = (ROOT / "tests" / "safety", ROOT / "tests" / "unit")
CASE_RE = re.compile(
    r'run_case\s+"([^"]+)"\s+\\\s*\n\s*"([^"]+)"',
    re.MULTILINE,
)
TEST_RE = re.compile(r"^def (test_[A-Za-z0-9_]+)\(", re.MULTILINE)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def load_cases() -> list[tuple[str, str]]:
    cases = CASE_RE.findall(BATTERY.read_text(encoding="utf-8"))
    if not cases:
        raise SystemExit(f"no run_case invocations found in {BATTERY}")
    return cases


def load_test_files() -> dict[str, list[str]]:
    """Map each test function name to the repo-relative files that define it."""
    found: dict[str, list[str]] = {}
    for directory in TEST_DIRS:
        for path in sorted(directory.glob("test_*.py")):
            relative = path.relative_to(ROOT).as_posix()
            for test in TEST_RE.findall(path.read_text(encoding="utf-8")):
                found.setdefault(test, []).append(relative)
    return found


def resolve_test_file(test: str, test_files: dict[str, list[str]]) -> str:
    """The one file defining `test`. The summary groups cases by this, so a
    test that resolves to no file or to several is a broken battery, not a
    detail to guess at."""
    matches = test_files.get(test, [])
    if len(matches) != 1:
        raise SystemExit(
            f"cannot resolve {test!r} to a single test file ({len(matches)} matches)"
        )
    return matches[0]


def load_log_text(logs_dir: Path) -> str:
    chunks = []
    for path in sorted(logs_dir.rglob("*.log")):
        chunks.append(ANSI_RE.sub("", path.read_text(encoding="utf-8", errors="replace")))
    if not chunks:
        raise SystemExit(f"no *.log files found under {logs_dir}")
    return "\n".join(chunks)


def classify(name: str, log_text: str) -> tuple[str, str | None]:
    """Match run_case's own printf output format in lab/verify-safety-suite.sh."""
    escaped = re.escape(name)

    match = re.search(rf"caught\s+{escaped}\s*->\s*(\S+)", log_text)
    if match:
        return "caught", match.group(1)

    match = re.search(rf"WRONG\s+{escaped}\s+expected\s+(\S+)", log_text)
    if match:
        return "wrong", match.group(1)

    if re.search(rf"MISSED\s+{escaped}\s+suite stayed green", log_text):
        return "missed", None

    if re.search(rf"ERROR\s+{escaped}\s+pytest/environment failure", log_text):
        return "error", None

    return "not_run", None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "logs_dir",
        type=Path,
        help="directory containing downloaded mutation-battery-log-* artifacts",
    )
    parser.add_argument("output", type=Path, help="path to write the JSON summary")
    args = parser.parse_args()

    cases = load_cases()
    log_text = load_log_text(args.logs_dir)
    test_files = load_test_files()

    results = []
    caught = 0
    for name, expect_test in cases:
        status, found_test = classify(name, log_text)
        if status == "caught":
            caught += 1
        results.append(
            {
                "name": name,
                "expected_test": expect_test,
                "test_file": resolve_test_file(expect_test, test_files),
                "status": status,
                "matched_test": found_test,
            }
        )

    total = len(cases)
    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": total,
        "caught": caught,
        "missed": total - caught,
        "cases": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"mutation battery summary: {caught}/{total} caught -> {args.output}")
    for result in results:
        if result["status"] != "caught":
            print(f"  {result['status']:>8}  {result['name']} (expected {result['expected_test']})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
