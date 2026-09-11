#!/usr/bin/env python3
"""Cross-language conformance gate for the native canary implementation.

The native binary is supplied explicitly because the Windows development
machine does not carry nvcc. The pinned CUDA image builds it and runs this
check before the image is considered usable.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import subprocess
import sys
from pathlib import Path


KEY = bytes.fromhex(
    "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
)
EXPERIMENT = bytes.fromhex("00112233445566778899aabbccddeeff")
ALLOCATION = bytes.fromhex("ffeeddccbbaa99887766554433221100")
NONCE = bytes.fromhex(
    "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
)


def expected_blob() -> str:
    header = (
        b"GPUSEALC"
        + struct.pack("<HHI", 1, 2, 0)
        + EXPERIMENT
        + ALLOCATION
        + NONCE
        + b"\x00" * 16
    )
    return (header + hashlib.blake2b(header, digest_size=32, key=KEY).digest()).hex()


def run(binary: Path, *args: str) -> dict[str, str]:
    completed = subprocess.run(  # noqa: S603 - explicit build artifact
        [str(binary), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    values: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def safety(binary: Path, *, zero_fraction: str, entropy: str, owned: str,
           buffer_size: str, expect_zeroed: str, shared: str) -> dict[str, str]:
    return run(
        binary,
        "--safety-check",
        "--zero-fraction",
        zero_fraction,
        "--entropy",
        entropy,
        "--owned-match",
        owned,
        "--buffer-size",
        buffer_size,
        "--expect-zeroed",
        expect_zeroed,
        "--shared-infrastructure",
        shared,
    )


def expected_safety_stop(
    *,
    zero_fraction: float,
    entropy: float,
    owned: bool,
    buffer_size: int,
    expect_zeroed: bool,
    shared: bool,
) -> bool:
    """Reference implementation of the span-aware safety gate.

    The CLI vector does not provide authenticated span ranges, so an owned
    canary flag cannot bless the complete allocation. This deliberately models
    the fail-closed whole-buffer case used by the mutation battery.
    """
    return (
        (expect_zeroed and zero_fraction < 0.99)
        or (shared and entropy > 0.85)
        or (shared and buffer_size < 256)
    )


def check_safety_vectors(binary: Path) -> int:
    """Exercise every boundary of the native safety-stop contract."""
    cases = [
        (1.0, 0.0, False, 256, False, True),
        (0.989999, 0.0, False, 256, True, False),
        (0.989999, 0.0, False, 256, True, True),
        (1.0, 0.850001, False, 256, False, True),
        (1.0, 0.85, False, 256, False, True),
        (1.0, 0.0, False, 255, False, True),
        (1.0, 0.99, False, 255, False, False),
        (0.0, 1.0, True, 1, True, True),
        (0.0, 1.0, False, 255, True, True),
        (0.99, 0.85, False, 256, True, True),
    ]
    for zero, entropy, owned, size, expect_zeroed, shared in cases:
        result = safety(
            binary,
            zero_fraction=str(zero),
            entropy=str(entropy),
            owned=str(owned).lower(),
            buffer_size=str(size),
            expect_zeroed=str(expect_zeroed).lower(),
            shared=str(shared).lower(),
        )
        expected = expected_safety_stop(
            zero_fraction=zero,
            entropy=entropy,
            owned=owned,
            buffer_size=size,
            expect_zeroed=expect_zeroed,
            shared=shared,
        )
        actual = result.get("sensitive_observation") == "true"
        if actual != expected:
            raise SystemExit(
                "native safety vector mismatch: "
                f"zero={zero} entropy={entropy} owned={owned} size={size} "
                f"expect_zeroed={expect_zeroed} shared={shared}"
            )
    return len(cases)


def run_full_python_suite() -> None:
    """Run the complete Python contract in the same image as the binary."""
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "Python conformance suite failed:\n"
            + (completed.stdout + completed.stderr)[-4000:]
        )
    summary = next(
        (
            line.strip()
            for line in reversed(completed.stdout.splitlines())
            if line.strip()
        ),
        "pytest completed",
    )
    print(f"Python safety contract: PASS ({summary})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument(
        "--full-suite",
        action="store_true",
        help="also run the complete Python test suite in this image",
    )
    args = parser.parse_args()
    binary = args.binary
    if not binary.is_file():
        raise SystemExit(f"native binary not found: {binary}")

    common = [
        "--key",
        KEY.hex(),
        "--experiment",
        EXPERIMENT.hex(),
        "--allocation",
        ALLOCATION.hex(),
        "--boundary",
        "2",
        "--flags",
        "0",
        "--nonce",
        NONCE.hex(),
    ]
    minted = run(binary, "--mint", *common)
    blob = minted.get("blob_hex")
    if blob != expected_blob():
        raise SystemExit("native canary does not match Python ADR-002 vector")

    auth_args = [
        "--authenticate",
        "--key",
        KEY.hex(),
        "--experiment",
        EXPERIMENT.hex(),
        "--blob",
        blob,
    ]
    if run(binary, *auth_args).get("owned") != "true":
        raise SystemExit("native rejected its own authenticated canary")

    mutated = blob[:-2] + ("00" if blob[-2:] != "00" else "ff")
    if run(binary, *auth_args[:-1], mutated).get("owned") != "false":
        raise SystemExit("native accepted a mutated canary")

    if run(binary, "--sha256", "--input", "616263").get("sha256") != (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    ):
        raise SystemExit("native SHA-256 does not match the reference vector")

    vector_count = check_safety_vectors(binary)
    print(f"native canary and safety conformance: PASS ({vector_count} vectors)")
    if args.full_suite:
        run_full_python_suite()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
