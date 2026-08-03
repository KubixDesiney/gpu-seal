"""Minimal NVML binding — CHARTER.md §9.1, §9.6.

The management library answers questions the CUDA runtime cannot: how many
devices the tenant can *see* (as opposed to use), whether MIG is enabled, and
whether the tenant can enumerate compute processes belonging to somebody else.
That last one is the §13.2 grade-D signal, and it is the reason this module
exists at all.

Deliberate design choices:

**ctypes, not a subprocess.** Shelling out to ``nvidia-smi`` and parsing its
output would mean text-processing whatever the environment hands back, in a
project whose entire premise is not doing that. A library call returns typed
values.

**No third-party dependency.** ``pynvml`` would do this job, but NVML is a
stable C ABI and the four calls needed here are not worth another pinned
dependency in a container that has to be reproducible.

**Counts, never identities.** ``compute_process_count`` returns how many
processes NVML was willing to describe. It does not return their PIDs, names,
or memory usage, and there is no accessor that does. Learning that isolation
is weak requires knowing *that* a neighbour is visible; it does not require
knowing anything about the neighbour, and CHARTER.md §4.3 forbids reading
another tenant's process metadata even when the interface offers it.

Every entry point degrades to "unavailable" rather than raising. NVML being
absent is itself an observation (§9.6 ``secure_restriction`` or
``not_testable``), not an error.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from ..safety.metadata import ascii_metadata, stable_hash

__all__ = ["NvmlSnapshot", "read_nvml"]

_NVML_SUCCESS = 0
_UUID_BUFFER_BYTES = 96

#: nvmlDeviceGetMigMode out-parameter values.
_MIG_DISABLED = 0

#: Candidate sonames, in the order NVIDIA ships them.
_LIBRARY_NAMES = ("libnvidia-ml.so.1", "libnvidia-ml.so", "nvml.dll")


@dataclass(frozen=True)
class NvmlSnapshot:
    """What the management library was willing to tell an ordinary tenant."""

    available: bool

    #: Devices NVML enumerates. May exceed the CUDA-visible count when the
    #: container restricts CUDA but not NVML — which is itself the finding.
    device_count: int | None = None

    #: ``True``/``False`` when readable, ``None`` when the query was refused.
    mig_enabled: bool | None = None

    #: Hashed per CHARTER.md §10 — a stable GPU UUID is never published clear.
    gpu_uuid_hash: str | None = None

    #: Number of compute processes NVML described, or ``None`` if refused.
    #: A refusal here is correct behaviour, not a failure.
    compute_process_count: int | None = None

    #: Why the snapshot is empty, when it is.
    unavailable_reason: str | None = None


def _load_library() -> ctypes.CDLL | None:
    for name in _LIBRARY_NAMES:
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    return None


def read_nvml(device_index: int = 0) -> NvmlSnapshot:
    """Take one NVML snapshot. Never raises; absence is an observation."""
    lib = _load_library()
    if lib is None:
        return NvmlSnapshot(
            available=False,
            unavailable_reason="the management library is not present on this host",
        )

    try:
        if lib.nvmlInit_v2() != _NVML_SUCCESS:
            return NvmlSnapshot(
                available=False,
                unavailable_reason="the management library declined to initialise",
            )
    except (AttributeError, OSError) as exc:
        return NvmlSnapshot(
            available=False,
            unavailable_reason=f"initialisation failed: {type(exc).__name__}",
        )

    try:
        return _collect(lib, device_index)
    finally:
        try:
            lib.nvmlShutdown()
        except (AttributeError, OSError):  # pragma: no cover - teardown
            pass


def _collect(lib: ctypes.CDLL, device_index: int) -> NvmlSnapshot:
    count = ctypes.c_uint(0)
    if lib.nvmlDeviceGetCount_v2(ctypes.byref(count)) != _NVML_SUCCESS:
        return NvmlSnapshot(
            available=True,
            unavailable_reason="device enumeration was refused",
        )

    handle = ctypes.c_void_p()
    got_handle = (
        lib.nvmlDeviceGetHandleByIndex_v2(
            ctypes.c_uint(device_index), ctypes.byref(handle)
        )
        == _NVML_SUCCESS
    )
    if not got_handle:
        return NvmlSnapshot(available=True, device_count=int(count.value))

    return NvmlSnapshot(
        available=True,
        device_count=int(count.value),
        mig_enabled=_read_mig_mode(lib, handle),
        gpu_uuid_hash=_read_uuid_hash(lib, handle),
        compute_process_count=_read_process_count(lib, handle),
    )


def _read_mig_mode(lib: ctypes.CDLL, handle: ctypes.c_void_p) -> bool | None:
    current = ctypes.c_uint(0)
    pending = ctypes.c_uint(0)
    try:
        rc = lib.nvmlDeviceGetMigMode(
            handle, ctypes.byref(current), ctypes.byref(pending)
        )
    except (AttributeError, OSError):  # pragma: no cover - old driver
        return None
    if rc != _NVML_SUCCESS:
        # Not supported on consumer silicon, and refused on some managed
        # instances. Both are "we do not know", not "MIG is off".
        return None
    return current.value != _MIG_DISABLED


def _read_uuid_hash(lib: ctypes.CDLL, handle: ctypes.c_void_p) -> str | None:
    buf = ctypes.create_string_buffer(_UUID_BUFFER_BYTES)
    try:
        rc = lib.nvmlDeviceGetUUID(handle, buf, ctypes.c_uint(_UUID_BUFFER_BYTES))
    except (AttributeError, OSError):  # pragma: no cover - old driver
        return None
    if rc != _NVML_SUCCESS:
        return None
    # ascii_metadata refuses anything that is not short printable ASCII, so
    # this cannot become a general decoder even though NVML hands back bytes.
    text = ascii_metadata(buf.value, field="gpu_uuid")
    if not text:
        return None
    return stable_hash(text, domain="gpu_uuid")


def _read_process_count(lib: ctypes.CDLL, handle: ctypes.c_void_p) -> int | None:
    """How many compute processes NVML will describe to this tenant.

    Called with a zero-length output array on purpose. NVML answers that with
    ``NVML_ERROR_INSUFFICIENT_SIZE`` and writes the required count into the
    in/out parameter — so the count comes back and the per-process structures
    never do. There is no buffer here for them to be written into, which makes
    "we did not read neighbour process metadata" a property of the call rather
    than a promise about what we did with it afterwards.
    """
    count = ctypes.c_uint(0)
    try:
        lib.nvmlDeviceGetComputeRunningProcesses_v3(
            handle, ctypes.byref(count), None
        )
    except (AttributeError, OSError):  # pragma: no cover - old driver
        return None
    return int(count.value)
