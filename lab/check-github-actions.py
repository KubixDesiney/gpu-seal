#!/usr/bin/env python3
"""Enforce immutable commit-SHA references for every workflow action."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def main() -> int:
    path = Path(__file__).with_name("check-release-readiness.py")
    spec = importlib.util.spec_from_file_location("release_readiness", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load release checks")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    check = module.check_github_action_pins()
    for problem in check.problems:
        print(problem)
    if check.ok:
        print("GitHub Action pin policy: PASS")
    return 0 if check.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
