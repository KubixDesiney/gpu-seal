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
from typing import Dict, List, Optional, Tuple

from ..safety.errors import LimitExceeded
from ..safety.metadata import ascii_metadata
from ..safety.policy import MAX_ALLOCATION_BYTES

__all__ = [
    "DeviceAllocation",
    "CudaBackend",
    "CupyBackend",
    "SimulatedBackend",
    "open_backend",
    "BackendUnavailable",
]


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

    @abstractmethod
    def device_info(self) -> Dict[str, str]:
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

    def __enter__(self) -> "CudaBackend":
        return self

    def __exit__(self, *exc: object) -> bool:
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

    def device_info(self) -> Dict[str, str]:
        rt = self._runtime
        props = rt.getDeviceProperties(self._device_id)
        return {
            "backend": self.name,
            "backend_is_real": "true",
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
        return DeviceAllocation(ptr=ptr, size=size, generation=self._generation)

    def free(self, alloc: DeviceAllocation) -> None:
        self._runtime.free(alloc.ptr)

    def copy_to_host(self, alloc: DeviceAllocation, view: memoryview) -> None:
        n = min(alloc.size, len(view))
        host_ptr = ctypes.addressof(ctypes.c_char.from_buffer(view))
        self._runtime.memcpy(host_ptr, alloc.ptr, n, self._D2H)

    def write_to_device(
        self, alloc: DeviceAllocation, offset: int, data: bytes
    ) -> None:
        if offset + len(data) > alloc.size:
            raise ValueError("canary write would overrun the allocation")
        src = ctypes.create_string_buffer(data, len(data))
        self._runtime.memcpy(
            alloc.ptr + offset, ctypes.addressof(src), len(data), self._H2D
        )

    def fill_device(self, alloc: DeviceAllocation, value: int) -> None:
        self._runtime.memset(alloc.ptr, value, alloc.size)

    def close(self) -> None:
        try:
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

    def __init__(
        self,
        *,
        sanitises_on_free: bool = False,
        pool_bytes: int = 64 * 1024 * 1024,
        seed: int = 0,
    ) -> None:
        self._sanitises = sanitises_on_free
        self._pool_bytes = pool_bytes
        self._free_list: List[Tuple[int, int]] = [(0, pool_bytes)]
        self._live: Dict[int, Tuple[int, int]] = {}
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

    def device_info(self) -> Dict[str, str]:
        return {
            "backend": self.name,
            "backend_is_real": "false",
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
        merged: List[Tuple[int, int]] = []
        for offset, length in self._free_list:
            if merged and merged[-1][0] + merged[-1][1] == offset:
                prev_off, prev_len = merged[-1]
                merged[-1] = (prev_off, prev_len + length)
            else:
                merged.append((offset, length))
        self._free_list = merged

    def _span(self, alloc: DeviceAllocation) -> Tuple[int, int]:
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


def describe_available() -> Dict[str, Optional[str]]:
    """Diagnostic summary of what this machine can do. Used by the smoke runner."""
    info: Dict[str, Optional[str]] = {"cupy": None, "cuda_devices": None}
    try:
        import cupy
        from cupy.cuda import runtime

        info["cupy"] = cupy.__version__
        info["cuda_devices"] = str(runtime.getDeviceCount())
    except Exception as exc:  # noqa: BLE001
        info["cupy"] = f"unavailable: {type(exc).__name__}"
    return info
