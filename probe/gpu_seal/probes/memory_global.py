"""Memory Probe B — device-global VRAM allocation. CHARTER.md §9.3.

The core of contribution D1: allocate device-global memory with a
**non-zeroing** allocator, measure the returned bytes **before writing any
application data**, and determine whether an owned canary survives across a
defined isolation boundary.

The read-before-write ordering is the whole experiment. Once anything is
written to the allocation, the question "what was here when I got it?" is
unanswerable.

Limitations, recorded on every result because they change what a result means
(CHARTER.md §9.3):

* The runtime or driver **may** initialise allocations. We do not know that it
  didn't.
* Caching allocators may return process-local reused memory. A canary
  recovered inside one process may say nothing about the driver — that is
  precisely why §9.4 exists as a separate probe.
* **A non-zero buffer does not prove cross-tenant residue.** Uninitialised
  memory is uninitialised; it is not evidence about anyone else.
* **An all-zero buffer does not prove provider sanitisation.** It may be a
  fresh page, a zeroing runtime, or luck.

Only one thing counts as a positive result: an **authenticated owned canary**
recovered across a boundary where sanitisation was expected. Everything else
is context.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from collections.abc import Container, Sequence

from ..cuda.backend import CudaBackend, DeviceAllocation
from ..safety.aggregation import AggregateRecord, aggregate
from ..safety.buffer import SafeBuffer
from ..safety.canary import Boundary, Canary, CanarySet
from ..safety.errors import SensitiveObservation

__all__ = ["GlobalMemoryProbe", "ReuseCycle", "PROBE_NAME", "PROBE_VERSION"]

PROBE_NAME = "memory_global_read_before_write"
PROBE_VERSION = "0.1.0"

#: Canaries are planted at a stride rather than only at offset 0.
#:
#: A real allocator may hand back a block whose *start* differs from ours even
#: when the underlying pages overlap, and a partial overwrite may clobber the
#: beginning while leaving the middle intact. Striping markers across the
#: allocation raises detection probability without changing what is searched
#: for — still only our own authenticated markers.
DEFAULT_CANARY_STRIDE = 1 << 20  # one marker per MiB


@dataclass
class ReuseCycle:
    """One allocate → plant → free → reallocate → read-before-write cycle."""

    boundary: Boundary
    size_bytes: int
    canaries_planted: int
    plant_offsets: list[int] = field(default_factory=list)

    #: Measurement of the SECOND allocation, taken before any host write.
    observation: AggregateRecord | None = None

    #: Set when the §7.3 automatic safety stop fired during the read-back.
    safety_stop: bool = False

    #: Populated on failure so a bad cycle is excluded rather than silently lost.
    error_code: str | None = None

    @property
    def canary_recovered(self) -> bool:
        return bool(self.observation and self.observation.owned_canary_match)

    @property
    def usable(self) -> bool:
        """A cycle with an error is excluded from statistics (CHARTER.md §12)."""
        return self.error_code is None and self.observation is not None


class GlobalMemoryProbe:
    """Read-before-write measurement of device-global allocations."""

    NAME = PROBE_NAME
    VERSION = PROBE_VERSION

    def __init__(
        self,
        backend: CudaBackend,
        canaries: CanarySet,
        *,
        canary_stride: int = DEFAULT_CANARY_STRIDE,
        shared_infrastructure: bool = True,
    ) -> None:
        """
        Args:
            shared_infrastructure: ``True`` (default) for any rented instance,
                which arms the entropy safety stop. Set ``False`` only for
                hardware the researcher owns exclusively — on a local
                workstation the residue is the researcher's own, and stopping
                on it is noise rather than protection. Defaults to the safe
                value so that forgetting to set it errs toward stopping.
        """
        self._backend = backend
        self._canaries = canaries
        self._stride = max(canary_stride, 1)
        self._shared = shared_infrastructure

    # ------------------------------------------------------------------
    # Primitive: measure an allocation without writing to it first
    # ------------------------------------------------------------------

    def read_before_write(
        self,
        alloc: DeviceAllocation,
        *,
        boundary: Boundary,
        expect_zeroed: bool = False,
        probe_name: str | None = None,
        probe_version: str | None = None,
        expected_owned_allocation_ids: Container[uuid.UUID] | None = None,
    ) -> AggregateRecord:
        """Copy the allocation to a SafeBuffer and reduce it to statistics.

        No host-side copy of the contents survives this call. The SafeBuffer
        is zeroed on scope exit whether or not aggregation succeeded.

        Args:
            probe_name / probe_version: override the identity stamped on the
                record. Required by any probe that *composes* this one --
                §9.4's ``FrameworkAllocatorProbe`` reuses these mechanics
                deliberately, and without the override its control records
                were written into evidence bundles under §9.3's name, making
                a passing control read as §9.3 finding residue. Composition
                is the right design; inheriting the label was not.
            expected_owned_allocation_ids: passed through to
                ``aggregate()``'s ``expected_allocation_ids``. Leave unset for
                the ordinary case (plant into and immediately measure the
                same allocation). Set it — to ``{planted_canary.allocation_id}``
                — when this measurement must match one *specific* canary and
                no other the experiment happens to have minted; see
                ``gpu_seal.probes.self_canary`` for why that distinction
                matters for the §9.5 A/B design.
        """
        metadata = dict(self._backend.device_info())
        metadata["boundary"] = boundary.name
        metadata["allocation_generation"] = str(alloc.generation)
        metadata["shared_infrastructure"] = str(self._shared).lower()

        started = time.perf_counter_ns()
        with SafeBuffer.acquire(
            alloc.size, provenance=f"{self._backend.name}:cudaMalloc:device_global"
        ) as buf:
            buf.fill_via(lambda view: self._backend.copy_to_host(alloc, view))
            elapsed = time.perf_counter_ns() - started
            return aggregate(
                buf,
                self._canaries,
                probe_name=probe_name or self.NAME,
                probe_version=probe_version or self.VERSION,
                expect_zeroed=expect_zeroed,
                shared_infrastructure=self._shared,
                driver_metadata=metadata,
                timing_ns=elapsed,
                expected_allocation_ids=expected_owned_allocation_ids,
            )

    # ------------------------------------------------------------------
    # Canary planting
    # ------------------------------------------------------------------

    def plant_canaries(
        self, alloc: DeviceAllocation, boundary: Boundary
    ) -> tuple[list[Canary], list[int]]:
        """Write authenticated owned markers across the allocation."""
        planted: list[Canary] = []
        offsets: list[int] = []
        offset = 0
        while offset + 128 <= alloc.size:
            canary = self._canaries.mint(boundary)
            self._backend.write_to_device(alloc, offset, canary.blob)
            planted.append(canary)
            offsets.append(offset)
            offset += self._stride
        return planted, offsets

    # ------------------------------------------------------------------
    # The §9.3 test-1 cycle: same-process allocator reuse
    # ------------------------------------------------------------------

    def same_process_reuse_cycle(
        self,
        size_bytes: int,
        *,
        boundary: Boundary = Boundary.SEPARATE_LAUNCH,
        expect_zeroed: bool = False,
    ) -> ReuseCycle:
        """Allocate → plant → free → reallocate → read before writing.

        In-process, so a recovered canary indicates allocator reuse rather
        than anything about the provider. This is the **positive control**
        that proves the harness can detect a surviving marker at all — the
        thing that makes a negative cloud result meaningful (CHARTER.md §11).
        """
        cycle = ReuseCycle(
            boundary=boundary, size_bytes=size_bytes, canaries_planted=0
        )

        first: DeviceAllocation | None = None
        second: DeviceAllocation | None = None
        try:
            first = self._backend.malloc(size_bytes)
            planted, offsets = self.plant_canaries(first, boundary)
            cycle.canaries_planted = len(planted)
            cycle.plant_offsets = offsets

            self._backend.free(first)
            first = None

            second = self._backend.malloc(size_bytes)
            cycle.observation = self.read_before_write(
                second, boundary=boundary, expect_zeroed=expect_zeroed
            )
        except SensitiveObservation as stop:
            # §7.3 fired. Statistics survive; the bytes do not. Not an error —
            # a result that requires manual review before it goes anywhere.
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

    # ------------------------------------------------------------------
    # Fresh-allocation measurement (no planting)
    # ------------------------------------------------------------------

    def fresh_allocation_observation(
        self, size_bytes: int, *, expect_zeroed: bool = False
    ) -> ReuseCycle:
        """Measure a brand-new allocation with no canary planted beforehand.

        Establishes the baseline distribution of a fresh `cudaMalloc` on this
        device: how often it is zeroed, what the entropy looks like. Needed to
        interpret everything else, and it is the cycle most likely to trip the
        §7.3 safety stop on a shared machine — which is the correct outcome.
        """
        cycle = ReuseCycle(
            boundary=Boundary.UNSPECIFIED, size_bytes=size_bytes, canaries_planted=0
        )
        alloc: DeviceAllocation | None = None
        try:
            alloc = self._backend.malloc(size_bytes)
            cycle.observation = self.read_before_write(
                alloc, boundary=Boundary.UNSPECIFIED, expect_zeroed=expect_zeroed
            )
        except SensitiveObservation as stop:
            cycle.safety_stop = True
            cycle.observation = stop.aggregate_record  # type: ignore[assignment]
        except (MemoryError, ValueError, RuntimeError) as exc:
            cycle.error_code = f"{type(exc).__name__}"
        finally:
            if alloc is not None:
                try:
                    self._backend.free(alloc)
                except Exception:  # noqa: BLE001
                    pass
        return cycle

    # ------------------------------------------------------------------
    # Negative control
    # ------------------------------------------------------------------

    def zeroed_reuse_cycle(self, size_bytes: int) -> ReuseCycle:
        """Plant a canary, explicitly zero the allocation, then reallocate.

        The canary must NOT be recovered. If it is, the probe is reporting
        false positives and every other result is void until that is
        explained (CHARTER.md §11 negative controls, §19 false positives).
        """
        cycle = ReuseCycle(
            boundary=Boundary.SEPARATE_LAUNCH,
            size_bytes=size_bytes,
            canaries_planted=0,
        )
        first: DeviceAllocation | None = None
        second: DeviceAllocation | None = None
        try:
            first = self._backend.malloc(size_bytes)
            planted, offsets = self.plant_canaries(first, Boundary.SEPARATE_LAUNCH)
            cycle.canaries_planted = len(planted)
            cycle.plant_offsets = offsets

            self._backend.fill_device(first, 0)  # explicit sanitisation
            self._backend.free(first)
            first = None

            second = self._backend.malloc(size_bytes)
            cycle.observation = self.read_before_write(
                second, boundary=Boundary.SEPARATE_LAUNCH, expect_zeroed=True
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
                    except Exception:  # noqa: BLE001
                        pass
        return cycle

    # ------------------------------------------------------------------
    # Campaign
    # ------------------------------------------------------------------

    def run_cycles(
        self,
        size_bytes: int,
        repetitions: int,
        *,
        mode: str = "reuse",
    ) -> list[ReuseCycle]:
        """Repeat a cycle N times. CHARTER.md §12 requires repeated measurement."""
        runners = {
            "reuse": lambda: self.same_process_reuse_cycle(size_bytes),
            "fresh": lambda: self.fresh_allocation_observation(size_bytes),
            "zeroed": lambda: self.zeroed_reuse_cycle(size_bytes),
        }
        if mode not in runners:
            raise ValueError(f"unknown mode {mode!r}; expected one of {sorted(runners)}")
        return [runners[mode]() for _ in range(repetitions)]


def summarise(cycles: Sequence[ReuseCycle]) -> dict[str, object]:
    """Counts for a set of cycles. CHARTER.md §12 reporting requirements.

    Deliberately reports interpretation-free counts. Turning these into a
    grade is the report card's job, and it applies the same-device gate that
    this function has no way to evaluate.
    """
    usable = [c for c in cycles if c.usable]
    recovered = [c for c in usable if c.canary_recovered]
    return {
        "cycles_attempted": len(cycles),
        "cycles_usable": len(usable),
        "cycles_excluded": len(cycles) - len(usable),
        "canary_recovered_cycles": len(recovered),
        "safety_stop_cycles": sum(1 for c in cycles if c.safety_stop),
        "recovery_rate": (len(recovered) / len(usable)) if usable else None,
        "exclusion_reasons": sorted(
            {c.error_code for c in cycles if c.error_code is not None}
        ),
    }
