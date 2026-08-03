"""Report and enforce mutation coverage across the safety test files."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATTERY = ROOT / "lab" / "verify-safety-suite.sh"
SAFETY = ROOT / "tests" / "safety"
UNIT = ROOT / "tests" / "unit"
CASE_RE = re.compile(
    r'run_case\s+"[^"]+"\s+\\\s*\n\s*"([^"]+)"',
    re.MULTILINE,
)
TEST_RE = re.compile(r"^def (test_[A-Za-z0-9_]+)\(", re.MULTILINE)


def main() -> int:
    expected = CASE_RE.findall(BATTERY.read_text(encoding="utf-8"))
    test_files = (*sorted(SAFETY.glob("test_*.py")), *sorted(UNIT.glob("test_*.py")))
    definitions = {
        path: set(TEST_RE.findall(path.read_text(encoding="utf-8")))
        for path in test_files
    }

    locations: dict[str, Path] = {}
    for name in expected:
        matches = [path for path, names in definitions.items() if name in names]
        if len(matches) != 1:
            print(f"mutation coverage: cannot resolve {name!r} ({len(matches)} matches)")
            return 1
        locations[name] = matches[0]

    counts = {path: 0 for path in sorted(SAFETY.glob("test_*.py"))}
    for path in locations.values():
        if path in counts:
            counts[path] += 1

    uncovered = [path for path, count in counts.items() if count == 0]
    print(
        f"mutation coverage: {len(expected)} cases across "
        f"{len(counts) - len(uncovered)}/{len(counts)} safety files"
    )
    for path, count in counts.items():
        print(f"  {path.relative_to(ROOT)}: {count}")
    if uncovered:
        print("mutation coverage: uncovered safety files:")
        for path in uncovered:
            print(f"  {path.relative_to(ROOT)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
