#!/usr/bin/env python3
"""§9.4 Memory Probe C battery — the detection-capability control.

    python3 lab/local-runner/run_framework_allocator.py

Finding 001 (docs/findings/2026-07-31-rtx3050-baseline.md) established that
§9.3's positive control fails on the RTX 3050: the driver zeroes memory on
free, so §9.3 can never supply its own positive control on this platform.
CHARTER.md §11 is explicit that a negative result without a working positive
control proves nothing -- so this script exists to supply one that does not
depend on the driver at all.

It runs FrameworkAllocatorProbe against PooledCupyBackend: allocate through a
private cupy.cuda.MemoryPool, plant a canary, free (which returns the block
to the pool, NOT to the driver), reallocate, read before writing. A recovered
canary here proves the harness can detect a marker it planted -- independent
of whatever the driver does on this or any other platform.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "probe"))

from gpu_seal.cuda import BackendUnavailable, PooledCupyBackend, SimulatedBackend  # noqa: E402
from gpu_seal.probes import FrameworkAllocatorProbe  # noqa: E402
from gpu_seal.probes.framework_allocator import summarise  # noqa: E402
from gpu_seal.safety import CanarySet  # noqa: E402

MIB = 1 << 20


def banner(text: str) -> None:
    print()
    print(text)
    print("-" * len(text))


def main() -> int:
    ap = argparse.ArgumentParser(description="GPU-SEAL §9.4 framework allocator battery")
    ap.add_argument("--size-mib", type=int, default=64)
    ap.add_argument("--cycles", type=int, default=10)
    ap.add_argument("--simulate", action="store_true",
                     help="force the simulated backend even if a GPU exists")
    args = ap.parse_args()
    size = args.size_mib * MIB

    print()
    print("GPU-SEAL §9.4 framework allocator battery")
    print("=" * 62)

    is_real = False
    if args.simulate:
        backend = SimulatedBackend(sanitises_on_free=False, pool_bytes=256 * MIB)
    else:
        try:
            backend = PooledCupyBackend()
            is_real = True
        except BackendUnavailable as exc:
            print(f"  no CUDA device: {exc}")
            print("  Re-run with --simulate to exercise the script itself.")
            return 2

    info = backend.device_info()
    print(f"  backend      {info['backend']} (real={info['backend_is_real']})")
    if is_real:
        print(
            f"  device       {info.get('device_name')} "
            f"cc{info.get('compute_capability')}"
        )
        print(
            f"  allocator    {info.get('allocator')} "
            f"(cupy {info.get('framework_version')})"
        )
    print(f"  test size    {args.size_mib} MiB, {args.cycles} cycles")

    canaries = CanarySet.create()
    probe = FrameworkAllocatorProbe(
        backend, canaries, canary_stride=4 * MIB, shared_infrastructure=False
    )

    banner("Pooled reuse: allocate -> plant -> free -> reallocate -> read")
    print("  free() here returns the block to the pool, never to the driver.")
    cycles = probe.run_cycles(size, args.cycles)
    stats = summarise(cycles)

    print(f"  usable cycles      {stats['cycles_usable']}/{stats['cycles_attempted']}")
    print(f"  buffer reuse rate  {stats['buffer_reuse_rate']}")
    print(f"  canary recovered   {stats['canary_recovered_cycles']}")
    print(f"  recovery rate      {stats['recovery_rate']}")
    if stats["exclusion_reasons"]:
        print(f"  exclusions         {stats['exclusion_reasons']}")

    detects = bool(stats["cycles_usable"]) and stats["canary_recovered_cycles"] > 0

    banner("Interpretation")
    if detects:
        print("  PASS: the harness can detect a canary the caching allocator")
        print("  handed back. This is the detection-capability control")
        print("  CHARTER.md §11 requires -- it says nothing about the driver")
        print("  or any provider, only that GPU-SEAL is not blind.")
    else:
        print("  FAIL: no canary recovered through the pool. Either the pool")
        print("  is not actually reusing blocks (check buffer_reuse_rate")
        print("  above) or something in the probe's write/read path is")
        print("  broken -- run lab/local-runner/instrument_check.py first.")

    print()
    if not is_real:
        print("  NOTE: simulated backend. This exercises probe logic only.")
    print("  RESULT:", "PASS" if detects else "FAIL")
    print()

    try:
        backend.close()
    except Exception:  # noqa: BLE001
        pass
    return 0 if detects else 1


if __name__ == "__main__":
    raise SystemExit(main())
