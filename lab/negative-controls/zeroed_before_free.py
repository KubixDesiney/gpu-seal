#!/usr/bin/env python3
"""Negative control: explicit zeroisation must defeat recovery. CHARTER.md §11, §19.

    python3 lab/negative-controls/zeroed_before_free.py

The positive control in ``lab/positive-controls/uninitialised_read.py`` shows
GPU-SEAL's harness *can* detect a surviving canary. That result is only
meaningful paired with this one: the same allocate -> plant -> free ->
reallocate -> read-before-write cycle, except the allocation is explicitly
memset to zero before it is freed. The canary must NOT come back.

    "Without positive controls you cannot prove a negative cloud result means
     the probe could detect a leak." -- CHARTER.md §11

The mirror image is just as load-bearing: if this script ever recovers a
canary, GPU-SEAL is reporting false positives and every other result --
positive or negative, local or cloud -- is void until that is understood
(CHARTER.md §19, and ``GlobalMemoryProbe.zeroed_reuse_cycle``, which this
reproduces independently of the probe class for the same reason the positive
control does).

Also runnable under Compute Sanitizer's initcheck:

    compute-sanitizer --tool initcheck python3 lab/negative-controls/zeroed_before_free.py

initcheck will still report the kernel's read as touching memory
"uninitialized" in this allocation's lifetime -- its shadow-memory tracking
resets on every ``cudaMalloc`` regardless of what a previous allocation's
``cudaMemset`` did underneath it. That is expected and not a contradiction:
initcheck is answering "has anything written to this allocation since it was
handed to me," GPU-SEAL is answering "does our own canary come back." This
script's pass/fail criterion is the latter.

Buffer handling goes through the same safe layer as the positive control:
:class:`CanarySet` for authenticated markers (CHARTER.md §7.1), :class:`SafeBuffer`
and :func:`aggregate` for the read-back (CHARTER.md §7.2). Only aggregate
fields are ever printed below.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "probe"))

import numpy as np  # noqa: E402

from gpu_seal import __version__  # noqa: E402
from gpu_seal.cuda import BackendUnavailable, CupyBackend  # noqa: E402
from gpu_seal.cuda.backend import DeviceAllocation  # noqa: E402
from gpu_seal.safety import (  # noqa: E402
    Boundary,
    CanarySet,
    SafeBuffer,
    SensitiveObservation,
    aggregate,
)

PROBE_NAME = "negative_control_zeroed_before_free"
PROBE_VERSION = "0.1.0"

ALLOCATION_BYTES = 256 * 1024  # 256 KiB -- matches the positive control
CANARY_STRIDE = 64 * 1024

#: Identical read pattern to the positive control's kernel, on purpose: the
#: two scripts must differ only in the zeroisation step, or a difference in
#: outcome would not isolate what caused it.
_READ_BEFORE_WRITE_KERNEL = r"""
extern "C" __global__
void read_before_write(unsigned long long src_ptr,
                        unsigned long long dst_ptr,
                        long long n)
{
    const unsigned char* src = reinterpret_cast<const unsigned char*>(src_ptr);
    unsigned char* dst = reinterpret_cast<unsigned char*>(dst_ptr);
    long long i = static_cast<long long>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (i < n) {
        dst[i] = src[i];
    }
}
"""


def banner(text: str) -> None:
    print()
    print(text)
    print("-" * len(text))


def plant_canaries(
    backend: CupyBackend, alloc: DeviceAllocation, canaries: CanarySet
) -> int:
    """Write authenticated owned markers across the allocation. Mirrors
    ``GlobalMemoryProbe.plant_canaries`` without depending on that class."""
    planted = 0
    offset = 0
    while offset + 128 <= alloc.size:
        canary = canaries.mint(Boundary.SEPARATE_LAUNCH)
        backend.write_to_device(alloc, offset, canary.blob)
        planted += 1
        offset += CANARY_STRIDE
    return planted


def main() -> int:
    print()
    print("GPU-SEAL negative control: explicit zeroisation before free")
    print(f"gpu-seal {__version__}")
    print("=" * 62)
    print("Same allocate/plant/free/reallocate/read cycle as the positive")
    print("control, with an explicit memset(0) before free. The canary must")
    print("NOT be recoverable (CHARTER.md §11, §19).")

    try:
        backend = CupyBackend()
    except BackendUnavailable as exc:
        print(f"\nNo CUDA device available: {exc}")
        print("This script validates a hardware behaviour, not probe logic --")
        print("it needs real silicon. For logic-only tests against the")
        print("simulated allocator see tests/unit/test_memory_global_probe.py.")
        return 1

    import cupy  # noqa: E402 - only needed once a real device is confirmed

    kernel = cupy.RawKernel(_READ_BEFORE_WRITE_KERNEL, "read_before_write")
    canaries = CanarySet.create()

    first: DeviceAllocation | None = None
    second: DeviceAllocation | None = None
    scratch: DeviceAllocation | None = None
    exit_code = 0
    try:
        banner("1. Allocate, plant owned canaries")
        first = backend.malloc(ALLOCATION_BYTES)
        planted = plant_canaries(backend, first, canaries)
        print(f"  planted {planted} canaries across {first.size} bytes")

        banner("2. Explicit sanitisation, then free")
        backend.fill_device(first, 0)
        backend.free(first)
        first = None
        print("  memset(0) applied before free -- the provider-sanitisation case")

        banner("3. Reallocate the same size (same process, no write yet)")
        second = backend.malloc(ALLOCATION_BYTES)
        scratch = backend.malloc(ALLOCATION_BYTES)
        print(
            f"  second allocation: {second.size} bytes, "
            f"generation {second.generation}"
        )

        banner("4. Read before write: a kernel copies the reused allocation")
        threads = 256
        blocks = -(-ALLOCATION_BYTES // threads)
        kernel(
            (blocks,),
            (threads,),
            (
                np.uint64(second.ptr),
                np.uint64(scratch.ptr),
                np.int64(ALLOCATION_BYTES),
            ),
        )
        cupy.cuda.runtime.deviceSynchronize()
        print("  kernel launch complete")

        banner("5. GPU-SEAL's own check: the canary must NOT come back")
        with SafeBuffer.acquire(
            ALLOCATION_BYTES,
            provenance="cudaMalloc:device_global:negative_control",
        ) as buf:
            buf.fill_via(lambda view: backend.copy_to_host(scratch, view))
            record = aggregate(
                buf,
                canaries,
                probe_name=PROBE_NAME,
                probe_version=PROBE_VERSION,
                expect_zeroed=True,
                # Researcher's own lab hardware, per the positive control.
                shared_infrastructure=False,
                driver_metadata=backend.device_info(),
            )

        print(f"  zero_fraction              {record.zero_fraction:.6f}")
        print(f"  entropy_estimate           {record.entropy_estimate:.4f}")
        print(f"  owned_canary_match         {record.owned_canary_match}")
        print(f"  owned_canary_exact_matches {record.owned_canary_exact_matches}")

        if record.owned_canary_match:
            print("\n  FAIL: a canary was recovered after explicit zeroisation.")
            print("  This is a false positive in the harness itself -- every")
            print("  other result, local or cloud, is void until this is")
            print("  explained (CHARTER.md §19).")
            exit_code = 1
        else:
            print("\n  PASS: no canary recovered after memset(0) + free +")
            print("  reallocate. The harness does not manufacture residue")
            print("  that was not there.")

    except SensitiveObservation as stop:
        print(f"\n  SAFETY STOP (CHARTER.md §7.3): {stop}")
        print("  Raw buffer already destroyed; only the aggregate record")
        print("  (if any) above survives. Run requires manual disclosure")
        print("  review before anything here is reused.")
        exit_code = 1
    finally:
        for alloc in (first, second, scratch):
            if alloc is not None:
                try:
                    backend.free(alloc)
                except Exception:  # noqa: BLE001 - teardown must not mask
                    pass
        backend.close()

    print()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
