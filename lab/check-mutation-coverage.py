"""Report and enforce mutation coverage across the safety test files.

Two independent things can silently rot without this check:

1. A safety test file with no mutation in the battery at all (the original
   purpose of this script).
2. A mutation case added to lab/verify-safety-suite.sh that matches none of
   the CASE_FILTER batch patterns in the suite-negative-control matrix in
   .github/workflows/safety.yml. Such a case is never run by CI batches (it
   only runs when CASE_FILTER is empty, which CI never does), so it is
   invisible: both jobs stay green while coverage silently drops.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATTERY = ROOT / "lab" / "verify-safety-suite.sh"
SAFETY = ROOT / "tests" / "safety"
UNIT = ROOT / "tests" / "unit"
WORKFLOW = ROOT / ".github" / "workflows" / "safety.yml"

# Captures both run_case arguments: the human-readable case name (arg 1, used
# to match CASE_FILTER patterns) and the pytest test name it must fail (arg 2,
# used to resolve which safety/unit file it exercises).
CASE_RE = re.compile(
    r'run_case\s+"([^"]+)"\s+\\\s*\n\s*"([^"]+)"',
    re.MULTILINE,
)
TEST_RE = re.compile(r"^def (test_[A-Za-z0-9_]+)\(", re.MULTILINE)

# Matches one `- id: ...` / `pattern: '...'` matrix.batch entry in the
# suite-negative-control job. Quote style (' or ") is captured and
# back-referenced so either is accepted.
BATCH_ITEM_RE = re.compile(
    r"-\s*id:\s*(?P<id>[A-Za-z0-9_.-]+)\s*\n\s*pattern:\s*"
    r"(?P<quote>['\"])(?P<pattern>.*?)(?P=quote)\s*$",
    re.MULTILINE,
)


def load_cases() -> list[tuple[str, str]]:
    cases = CASE_RE.findall(BATTERY.read_text(encoding="utf-8"))
    if not cases:
        raise SystemExit(f"mutation coverage: no run_case invocations found in {BATTERY}")
    return cases


def load_batches() -> list[tuple[str, str]]:
    text = WORKFLOW.read_text(encoding="utf-8")
    return [(m.group("id"), m.group("pattern")) for m in BATCH_ITEM_RE.finditer(text)]


def check_file_coverage(expect_tests: list[str]) -> list[str]:
    test_files = (*sorted(SAFETY.glob("test_*.py")), *sorted(UNIT.glob("test_*.py")))
    definitions = {
        path: set(TEST_RE.findall(path.read_text(encoding="utf-8")))
        for path in test_files
    }

    locations: dict[str, Path] = {}
    problems: list[str] = []
    for name in expect_tests:
        matches = [path for path, names in definitions.items() if name in names]
        if len(matches) != 1:
            problems.append(f"mutation coverage: cannot resolve {name!r} ({len(matches)} matches)")
            continue
        locations[name] = matches[0]

    counts = {path: 0 for path in sorted(SAFETY.glob("test_*.py"))}
    for path in locations.values():
        if path in counts:
            counts[path] += 1

    print(
        f"mutation coverage: {len(expect_tests)} cases across "
        f"{sum(1 for c in counts.values() if c) }/{len(counts)} safety files"
    )
    for path, count in counts.items():
        print(f"  {path.relative_to(ROOT)}: {count}")

    uncovered = [path for path, count in counts.items() if count == 0]
    if uncovered:
        print("mutation coverage: uncovered safety files:")
        for path in uncovered:
            print(f"  {path.relative_to(ROOT)}")
        problems.append("mutation coverage: one or more safety files have no mutation case")
    return problems


def check_matrix_coverage(case_names: list[str]) -> list[str]:
    problems: list[str] = []
    batches = load_batches()
    if not batches:
        return [f"mutation coverage: no matrix.batch entries found in {WORKFLOW.relative_to(ROOT)}"]

    compiled = []
    seen_ids: set[str] = set()
    for batch_id, pattern in batches:
        if batch_id in seen_ids:
            problems.append(f"mutation coverage: duplicate matrix.batch id {batch_id!r}")
        seen_ids.add(batch_id)
        try:
            compiled.append((batch_id, re.compile(pattern)))
        except re.error as exc:
            problems.append(
                f"mutation coverage: matrix.batch {batch_id!r} has an invalid "
                f"CASE_FILTER pattern {pattern!r}: {exc}"
            )
    if problems:
        return problems

    uncovered = [name for name in case_names if not any(rx.search(name) for _, rx in compiled)]
    print(f"mutation coverage: {len(case_names)} cases across {len(compiled)} matrix batches")
    if uncovered:
        problems.append(
            "mutation coverage: the following battery cases match no CASE_FILTER "
            f"batch in {WORKFLOW.relative_to(ROOT)}:"
        )
        for name in uncovered:
            problems.append(f"  {name!r}")
        problems.append(
            "Add each one to an existing (or a new) batch pattern in the "
            "suite-negative-control matrix so CI actually runs it."
        )
    return problems


def main() -> int:
    cases = load_cases()
    case_names = [name for name, _ in cases]
    expect_tests = [expect_test for _, expect_test in cases]

    problems = check_file_coverage(expect_tests)
    problems += check_matrix_coverage(case_names)

    if problems:
        print()
        for problem in problems:
            print(problem)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
