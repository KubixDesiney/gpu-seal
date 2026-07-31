"""CUDA device access.

Two backends: real device memory via the CUDA runtime API, and a host-side
simulation used only to test probe logic where no GPU exists.

Simulated results are stamped ``backend_is_real=false`` and cannot be cleared
for publication. See :mod:`gpu_seal.cuda.backend`.
"""

from .backend import (
    BackendUnavailable,
    CudaBackend,
    CupyBackend,
    DeviceAllocation,
    SimulatedBackend,
    describe_available,
    open_backend,
)

__all__ = [
    "CudaBackend",
    "CupyBackend",
    "SimulatedBackend",
    "DeviceAllocation",
    "BackendUnavailable",
    "open_backend",
    "describe_available",
]
