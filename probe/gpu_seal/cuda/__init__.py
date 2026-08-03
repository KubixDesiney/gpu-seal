"""CUDA device access.

Three backends: real device memory via the raw CUDA runtime API
(``CupyBackend``, §9.3 — bypasses any pool so results speak to the driver),
real device memory via a private caching allocator (``PooledCupyBackend``,
§9.4 — results speak to the harness's own detection capability, not the
driver), and a host-side simulation used only to test probe logic where no
GPU exists.

Simulated results are stamped ``backend_is_real=false`` and cannot be cleared
for publication. See :mod:`gpu_seal.cuda.backend`.
"""

from .backend import (
    BackendUnavailable,
    CudaBackend,
    CupyBackend,
    DeviceAllocation,
    PooledCupyBackend,
    SimulatedBackend,
    describe_available,
    open_backend,
)

__all__ = [
    "CudaBackend",
    "CupyBackend",
    "PooledCupyBackend",
    "SimulatedBackend",
    "DeviceAllocation",
    "BackendUnavailable",
    "open_backend",
    "describe_available",
]
