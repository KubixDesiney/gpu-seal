#!/usr/bin/env python3
"""Instrument check — is the probe actually able to see anything?

    python3 lab/local-runner/instrument_check.py

The Phase 1 battery on the RTX 3050 returned zero_fraction == 1.000000 on
40 of 40 measurements and recovered no canaries. Two explanations produce that
identical result:

    (A) the driver/OS zeroes device memory, so there is genuinely nothing to
        find — a real and interesting finding;

    (B) the probe's host-to-device write silently does nothing, so we planted
        no canary, found no canary, and learned nothing.

Until (B) is excluded, the run means nothing at all. This script excludes it.

It is deliberately not a probe: it plants only our own markers, reads only
our own allocations, and reports pass/fail on the instrument rather than on
any provider. Think of it as calibrating the scale before weighing anything.

Checks, in order of what they rule out:

    1. memset      fill_device(0xAB) -> is the buffer 0xAB?
                   Rules out: device writes not landing at all.
    2. write/read  plant a canary, read back WITHOUT freeing.
                   Rules out: (B). This is the decisive one.
    3. free/realloc  plant, free, realloc, read.
                   The Phase 1 positive control, isolated.
    4. pressure    repeat (3) using most of VRAM, so the allocator has no
                   spare pages and MUST hand ours back.
                   Rules out: "we simply got different physical pages."
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "probe"))

from gpu_seal.cuda import BackendUnavailable, CupyBackend, SimulatedBackend  # noqa: E402
from gpu_seal.probes import GlobalMemoryProbe  # noqa: E402
from gpu_seal.safety import Boundary, CanarySet, SafeBuffer, aggregate  # noqa: E402

MIB = 1 << 20
results: dict[str, bool | None] = {}


def hr(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def verdict(key: str, ok: bool, msg: str) -> None:
    results[key] = ok
    print(f"  -> {'PASS' if ok else 'FAIL'}: {msg}")


def measure(probe, backend, alloc, canaries, label):
    """Read an allocation through the safe layer and return the record."""
    return probe.read_before_write(alloc, boundary=Boundary.UNSPECIFIED)


def main() -> int:
    ap = argparse.ArgumentParser(description="GPU-SEAL instrument check")
    ap.add_argument("--size-mib", type=int, default=64)
    ap.add_argument("--simulate", action="store_true")
    ap.add_argument("--skip-pressure", action="store_true",
                    help="skip check 4 (allocates most of VRAM)")
    args = ap.parse_args()
    size = args.size_mib * MIB

    print()
    print("GPU-SEAL instrument check")
    print("=" * 62)

    if args.simulate:
        backend = SimulatedBackend(sanitises_on_free=False, pool_bytes=256 * MIB)
        is_real = False
    else:
        try:
            backend = CupyBackend()
            is_real = True
        except BackendUnavailable as exc:
            print(f"  no CUDA device: {exc}")
            print("  Re-run with --simulate to exercise the script itself.")
            return 2

    info = backend.device_info()
    print(f"  backend      {info['backend']} (real={info['backend_is_real']})")
    if is_real:
        total = int(info.get("total_memory_bytes", 0))
        print(f"  device       {info.get('device_name')} cc{info.get('compute_capability')}")
        print(f"  vram         {total / 2**30:.2f} GiB")
        print(f"  cuda rt/drv  {info.get('cuda_runtime_version')} / {info.get('cuda_driver_version')}")
    print(f"  test size    {args.size_mib} MiB")

    canaries = CanarySet.create()
    probe = GlobalMemoryProbe(
        backend, canaries, canary_stride=4 * MIB, shared_infrastructure=False
    )

    # ------------------------------------------------------------------
    # 1. Do device writes land at all?
    # ------------------------------------------------------------------
    hr("1. memset — do device writes land?")
    print("   fill_device(0xAB), then read back. If the histogram is not all")
    print("   0xAB, nothing this project does is trustworthy.")
    alloc = backend.malloc(size)
    try:
        backend.fill_device(alloc, 0xAB)
        rec = probe.read_before_write(alloc, boundary=Boundary.UNSPECIFIED)
        hist = rec.byte_histogram
        ab = hist[0xAB]
        others = sum(v for i, v in enumerate(hist) if i != 0xAB)
        print(f"   bytes == 0xAB   {ab:,} / {rec.buffer_size_bytes:,}")
        print(f"   other bytes     {others:,}")
        verdict("memset", others == 0 and ab == rec.buffer_size_bytes,
                "device writes land and are readable"
                if others == 0 else "device writes are NOT landing correctly")
    finally:
        backend.free(alloc)

    # ------------------------------------------------------------------
    # 2. THE DECISIVE CHECK — canary write/read with no free in between
    # ------------------------------------------------------------------
    hr("2. write/read — can we find a canary we just planted?")
    print("   Plant owned canaries, read back WITHOUT freeing. There is no")
    print("   allocator or driver behaviour in the way here: if this fails,")
    print("   the probe is blind and the Phase 1 zeros mean nothing.")
    alloc = backend.malloc(size)
    try:
        planted, offsets = probe.plant_canaries(alloc, Boundary.UNSPECIFIED)
        rec = probe.read_before_write(alloc, boundary=Boundary.UNSPECIFIED)
        print(f"   canaries planted {len(planted)} at offsets {offsets[:4]}"
              f"{' ...' if len(offsets) > 4 else ''}")
        print(f"   exact matches    {rec.owned_canary_exact_matches}")
        print(f"   longest prefix   {rec.owned_canary_longest_prefix}/128 bytes")
        print(f"   zero fraction    {rec.zero_fraction:.6f}")
        verdict("write_read", rec.owned_canary_match,
                "the probe CAN see its own markers — instrument is sound"
                if rec.owned_canary_match else
                "the probe CANNOT see markers it just wrote — INSTRUMENT BROKEN")
    finally:
        backend.free(alloc)

    # ------------------------------------------------------------------
    # 3. The Phase 1 positive control, isolated
    # ------------------------------------------------------------------
    hr("3. free/realloc — does a canary survive the allocator?")
    print("   This is the Phase 1 positive control on its own.")
    cycle = probe.same_process_reuse_cycle(size)
    if cycle.usable:
        print(f"   canaries planted {cycle.canaries_planted}")
        print(f"   exact matches    {cycle.observation.owned_canary_exact_matches}")
        print(f"   zero fraction    {cycle.observation.zero_fraction:.6f}")
    else:
        print(f"   cycle excluded: {cycle.error_code}")
    results["free_realloc"] = cycle.canary_recovered
    print(f"   -> canary {'RECOVERED' if cycle.canary_recovered else 'not recovered'}")

    # ------------------------------------------------------------------
    # 4. Pressure — remove the "we got different pages" explanation
    # ------------------------------------------------------------------
    if args.skip_pressure or not is_real:
        results["pressure"] = None
        hr("4. pressure — SKIPPED")
    else:
        hr("4. pressure — force the allocator to reuse our pages")
        print("   With 64 MiB on a multi-GiB card the allocator has plenty of")
        print("   spare pages and may simply hand back different ones. Fill")
        print("   most of VRAM so it has no choice but to reuse ours.")
        total = int(info.get("total_memory_bytes", 0))
        chunk = 256 * MIB
        target = int(total * 0.70)
        held = []
        try:
            while sum(a.size for a in held) + chunk <= target:
                try:
                    held.append(backend.malloc(chunk))
                except Exception:  # noqa: BLE001 - out of memory is the goal
                    break
            filled = sum(a.size for a in held)
            print(f"   held             {filled / 2**30:.2f} GiB in {len(held)} blocks")

            for a in held:
                probe.plant_canaries(a, Boundary.SEQUENTIAL_ALLOCATION)
            print(f"   planted markers across all held blocks")

            for a in held:
                backend.free(a)
            held.clear()
            print("   freed everything, reallocating...")

            probe2 = GlobalMemoryProbe(
                backend, canaries, canary_stride=4 * MIB,
                shared_infrastructure=False,
            )
            re_alloc = backend.malloc(chunk)
            try:
                rec = probe2.read_before_write(
                    re_alloc, boundary=Boundary.SEQUENTIAL_ALLOCATION
                )
                print(f"   exact matches    {rec.owned_canary_exact_matches}")
                print(f"   longest prefix   {rec.owned_canary_longest_prefix}/128")
                print(f"   zero fraction    {rec.zero_fraction:.6f}")
                results["pressure"] = rec.owned_canary_match
                print(f"   -> canary {'RECOVERED' if rec.owned_canary_match else 'not recovered'}")
            finally:
                backend.free(re_alloc)
        finally:
            for a in held:
                try:
                    backend.free(a)
                except Exception:  # noqa: BLE001
                    pass

    # ------------------------------------------------------------------
    hr("Interpretation")
    ok_write = results.get("memset") and results.get("write_read")
    if not ok_write:
        print("  The instrument is BROKEN. Device writes are not landing or")
        print("  are not readable. Every Phase 1 result to date is void — not")
        print("  wrong, void. Fix the backend before drawing any conclusion")
        print("  about driver behaviour.")
        rc = 1
    elif results.get("free_realloc") or results.get("pressure"):
        print("  The instrument works AND residue is detectable on this device.")
        print("  The Phase 1 positive control should pass; if it did not,")
        print("  investigate the difference between the two code paths.")
        rc = 0
    else:
        print("  The instrument works: the probe can see markers it planted.")
        print("  It found nothing after free/realloc because there was nothing")
        print("  to find — this device returned zeroed memory.")
        print()
        print("  That is a real observation, not a failure. But note what it")
        print("  costs: this platform cannot serve as a positive control, so")
        print("  a clean result from a PROVIDER measured the same way would")
        print("  be uninterpretable. A detection-capability control that does")
        print("  not depend on driver behaviour is now required before any")
        print("  cloud testing (CHARTER.md §11).")
        rc = 0

    print()
    for k, v in results.items():
        mark = "?" if v is None else ("x" if v else " ")
        print(f"  [{mark}] {k}")
    print()

    try:
        backend.close()
    except Exception:  # noqa: BLE001
        pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
