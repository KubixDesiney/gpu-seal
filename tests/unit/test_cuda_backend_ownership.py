"""CupyBackend / PooledCupyBackend must refuse to copy device memory through
a DeviceAllocation they did not themselves hand out via malloc().

DeviceAllocation is a publicly-constructible frozen dataclass (just a
ptr/size/generation tuple), so nothing about it proves the pointer is real,
live, or owned by this backend instance. These tests run against a faked
``cupy.cuda.runtime``/``MemoryPool`` — there is no GPU in this environment —
so they exercise the ownership bookkeeping directly rather than real CUDA.
"""

from __future__ import annotations

import sys
import types

import pytest

from gpu_seal.cuda.backend import CupyBackend, DeviceAllocation, PooledCupyBackend


class _FakeRuntime:
    """Just enough of cupy.cuda.runtime to construct and drive a backend."""

    def __init__(self) -> None:
        self._next_ptr = 0x1000
        self.memcpy_calls: list[tuple[int, int, int, int]] = []

    def getDeviceCount(self) -> int:
        return 1

    def setDevice(self, device_id: int) -> None:
        return None

    def getDeviceProperties(self, device_id: int) -> dict:
        return {
            "name": b"Fake GPU",
            "major": 8,
            "minor": 6,
            "totalGlobalMem": 4 * 1024**3,
        }

    def runtimeGetVersion(self) -> int:
        return 12060

    def driverGetVersion(self) -> int:
        return 12060

    def deviceSynchronize(self) -> None:
        return None

    def malloc(self, size: int) -> int:
        ptr = self._next_ptr
        self._next_ptr += size + 4096  # leave a gap, like a real allocator
        return ptr

    def free(self, ptr: int) -> None:
        return None

    def memcpy(self, dst: int, src: int, size: int, kind: int) -> None:
        self.memcpy_calls.append((dst, src, size, kind))


class _FakeMemoryPointer:
    def __init__(self, ptr: int) -> None:
        self.ptr = ptr


class _FakeMemoryPool:
    def __init__(self) -> None:
        self._next_ptr = 0x9000

    def malloc(self, size: int) -> _FakeMemoryPointer:
        ptr = self._next_ptr
        self._next_ptr += size + 4096
        return _FakeMemoryPointer(ptr)

    def used_bytes(self) -> int:
        return 0

    def total_bytes(self) -> int:
        return 0

    def free_all_blocks(self) -> None:
        return None


@pytest.fixture
def fake_cupy(monkeypatch):
    """Install a fake cupy.cuda module tree so CupyBackend/PooledCupyBackend
    construct without a real GPU, and return the fake runtime for assertions.
    """
    runtime = _FakeRuntime()

    cupy_module = types.ModuleType("cupy")
    cupy_module.__version__ = "0.0.0-fake"
    cuda_module = types.ModuleType("cupy.cuda")
    cuda_module.runtime = runtime
    cuda_module.MemoryPool = _FakeMemoryPool
    cupy_module.cuda = cuda_module

    monkeypatch.setitem(sys.modules, "cupy", cupy_module)
    monkeypatch.setitem(sys.modules, "cupy.cuda", cuda_module)
    return runtime


def test_cupy_backend_refuses_a_forged_device_allocation(fake_cupy):
    backend = CupyBackend(device_id=0)
    real = backend.malloc(64)

    forged = DeviceAllocation(ptr=0xDEAD_BEEF, size=64, generation=real.generation)
    view = bytearray(64)
    with pytest.raises(ValueError, match="not a live allocation"):
        backend.copy_to_host(forged, memoryview(view))
    assert fake_cupy.memcpy_calls == [], "no copy should happen for a forged pointer"


def test_cupy_backend_allows_a_real_allocation(fake_cupy):
    backend = CupyBackend(device_id=0)
    real = backend.malloc(64)
    view = bytearray(64)
    backend.copy_to_host(real, memoryview(view))
    assert len(fake_cupy.memcpy_calls) == 1


def test_cupy_backend_refuses_a_freed_allocation(fake_cupy):
    backend = CupyBackend(device_id=0)
    real = backend.malloc(64)
    backend.free(real)
    view = bytearray(64)
    with pytest.raises(ValueError, match="not a live allocation"):
        backend.copy_to_host(real, memoryview(view))


def test_cupy_backend_clamps_a_claimed_size_larger_than_the_real_allocation(fake_cupy):
    """A caller could hold a real, live pointer but lie about its size to try
    to read past the actual allocation. The copy must be clamped."""
    backend = CupyBackend(device_id=0)
    real = backend.malloc(16)
    oversized = DeviceAllocation(ptr=real.ptr, size=4096, generation=real.generation)
    view = bytearray(4096)
    backend.copy_to_host(oversized, memoryview(view))
    (_, _, copied_size, _) = fake_cupy.memcpy_calls[0]
    assert copied_size == 16


def test_pooled_backend_refuses_a_forged_device_allocation(fake_cupy):
    backend = PooledCupyBackend(device_id=0)
    real = backend.malloc(64)

    forged = DeviceAllocation(ptr=0xDEAD_BEEF, size=64, generation=real.generation)
    view = bytearray(64)
    with pytest.raises(ValueError, match="not a live allocation"):
        backend.copy_to_host(forged, memoryview(view))
    assert fake_cupy.memcpy_calls == []


def test_pooled_backend_refuses_a_freed_allocation(fake_cupy):
    backend = PooledCupyBackend(device_id=0)
    real = backend.malloc(64)
    backend.free(real)
    view = bytearray(64)
    with pytest.raises(ValueError, match="not a live allocation"):
        backend.copy_to_host(real, memoryview(view))


def test_pooled_backend_clamps_a_claimed_size_larger_than_the_real_allocation(fake_cupy):
    backend = PooledCupyBackend(device_id=0)
    real = backend.malloc(16)
    oversized = DeviceAllocation(ptr=real.ptr, size=4096, generation=real.generation)
    view = bytearray(4096)
    backend.copy_to_host(oversized, memoryview(view))
    (_, _, copied_size, _) = fake_cupy.memcpy_calls[0]
    assert copied_size == 16


def test_pooled_backend_write_refuses_a_forged_allocation(fake_cupy):
    backend = PooledCupyBackend(device_id=0)
    real = backend.malloc(64)
    forged = DeviceAllocation(ptr=0xDEAD_BEEF, size=64, generation=real.generation)
    with pytest.raises(ValueError, match="not a live allocation"):
        backend.write_to_device(forged, 0, b"ABCD")
    assert fake_cupy.memcpy_calls == []
