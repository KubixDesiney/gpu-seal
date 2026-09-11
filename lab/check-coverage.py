#!/usr/bin/env python3
"""Enforce separate line and branch coverage floors from coverage.py JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("coverage_json", type=Path)
    parser.add_argument("--min-line", type=float, default=80.0)
    parser.add_argument("--min-branch", type=float, default=77.0)
    args = parser.parse_args()
    report: dict[str, Any] = json.loads(args.coverage_json.read_text(encoding="utf-8"))
    totals = report["totals"]
    line = float(totals["percent_covered_display"])
    branch = 100.0 * totals["covered_branches"] / totals["num_branches"]
    print(f"line coverage: {line:.2f}% (required {args.min_line:.2f}%)")
    print(f"branch coverage: {branch:.2f}% (required {args.min_branch:.2f}%)")
    if line < args.min_line or branch < args.min_branch:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
