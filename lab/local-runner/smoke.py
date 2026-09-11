#!/usr/bin/env python3
"""Is this machine able to run GPU-SEAL, and against what?

Run first, before anything else:

    python3 lab/local-runner/smoke.py

Reports what backend is available and what it can and cannot measure. Exits
non-zero only if GPU-SEAL itself is broken — a missing GPU is reported, not
treated as an error, because the simulated backend is a legitimate way to
exercise probe logic.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "probe"))

from gpu_seal import __version__  # noqa: E402
from gpu_seal.cuda import (  # noqa: E402
    BackendUnavailable,
    CupyBackend,
    SimulatedBackend,
    describe_available,
)


def line(label: str, value: object) -> None:
    print(f"  {label:<28} {value}")


def main() -> int:
    print()
    print("GPU-SEAL smoke check")
    print("=" * 62)

    print("\nHost")
    line("gpu-seal version", __version__)
    line("python", platform.python_version())
    line("platform", platform.platform())
    line(
        "container profile",
        os.environ.get("GPU_SEAL_CONTAINER_PROFILE", "none (bare metal)"),
    )

    prov = Path("/etc/gpu-seal/provenance")
    if prov.exists():
        print("\nContainer provenance")
        for row in prov.read_text().strip().splitlines():
            if "=" in row:
                k, v = row.split("=", 1)
                line(k, v)

    print("\nCUDA")
    for k, v in describe_available().items():
        line(k, v)

    print("\nBackend")
    backend = None
    try:
        backend = CupyBackend()
        line("selected", "CupyBackend (real device)")
        for k, v in backend.device_info().items():
            line(f"  {k}", v)
    except BackendUnavailable as exc:
        line("selected", "SimulatedBackend (NO GPU)")
        line("reason", str(exc).split(".")[0])
        backend = SimulatedBackend()
        print()
        print("  Probe logic can be exercised, but nothing measured here is")
        print("  evidence. Results will be stamped backend_is_real=false and")
        print("  cannot be cleared for publication.")

    print("\nWhat this machine can measure")
    real = getattr(backend, "is_real", False)
    caps = [
        ("§9.3  global VRAM read-before-write", real),
        ("§9.3  same-process allocator reuse", real),
        ("§9.1  environment inventory", True),
        ("§9.6  device & namespace exposure", real),
        ("§9.8  topology fingerprint", real),
        ("§9.12 MIG temporal isolation", False),
        ("§9.10 confidential-computing attestation", False),
        ("§9.8b same-model die separation", False),
    ]
    for name, ok in caps:
        print(f"  [{'x' if ok else ' '}] {name}")

    if not real:
        print("\n  Unchecked items above need a real GPU.")
    else:
        print("\n  MIG, CC attestation, and same-model separation need rented")
        print("  A100/H100-class hardware — see CHARTER.md §20.")

    try:
        backend.close()
    except Exception:  # noqa: BLE001
        pass

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
