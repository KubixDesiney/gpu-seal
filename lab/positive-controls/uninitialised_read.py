#!/usr/bin/env python3
"""Positive control, cross-checked by NVIDIA Compute Sanitizer. CHARTER.md §9.3, §11.

    compute-sanitizer --tool initcheck python3 lab/positive-controls/uninitialised_read.py
    # or, unwrapped:
    python3 lab/positive-controls/uninitialised_read.py

This reproduces the same scenario as
``gpu_seal.probes.memory_global.GlobalMemoryProbe.same_process_reuse_cycle`` --
allocate, plant an owned canary, free, reallocate, read before writing
anything new -- but deliberately does **not** go through that class. The
point of this script is a second, independent line of evidence for the same
phenomenon (CHARTER.md §9.3 "Independent validation"): GPU-SEAL's own canary
match is one detector; NVIDIA's own tool flagging the reused allocation as
uninitialised, from the driver's side, is a second, unrelated one. Vendor
confirmation that the phenomenon is real is what makes the methodology
section credible.

The read is done through a tiny CUDA kernel rather than a host-side
``cudaMemcpy``, because that is what Compute Sanitizer's initcheck actually
instruments: a per-thread global-memory load inside a kernel launch, not the
DMA copy engine. A kernel that copies the reallocated buffer byte-for-byte
into a scratch buffer gives every thread's read a chance to be flagged as an
"Uninitialized __global__ memory read" the moment it touches a byte nothing
has written since this allocation's ``cudaMalloc`` call -- regardless of
what the freed allocation physically left behind underneath it.

Buffer handling still goes through the project's normal safe layer even
though this script sits outside the probe package: :class:`CanarySet` mints
and authenticates the only markers ever searched for (CHARTER.md §7.1), and
the copy back to host lands in a :class:`SafeBuffer`, reduced to
:func:`aggregate` statistics before anything reaches stdout (CHARTER.md §7.2,
§16 tests 1-4). Only aggregate fields are ever printed below.
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

PROBE_NAME = "positive_control_initcheck_cross_check"
PROBE_VERSION = "0.1.0"

#: Small on purpose: Compute Sanitizer instruments every single memory access,
#: and this script exists to be run under it routinely, not just once.
ALLOCATION_BYTES = 256 * 1024  # 256 KiB
CANARY_STRIDE = 64 * 1024

#: extern "C" so the exported symbol name is not C++ mangled. Pointers travel
#: as plain 64-bit integers -- this kernel never allocates or frees anything
#: itself, it only dereferences memory this script already owns via
#: CupyBackend.malloc/free.
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
        // The read of `src` is the access compute-sanitizer --tool initcheck
        // is watching: this allocation was cudaMalloc'd moments ago and
        // nothing has written to it in its CURRENT lifetime, whatever the
        // freed allocation physically left behind.
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
    print("GPU-SEAL positive control: same-process allocator reuse")
    print(f"gpu-seal {__version__}")
    print("=" * 62)
    print("Independent validation via NVIDIA Compute Sanitizer --tool initcheck")
    print("(CHARTER.md §9.3, §11). Run under the sanitizer to see it flag the")
    print("kernel's read below; run bare to see GPU-SEAL's own canary check.")

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
        banner("1. Allocate, plant owned canaries, free")
        first = backend.malloc(ALLOCATION_BYTES)
        planted = plant_canaries(backend, first, canaries)
        print(f"  planted {planted} canaries across {first.size} bytes")
        backend.free(first)
        first = None

        banner("2. Reallocate the same size (same process, no write yet)")
        second = backend.malloc(ALLOCATION_BYTES)
        scratch = backend.malloc(ALLOCATION_BYTES)
        print(
            f"  second allocation: {second.size} bytes, "
            f"generation {second.generation}"
        )

        banner("3. Read before write: a kernel copies the reused allocation")
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
        print("  kernel launch complete -- under compute-sanitizer --tool")
        print("  initcheck this is reported as an uninitialised __global__")
        print("  memory read.")

        banner("4. GPU-SEAL's own check: did a canary survive?")
        with SafeBuffer.acquire(
            ALLOCATION_BYTES,
            provenance="cudaMalloc:device_global:positive_control",
        ) as buf:
            buf.fill_via(lambda view: backend.copy_to_host(scratch, view))
            record = aggregate(
                buf,
                canaries,
                probe_name=PROBE_NAME,
                probe_version=PROBE_VERSION,
                # This is the researcher's own lab hardware (CHARTER.md
                # §7.3): any residue found here is our own from the plant
                # step above, not a stranger's. On a rented instance this
                # must stay True.
                shared_infrastructure=False,
                driver_metadata=backend.device_info(),
            )

        print(f"  zero_fraction              {record.zero_fraction:.6f}")
        print(f"  entropy_estimate           {record.entropy_estimate:.4f}")
        print(f"  owned_canary_match         {record.owned_canary_match}")
        print(f"  owned_canary_exact_matches {record.owned_canary_exact_matches}")

        if record.owned_canary_match:
            print("\n  PASS: a canary survived free + reallocate in this")
            print("  process. The allocator handed back memory it did not")
            print("  clear, and the kernel above read it before anything new")
            print("  was written -- the exact read initcheck is watching.")
        else:
            print("\n  FAIL: no canary survived. Without a working positive")
            print("  control, a clean cloud result from this probe proves")
            print("  nothing (CHARTER.md §11) -- this is a harness problem to")
            print("  fix, not a provider finding.")
            exit_code = 1

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
