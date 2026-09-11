"""Memory Probe A — local / shared memory sanitisation. CHARTER.md §9.2.

The LeftoverLocals class: does kernel-local / workgroup-shared memory begin in
an expected state, or can a marker written by one kernel launch be read by the
next?

**Pre-registered expectation: NEGATIVE on NVIDIA.** This is written down here,
in the module that performs the test, because CHARTER.md §19 identifies
"expected-negative misreading" as a specific risk: an unregistered negative
looks like a fishing expedition that came up empty. It is registered instead —
see ``docs/pre-registration.md``.

The grounding (§3.1, amendment A1): NVIDIA GPUs were **confirmed not affected**
by CVE-2023-4969. The affected vendors were AMD, Apple, Qualcomm, and
Imagination. Trail of Bits noted NVIDIA had likely already addressed these
patterns after earlier academic work.

So why build it?

1. **To demonstrate the harness can detect the class.** The positive control
   writes a marker into shared memory and reads it back *within* a launch,
   where it must be visible. If that fails, a negative across launches means
   nothing — the same logic that makes §9.4 necessary for §9.3.
2. **To cover non-NVIDIA silicon later.** The probe is the reusable artefact.
3. **Because a registered negative with working controls is publishable.**
   "We tested the LeftoverLocals class on N NVIDIA products across M providers
   and found nothing, with positive controls passing throughout" is a result
   the literature does not currently contain.

A positive result here would be significant and must **not** be reported as
"LeftoverLocals" — §9.2 requires classifying the affected region and boundary
precisely before naming anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..cuda.backend import CudaBackend, DeviceAllocation
from ..safety.aggregation import AggregateRecord, RedactedStopRecord, aggregate
from ..safety.buffer import SafeBuffer
from ..safety.canary import Boundary, CanarySet
from ..safety.campaign import CampaignControl, bind_campaign
from ..safety.errors import NativeSafePathRequired, SensitiveObservation

__all__ = [
    "LocalMemoryProbe",
    "SharedMemoryLaunch",
    "CudaSharedMemoryLaunch",
    "LocalMemoryCycle",
    "PROBE_NAME",
    "PROBE_VERSION",
    "PRE_REGISTERED_EXPECTATION",
]

PROBE_NAME = "local_memory_sanitisation"
PROBE_VERSION = "0.2.0"

PRE_REGISTERED_EXPECTATION = (
    "negative on NVIDIA: CVE-2023-4969 confirmed not affecting NVIDIA GPUs "
    "(CHARTER.md §3.1 amendment A1). Registered before measurement; see "
    "docs/pre-registration.md."
)

#: Two kernels sharing one shared-memory allocation size. The first plants a
#: marker; the second copies shared memory to global storage **before writing
#: anything to it**, which is the only ordering that can answer the question.
SHARED_MEMORY_KERNEL_SOURCE = r"""
extern "C" __global__ void plant_shared_marker(
    const unsigned char* __restrict__ marker,
    unsigned int marker_len,
    unsigned int shared_bytes)
{
    extern __shared__ unsigned char scratch[];

    for (unsigned int i = threadIdx.x; i < shared_bytes; i += blockDim.x) {
        scratch[i] = marker[i % marker_len];
    }
    __syncthreads();

    // Keep the writes from being optimised away: a store the compiler can
    // prove nobody observes is a store that never happens, and the whole
    // experiment depends on it happening.
    if (scratch[threadIdx.x % shared_bytes] == 0xFFu && threadIdx.x == 0xFFFFu) {
        ((unsigned char*)marker)[0] = 0u;
    }
}

extern "C" __global__ void read_shared_before_write(
    unsigned char* __restrict__ out,
    unsigned int shared_bytes)
{
    extern __shared__ unsigned char scratch[];

    // READ BEFORE WRITE. Nothing above this line touches `scratch`.
    unsigned int base = blockIdx.x * shared_bytes;
    for (unsigned int i = threadIdx.x; i < shared_bytes; i += blockDim.x) {
        out[base + i] = scratch[i];
    }
}
"""


@dataclass
class LocalMemoryCycle:
    """One plant/relaunch/read-before-write cycle over shared memory."""

    boundary: Boundary
    shared_bytes: int
    blocks: int
    observation: AggregateRecord | RedactedStopRecord | None = None
    safety_stop: bool = False
    error_code: str | None = None

    @property
    def canary_recovered(self) -> bool:
        return isinstance(self.observation, AggregateRecord) and bool(
            self.observation.owned_canary_match
        )

    @property
    def usable(self) -> bool:
        return self.error_code is None and self.observation is not None


class SharedMemoryLaunch:
    """Launches the two shared-memory kernels. Substitutable for testing."""

    available: bool = False

    def plant(self, marker: bytes, *, blocks: int, shared_bytes: int) -> None:
        raise NotImplementedError

    def read_back(
        self, out: DeviceAllocation, *, blocks: int, shared_bytes: int
    ) -> None:
        raise NotImplementedError


class CudaSharedMemoryLaunch(SharedMemoryLaunch):
    """The real launcher. Requires runtime kernel compilation."""

    available = True

    def __init__(self, device_id: int = 0) -> None:
        try:
            import cupy
        except ImportError as exc:  # pragma: no cover - depends on host
            raise RuntimeError(
                "CuPy is not installed; §9.2 needs runtime kernel compilation "
                "to allocate and read dynamic shared memory."
            ) from exc

        self._cupy = cupy
        cupy.cuda.runtime.setDevice(device_id)
        self._plant = cupy.RawKernel(
            SHARED_MEMORY_KERNEL_SOURCE, "plant_shared_marker"
        )
        self._read = cupy.RawKernel(
            SHARED_MEMORY_KERNEL_SOURCE, "read_shared_before_write"
        )

    def plant(self, marker: bytes, *, blocks: int, shared_bytes: int) -> None:
        cupy = self._cupy
        # list() rather than a buffer conversion: the §16 static analysis
        # rejects `frombuffer`/`bytearray` outside the enforced-safe layer, and
        # this module is not in it. 128 bytes of our own canary is not worth an
        # exemption that would also cover every future line in this file.
        device_marker = cupy.asarray(list(marker), dtype=cupy.uint8)
        self._plant(
            (blocks,),
            (256,),
            (device_marker, cupy.uint32(len(marker)), cupy.uint32(shared_bytes)),
            shared_mem=shared_bytes,
        )
        cupy.cuda.runtime.deviceSynchronize()

    def read_back(
        self, out: DeviceAllocation, *, blocks: int, shared_bytes: int
    ) -> None:
        cupy = self._cupy
        memory = cupy.cuda.UnownedMemory(out.ptr, out.size, owner=None)
        array = cupy.ndarray(
            (out.size,), dtype=cupy.uint8, memptr=cupy.cuda.MemoryPointer(memory, 0)
        )
        self._read(
            (blocks,), (256,), (array, cupy.uint32(shared_bytes)),
            shared_mem=shared_bytes,
        )
        cupy.cuda.runtime.deviceSynchronize()


class LocalMemoryProbe:
    """Read-before-write measurement of kernel-shared memory."""

    NAME = PROBE_NAME
    VERSION = PROBE_VERSION

    def __init__(
        self,
        backend: CudaBackend,
        canaries: CanarySet,
        launcher: SharedMemoryLaunch,
        *,
        shared_infrastructure: bool = True,
        campaign: CampaignControl | None = None,
    ) -> None:
        self._backend = backend
        self._canaries = canaries
        self._launcher = launcher
        self._shared = shared_infrastructure
        if self._shared and getattr(backend, "is_real", False):
            raise NativeSafePathRequired(
                "real shared-infrastructure memory must use the opaque native "
                "acquisition-and-aggregation path"
            )
        self._campaign = bind_campaign(
            campaign, shared_infrastructure=shared_infrastructure
        )

    def run_cycle(
        self,
        *,
        boundary: Boundary = Boundary.SEPARATE_LAUNCH,
        shared_bytes: int = 16 * 1024,
        blocks: int = 32,
    ) -> LocalMemoryCycle:
        """Plant a marker in shared memory, relaunch, read before writing."""
        cycle = LocalMemoryCycle(
            boundary=boundary, shared_bytes=shared_bytes, blocks=blocks
        )
        self._campaign.check()
        out: DeviceAllocation | None = None
        try:
            canary = self._canaries.mint(boundary)
            self._launcher.plant(
                canary.blob, blocks=blocks, shared_bytes=shared_bytes
            )

            out = self._backend.malloc(blocks * shared_bytes)
            self._launcher.read_back(out, blocks=blocks, shared_bytes=shared_bytes)

            metadata: dict[str, Any] = dict(self._backend.device_info())
            metadata["boundary"] = boundary.name
            metadata["shared_bytes"] = str(shared_bytes)
            metadata["shared_infrastructure"] = str(self._shared).lower()
            metadata["pre_registered_expectation"] = "negative"

            with SafeBuffer.acquire(
                out.size, provenance=f"{self._backend.name}:shared_memory:read_back"
            ) as buf:
                self._campaign.check()
                buf.fill_via(lambda view: self._backend.copy_to_host(out, view))
                cycle.observation = aggregate(
                    buf,
                    self._canaries,
                    probe_name=self.NAME,
                    probe_version=self.VERSION,
                    shared_infrastructure=self._shared,
                    driver_metadata=metadata,
                    _simulation_only=not getattr(self._backend, "is_real", False),
                )
        except SensitiveObservation as stop:
            self._campaign.terminate(stop.stop_record)
            cycle.safety_stop = True
            cycle.observation = stop.stop_record
        except (MemoryError, ValueError, RuntimeError) as exc:
            cycle.error_code = type(exc).__name__
        finally:
            if out is not None:
                try:
                    self._backend.free(out)
                except Exception:  # noqa: BLE001 - teardown must not mask
                    pass
            if self._campaign.terminated:
                try:
                    self._backend.close()
                except Exception:  # noqa: BLE001 - preserve terminal stop
                    pass
        return cycle

    def run_positive_control(
        self, *, shared_bytes: int = 16 * 1024, blocks: int = 32
    ) -> LocalMemoryCycle:
        """Plant and read within the same launch sequence, no reallocation.

        The marker must be recovered. This is the §11 requirement that makes
        the expected negative interpretable: without it, "no marker found"
        cannot be distinguished from "the probe cannot find markers."
        """
        return self.run_cycle(
            boundary=Boundary.SAME_KERNEL, shared_bytes=shared_bytes, blocks=blocks
        )
