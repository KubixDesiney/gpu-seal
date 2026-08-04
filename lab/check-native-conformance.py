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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    binary = parser.parse_args().binary
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

    flagged = safety(
        binary,
        zero_fraction="0.1",
        entropy="0.9",
        owned="false",
        buffer_size="1024",
        expect_zeroed="false",
        shared="true",
    )
    if flagged.get("sensitive_observation") != "true":
        raise SystemExit("native safety stop did not fire for high-information data")

    owned = safety(
        binary,
        zero_fraction="0.1",
        entropy="0.9",
        owned="true",
        buffer_size="1024",
        expect_zeroed="true",
        shared="true",
    )
    if owned.get("sensitive_observation") != "false":
        raise SystemExit("native safety stop did not honor an owned canary match")

    print("native canary conformance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
