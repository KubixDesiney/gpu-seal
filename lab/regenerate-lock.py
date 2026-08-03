#!/usr/bin/env python3
"""Regenerate the hash-pinned container lock file — CHARTER.md §10, §14.

    python3 -m pip install --dry-run --ignore-installed --only-binary=:all: \\
        --platform manylinux2014_x86_64 --python-version 3.11 \\
        --target /tmp/resolve --report /tmp/report.json \\
        "cryptography>=42" "numpy>=1.24,<3" "jsonschema>=4" "pytest>=8" \\
        "cupy-cuda12x>=13"
    python3 lab/regenerate-lock.py /tmp/report.json

Reads pip's own resolver report and writes `--require-hashes`-compatible
pins for the **whole transitive closure**. Transitivity matters: pip refuses a
`--require-hashes` install where any package lacks a hash, so a lock file
listing only the direct dependencies fails the build rather than securing it.

`pip-tools` is the documented tool for this and is the better answer where it
works. It does not work against every pip version — on the machine this was
written for it fails importing `stdlib_pkgs` from a pip internal that moved —
and a supply-chain control that only functions on one pip release is not much
of a control. Pip's `--report` is a stable public interface and needs nothing
installed.

**The platform flags are not optional.** Without them the resolver picks
wheels for the machine you are standing at, and the resulting hashes fail
inside a Linux image in a way that reads as tampering rather than as a
platform mismatch.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

DEFAULT_OUTPUT = Path("infrastructure/containers/requirements-lock.txt")

HEADER = """# GPU-SEAL pinned dependencies — CHARTER.md §10, §14.
#
# Installed with `pip install --require-hashes`, which refuses any artifact
# whose hash does not match. Pinned versions alone still trust the index to
# serve the same bytes; hashes do not.
#
# Resolved for the CONTAINER TARGET, not for the machine that generated this:
#
#   --platform {platform}   --python-version {python_version}   --only-binary=:all:
#
# so the hashes are for the Linux wheels the image actually installs. A lock
# file generated on a developer workstation without those flags pins Windows
# or macOS wheels; the build then fails looking like a hash mismatch when it
# is really a platform mismatch.
#
# One hash per package, because --only-binary resolves exactly one wheel per
# package for this platform. Building for a different platform requires
# regenerating, which is the intended behaviour: the image is reproducible for
# its own target, not universally.
#
# REGENERATE: see lab/regenerate-lock.py
#
# Generated {today} · {count} packages, transitive closure included.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", type=Path, help="pip --report JSON output")
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--platform", default="manylinux2014_x86_64")
    ap.add_argument("--python-version", default="3.11")
    args = ap.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))

    entries: list[tuple[str, str, str]] = []
    missing: list[str] = []
    for item in report.get("install", []):
        meta = item["metadata"]
        hashes = (item.get("download_info", {}).get("archive_info") or {}).get(
            "hashes", {}
        )
        digest = hashes.get("sha256")
        if not digest:
            missing.append(meta["name"])
            continue
        entries.append((meta["name"].lower(), meta["version"], digest))

    if missing:
        print(
            f"error: no sha256 for {sorted(missing)}. A lock file with a gap in "
            f"it fails the --require-hashes install for every package, so this "
            f"refuses to write rather than producing something that half works.",
            file=sys.stderr,
        )
        return 1

    if not entries:
        print("error: the report contained no packages to pin.", file=sys.stderr)
        return 1

    entries.sort()
    body = [
        HEADER.format(
            platform=args.platform,
            python_version=args.python_version,
            today=datetime.date.today().isoformat(),
            count=len(entries),
        )
    ]
    for name, version, digest in entries:
        body.append(f"{name}=={version} \\\n    --hash=sha256:{digest}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(body) + "\n", encoding="utf-8")

    print(f"wrote {args.output} with {len(entries)} pinned packages")
    for name, version, _ in entries:
        print(f"  {name}=={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
