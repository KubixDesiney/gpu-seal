#!/usr/bin/env python3
"""Release gate — the things that must be true before GPU-SEAL goes public.

    python lab/check-release-readiness.py

For a built release, also pass ``--wheel <wheel> --dashboard-dist
dashboard/dist/client`` to inspect the actual packaged artifacts.

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

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
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
    check = Check("CITATION.cff author metadata", "section 21, section 23")
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
    check = Check("container lock file", "section 10, section 14")
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
    check = Check("release base image digest", "section 10, section 14")
    path = REPO_ROOT / "infrastructure" / "containers" / "Dockerfile"
    text = path.read_text(encoding="utf-8")
    if not re.search(
        r"^FROM [^\s:@]+/[^\s:@]+@sha256:[0-9a-f]{64}(?:\s+AS\s+\w+)?\s*$",
        text,
        re.MULTILINE,
    ):
        check.fail("release Dockerfile CUDA_IMAGE is not pinned by sha256 digest")
    return check


def check_container_registers_package_metadata() -> Check:
    """The pinned image must install gpu-seal before it runs its own tests.

    tests/unit/test_version.py asserts gpu_seal.__version__ tracks
    importlib.metadata.version("gpu-seal"). The Dockerfile deliberately never
    runs an editable install (old setuptools on Ubuntu 22.04 mishandles PEP
    621 metadata -- see the comment above its WORKDIR), so the only thing
    that can make that lookup succeed inside the image is a plain, non-
    editable `pip install --no-deps .` of the already-copied source, run
    before anything that invokes pytest. Without it, every test that touches
    __version__ fails with PackageNotFoundError and the build never reaches
    GHCR -- exactly what shipped to main in 322b094 and was only caught by
    the (slow, 3-minute) native-container docker build, after the push had
    already landed (fixed in 530f769).
    """
    check = Check(
        "container registers gpu-seal's dist-info", "CI: importlib.metadata resolution"
    )
    path = REPO_ROOT / "infrastructure" / "containers" / "Dockerfile"
    lines = path.read_text(encoding="utf-8").splitlines()

    def first_index(pattern: str) -> int | None:
        regex = re.compile(pattern)
        for index, line in enumerate(lines):
            if regex.search(line):
                return index
        return None

    # Anchored on RUN/COPY instructions only -- several comments in this
    # Dockerfile (accurately) mention check-native-conformance.py and
    # `pytest tests` ahead of where either instruction actually appears.
    copy_source_index = first_index(r"^COPY probe/ ")
    install_index = first_index(r"^RUN\b.*pip install\b(?!.*-e\b).*--no-deps\b")
    test_run_index = first_index(
        r"^\s*(RUN\b|&&)[^#]*(check-native-conformance\.py|pytest tests)"
    )

    if copy_source_index is None:
        check.fail("Dockerfile no longer copies probe/ into the image")
        return check
    if install_index is None:
        check.fail(
            'no non-editable `pip install --no-deps .` step registers '
            "gpu-seal's dist-info; importlib.metadata.version(\"gpu-seal\") "
            "will raise PackageNotFoundError for every caller inside the "
            "image, including tests/unit/test_version.py"
        )
        return check
    if install_index < copy_source_index:
        check.fail("the pip install step runs before the source is copied in")
    if test_run_index is not None and test_run_index < install_index:
        check.fail(
            "the image runs its test suite before installing gpu-seal's own "
            "dist-info metadata"
        )
    return check


def check_github_action_pins() -> Check:
    """Reject mutable GitHub Action references in workflow files."""
    check = Check("GitHub Action commit pins", "CI supply-chain integrity")
    workflow_root = REPO_ROOT / ".github" / "workflows"
    if not workflow_root.is_dir():
        check.fail(f"workflow directory does not exist: {workflow_root}")
        return check

    uses_pattern = re.compile(r"^\s*-\s*uses:\s*([^\s#]+)")
    sha_pattern = re.compile(r"^[0-9a-f]{40}$")
    for path in sorted(workflow_root.glob("*.y*ml")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            match = uses_pattern.match(line)
            if match is None:
                continue
            reference = match.group(1)
            if "@" not in reference:
                check.fail(f"{path.relative_to(REPO_ROOT)}:{line_number} has no ref")
                continue
            ref = reference.rsplit("@", 1)[1]
            if not sha_pattern.fullmatch(ref):
                check.fail(
                    f"{path.relative_to(REPO_ROOT)}:{line_number} uses mutable "
                    f"GitHub Action reference {reference!r}; pin a full commit SHA"
                )
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

    check = Check("provider policy matrix", "section 7.4, section 23")
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


def _files_for_name_scan() -> list[str]:
    """Return publishable-tree paths, with a source-archive fallback.

    Release checks run both from a Git checkout and inside the pinned image.
    The image deliberately does not contain ``.git``, so a check that only
    knows how to call ``git ls-files`` would make the container unable to run
    its own conformance suite.
    """
    git = shutil.which("git")
    if git is not None:
        result = subprocess.run(  # noqa: S603 - git resolved above
            [git, "-C", str(REPO_ROOT), "ls-files"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    ignored_parts = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "node_modules",
    }
    private_review_prefix = "docs/provider-policy-review/private/"
    return [
        path.relative_to(REPO_ROOT).as_posix()
        for path in REPO_ROOT.rglob("*")
        if path.is_file()
        and not ignored_parts.intersection(path.parts)
        and not path.relative_to(REPO_ROOT).as_posix().startswith(
            private_review_prefix
        )
    ]


def check_no_named_providers() -> Check:
    """CHARTER.md §7.6: a provider is pseudonymous or it is not published.

    Scans every git-tracked file, not just probe/controller source, because
    the leak this guards against happened in docs/provider-policy-review/*.json
    and a docs/findings/*.md note — both outside the CI job's old scan scope.
    """
    check = Check("no named providers in publishable tree", "section 7.6")
    for rel in _files_for_name_scan():
        if rel in NAMED_PROVIDER_ALLOWLIST:
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
    check = Check("quarantined evidence", "section 10")
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
    check = Check("measurement pre-registration", "section 12, section 19")
    path = REPO_ROOT / "docs" / "pre-registration.md"
    if not path.exists():
        check.fail("docs/pre-registration.md does not exist")
        return check
    text = path.read_text(encoding="utf-8")
    for required in ("§9.2", "expected negative", "Amendments"):
        if required.lower() not in text.lower():
            check.fail(f"pre-registration does not mention {required!r}")
    return check


def check_wheel_contents(wheel: Path) -> Check:
    """A release wheel must contain the runtime resources it advertises."""
    check = Check("built wheel contents", "packaging integrity")
    if not wheel.is_file():
        check.fail(f"wheel does not exist: {wheel}")
        return check

    expected = {
        "gpu_seal/cli.py",
        "gpu_seal/schemas/experiment.schema.json",
        "gpu_seal/schemas/provider-policy.schema.json",
        "gpu_seal/schemas/report-card.schema.json",
        "gpu_seal/schemas/result.schema.json",
    }
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        check.fail(f"could not inspect wheel {wheel}: {exc}")
        return check

    missing = sorted(expected - names)
    if missing:
        check.fail("wheel is missing: " + ", ".join(missing))
    return check


def check_dashboard_assets(dist_client: Path) -> Check:
    """A production dashboard artifact must have manifest-backed static assets."""
    check = Check("dashboard production assets", "release artifact integrity")
    manifest_path = dist_client / ".vite" / "manifest.json"
    if not manifest_path.is_file():
        check.fail(f"dashboard manifest does not exist: {manifest_path}")
        return check

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        check.fail(f"could not read dashboard manifest: {exc}")
        return check
    if not isinstance(manifest, dict):
        check.fail("dashboard manifest must contain a JSON object")
        return check

    asset_paths: set[str] = set()
    for record in manifest.values():
        if not isinstance(record, dict):
            continue
        for key in ("file", "css"):
            values = record.get(key, [])
            if isinstance(values, str):
                values = [values]
            if isinstance(values, list):
                asset_paths.update(value for value in values if isinstance(value, str))

    if not any(dist_client.rglob("*.css")):
        check.fail("dashboard production artifact contains no CSS asset")
    if not any(dist_client.rglob("*.js")):
        check.fail("dashboard production artifact contains no JavaScript asset")
    for relative in sorted(asset_paths):
        if not (dist_client / relative).is_file():
            check.fail(f"dashboard manifest references missing asset: {relative}")
    return check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, help="built wheel to inspect")
    parser.add_argument(
        "--dashboard-dist",
        type=Path,
        help="dashboard dist/client directory to inspect",
    )
    args = parser.parse_args(argv)

    print()
    print("GPU-SEAL release readiness")
    print("=" * 62)
    print()

    checks = [
        check_citation(),
        check_lock_file(),
        check_release_base_digest(),
        check_container_registers_package_metadata(),
        check_github_action_pins(),
        check_worktree_clean(),
        check_provider_policy(),
        check_no_named_providers(),
        check_quarantined_bundles(),
        check_pre_registration(),
    ]
    if args.wheel is not None:
        checks.append(check_wheel_contents(args.wheel))
    if args.dashboard_dist is not None:
        checks.append(check_dashboard_assets(args.dashboard_dist))

    for check in checks:
        marker = "x" if check.ok else " "
        print(f"  [{marker}] {check.name:<34} {check.clause}")
        for problem in check.problems:
            print(f"        - {problem}")

    blocking = [c for c in checks if not c.ok]
    print()
    if blocking:
        print(f"NOT RELEASABLE - {len(blocking)} check(s) failed.")
        print()
        return 1
    print("RELEASABLE.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
