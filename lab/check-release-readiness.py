#!/usr/bin/env python3
"""Release gate — the things that must be true before GPU-SEAL goes public.

    python3 lab/check-release-readiness.py

Every check here guards something that is easy to leave half-done and
expensive to discover after publication. Each prints its own reason and cites
the charter clause it enforces.

Exit 0 when the repository is releasable, 1 otherwise. Run by CI on a tag; run
by hand before an arXiv submission.

The point is not that these are hard checks. The point is that "populate the
author fields" is the kind of task that survives three sprints as a TODO
comment and then ships.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPO_ROOT / "probe"))


class Check:
    def __init__(self, name: str, clause: str) -> None:
        self.name = name
        self.clause = clause
        self.problems: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)

    @property
    def ok(self) -> bool:
        return not self.problems


def check_citation() -> Check:
    """CHARTER.md §21: author metadata before any public release."""
    check = Check("CITATION.cff author metadata", "§21, §23")
    text = (REPO_ROOT / "CITATION.cff").read_text(encoding="utf-8")

    authors_block = text.split("authors:", 1)[-1].split("references:", 1)[0]
    if "TODO" in authors_block:
        check.fail(
            "author given-names / family-names / affiliation are still "
            "placeholders. A preprint cannot be submitted without them, and "
            "they must not be guessed from a git handle (§23: never cite by "
            "unverified author name)."
        )
    return check


def check_lock_file() -> Check:
    """CHARTER.md §10, §14: the release image must be reproducible."""
    check = Check("container lock file", "§10, §14")
    path = REPO_ROOT / "infrastructure" / "containers" / "requirements-lock.txt"
    text = path.read_text(encoding="utf-8")

    lines = text.splitlines()
    pins = [
        line for line in lines if "==" in line and not line.lstrip().startswith("#")
    ]
    hashes = [line for line in lines if "--hash=sha256:" in line]
    placeholder = [line for line in hashes if "sha256:" + "0" * 64 in line]

    if not pins:
        check.fail("no packages are pinned")
    for index, line in enumerate(lines):
        if "==" not in line or line.lstrip().startswith("#"):
            continue
        if not line.rstrip().endswith("\\"):
            check.fail(f"{line.split('==', 1)[0]} is missing a real continuation line")
            continue
        if index + 1 >= len(lines) or not re.fullmatch(
            r"\s+--hash=sha256:[0-9a-f]{64}", lines[index + 1]
        ):
            check.fail(f"{line.split('==', 1)[0]} has no valid continuation hash")
    if len(hashes) < len(pins):
        check.fail(
            f"{len(pins)} pinned packages but only {len(hashes)} hashes; pip "
            f"refuses a --require-hashes install where any package lacks one"
        )
    if placeholder:
        check.fail(f"{len(placeholder)} placeholder hash(es) remain")
    return check


def check_release_base_digest() -> Check:
    """The release image must name an immutable base image digest."""
    check = Check("release base image digest", "§10, §14")
    path = REPO_ROOT / "infrastructure" / "containers" / "Dockerfile"
    text = path.read_text(encoding="utf-8")
    if not re.search(
        r"^FROM [^\s:@]+/[^\s:@]+@sha256:[0-9a-f]{64}(?:\s+AS\s+\w+)?\s*$",
        text,
        re.MULTILINE,
    ):
        check.fail("release Dockerfile CUDA_IMAGE is not pinned by sha256 digest")
    return check


def check_worktree_clean() -> Check:
    """A release tag must identify exactly the reviewed tree."""
    check = Check("clean git worktree", "release integrity")
    git = shutil.which("git")
    if git is None:
        check.fail("git executable is unavailable")
        return check
    result = subprocess.run(  # noqa: S603 - executable is resolved above
        [
            git,
            "-C",
            str(REPO_ROOT),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        check.fail(f"git status failed with exit code {result.returncode}")
    elif result.stdout.strip():
        check.fail("working tree has modified or untracked files")
    return check


def check_provider_policy() -> Check:
    """CHARTER.md §7.4, §23: no named-provider testing before the review."""
    from gpu_seal.controller.policy_matrix import load_policy_matrix

    check = Check("provider policy matrix", "§7.4, §23")
    matrix = load_policy_matrix(REPO_ROOT / "docs" / "provider-policy-review")
    if len(matrix) == 0:
        check.fail(
            "no provider has a complete review record, so no provider data "
            "exists and none may be published. Not a blocker for releasing the "
            "tool; it is a blocker for releasing a measurement study."
        )
    return check


#: Real-world provider names that must never reach the publishable tree once
#: a provider enters the CHARTER.md §7.4 review pipeline (§7.6). This is
#: broader than .github/workflows/safety.yml's own PATTERN, which only ever
#: scanned probe/ and controller/ and covered a much shorter provider list —
#: a gap that let a real hyperscaler's name reach docs/provider-policy-review
#: and a findings note in cleartext while that job stayed green.
NAMED_PROVIDER_PATTERN = re.compile(
    r"\bAWS\b|Amazon Web Services|amazon\.com|"
    r"Lambda Labs|lambda\.ai|"
    r"Vast\.ai|"
    r"Scaleway|Exoscale|STACKIT|"
    r"CoreWeave|RunPod|Paperspace|Together\.ai|"
    r"Google Cloud|\bGCP\b|Microsoft Azure|Oracle Cloud|\bOCI\b|"
    r"\bEC2\b|\bg4dn\b",
    re.IGNORECASE,
)

#: Files reviewed by hand where a match is expected and not a leak: two
#: discuss the *candidate pool* of pilot providers in the abstract
#: (CHARTER.md §11's design-time menu, the prior-art survey of EU-sovereign
#: research) rather than asserting which pseudonym is which real provider;
#: two are this scanner's own pattern definition and the CI job's, which
#: must spell out what they block; one is this scanner's own test fixture,
#: which asserts a name is caught and so must contain one. Adding a file
#: here is a claim that every match inside it is non-identifying — re-check
#: on every edit.
NAMED_PROVIDER_ALLOWLIST = frozenset(
    {
        "CHARTER.md",
        "docs/prior-art.md",
        "lab/check-release-readiness.py",
        ".github/workflows/safety.yml",
        "tests/unit/test_release_gates.py",
    }
)


def check_no_named_providers() -> Check:
    """CHARTER.md §7.6: a provider is pseudonymous or it is not published.

    Scans every git-tracked file, not just probe/controller source, because
    the leak this guards against happened in docs/provider-policy-review/*.json
    and a docs/findings/*.md note — both outside the CI job's old scan scope.
    """
    check = Check("no named providers in publishable tree", "§7.6")
    git = shutil.which("git")
    if git is None:
        check.fail("git executable is unavailable")
        return check
    result = subprocess.run(  # noqa: S603 - executable resolved above
        [git, "-C", str(REPO_ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        check.fail(f"git ls-files failed with exit code {result.returncode}")
        return check

    for line in result.stdout.splitlines():
        rel = line.strip()
        if not rel or rel in NAMED_PROVIDER_ALLOWLIST:
            continue
        path = REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        match = NAMED_PROVIDER_PATTERN.search(text)
        if match:
            check.fail(
                f"{rel}: contains {match.group(0)!r} — a real provider name "
                f"in a tracked file. CHARTER.md §7.6 requires pseudonyms "
                f"(provider-a, provider-b, ...) everywhere outside "
                f"docs/provider-policy-review/private/, which is gitignored."
            )
    return check


def check_quarantined_bundles() -> Check:
    """Quarantined evidence must stay quarantined and stay explained."""
    check = Check("quarantined evidence", "§10")
    out = REPO_ROOT / "out"
    readme = out / "MISLABELLED-README.md"
    if not out.is_dir():
        return check
    if not readme.exists():
        check.fail(
            "out/ contains bundles but no MISLABELLED-README.md explaining "
            "which are quarantined and why"
        )
        return check

    named = readme.read_text(encoding="utf-8")
    for path in sorted(out.glob("*.result.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        probes = payload.get("probes", [])

        # A recovery under §9.3's name through a pooled allocator is the
        # original mislabelling.
        mislabelled = [
            p
            for p in probes
            if (p.get("driver_metadata") or {}).get("measurement_path")
            == "framework_pooled"
            and p.get("probe_name") != "framework_allocator_reuse"
        ]

        # And any recovery at all with no stated measurement path is
        # pre-ADR-003 evidence: it cannot be established whether the driver
        # ever had an opportunity to sanitise, so the record cannot be read as
        # either a control or a finding. The bundles that started this whole
        # problem are exactly this shape.
        unstated = [
            p
            for p in probes
            if p.get("owned_canary_match")
            and not (p.get("driver_metadata") or {}).get("measurement_path")
        ]

        if (mislabelled or unstated) and path.name not in named:
            reason = (
                "carries §9.4 records under another probe's name"
                if mislabelled
                else "shows canary recoveries with no measurement_path (pre-ADR-003)"
            )
            check.fail(
                f"{path.name} {reason} and is not listed in "
                f"MISLABELLED-README.md"
            )
    return check


def check_pre_registration() -> Check:
    """CHARTER.md §12: scoring pre-registered before named-provider results."""
    check = Check("measurement pre-registration", "§12, §19")
    path = REPO_ROOT / "docs" / "pre-registration.md"
    if not path.exists():
        check.fail("docs/pre-registration.md does not exist")
        return check
    text = path.read_text(encoding="utf-8")
    for required in ("§9.2", "expected negative", "Amendments"):
        if required.lower() not in text.lower():
            check.fail(f"pre-registration does not mention {required!r}")
    return check


def main() -> int:
    print()
    print("GPU-SEAL release readiness")
    print("=" * 62)
    print()

    checks = [
        check_citation(),
        check_lock_file(),
        check_release_base_digest(),
        check_worktree_clean(),
        check_provider_policy(),
        check_no_named_providers(),
        check_quarantined_bundles(),
        check_pre_registration(),
    ]

    for check in checks:
        marker = "x" if check.ok else " "
        print(f"  [{marker}] {check.name:<34} {check.clause}")
        for problem in check.problems:
            print(f"        - {problem}")

    blocking = [c for c in checks if not c.ok]
    print()
    if blocking:
        print(f"NOT RELEASABLE — {len(blocking)} check(s) failed.")
        print()
        return 1
    print("RELEASABLE.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
