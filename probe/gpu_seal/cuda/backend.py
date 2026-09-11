"""CUDA backend abstraction.

Two implementations:

``CupyBackend``
    Real device memory via the CUDA runtime API. Uses ``cudaMalloc``, which
    NVIDIA documents as **not** clearing the returned memory — that
    documented behaviour is the subject of Memory Probe B (CHARTER.md §9.3).

``SimulatedBackend``
    A host-side model of a non-zeroing allocator with a reuse pool. Exists so
    that probe *logic* is testable in CI on machines with no GPU, and so the
    positive controls can be exercised without hardware.

    Results from the simulated backend are **not evidence**. Every record it
    produces is stamped ``backend_is_real=false``, and
    ``ResultBundle.clear_for_publication`` refuses any bundle carrying that
    stamp. Simulating residue and publishing it would be fabrication; the
    guard makes that a mechanical impossibility rather than a matter of
    discipline.

Neither backend ever returns bytes to a caller. Device-to-host copies write
directly into the writable view supplied by ``SafeBuffer.fill_via``.
"""

from __future__ import annotations

import ctypes
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from ..safety.errors import LimitExceeded
from ..safety.metadata import ascii_metadata
from ..safety.policy import MAX_ALLOCATION_BYTES

__all__ = [
    "DeviceAllocation",
    "CudaBackend",
    "CupyBackend",
    "PooledCupyBackend",
    "SimulatedBackend",
    "open_backend",
    "BackendUnavailable",
]

#: cudaMemcpyKind values used by the host<->device copy helpers below.
_MEMCPY_HOST_TO_DEVICE = 1
_MEMCPY_DEVICE_TO_HOST = 2


class BackendUnavailable(RuntimeError):
    """No usable CUDA backend on this machine."""


@dataclass(frozen=True)
class DeviceAllocation:
    """A device pointer we own. Opaque; never dereferenced on the host."""

    ptr: int
    size: int
    generation: int = 0


class CudaBackend(ABC):
    """Minimal device-memory interface required by the memory probes."""

    #: Short identifier recorded in result provenance.
    name: str = "abstract"

    #: False for anything whose results must never be published as evidence.
    is_real: bool = False

    #: How this backend allocates and frees, in the vocabulary the §13.1
    #: grader gates on. Declared by the backend rather than the probe,
    #: because it is the *allocator* that determines whether the driver is
    #: ever told the memory was released -- which is the whole distinction
    #: between a measurement and a control. See
    #: gpu_seal.reporting.MeasurementPath.
    measurement_path: str = "unknown"

    #: True for backends that source memory from a process-local caching
    #: allocator (CHARTER.md §9.4), where ``free()`` never reaches the driver.
    #: ``FrameworkAllocatorProbe`` requires this so §9.4 cannot accidentally
    #: be run against a raw-runtime backend and mislabelled as driver-independent.
    pooled: bool = False

    @abstractmethod
    def device_info(self) -> dict[str, str]:
        """Driver, runtime, and device metadata for the result bundle."""

    @abstractmethod
    def malloc(self, size: int) -> DeviceAllocation:
        """Allocate device memory with a NON-zeroing allocator."""

    @abstractmethod
    def free(self, alloc: DeviceAllocation) -> None: ...

    @abstractmethod
    def copy_to_host(self, alloc: DeviceAllocation, view: memoryview) -> None:
        """Copy device memory into a host view. The view belongs to a SafeBuffer."""

    @abstractmethod
    def write_to_device(
        self, alloc: DeviceAllocation, offset: int, data: bytes
    ) -> None:
        """Copy host bytes to device. Used only to plant our own canaries."""

    def write_canaries_to_device(
        self, alloc: DeviceAllocation, placements: list[tuple[int, bytes]]
    ) -> None:
        """Plant several canaries, with a batching hook for CUDA backends.

        The default preserves the simple backend contract. Real CUDA
        backends override this to turn the many tiny marker writes produced by
        a probe cycle into one contiguous host-to-device copy.
        """
        for offset, data in placements:
            self.write_to_device(alloc, offset, data)

    @abstractmethod
    def fill_device(self, alloc: DeviceAllocation, value: int) -> None:
        """Set every byte of the allocation. Used by negative controls."""

    def check_size(self, size: int) -> None:
        if size <= 0:
            raise ValueError("allocation size must be positive")
        if size > MAX_ALLOCATION_BYTES:
            raise LimitExceeded(
                f"{size} bytes exceeds MAX_ALLOCATION_BYTES "
                f"({MAX_ALLOCATION_BYTES}); CHARTER.md §16 test 12."
            )

    def close(self) -> None:  # pragma: no cover - overridden where needed
        return None

    def __enter__(self) -> CudaBackend:
        return self

    def __exit__(self, *exc: object) -> Literal[False]:
        self.close()
        return False


# ---------------------------------------------------------------------------
# Real CUDA
# ---------------------------------------------------------------------------


class CupyBackend(CudaBackend):
    """Real device memory via the CUDA runtime API, through CuPy.

    CuPy is used only as a thin binding to ``cudaMalloc`` / ``cudaFree`` /
    ``cudaMemcpy``. The probe deliberately does **not** use CuPy's own
    memory pool: the pool is a caching allocator, and a cached block handed
    back to us would be process-local reuse rather than anything the driver
    did. Distinguishing those two is the entire point of §9.3 vs §9.4, so we
    go to the runtime API directly.
    """

    name = "cupy"
    is_real = True
    pooled = False
    measurement_path = "driver_direct"

    _H2D = 1  # cudaMemcpyHostToDevice
    _D2H = 2  # cudaMemcpyDeviceToHost

    def __init__(self, device_id: int = 0) -> None:
        try:
            import cupy  # noqa: F401
            from cupy.cuda import runtime
        except ImportError as exc:  # pragma: no cover - depends on host
            raise BackendUnavailable(
                "CuPy is not installed. Install cupy-cuda12x, or use "
                "SimulatedBackend for logic tests without a GPU."
            ) from exc

        self._runtime = runtime
        self._device_id = device_id
        try:
            if runtime.getDeviceCount() <= device_id:
                raise BackendUnavailable(
                    f"CUDA device {device_id} not present "
                    f"({runtime.getDeviceCount()} visible)."
                )
            runtime.setDevice(device_id)
        except Exception as exc:  # pragma: no cover - depends on host
            raise BackendUnavailable(f"CUDA unavailable: {exc}") from exc

        self._generation = 0
        #: ptr -> size actually allocated by this backend instance. The sole
        #: source of truth for copy_to_host/write_to_device below — a caller
        #: cannot get this backend to touch device memory through a
        #: DeviceAllocation it did not itself hand out, however the pointer
        #: was obtained or guessed.
        self._live: dict[int, int] = {}

    def device_info(self) -> dict[str, str]:
        rt = self._runtime
        props = rt.getDeviceProperties(self._device_id)
        return {
            "backend": self.name,
            "backend_is_real": "true",
            "measurement_path": self.measurement_path,
            "device_id": str(self._device_id),
            # ascii_metadata refuses anything that is not short printable
            # ASCII, so this cannot become a general decoder. See
            # gpu_seal/safety/metadata.py.
            "device_name": ascii_metadata(
                props.get("name", "unknown"), field="device_name"
            ),
            "compute_capability": f"{props.get('major', '?')}.{props.get('minor', '?')}",
            "total_memory_bytes": str(props.get("totalGlobalMem", 0)),
            "cuda_runtime_version": str(rt.runtimeGetVersion()),
            "cuda_driver_version": str(rt.driverGetVersion()),
            "container_profile": os.environ.get(
                "GPU_SEAL_CONTAINER_PROFILE", "unspecified"
            ),
        }

    def malloc(self, size: int) -> DeviceAllocation:
        self.check_size(size)
        # cudaMalloc. NVIDIA: "The memory is not cleared."
        ptr = self._runtime.malloc(size)
        self._generation += 1
        self._live[ptr] = size
        return DeviceAllocation(ptr=ptr, size=size, generation=self._generation)

    def free(self, alloc: DeviceAllocation) -> None:
        if self._live.pop(alloc.ptr, None) is None:
            raise ValueError("double free or foreign pointer in CupyBackend")
        self._runtime.free(alloc.ptr)

    def _live_size(self, alloc: DeviceAllocation) -> int:
        """The size this backend actually allocated at ``alloc.ptr``.

        Refuses a ``DeviceAllocation`` this backend did not itself hand out
        via ``malloc()`` — a publicly-constructible ``ptr``/``size`` pair is
        not proof of ownership on its own.
        """
        live_size = self._live.get(alloc.ptr)
        if live_size is None:
            raise ValueError(
                "DeviceAllocation is not a live allocation from this "
                "CupyBackend instance; refusing to copy device memory "
                "through a pointer this backend did not itself hand out."
            )
        return live_size

    def copy_to_host(self, alloc: DeviceAllocation, view: memoryview) -> None:
        n = min(alloc.size, self._live_size(alloc), len(view))
        host_ptr = ctypes.addressof(ctypes.c_char.from_buffer(view))
        self._runtime.memcpy(host_ptr, alloc.ptr, n, self._D2H)

    def write_to_device(
        self, alloc: DeviceAllocation, offset: int, data: bytes
    ) -> None:
        live_size = self._live_size(alloc)
        if (
            offset < 0
            or offset + len(data) > alloc.size
            or offset + len(data) > live_size
        ):
            raise ValueError("canary write would overrun the allocation")
        src = ctypes.create_string_buffer(data, len(data))
        self._runtime.memcpy(
            alloc.ptr + offset, ctypes.addressof(src), len(data), self._H2D
        )

    def write_canaries_to_device(
        self, alloc: DeviceAllocation, placements: list[tuple[int, bytes]]
    ) -> None:
        live_size = self._live_size(alloc)
        if not placements:
            return

        payload_size = 0
        for offset, data in placements:
            if (
                offset < 0
                or offset + len(data) > alloc.size
                or offset + len(data) > live_size
            ):
                raise ValueError("canary write would overrun the allocation")
            payload_size = max(payload_size, offset + len(data))

        payload = bytearray(payload_size)
        for offset, data in placements:
            payload[offset : offset + len(data)] = data
        src = ctypes.create_string_buffer(bytes(payload), payload_size)
        self._runtime.memcpy(
            alloc.ptr, ctypes.addressof(src), payload_size, self._H2D
        )

    def fill_device(self, alloc: DeviceAllocation, value: int) -> None:
        n = min(alloc.size, self._live_size(alloc))
        self._runtime.memset(alloc.ptr, value, n)

    def close(self) -> None:
        try:
            self._runtime.deviceSynchronize()
        except Exception:  # pragma: no cover  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Real CUDA, through a caching allocator — CHARTER.md §9.4
# ---------------------------------------------------------------------------


class PooledCupyBackend(CudaBackend):
    """Real device memory via a private ``cupy.cuda.MemoryPool``.

    ``CupyBackend`` calls ``cudaMalloc``/``cudaFree`` directly so that a
    recovered canary says something about the **driver**. This backend does
    the opposite on purpose: it allocates through a caching allocator, so
    ``free()`` returns the block to the pool's own free list and the driver
    is never told the memory was released. The pool hands the same block
    back on the next allocation of a matching size, canary intact.

    That makes this backend the **detection-capability control** CHARTER.md
    §11 requires: a canary recovered here proves the harness can see a
    marker it planted, independent of anything the driver does. It is not
    evidence about driver or provider behaviour — see
    ``gpu_seal.probes.framework_allocator`` for why that distinction matters.

    The pool is a private instance, not CuPy's process-wide default
    allocator, so this backend's behaviour does not depend on, or leak into,
    any other CuPy usage in the same process.
    """

    name = "cupy_pooled"
    is_real = True
    pooled = True
    measurement_path = "framework_pooled"

    def __init__(self, device_id: int = 0) -> None:
        try:
            import cupy
            from cupy.cuda import MemoryPool, runtime
        except ImportError as exc:  # pragma: no cover - depends on host
            raise BackendUnavailable(
                "CuPy is not installed. Install cupy-cuda12x, or use "
                "SimulatedBackend for logic tests without a GPU."
            ) from exc

        self._cupy = cupy
        self._runtime = runtime
        self._device_id = device_id
        try:
            if runtime.getDeviceCount() <= device_id:
                raise BackendUnavailable(
                    f"CUDA device {device_id} not present "
                    f"({runtime.getDeviceCount()} visible)."
                )
            runtime.setDevice(device_id)
        except Exception as exc:  # pragma: no cover - depends on host
            raise BackendUnavailable(f"CUDA unavailable: {exc}") from exc

        self._pool = MemoryPool()
        # Keeps each live MemoryPointer referenced. Dropping the reference in
        # free() is what returns the block to the pool -- cudaFree is never
        # called from here.
        self._live: dict[int, object] = {}
        #: ptr -> size requested at malloc() time. free()'s ownership check
        #: already guards the pool; this is the same guard extended to reads
        #: and writes, so copy_to_host/write_to_device also refuse a
        #: DeviceAllocation this backend did not itself hand out.
        self._live_sizes: dict[int, int] = {}
        self._generation = 0

    def device_info(self) -> dict[str, str]:
        rt = self._runtime
        props = rt.getDeviceProperties(self._device_id)
        return {
            "backend": self.name,
            "backend_is_real": "true",
            "measurement_path": self.measurement_path,
            "device_id": str(self._device_id),
            "device_name": ascii_metadata(
                props.get("name", "unknown"), field="device_name"
            ),
            "compute_capability": f"{props.get('major', '?')}.{props.get('minor', '?')}",
            "total_memory_bytes": str(props.get("totalGlobalMem", 0)),
            "cuda_runtime_version": str(rt.runtimeGetVersion()),
            "cuda_driver_version": str(rt.driverGetVersion()),
            "container_profile": os.environ.get(
                "GPU_SEAL_CONTAINER_PROFILE", "unspecified"
            ),
            "allocator": "cupy.cuda.MemoryPool",
            "framework": "cupy",
            "framework_version": str(self._cupy.__version__),
            "pool_used_bytes": str(self._pool.used_bytes()),
            "pool_total_bytes": str(self._pool.total_bytes()),
        }

    def malloc(self, size: int) -> DeviceAllocation:
        self.check_size(size)
        memptr = self._pool.malloc(size)
        self._generation += 1
        self._live[memptr.ptr] = memptr
        self._live_sizes[memptr.ptr] = size
        return DeviceAllocation(ptr=memptr.ptr, size=size, generation=self._generation)

    def free(self, alloc: DeviceAllocation) -> None:
        if self._live.pop(alloc.ptr, None) is None:
            raise ValueError("double free or foreign pointer in PooledCupyBackend")
        self._live_sizes.pop(alloc.ptr, None)
        # The MemoryPointer's refcount just dropped to zero (or to whatever
        # else holds it, which should be nothing); the pool reclaims the
        # block onto its free list. No cudaFree happens here.

    def _live_size(self, alloc: DeviceAllocation) -> int:
        """The size this backend actually allocated at ``alloc.ptr``.

        ``free()`` already checks pool ownership; this is the same check
        extended to reads and writes, which previously trusted a
        publicly-constructible ``DeviceAllocation`` outright.
        """
        live_size = self._live_sizes.get(alloc.ptr)
        if live_size is None:
            raise ValueError(
                "DeviceAllocation is not a live allocation from this "
                "PooledCupyBackend instance; refusing to copy device memory "
                "through a pointer this backend did not itself hand out."
            )
        return live_size

    def copy_to_host(self, alloc: DeviceAllocation, view: memoryview) -> None:
        n = min(alloc.size, self._live_size(alloc), len(view))
        host_ptr = ctypes.addressof(ctypes.c_char.from_buffer(view))
        self._runtime.memcpy(host_ptr, alloc.ptr, n, _MEMCPY_DEVICE_TO_HOST)

    def write_to_device(
        self, alloc: DeviceAllocation, offset: int, data: bytes
    ) -> None:
        live_size = self._live_size(alloc)
        if (
            offset < 0
            or offset + len(data) > alloc.size
            or offset + len(data) > live_size
        ):
            raise ValueError("canary write would overrun the allocation")
        src = ctypes.create_string_buffer(data, len(data))
        self._runtime.memcpy(
            alloc.ptr + offset, ctypes.addressof(src), len(data), _MEMCPY_HOST_TO_DEVICE
        )

    def write_canaries_to_device(
        self, alloc: DeviceAllocation, placements: list[tuple[int, bytes]]
    ) -> None:
        live_size = self._live_size(alloc)
        if not placements:
            return

        payload_size = 0
        for offset, data in placements:
            if (
                offset < 0
                or offset + len(data) > alloc.size
                or offset + len(data) > live_size
            ):
                raise ValueError("canary write would overrun the allocation")
            payload_size = max(payload_size, offset + len(data))

        payload = bytearray(payload_size)
        for offset, data in placements:
            payload[offset : offset + len(data)] = data
        src = ctypes.create_string_buffer(bytes(payload), payload_size)
        self._runtime.memcpy(
            alloc.ptr, ctypes.addressof(src), payload_size, _MEMCPY_HOST_TO_DEVICE
        )

    def fill_device(self, alloc: DeviceAllocation, value: int) -> None:
        n = min(alloc.size, self._live_size(alloc))
        self._runtime.memset(alloc.ptr, value, n)

    def close(self) -> None:
        try:
            self._live.clear()
            self._live_sizes.clear()
            self._pool.free_all_blocks()
            self._runtime.deviceSynchronize()
        except Exception:  # pragma: no cover  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


class SimulatedBackend(CudaBackend):
    """Host-side model of a non-zeroing allocator. NOT A MEASUREMENT DEVICE.

    Models the one behaviour §9.3 is about: freed memory is returned to a
    pool and handed back on a later allocation of the same size, with its
    previous contents intact.

    ``sanitises_on_free`` flips that: the pool is zeroed on free, modelling a
    provider that scrubs. Together the two modes give a positive and a
    negative control that run anywhere, which is what lets probe logic be
    tested in CI on machines with no GPU.

    What it does not and cannot model: driver behaviour, real allocator
    granularity, MIG, scheduling, or anything a provider actually does. It
    tests our code, not the world.
    """

    name = "simulated"
    is_real = False
    measurement_path = "simulated"
    # A free-list pool that hands back the same offset's prior contents on
    # reuse is exactly the §9.4 caching-allocator model, so probe logic for
    # both §9.3's positive control and FrameworkAllocatorProbe can be tested
    # against it without hardware.
    pooled = True

    def __init__(
        self,
        *,
        sanitises_on_free: bool = False,
        pool_bytes: int = 64 * 1024 * 1024,
        seed: int = 0,
    ) -> None:
        self._sanitises = sanitises_on_free
        self._pool_bytes = pool_bytes
        self._free_list: list[tuple[int, int]] = [(0, pool_bytes)]
        self._live: dict[int, tuple[int, int]] = {}
        self._generation = 0

        # Deterministic non-zero background, so "not zero" alone is never
        # mistaken for "residue" in a test. Only an authenticated canary counts.
        #
        # Built by tiling a 4 KiB block rather than filling byte by byte: the
        # naive loop cost ~25 s of test time on a 16 MiB pool. The background
        # only needs to be non-zero and reproducible, not statistically ideal.
        block = bytearray(4096)
        state = seed or 0x5EA1
        for i in range(0, 4096, 8):
            state = (
                state * 6364136223846793005 + 1442695040888963407
            ) & 0xFFFFFFFFFFFFFFFF
            block[i : i + 8] = (state >> 8).to_bytes(8, "little")
        reps = -(-pool_bytes // 4096)
        self._pool = bytearray(block * reps)[:pool_bytes]

    def device_info(self) -> dict[str, str]:
        return {
            "backend": self.name,
            "backend_is_real": "false",
            "measurement_path": self.measurement_path,
            "simulation_sanitises_on_free": str(self._sanitises).lower(),
            "pool_bytes": str(self._pool_bytes),
            "container_profile": os.environ.get(
                "GPU_SEAL_CONTAINER_PROFILE", "unspecified"
            ),
        }

    def malloc(self, size: int) -> DeviceAllocation:
        self.check_size(size)
        for idx, (offset, length) in enumerate(self._free_list):
            if length >= size:
                if length == size:
                    self._free_list.pop(idx)
                else:
                    self._free_list[idx] = (offset + size, length - size)
                self._generation += 1
                handle = offset + 1  # non-zero pseudo-pointer
                self._live[handle] = (offset, size)
                return DeviceAllocation(
                    ptr=handle, size=size, generation=self._generation
                )
        raise MemoryError(
            f"simulated pool exhausted: {size} bytes requested, "
            f"largest free block {max((n for _, n in self._free_list), default=0)}"
        )

    def free(self, alloc: DeviceAllocation) -> None:
        span = self._live.pop(alloc.ptr, None)
        if span is None:
            raise ValueError("double free or foreign pointer in simulated backend")
        offset, size = span
        if self._sanitises:
            # Modelling a provider that scrubs on release. Slice assignment,
            # not a byte loop — the loop version made an 8 MiB scrub take
            # tens of seconds and timed out the Phase 1 battery.
            self._pool[offset : offset + size] = bytes(size)
        self._free_list.append((offset, size))
        self._free_list.sort()
        self._coalesce()

    def _coalesce(self) -> None:
        merged: list[tuple[int, int]] = []
        for offset, length in self._free_list:
            if merged and merged[-1][0] + merged[-1][1] == offset:
                prev_off, prev_len = merged[-1]
                merged[-1] = (prev_off, prev_len + length)
            else:
                merged.append((offset, length))
        self._free_list = merged

    def _span(self, alloc: DeviceAllocation) -> tuple[int, int]:
        span = self._live.get(alloc.ptr)
        if span is None:
            raise ValueError("use of a freed or foreign simulated allocation")
        return span

    def copy_to_host(self, alloc: DeviceAllocation, view: memoryview) -> None:
        offset, size = self._span(alloc)
        n = min(size, len(view))
        view[:n] = self._pool[offset : offset + n]

    def write_to_device(
        self, alloc: DeviceAllocation, offset: int, data: bytes
    ) -> None:
        base, size = self._span(alloc)
        if offset + len(data) > size:
            raise ValueError("canary write would overrun the allocation")
        self._pool[base + offset : base + offset + len(data)] = data

    def fill_device(self, alloc: DeviceAllocation, value: int) -> None:
        base, size = self._span(alloc)
        self._pool[base : base + size] = bytes([value & 0xFF]) * size


# ---------------------------------------------------------------------------


def open_backend(
    prefer_real: bool = True, device_id: int = 0, **sim_kwargs: object
) -> CudaBackend:
    """Open the best available backend.

    With ``prefer_real=True`` this tries CUDA and falls back to simulation.
    The fallback is *not* silent in the results: the record carries
    ``backend_is_real=false`` and the bundle cannot be published.
    """
    if prefer_real:
        try:
            return CupyBackend(device_id=device_id)
        except BackendUnavailable:
            pass
    return SimulatedBackend(**sim_kwargs)  # type: ignore[arg-type]


def describe_available() -> dict[str, str | None]:
    """Diagnostic summary of what this machine can do. Used by the smoke runner."""
    info: dict[str, str | None] = {"cupy": None, "cuda_devices": None}
    try:
        import cupy
        from cupy.cuda import runtime

        info["cupy"] = cupy.__version__
        info["cuda_devices"] = str(runtime.getDeviceCount())
    except Exception as exc:  # noqa: BLE001
        info["cupy"] = f"unavailable: {type(exc).__name__}"
    return info
