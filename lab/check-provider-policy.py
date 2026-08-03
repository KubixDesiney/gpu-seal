#!/usr/bin/env python3
"""Check the provider policy matrix — CHARTER.md §7.4, §16 test 13, §23.

Run by the Phase 0 CI job. Decides one thing:

    may the no-named-provider gate be lifted yet?

The answer is yes only when at least one provider record is *complete* — read,
classified, sourced, dated, attributed, not stale, and carrying a permission
reference if its class requires one — and no record is malformed.

The previous version of this check tested whether the directory was non-empty.
That was enough while the directory was empty and wrong the moment it was not:
a directory of unreviewed slot files would have lifted the gate on the strength
of existing.

    python3 lab/check-provider-policy.py [--dir docs/provider-policy-review]

Exit 0 when the matrix is coherent (whether or not any provider is reviewed);
exit 1 when a record is malformed. The gate decision is printed for CI to read
and is deliberately separate from the exit code — "nothing reviewed yet" is a
correct state, not a build failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "probe"))

from gpu_seal.controller.policy_matrix import (  # noqa: E402
    REVIEW_VALIDITY_DAYS,
    ProviderPolicy,
)
from gpu_seal.safety.policy import PROVIDER_POLICY_CLASSES  # noqa: E402

REQUIRED_FIELDS = (
    "provider_code",
    "classification",
    "policy_sources",
    "policy_version",
    "reviewed_on",
    "reviewed_by",
)


def check_record(path: Path) -> tuple[str, list[str]]:
    """Return (state, problems) for one record file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "malformed", [f"not valid JSON: {exc}"]

    if raw.get("template"):
        return "template", []

    if raw.get("status") != "reviewed":
        return "awaiting-review", []

    problems: list[str] = []
    for field in REQUIRED_FIELDS:
        if not raw.get(field):
            problems.append(f"missing required field {field!r}")

    classification = raw.get("classification")
    if classification and classification not in PROVIDER_POLICY_CLASSES:
        problems.append(
            f"classification {classification!r} is not one of "
            f"{sorted(PROVIDER_POLICY_CLASSES)}"
        )

    if problems:
        return "incomplete", problems

    try:
        policy = ProviderPolicy.from_dict(raw)
    except (ValueError, KeyError) as exc:
        return "malformed", [str(exc)]

    if policy.is_stale():
        problems.append(
            f"reviewed on {policy.reviewed_on.isoformat()}, older than "
            f"{REVIEW_VALIDITY_DAYS} days — provider terms change, re-read them"
        )
    if (
        policy.classification == "needs-written-permission"
        and not policy.permission_reference
    ):
        problems.append(
            "classified needs-written-permission with no permission_reference; "
            "nothing may run against this provider until permission is on record"
        )

    return ("complete" if not problems else "incomplete"), problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=Path("docs/provider-policy-review"))
    args = parser.parse_args()

    print()
    print("GPU-SEAL provider policy matrix check")
    print("=" * 62)
    print(f"  directory   {args.dir}")
    print(f"  today       {date.today().isoformat()}")
    print()

    if not args.dir.is_dir():
        print("  directory absent — Phase 0 gate ENFORCED")
        print()
        print("GATE: enforced")
        return 0

    states: dict[str, list[str]] = {}
    malformed = False

    for path in sorted(args.dir.glob("*.json")):
        state, problems = check_record(path)
        states.setdefault(state, []).append(path.name)
        marker = {
            "complete": "x",
            "awaiting-review": " ",
            "template": "-",
            "incomplete": "!",
            "malformed": "!",
        }[state]
        print(f"  [{marker}] {path.name:28s} {state}")
        for problem in problems:
            print(f"        - {problem}")
        if state == "malformed":
            malformed = True

    complete = states.get("complete", [])
    incomplete = states.get("incomplete", [])

    print()
    print(f"  complete    {len(complete)}")
    print(f"  awaiting    {len(states.get('awaiting-review', []))}")
    print(f"  incomplete  {len(incomplete)}")
    print()

    if malformed:
        print("RESULT: FAIL — a policy record is malformed.")
        return 1

    if incomplete:
        print("RESULT: FAIL — a record claims to be reviewed but is not complete.")
        print("A half-filled record is more dangerous than an empty one: it")
        print("looks like the review happened.")
        return 1

    if complete:
        print(f"GATE: lifted — {len(complete)} reviewed provider(s): {complete}")
    else:
        print("GATE: enforced — no provider has a complete review record.")
        print("CHARTER.md §23: do not begin named-provider testing until the")
        print("ethics and policy checklist is complete.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
