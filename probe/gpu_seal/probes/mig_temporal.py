"""MIG temporal isolation — CHARTER.md §9.12, contribution **D2**.

    "Runtime isolation ≠ temporal isolation."

The MIG User Guide specifies runtime isolation in detail — separate crossbar
ports, L2 cache banks, memory controllers, DRAM address buses — and specifies
**nothing** about whether memory is scrubbed when a MIG instance is destroyed
and recreated for a successive tenant. That silence is the gap. Nobody has
measured it.

The experiment (§9.12), all within researcher-owned or researcher-controlled
hardware:

    1. Create MIG instance M1
    2. Write an authenticated owned canary into M1's device-global memory
    3. Destroy M1
    4. Recreate M2 with the same profile (and separately, a different profile)
    5. Read-before-write in M2, safe aggregation, owned-canary match only
    6. Repeat across: same profile, different profile, full GPU reset,
       driver reload, host reboot

**Three mechanisms, never conflated.** MIG teardown, GPU-wide function-level
reset, and driver reload are different things, and reporting a result from one
as though it came from another would be the obvious methodological error. Each
boundary is a distinct :class:`~gpu_seal.safety.canary.Boundary` value and is
reported separately — :func:`summarise` refuses to pool them.

**Ethics: entirely self-canary.** This probe only ever touches the
researcher's own marker data in the researcher's own MIG instances, which
means it remains runnable under a ``self-canary-only`` provider policy — a
significant practical advantage when a provider prohibits benchmarking.

**Hardware: not runnable here.** MIG requires A100/H100-class datacentre
silicon. The RTX 3050 cannot run it (§20), so on this hardware the probe
refuses to produce a result rather than producing a meaningless one. The
orchestration and the safety properties are built and tested now so that
renting an hour of A100 time later is a scheduling decision, not a build.

**Lifecycle is the operator's, not the probe's.** Creating and destroying MIG
instances requires administrative privilege on the parent GPU, which GPU-SEAL
does not assume and will not request (§6). The operator drives the lifecycle;
this module supplies the plan, plants the marker, measures the successor, and
enforces that the two halves are correctly labelled.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..cuda.backend import CudaBackend, DeviceAllocation
from ..cuda.nvml import NvmlSnapshot, read_nvml
from ..safety.aggregation import AggregateRecord
from ..safety.canary import Boundary, CanarySet
from ..safety.errors import SensitiveObservation
from .memory_global import GlobalMemoryProbe

__all__ = [
    "MigTemporalProbe",
    "MigBoundaryResult",
    "MigUnavailable",
    "PlantReceipt",
    "TEMPORAL_BOUNDARIES",
    "PROBE_NAME",
    "PROBE_VERSION",
]

PROBE_NAME = "mig_temporal_isolation"
PROBE_VERSION = "0.2.0"

#: The six boundaries §9.12 asks for, each a separate mechanism. Reported
#: separately, always.
TEMPORAL_BOUNDARIES = (
    Boundary.MIG_SAME_PROFILE,
    Boundary.MIG_DIFFERENT_PROFILE,
    Boundary.GPU_RESET,
    Boundary.DRIVER_RELOAD,
    Boundary.HOST_REBOOT,
)


class MigUnavailable(RuntimeError):
    """This hardware cannot run §9.12, and saying so is the correct output."""


@dataclass(frozen=True)
class PlantReceipt:
    """Proof that :meth:`MigTemporalProbe.plant` actually ran for this
    boundary, required by :meth:`MigTemporalProbe.measure_successor`.

    This is same-process bookkeeping, not a cryptographic credential — a
    caller who really wants to construct one by hand still can, same trust
    boundary as the rest of this library. What it closes is the previous gap
    where ``measure_successor`` accepted a bare ``canaries_planted: int``
    with no connection to a real ``plant()`` call at all: skipping ``plant()``
    now means having no receipt to pass, rather than just passing ``0``.
    """

    boundary: Boundary
    canaries_planted: int


@dataclass
class MigBoundaryResult:
    """One plant/destroy/recreate/read cycle across one named boundary."""

    boundary: Boundary
    size_bytes: int
    canaries_planted: int = 0
    observation: AggregateRecord | None = None
    safety_stop: bool = False
    error_code: str | None = None
    #: Operator's note on what was actually done between plant and read.
    #: Required: a §9.12 record without it cannot be attributed to a mechanism.
    teardown_performed: str = ""

    @property
    def canary_recovered(self) -> bool:
        return bool(self.observation and self.observation.owned_canary_match)

    @property
    def usable(self) -> bool:
        return (
            self.error_code is None
            and self.observation is not None
            and bool(self.teardown_performed)
        )


class MigTemporalProbe:
    """Plant into one MIG instance, measure its successor."""

    NAME = PROBE_NAME
    VERSION = PROBE_VERSION

    def __init__(
        self,
        backend: CudaBackend,
        canaries: CanarySet,
        *,
        nvml: NvmlSnapshot | None = None,
        require_mig: bool = True,
    ) -> None:
        """
        Args:
            require_mig: refuse to run where MIG is not enabled. Default
                ``True`` — a §9.12 record produced on non-MIG hardware would
                be a §9.3 record wearing the wrong name, which is exactly the
                mislabelling that quarantined two earlier evidence bundles.
        """
        self._backend = backend
        self._canaries = canaries
        self._nvml = nvml if nvml is not None else read_nvml()
        if require_mig and not self._nvml.mig_enabled:
            raise MigUnavailable(
                "MIG is not enabled on this device, so §9.12 cannot run here. "
                "MIG requires A100/H100-class datacentre silicon (CHARTER.md "
                "§9.12, §20); the RTX 3050 in the local lab cannot host it. "
                "Refusing rather than producing a §9.3-equivalent measurement "
                "under a §9.12 label."
            )
        self._inner = GlobalMemoryProbe(
            backend, canaries, shared_infrastructure=False
        )

    # ------------------------------------------------------------------

    def plant(
        self, size_bytes: int, *, boundary: Boundary
    ) -> tuple[DeviceAllocation, PlantReceipt]:
        """Step 2: write owned canaries into the current instance's memory.

        The allocation is deliberately **not** freed and **not** returned to a
        pool. The teardown under test is the MIG instance being destroyed, and
        freeing first would test the allocator instead.

        Returns the allocation and a :class:`PlantReceipt` that
        :meth:`measure_successor` requires — see its docstring for why.
        """
        _require_temporal_boundary(boundary)
        alloc = self._backend.malloc(size_bytes)
        planted, _offsets = self._inner.plant_canaries(alloc, boundary)
        return alloc, PlantReceipt(boundary=boundary, canaries_planted=len(planted))

    def measure_successor(
        self,
        size_bytes: int,
        *,
        boundary: Boundary,
        teardown_performed: str,
        receipt: PlantReceipt,
    ) -> MigBoundaryResult:
        """Step 5: read-before-write in the recreated instance.

        Args:
            teardown_performed: what the operator actually did between the two
                halves, in their own words. Required. The three mechanisms
                §9.12 distinguishes are indistinguishable from inside the
                guest, so the record depends on this being stated.
            receipt: what :meth:`plant` returned for this same boundary. This
                is the self-canary-only policy's actual enforcement point:
                previously this method took a caller-supplied
                ``canaries_planted: int`` with no connection to whether
                ``plant()`` had ever run, so a caller could invoke it directly
                — skipping the plant step entirely — and still get a
                measurement with the entropy safety stop disarmed (this
                probe's inner ``GlobalMemoryProbe`` is always
                ``shared_infrastructure=False``, appropriate for its
                self-canary-only design, but only *if* a canary was actually
                planted first). Requiring the object ``plant()`` returned, and
                checking its boundary matches, makes skipping ``plant()`` a
                deliberate, visible act rather than an easy default.
        """
        _require_temporal_boundary(boundary)
        if not teardown_performed.strip():
            raise ValueError(
                "teardown_performed is required: MIG teardown, GPU-wide reset, "
                "and driver reload are three different mechanisms and cannot "
                "be distinguished from inside the instance (CHARTER.md §9.12)."
            )
        if receipt.boundary is not boundary:
            raise ValueError(
                f"receipt is for boundary {receipt.boundary.name}, not "
                f"{boundary.name}. measure_successor() requires the "
                f"PlantReceipt plant() returned for this same boundary."
            )
        if receipt.canaries_planted <= 0:
            raise ValueError(
                "receipt.canaries_planted is 0: plant() did not actually "
                "place a canary for this boundary. Refusing to measure a "
                "successor with no owned marker to authenticate it against."
            )

        result = MigBoundaryResult(
            boundary=boundary,
            size_bytes=size_bytes,
            canaries_planted=receipt.canaries_planted,
            teardown_performed=teardown_performed,
        )
        alloc: DeviceAllocation | None = None
        try:
            alloc = self._backend.malloc(size_bytes)
            result.observation = self._inner.read_before_write(
                alloc,
                boundary=boundary,
                probe_name=self.NAME,
                probe_version=self.VERSION,
            )
        except SensitiveObservation as stop:
            result.safety_stop = True
            result.observation = stop.aggregate_record  # type: ignore[assignment]
        except (MemoryError, ValueError, RuntimeError) as exc:
            result.error_code = type(exc).__name__
        finally:
            if alloc is not None:
                try:
                    self._backend.free(alloc)
                except Exception:  # noqa: BLE001 - teardown must not mask
                    pass
        return result


def _require_temporal_boundary(boundary: Boundary) -> None:
    if boundary not in TEMPORAL_BOUNDARIES:
        raise ValueError(
            f"{boundary.name} is not a §9.12 temporal boundary. Expected one "
            f"of {[b.name for b in TEMPORAL_BOUNDARIES]} — using a §9.3 "
            f"boundary here would file an allocator result under a MIG "
            f"teardown claim."
        )


def summarise(results: Sequence[MigBoundaryResult]) -> dict[str, Any]:
    """Counts **per boundary**. Never pooled.

    Pooling would average a MIG teardown together with a driver reload and
    report the mean as "MIG temporal isolation", which is the methodological
    error §9.12 names explicitly. The return shape makes that impossible:
    there is no total.
    """
    by_boundary: dict[str, dict[str, Any]] = {}
    for boundary in TEMPORAL_BOUNDARIES:
        subset = [r for r in results if r.boundary is boundary]
        if not subset:
            continue
        usable = [r for r in subset if r.usable]
        recovered = [r for r in usable if r.canary_recovered]
        by_boundary[boundary.name] = {
            "mechanism": _MECHANISM_NOTES[boundary],
            "cycles_attempted": len(subset),
            "cycles_usable": len(usable),
            "canary_recovered_cycles": len(recovered),
            "recovery_rate": (len(recovered) / len(usable)) if usable else None,
            "safety_stop_cycles": sum(1 for r in subset if r.safety_stop),
            "teardowns_recorded": sorted(
                {r.teardown_performed for r in subset if r.teardown_performed}
            ),
        }
    return by_boundary


_MECHANISM_NOTES: dict[Boundary, str] = {
    Boundary.MIG_SAME_PROFILE: (
        "MIG instance destroyed and recreated with the same profile. The "
        "boundary NVIDIA's documentation is silent about."
    ),
    Boundary.MIG_DIFFERENT_PROFILE: (
        "MIG instance destroyed and recreated with a different profile, so "
        "the memory slice geometry changes as well as its owner."
    ),
    Boundary.GPU_RESET: (
        "GPU-wide reset. A different mechanism from MIG teardown — do not "
        "report one as the other."
    ),
    Boundary.DRIVER_RELOAD: (
        "Kernel driver unloaded and reloaded. A third mechanism again."
    ),
    Boundary.HOST_REBOOT: (
        "Full host reboot. The strongest boundary available, and the one a "
        "provider is least likely to perform between tenants."
    ),
}
