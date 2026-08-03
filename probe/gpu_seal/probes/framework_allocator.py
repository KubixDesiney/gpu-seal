"""Memory Probe C — framework allocator behaviour. CHARTER.md §9.4.

§9.3 (``memory_global``) goes to the raw CUDA runtime API on purpose, so that
a recovered canary says something about the **driver**. But that choice has
a cost, recorded in
[Finding 001](../../../docs/findings/2026-07-31-rtx3050-baseline.md): if the
driver zeroes memory on free, §9.3 can never produce a positive control on
that platform, and a clean result from a provider measured the same way is
uninterpretable — CHARTER.md §11 is explicit that a negative result without
a working positive control proves nothing.

§9.4 exists to supply that positive control without depending on driver
behaviour. It allocates through a **caching allocator** — a
``PooledCupyBackend`` wrapping ``cupy.cuda.MemoryPool`` — which returns a
freed block to its own free list and never calls ``cudaFree``. The driver
never learns the allocation was released, so a canary recovered here proves
the harness *can* detect a marker it planted, independent of whatever the
driver does. It is not evidence about the driver, a provider, or cross-tenant
residue — see CHARTER.md §9.4's note that this is primarily a
local/dedicated-lab instrument, not a probe to run against rented or
provider-managed infrastructure.

This module deliberately requires a backend with ``pooled = True``
(``CudaBackend.pooled``). Running it against the raw runtime backend would
silently produce a driver-dependent result mislabelled as a
driver-independent one — the exact confusion §9.3 vs §9.4 exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from ..cuda.backend import CudaBackend, DeviceAllocation
from ..safety.canary import Boundary, CanarySet
from ..safety.errors import SensitiveObservation
from .memory_global import DEFAULT_CANARY_STRIDE, GlobalMemoryProbe, ReuseCycle

__all__ = [
    "FrameworkAllocatorProbe",
    "PooledReuseCycle",
    "PROBE_NAME",
    "PROBE_VERSION",
]

PROBE_NAME = "framework_allocator_reuse"
PROBE_VERSION = "0.1.0"


@dataclass
class PooledReuseCycle(ReuseCycle):
    """A §9.3 ``ReuseCycle`` plus the one extra signal §9.4 can observe
    because it controls the allocator: whether the pool handed back the
    literal same block, independent of whether the canary survived on it.
    """

    #: True when the reallocated block's address equals the freed block's.
    #: None when the cycle errored before both addresses were known.
    ptr_reused: bool | None = None


class FrameworkAllocatorProbe:
    """Detection-capability control: does a caching allocator hand back a
    freed block with an owned canary still on it?

    Deliberately thin: the read-before-write and canary-planting mechanics
    are identical to §9.3's, so this composes a ``GlobalMemoryProbe`` for
    them rather than re-implementing safety-relevant logic a second time.
    What differs is the backend it is required to run against, and the
    interpretation of what a result means.
    """

    NAME = PROBE_NAME
    VERSION = PROBE_VERSION

    def __init__(
        self,
        backend: CudaBackend,
        canaries: CanarySet,
        *,
        canary_stride: int = DEFAULT_CANARY_STRIDE,
        shared_infrastructure: bool,
    ) -> None:
        """
        Args:
            shared_infrastructure: no default — CHARTER.md §9.4 describes
                this probe as "primarily a local/dedicated-lab test", which
                makes ``False`` the ordinary answer, but a silent default
                to the value that disarms the entropy safety stop is exactly
                the kind of thing that should require a conscious choice
                rather than happen automatically when a caller forgets the
                argument. Pass ``False`` for hardware you own exclusively;
                ``True`` only if you have a specific, permitted reason to
                run this against infrastructure you do not — see
                ``GlobalMemoryProbe`` for what the flag actually arms.
        """
        if not getattr(backend, "pooled", False):
            raise ValueError(
                f"{type(backend).__name__} is not a pooled/caching backend "
                f"(CudaBackend.pooled is False). CHARTER.md §9.4 exists "
                f"specifically to measure a caching allocator, not the raw "
                f"runtime API -- that is §9.3 (GlobalMemoryProbe). Use "
                f"PooledCupyBackend, or SimulatedBackend for logic tests."
            )
        self._backend = backend
        self._canaries = canaries
        self._inner = GlobalMemoryProbe(
            backend,
            canaries,
            canary_stride=canary_stride,
            shared_infrastructure=shared_infrastructure,
        )

    # ------------------------------------------------------------------
    # The §9.4 cycle: allocate -> plant -> free -> reallocate -> read,
    # entirely through the caching allocator.
    # ------------------------------------------------------------------

    def pooled_reuse_cycle(
        self,
        size_bytes: int,
        *,
        boundary: Boundary = Boundary.SEPARATE_LAUNCH,
    ) -> PooledReuseCycle:
        """One allocate/plant/free/reallocate/read cycle through the pool.

        Unlike ``GlobalMemoryProbe.same_process_reuse_cycle``, ``free()``
        here never reaches the driver -- see ``PooledCupyBackend``. A
        recovered canary is a statement about the harness, not the driver.
        """
        cycle = PooledReuseCycle(
            boundary=boundary, size_bytes=size_bytes, canaries_planted=0
        )
        first: DeviceAllocation | None = None
        second: DeviceAllocation | None = None
        try:
            first = self._backend.malloc(size_bytes)
            planted, offsets = self._inner.plant_canaries(first, boundary)
            cycle.canaries_planted = len(planted)
            cycle.plant_offsets = offsets
            first_ptr = first.ptr

            self._backend.free(first)
            first = None

            second = self._backend.malloc(size_bytes)
            cycle.ptr_reused = second.ptr == first_ptr
            cycle.observation = self._inner.read_before_write(
                second,
                boundary=boundary,
                # Stamp §9.4's identity, not the composed probe's. Without
                # this the record claims to be a §9.3 driver measurement.
                probe_name=self.NAME,
                probe_version=self.VERSION,
            )
        except SensitiveObservation as stop:
            cycle.safety_stop = True
            cycle.observation = stop.aggregate_record  # type: ignore[assignment]
        except (MemoryError, ValueError, RuntimeError) as exc:
            cycle.error_code = f"{type(exc).__name__}"
        finally:
            for alloc in (first, second):
                if alloc is not None:
                    try:
                        self._backend.free(alloc)
                    except Exception:  # noqa: BLE001 - teardown must not mask
                        pass
        return cycle

    def run_cycles(
        self,
        size_bytes: int,
        repetitions: int,
        *,
        boundary: Boundary = Boundary.SEPARATE_LAUNCH,
    ) -> list[PooledReuseCycle]:
        """Repeat the pooled-reuse cycle N times. CHARTER.md §12."""
        return [
            self.pooled_reuse_cycle(size_bytes, boundary=boundary)
            for _ in range(repetitions)
        ]


def summarise(cycles: Sequence[PooledReuseCycle]) -> dict[str, object]:
    """Counts for a set of pooled-reuse cycles, plus the §9.4-specific
    buffer-reuse rate: how often the pool handed back the same block at
    all, whether or not the canary on it was recovered. A low canary
    recovery rate alongside a high buffer-reuse rate would point at a
    matching bug rather than a real absence of residue.
    """
    usable = [c for c in cycles if c.usable]
    recovered = [c for c in usable if c.canary_recovered]
    reused = [c for c in usable if c.ptr_reused]
    return {
        "cycles_attempted": len(cycles),
        "cycles_usable": len(usable),
        "cycles_excluded": len(cycles) - len(usable),
        "canary_recovered_cycles": len(recovered),
        "recovery_rate": (len(recovered) / len(usable)) if usable else None,
        "buffer_reuse_cycles": len(reused),
        "buffer_reuse_rate": (len(reused) / len(usable)) if usable else None,
        "safety_stop_cycles": sum(1 for c in cycles if c.safety_stop),
        "exclusion_reasons": sorted(
            {c.error_code for c in cycles if c.error_code is not None}
        ),
    }
