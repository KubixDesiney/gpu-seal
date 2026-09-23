#!/usr/bin/env python3
"""§9.12 MIG temporal-isolation experiment — CHARTER.md §9.12, contribution D2.

    python3 lab/cloud-runner/run_mig_isolation.py \\
        --gpu-instance-profile-id 9 --compute-instance-profile-id 0 \\
        --exclusive-possession-attestation "sole tenant, bare-metal A100, \\
confirmed via nvidia-smi -a" \\
        --unsafe-development-ephemeral --out ./out

For a researcher-owned (or researcher-controlled, root-having) A100 or H100.
Unlike ``probe/gpu_seal/probes/mig_temporal.py``, whose own docstring is
explicit that "lifecycle is the operator's, not the probe's" — MIG create/
destroy is left to a human between two probe calls — this script *is* that
operator, driving the whole lifecycle end to end because it runs with root on
hardware the researcher controls. It never uses ``nvidia-smi`` text parsing;
every MIG management call goes through NVML via ``ctypes``, matching
``gpu_seal.cuda.nvml``'s own "ctypes, not a subprocess" convention.

Sequence, every step recorded as its own timestamped observation:

    1. Assert MIG capability (NVML ``nvmlDeviceGetMigMode`` must be a
       supported query). Refuse otherwise — see ``_assert_capability`` below.
       ``MigTemporalProbe`` enforces the same refusal a second time, inside
       every worker process, for every plant and every measurement
       (``require_mig=True``, never weakened to ``False``): a mutation case
       in ``lab/verify-safety-suite.sh`` proves that guard fires, and this
       script relies on it firing rather than disabling it.
    2. Enable MIG mode; record the before/after state (``MigModeChange``).
    3. Create a GPU instance and a compute instance. Profile IDs are recorded
       in the clear (they are not identifiers, just a slice size choice).
       Instance UUIDs are hashed with ``gpu_seal.safety.metadata.stable_hash``
       before they are ever recorded — see ``_resolve_mig_device`` for the
       one place the raw UUID is held, transiently, only to address a tenant
       subprocess, and never logged, printed, or returned.
    4. Inside a subprocess scoped to that instance (its own ``CUDA_VISIBLE_
       DEVICES``, a fresh CUDA context), allocate and fill owned canaries —
       ``MigTemporalProbe.plant()``, which reaches ``SafeBuffer`` machinery
       the same way every other probe does.
    5. Destroy the compute instance and the GPU instance.
    6. Recreate them with the same profile (or, if ``--different-*-profile-
       id`` is given, a different one — a second, separately reported
       boundary).
    7. In a fresh subprocess scoped to the *new* instance, read before
       writing. The search is ``CanarySet.search()`` restricted to exactly
       the allocation IDs ``plant()`` minted (``PlantReceipt.
       canary_allocation_ids``) — there is no caller-supplied pattern API
       anywhere in this file, and static analysis over ``probe/`` rejects one
       being added there.
    8. Aggregate per boundary (never pooled — see ``mig_temporal.summarise``)
       sign, and write. MIG mode is always restored to what it was before
       this script touched it, including on failure (the outermost
       ``finally`` in ``main()``).

The destroy→recreate boundary itself is recorded as an explicit field
(``DestroyRecreateBoundary``, folded into ``bundle.environment["mig_
lifecycle"]``) separately from the plant/measure statistics, because
docs/STATUS.md's MIG row requires exactly that: "destroy/recreate boundaries
recorded separately" for the claim to count.

**Only GPU teardown (MIG_SAME_PROFILE / MIG_DIFFERENT_PROFILE) is automated
here.** GPU-wide function-level reset, driver reload, and host reboot are
three different mechanisms (CHARTER.md §9.12) that this script's own process
cannot survive to drive — a rebooted host has no script left running. Those
three boundaries stay operator-driven across two separate invocations, the
same as ``mig_temporal.py`` already documents; this script does not attempt
to automate them.

**Testing without hardware.** ``FakeMigRuntime`` is a driver-level double for
the whole MIG lifecycle — the way ``DeterministicFakeRuntime``
(``gpu_seal.controller.fake_runtime``) stands in for the native provider
path. It never touches NVML or CUDA, but it *does* exercise the real
``plant()`` / ``measure_successor()`` / ``CanarySet`` round-trip, against
``SimulatedBackend``, by calling the exact same ``_execute_worker`` function
the real subprocess path calls. See ``tests/unit/test_run_mig_isolation.py``.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "probe"))

from gpu_seal import __version__  # noqa: E402
from gpu_seal.controller.evidence_store import EvidenceStore  # noqa: E402
from gpu_seal.cuda.backend import (  # noqa: E402
    CudaBackend,
    CupyBackend,
    SimulatedBackend,
)
from gpu_seal.cuda.nvml import NvmlSnapshot, read_nvml  # noqa: E402
from gpu_seal.evidence import key_source_from_options, signing_metadata  # noqa: E402
from gpu_seal.evidence.result import ResultBundle, ToolProvenance  # noqa: E402
from gpu_seal.probes import ExclusivityEvidence, MigTemporalProbe, MigUnavailable  # noqa: E402
from gpu_seal.probes.mig_temporal import (  # noqa: E402
    MigBoundaryResult,
    PlantReceipt,
)
from gpu_seal.probes.mig_temporal import summarise as summarise_mig  # noqa: E402
from gpu_seal.safety import (  # noqa: E402
    Boundary,
    CampaignControl,
    CanarySet,
    RunBudget,
    RunBudgetExceeded,
)
from gpu_seal.safety.aggregation import CanaryOnlyRecord, RedactedStopRecord  # noqa: E402
from gpu_seal.safety.canary import Canary  # noqa: E402
from gpu_seal.safety.errors import CampaignTerminated  # noqa: E402
from gpu_seal.safety.metadata import ascii_metadata, stable_hash  # noqa: E402

__all__ = [
    "MigCapability",
    "MigModeChange",
    "MigInstanceHandle",
    "DestroyRecreateBoundary",
    "TenantCommandResult",
    "MigRuntime",
    "NvmlMigRuntime",
    "FakeMigRuntime",
    "MigLifecycleError",
    "run_boundary_cycle",
]

MIB = 1 << 20
_NVML_SUCCESS = 0
_MIG_DISABLED = 0
_LIBRARY_NAMES = ("libnvidia-ml.so.1", "libnvidia-ml.so", "nvml.dll")
_UUID_BUFFER_BYTES = 96


class MigLifecycleError(RuntimeError):
    """An NVML MIG management call failed. Not an ethics-model violation —
    a plain operational failure, the MIG equivalent of ``BackendUnavailable``.
    """


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MigCapability:
    """Step 1's answer. ``available=False`` means: refuse, do not proceed."""

    available: bool
    reason: str


@dataclass(frozen=True)
class MigModeChange:
    """Step 2's before/after record."""

    before: bool | None
    after: bool | None

    @property
    def changed(self) -> bool:
        return self.before != self.after

    def to_dict(self) -> dict[str, Any]:
        return {"before": self.before, "after": self.after, "changed": self.changed}


@dataclass(frozen=True)
class MigInstanceHandle:
    """One created GPU instance + compute instance pair.

    Never carries a raw UUID — only ``stable_hash``-ed ones (CHARTER.md §10).
    Profile IDs and NVML-assigned integer instance IDs are not identifiers in
    the §10 sense (they do not name a specific physical device across runs)
    and are recorded in the clear.
    """

    gpu_instance_profile_id: int
    compute_instance_profile_id: int
    gpu_instance_id: int
    compute_instance_id: int
    gpu_instance_uuid_hash: str | None
    compute_instance_uuid_hash: str | None
    created_monotonic: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "gpu_instance_profile_id": self.gpu_instance_profile_id,
            "compute_instance_profile_id": self.compute_instance_profile_id,
            "gpu_instance_id": self.gpu_instance_id,
            "compute_instance_id": self.compute_instance_id,
            "gpu_instance_uuid_hash": self.gpu_instance_uuid_hash,
            "compute_instance_uuid_hash": self.compute_instance_uuid_hash,
        }


@dataclass(frozen=True)
class DestroyRecreateBoundary:
    """The destroy→recreate boundary itself, as its own explicit record.

    docs/STATUS.md's MIG row requires "destroy/recreate boundaries recorded
    separately" for the claim to count — this is that record, kept apart from
    the plant/measure statistics in ``MigBoundaryResult.observation`` and
    folded into ``ResultBundle.environment["mig_lifecycle"]`` rather than into
    any egress-allowlisted probe record (it is operational bookkeeping about
    *this script's* actions, not a memory measurement).
    """

    boundary: str
    predecessor: dict[str, Any]
    successor: dict[str, Any]
    destroyed_monotonic: float
    recreated_monotonic: float
    profile_changed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary": self.boundary,
            "predecessor_instance": self.predecessor,
            "successor_instance": self.successor,
            "destroyed_monotonic": self.destroyed_monotonic,
            "recreated_monotonic": self.recreated_monotonic,
            "teardown_to_recreate_seconds": max(
                0.0, self.recreated_monotonic - self.destroyed_monotonic
            ),
            "profile_changed": self.profile_changed,
        }


@dataclass(frozen=True)
class TenantCommandResult:
    """Output of one tenant-subprocess invocation. Mirrors
    ``gpu_seal.controller.native_runner.NativeCommandResult`` deliberately —
    same shape, same reason: a provider/lifecycle adapter should look
    interchangeable with the one this codebase already trusts."""

    returncode: int
    stdout: str
    stderr: str = ""
    timed_out: bool = False


class MigRuntime(Protocol):
    """The whole MIG lifecycle surface this script needs.

    Two implementations: ``NvmlMigRuntime`` (real NVML + subprocess tenants)
    and ``FakeMigRuntime`` (no hardware, for tests). The orchestration
    functions below (``run_boundary_cycle``, ``main``) know nothing about
    which one they were handed.
    """

    def capability(self) -> MigCapability: ...

    def set_mig_mode(self, enabled: bool) -> MigModeChange: ...

    def create_instance(
        self, gpu_instance_profile_id: int, compute_instance_profile_id: int
    ) -> MigInstanceHandle: ...

    def destroy_instance(self, handle: MigInstanceHandle) -> None: ...

    def run_tenant(
        self,
        handle: MigInstanceHandle,
        role: str,
        request: dict[str, Any],
        timeout_s: int,
    ) -> TenantCommandResult: ...


# ---------------------------------------------------------------------------
# The tenant worker — runs inside a subprocess scoped to one MIG instance
# (real runtime), or in-process against SimulatedBackend (fake runtime).
# Both paths call this exact function, so the fake exercises real logic.
# ---------------------------------------------------------------------------


def _execute_worker(request: dict[str, Any]) -> dict[str, Any]:
    """Steps 4 and 7, run with a CUDA context scoped to one MIG instance.

    ``request["nvml_mig_enabled"]`` is the orchestrator's own step-1
    capability assertion, forwarded so ``MigTemporalProbe``'s
    ``require_mig=True`` gate is re-checked here too, in the process that
    actually touches device memory — defense in depth, not decoration: the
    gate is never constructed with ``require_mig=False``.
    """
    role = request["role"]
    experiment_id = uuid.UUID(request["experiment_id"])
    key_bytes = bytes.fromhex(request["canary_key_hex"])
    boundary = Boundary[request["boundary"]]
    size_bytes = int(request["size_bytes"])
    simulate = bool(request.get("simulate", False))
    nvml_mig_enabled = request.get("nvml_mig_enabled")

    nvml_snapshot = (
        NvmlSnapshot(available=True, mig_enabled=nvml_mig_enabled)
        if simulate
        else read_nvml()
    )
    exclusivity = ExclusivityEvidence(
        source=request["exclusivity_evidence"]["source"],
        reference=request["exclusivity_evidence"]["reference"],
        verification_method=request["exclusivity_evidence"]["verification_method"],
        verified=True,
    )

    backend: CudaBackend
    if simulate:
        backend = SimulatedBackend(
            sanitises_on_free=False, pool_bytes=max(size_bytes * 2, 1 << 20)
        )
    else:
        backend = CupyBackend()

    try:
        if role == "plant":
            canaries = CanarySet(experiment_id=experiment_id, _key=key_bytes)
            probe = MigTemporalProbe(
                backend,
                canaries,
                nvml=nvml_snapshot,
                require_mig=True,
                shared_infrastructure=False,
                exclusivity_evidence=exclusivity,
            )
            _alloc, receipt = probe.plant(size_bytes, boundary=boundary)
            minted = {canary.allocation_id: canary for canary in canaries.emitted}
            return {
                "canaries_planted": receipt.canaries_planted,
                "canary_allocation_ids": [
                    str(item) for item in receipt.canary_allocation_ids
                ],
                "canaries": [
                    {
                        "allocation_id": str(allocation_id),
                        "nonce_hex": minted[allocation_id].nonce.hex(),
                        "blob_hex": minted[allocation_id].blob.hex(),
                    }
                    for allocation_id in receipt.canary_allocation_ids
                ],
                "backend_is_real": backend.is_real,
            }

        if role == "measure":
            emitted: dict[uuid.UUID, Canary] = {}
            for item in request["canaries"]:
                allocation_id = uuid.UUID(item["allocation_id"])
                emitted[allocation_id] = Canary(
                    blob=bytes.fromhex(item["blob_hex"]),
                    experiment_id=experiment_id,
                    allocation_id=allocation_id,
                    boundary=boundary,
                    nonce=bytes.fromhex(item["nonce_hex"]),
                )
            canaries = CanarySet(
                experiment_id=experiment_id, _key=key_bytes, _emitted=emitted
            )
            receipt = PlantReceipt(
                boundary=boundary,
                canaries_planted=int(request["receipt"]["canaries_planted"]),
                canary_allocation_ids=tuple(
                    uuid.UUID(item)
                    for item in request["receipt"]["canary_allocation_ids"]
                ),
            )
            probe = MigTemporalProbe(
                backend,
                canaries,
                nvml=nvml_snapshot,
                require_mig=True,
                shared_infrastructure=False,
                exclusivity_evidence=exclusivity,
            )
            result = probe.measure_successor(
                size_bytes,
                boundary=boundary,
                teardown_performed=request["teardown_performed"],
                receipt=receipt,
            )
            return {
                "safety_stop": result.safety_stop,
                "error_code": result.error_code,
                "observation": (
                    result.observation.to_dict() if result.observation else None
                ),
            }

        raise ValueError(f"unknown worker role {role!r}")
    finally:
        try:
            backend.close()
        except Exception:  # noqa: BLE001 - worker teardown must not mask the result
            pass


def _decode_observation(
    payload: dict[str, Any] | None,
) -> CanaryOnlyRecord | RedactedStopRecord | None:
    if payload is None:
        return None
    if payload.get("sensitive_observation"):
        return RedactedStopRecord(**payload)
    return CanaryOnlyRecord(**payload)


# ---------------------------------------------------------------------------
# Real runtime — NVML ctypes bindings, no nvidia-smi text parsing
# ---------------------------------------------------------------------------


class _GpuInstancePlacement(ctypes.Structure):
    _fields_ = [("start", ctypes.c_uint), ("size", ctypes.c_uint)]


class _GpuInstanceInfo(ctypes.Structure):
    _fields_ = [
        ("device", ctypes.c_void_p),
        ("id", ctypes.c_uint),
        ("profileId", ctypes.c_uint),
        ("placement", _GpuInstancePlacement),
    ]


class _ComputeInstancePlacement(ctypes.Structure):
    _fields_ = [("start", ctypes.c_uint), ("size", ctypes.c_uint)]


class _ComputeInstanceInfo(ctypes.Structure):
    _fields_ = [
        ("device", ctypes.c_void_p),
        ("gpuInstance", ctypes.c_void_p),
        ("id", ctypes.c_uint),
        ("profileId", ctypes.c_uint),
        ("placement", _ComputeInstancePlacement),
    ]


def _load_nvml() -> ctypes.CDLL | None:
    for name in _LIBRARY_NAMES:
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    return None


class NvmlMigRuntime:
    """Real MIG lifecycle via NVML, plus subprocess tenants.

    Requires root (``nvmlDeviceSetMigMode`` and instance creation/destruction
    are privileged calls) and A100/H100-class silicon. Never exercised in
    this repository's own test run — there is no such GPU here — which is
    exactly why ``FakeMigRuntime`` exists and carries the unit-test burden.
    """

    def __init__(self, device_index: int = 0) -> None:
        lib = _load_nvml()
        if lib is None:
            raise MigLifecycleError(
                "the NVIDIA management library (NVML) is not present on this host"
            )
        rc = lib.nvmlInit_v2()
        if rc != _NVML_SUCCESS:
            raise MigLifecycleError(f"NVML failed to initialise (rc={rc})")
        handle = ctypes.c_void_p()
        rc = lib.nvmlDeviceGetHandleByIndex_v2(
            ctypes.c_uint(device_index), ctypes.byref(handle)
        )
        if rc != _NVML_SUCCESS:
            lib.nvmlShutdown()
            raise MigLifecycleError(
                f"NVML could not open device index {device_index} (rc={rc})"
            )
        self._lib = lib
        self._device_index = device_index
        self._handle = handle
        #: (gpu_instance_id, compute_instance_id) -> (gpuInstance, computeInstance)
        #: opaque NVML handles, kept only so destroy_instance() can address
        #: exactly the pair create_instance() made — never reconstructed from
        #: a caller-supplied id.
        self._live: dict[tuple[int, int], tuple[ctypes.c_void_p, ctypes.c_void_p]] = {}
        #: Raw MIG device UUID strings, kept ONLY to build a tenant
        #: subprocess's CUDA_VISIBLE_DEVICES — never logged, printed, hashed
        #: for the record (the record gets the hash, from the same lookup),
        #: or returned from any public method. This is the one place a raw
        #: identifier is deliberately held, and only for that reason.
        self._raw_uuid: dict[tuple[int, int], str] = {}

    def close(self) -> None:
        try:
            self._lib.nvmlShutdown()
        except Exception:  # noqa: BLE001 - teardown must not raise
            pass

    def __enter__(self) -> NvmlMigRuntime:
        return self

    def __exit__(self, *exc: object) -> bool:
        self.close()
        return False

    def _read_mode(self) -> bool | None:
        current = ctypes.c_uint(0)
        pending = ctypes.c_uint(0)
        rc = self._lib.nvmlDeviceGetMigMode(
            self._handle, ctypes.byref(current), ctypes.byref(pending)
        )
        if rc != _NVML_SUCCESS:
            return None
        return current.value != _MIG_DISABLED

    def capability(self) -> MigCapability:
        mode = self._read_mode()
        if mode is None:
            return MigCapability(
                available=False,
                reason=(
                    "nvmlDeviceGetMigMode is not supported or was refused on "
                    "this device; it is not MIG-capable silicon, or the "
                    "caller lacks permission"
                ),
            )
        return MigCapability(
            available=True, reason="nvmlDeviceGetMigMode succeeded"
        )

    def set_mig_mode(self, enabled: bool) -> MigModeChange:
        before = self._read_mode()
        activation = ctypes.c_uint(0)
        rc = self._lib.nvmlDeviceSetMigMode(
            self._handle, ctypes.c_uint(1 if enabled else 0), ctypes.byref(activation)
        )
        if rc != _NVML_SUCCESS:
            raise MigLifecycleError(
                f"nvmlDeviceSetMigMode({enabled}) failed "
                f"(rc={rc}, activationStatus={activation.value})"
            )
        return MigModeChange(before=before, after=self._read_mode())

    def _resolve_mig_device(
        self, gpu_instance_id: int, compute_instance_id: int
    ) -> tuple[str | None, str | None]:
        """Find the MIG device handle for a (GI, CI) pair; hash its UUID.

        Returns ``(raw_uuid_or_None, hashed_uuid_or_None)``. Only the hash is
        ever returned to a caller outside this method's own use of the raw
        value to populate ``self._raw_uuid``.
        """
        max_count = ctypes.c_uint(0)
        if (
            self._lib.nvmlDeviceGetMaxMigDeviceCount(
                self._handle, ctypes.byref(max_count)
            )
            != _NVML_SUCCESS
        ):
            return None, None
        for index in range(max_count.value):
            mig_handle = ctypes.c_void_p()
            if (
                self._lib.nvmlDeviceGetMigDeviceHandleByIndex(
                    self._handle, ctypes.c_uint(index), ctypes.byref(mig_handle)
                )
                != _NVML_SUCCESS
            ):
                continue
            gi_id = ctypes.c_uint(0)
            ci_id = ctypes.c_uint(0)
            if (
                self._lib.nvmlDeviceGetGpuInstanceId(mig_handle, ctypes.byref(gi_id))
                != _NVML_SUCCESS
            ):
                continue
            if (
                self._lib.nvmlDeviceGetComputeInstanceId(
                    mig_handle, ctypes.byref(ci_id)
                )
                != _NVML_SUCCESS
            ):
                continue
            if gi_id.value != gpu_instance_id or ci_id.value != compute_instance_id:
                continue
            buf = ctypes.create_string_buffer(_UUID_BUFFER_BYTES)
            if (
                self._lib.nvmlDeviceGetUUID(
                    mig_handle, buf, ctypes.c_uint(_UUID_BUFFER_BYTES)
                )
                != _NVML_SUCCESS
            ):
                return None, None
            text = ascii_metadata(buf.value, field="mig_device_uuid")
            if not text:
                return None, None
            return text, stable_hash(text, domain="mig_device_uuid")
        return None, None

    def create_instance(
        self, gpu_instance_profile_id: int, compute_instance_profile_id: int
    ) -> MigInstanceHandle:
        gi = ctypes.c_void_p()
        rc = self._lib.nvmlDeviceCreateGpuInstance(
            self._handle, ctypes.c_uint(gpu_instance_profile_id), ctypes.byref(gi)
        )
        if rc != _NVML_SUCCESS:
            raise MigLifecycleError(
                f"nvmlDeviceCreateGpuInstance({gpu_instance_profile_id}) "
                f"failed (rc={rc})"
            )
        try:
            gi_info = _GpuInstanceInfo()
            self._lib.nvmlGpuInstanceGetInfo(gi, ctypes.byref(gi_info))
            ci = ctypes.c_void_p()
            rc = self._lib.nvmlGpuInstanceCreateComputeInstance(
                gi, ctypes.c_uint(compute_instance_profile_id), ctypes.byref(ci)
            )
            if rc != _NVML_SUCCESS:
                raise MigLifecycleError(
                    f"nvmlGpuInstanceCreateComputeInstance"
                    f"({compute_instance_profile_id}) failed (rc={rc})"
                )
            ci_info = _ComputeInstanceInfo()
            self._lib.nvmlComputeInstanceGetInfo(ci, ctypes.byref(ci_info))

            key = (int(gi_info.id), int(ci_info.id))
            raw_uuid, uuid_hash = self._resolve_mig_device(*key)
            self._live[key] = (gi, ci)
            if raw_uuid is not None:
                self._raw_uuid[key] = raw_uuid
            return MigInstanceHandle(
                gpu_instance_profile_id=gpu_instance_profile_id,
                compute_instance_profile_id=compute_instance_profile_id,
                gpu_instance_id=key[0],
                compute_instance_id=key[1],
                gpu_instance_uuid_hash=uuid_hash,
                compute_instance_uuid_hash=uuid_hash,
                created_monotonic=time.monotonic(),
            )
        except Exception:
            try:
                self._lib.nvmlGpuInstanceDestroy(gi)
            except Exception:  # noqa: BLE001
                pass
            raise

    def destroy_instance(self, handle: MigInstanceHandle) -> None:
        key = (handle.gpu_instance_id, handle.compute_instance_id)
        pair = self._live.pop(key, None)
        self._raw_uuid.pop(key, None)
        if pair is None:
            raise ValueError(
                "destroy_instance called on a handle this runtime did not "
                "create, or already destroyed"
            )
        gi, ci = pair
        try:
            rc = self._lib.nvmlComputeInstanceDestroy(ci)
            if rc != _NVML_SUCCESS:
                raise MigLifecycleError(
                    f"nvmlComputeInstanceDestroy failed (rc={rc})"
                )
        finally:
            rc = self._lib.nvmlGpuInstanceDestroy(gi)
            if rc != _NVML_SUCCESS:
                raise MigLifecycleError(f"nvmlGpuInstanceDestroy failed (rc={rc})")

    def run_tenant(
        self,
        handle: MigInstanceHandle,
        role: str,
        request: dict[str, Any],
        timeout_s: int,
    ) -> TenantCommandResult:
        raw_uuid = self._raw_uuid.get(
            (handle.gpu_instance_id, handle.compute_instance_id)
        )
        if raw_uuid is None:
            raise MigLifecycleError(
                "no live MIG device UUID recorded for this handle; refusing "
                "to launch a tenant subprocess with an unscoped GPU view"
            )
        env = dict(os.environ)
        env["CUDA_VISIBLE_DEVICES"] = raw_uuid
        command = [sys.executable, str(Path(__file__).resolve()), "--worker", role]
        try:
            completed = subprocess.run(  # noqa: S603
                command,
                input=json.dumps(request),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return TenantCommandResult(
                returncode=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                timed_out=True,
            )
        return TenantCommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


# ---------------------------------------------------------------------------
# Fake runtime — driver-level double, the way DeterministicFakeRuntime is for
# the native provider path. Real orchestration logic, real plant()/
# measure_successor()/CanarySet round-trip, zero hardware.
# ---------------------------------------------------------------------------


@dataclass
class FakeMigRuntime:
    """No NVML, no CUDA, no subprocess — but ``run_tenant`` still calls the
    real ``_execute_worker`` against ``SimulatedBackend``, so the canary
    plant/measure round trip is genuinely exercised, not just stubbed."""

    capability_available: bool = True
    capability_reason: str = "fake: MIG-capable"
    force_timeout: bool = False
    #: Forwarded into every worker request as ``nvml_mig_enabled``. Defaults
    #: to mirroring ``capability_available`` so a capability-refused fake
    #: cannot accidentally still report a MIG-enabled worker.
    worker_mig_enabled: bool | None = None

    created: list[MigInstanceHandle] = field(default_factory=list)
    destroyed: list[MigInstanceHandle] = field(default_factory=list)
    mode_changes: list[MigModeChange] = field(default_factory=list)

    _mode: bool | None = field(default=None, init=False, repr=False)
    _next_id: int = field(default=1, init=False, repr=False)
    _live: set[tuple[int, int]] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.worker_mig_enabled is None:
            self.worker_mig_enabled = self.capability_available

    def capability(self) -> MigCapability:
        return MigCapability(
            available=self.capability_available, reason=self.capability_reason
        )

    def set_mig_mode(self, enabled: bool) -> MigModeChange:
        change = MigModeChange(before=self._mode, after=enabled)
        self._mode = enabled
        self.mode_changes.append(change)
        return change

    def create_instance(
        self, gpu_instance_profile_id: int, compute_instance_profile_id: int
    ) -> MigInstanceHandle:
        n = self._next_id
        self._next_id += 1
        fake_uuid_hash = stable_hash(f"fake-mig-{n}", domain="mig_device_uuid")
        handle = MigInstanceHandle(
            gpu_instance_profile_id=gpu_instance_profile_id,
            compute_instance_profile_id=compute_instance_profile_id,
            gpu_instance_id=n,
            compute_instance_id=n,
            gpu_instance_uuid_hash=fake_uuid_hash,
            compute_instance_uuid_hash=fake_uuid_hash,
            created_monotonic=time.monotonic(),
        )
        self._live.add((handle.gpu_instance_id, handle.compute_instance_id))
        self.created.append(handle)
        return handle

    def destroy_instance(self, handle: MigInstanceHandle) -> None:
        key = (handle.gpu_instance_id, handle.compute_instance_id)
        if key not in self._live:
            raise ValueError(
                "destroy_instance called on an unknown or already-destroyed "
                "fake handle"
            )
        self._live.discard(key)
        self.destroyed.append(handle)

    def run_tenant(
        self,
        handle: MigInstanceHandle,
        role: str,
        request: dict[str, Any],
        timeout_s: int,
    ) -> TenantCommandResult:
        del handle, timeout_s
        if self.force_timeout:
            return TenantCommandResult(
                returncode=124, stdout="", stderr="fake timeout", timed_out=True
            )
        forced = {
            **request,
            "simulate": True,
            "nvml_mig_enabled": self.worker_mig_enabled,
        }
        try:
            payload = _execute_worker(forced)
        except Exception as exc:  # noqa: BLE001 - report as a failed tenant command
            return TenantCommandResult(
                returncode=1, stdout="", stderr=f"{type(exc).__name__}: {exc}"
            )
        return TenantCommandResult(returncode=0, stdout=json.dumps(payload))


# ---------------------------------------------------------------------------
# Orchestration — steps 1-8, one boundary cycle at a time
# ---------------------------------------------------------------------------


def _assert_capability(runtime: MigRuntime) -> None:
    """Step 1. Refuses before anything else on this run has happened —
    before MIG mode is even touched, let alone an instance created."""
    capability = runtime.capability()
    if not capability.available:
        raise MigUnavailable(
            f"§9.12 cannot run here: {capability.reason}. MIG requires "
            f"A100/H100-class datacentre silicon (CHARTER.md §9.12, §20); "
            f"refusing rather than producing a §9.3-equivalent measurement "
            f"under a §9.12 label."
        )


def _decode_worker_output(result: TenantCommandResult, *, phase: str) -> dict[str, Any]:
    if result.timed_out:
        raise MigLifecycleError(f"{phase} tenant subprocess timed out")
    if result.returncode != 0:
        raise MigLifecycleError(
            f"{phase} tenant subprocess exited {result.returncode}: "
            f"{result.stderr.strip()[:500]}"
        )
    return json.loads(result.stdout)


def run_boundary_cycle(
    runtime: MigRuntime,
    *,
    experiment_id: uuid.UUID,
    canary_key: bytes,
    boundary: Boundary,
    predecessor_profile: tuple[int, int],
    successor_profile: tuple[int, int],
    size_bytes: int,
    exclusivity_evidence: dict[str, str],
    nvml_mig_enabled: bool,
    simulate: bool,
    timeout_s: int,
) -> tuple[MigBoundaryResult, DestroyRecreateBoundary]:
    """Steps 3-7 for one plant/destroy/recreate/measure cycle.

    Every allocation this makes (a GPU instance, a compute instance) is
    either handed off to a later step or destroyed before this function
    returns or raises — there is no path that leaks a live MIG instance.
    """
    predecessor = runtime.create_instance(*predecessor_profile)
    successor: MigInstanceHandle | None = None
    try:
        plant_request = {
            "role": "plant",
            "experiment_id": str(experiment_id),
            "canary_key_hex": canary_key.hex(),
            "boundary": boundary.name,
            "size_bytes": size_bytes,
            "simulate": simulate,
            "nvml_mig_enabled": nvml_mig_enabled,
            "exclusivity_evidence": exclusivity_evidence,
        }
        plant_payload = _decode_worker_output(
            runtime.run_tenant(predecessor, "plant", plant_request, timeout_s),
            phase="plant",
        )

        destroyed_monotonic = time.monotonic()
        runtime.destroy_instance(predecessor)
        predecessor_destroyed = predecessor
        predecessor = None  # already destroyed; nothing left to clean up

        successor = runtime.create_instance(*successor_profile)
        recreated_monotonic = time.monotonic()

        teardown_performed = (
            f"MIG compute instance {predecessor_destroyed.compute_instance_id} "
            f"and GPU instance {predecessor_destroyed.gpu_instance_id} "
            f"destroyed via NVML, then recreated as compute instance "
            f"{successor.compute_instance_id} / GPU instance "
            f"{successor.gpu_instance_id} "
            f"(profile_changed={predecessor_profile != successor_profile})"
        )
        measure_request = {
            "role": "measure",
            "experiment_id": str(experiment_id),
            "canary_key_hex": canary_key.hex(),
            "boundary": boundary.name,
            "size_bytes": size_bytes,
            "simulate": simulate,
            "nvml_mig_enabled": nvml_mig_enabled,
            "exclusivity_evidence": exclusivity_evidence,
            "receipt": {
                "canaries_planted": plant_payload["canaries_planted"],
                "canary_allocation_ids": plant_payload["canary_allocation_ids"],
            },
            "canaries": plant_payload["canaries"],
            "teardown_performed": teardown_performed,
        }
        measure_payload = _decode_worker_output(
            runtime.run_tenant(successor, "measure", measure_request, timeout_s),
            phase="measure",
        )

        boundary_result = MigBoundaryResult(
            boundary=boundary,
            size_bytes=size_bytes,
            canaries_planted=plant_payload["canaries_planted"],
            observation=_decode_observation(measure_payload["observation"]),
            safety_stop=measure_payload["safety_stop"],
            error_code=measure_payload["error_code"],
            teardown_performed=teardown_performed,
        )
        destroy_recreate = DestroyRecreateBoundary(
            boundary=boundary.name,
            predecessor=predecessor_destroyed.to_dict(),
            successor=successor.to_dict(),
            destroyed_monotonic=destroyed_monotonic,
            recreated_monotonic=recreated_monotonic,
            profile_changed=predecessor_profile != successor_profile,
        )
        return boundary_result, destroy_recreate
    finally:
        if predecessor is not None:
            try:
                runtime.destroy_instance(predecessor)
            except Exception:  # noqa: BLE001 - teardown must not mask the real error
                pass
        if successor is not None:
            try:
                runtime.destroy_instance(successor)
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worker", choices=("plant", "measure"), help=argparse.SUPPRESS)
    ap.add_argument("--gpu-instance-profile-id", type=int)
    ap.add_argument("--compute-instance-profile-id", type=int)
    ap.add_argument(
        "--different-gpu-instance-profile-id",
        type=int,
        help="if given (with --different-compute-instance-profile-id), also "
        "runs the MIG_DIFFERENT_PROFILE boundary",
    )
    ap.add_argument("--different-compute-instance-profile-id", type=int)
    ap.add_argument("--device-index", type=int, default=0)
    ap.add_argument("--size-mib", type=int, default=4)
    ap.add_argument("--cycles", type=int, default=3)
    ap.add_argument("--tenant-timeout-s", type=int, default=120)
    ap.add_argument("--max-runtime-s", type=int, default=1800)
    ap.add_argument("--simulate", action="store_true")
    ap.add_argument(
        "--fake-runtime",
        action="store_true",
        help="drive the whole lifecycle through FakeMigRuntime; no NVML, no "
        "CUDA, no root required. For rehearsal and CI, never for evidence.",
    )
    ap.add_argument(
        "--exclusive-possession-attestation",
        help="required against real hardware: a short operator statement of "
        "how sole tenancy of this GPU was confirmed (e.g. 'bare-metal "
        "rental, confirmed via nvidia-smi -a; no other NVML process visible')",
    )
    ap.add_argument(
        "--exclusivity-verification-method",
        default="operator manual attestation",
    )
    ap.add_argument("--signing-key", type=Path)
    ap.add_argument("--unsafe-development-ephemeral", action="store_true")
    ap.add_argument("--out", type=Path, default=Path("out"))
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = _build_arg_parser()
    args = ap.parse_args(argv)

    if args.worker:
        try:
            result = _execute_worker(json.loads(sys.stdin.read()))
        except Exception as exc:  # noqa: BLE001 - never leak a traceback with content
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result))
        return 0

    if args.gpu_instance_profile_id is None or args.compute_instance_profile_id is None:
        ap.error(
            "--gpu-instance-profile-id and --compute-instance-profile-id "
            "are required"
        )
    if (args.different_gpu_instance_profile_id is None) != (
        args.different_compute_instance_profile_id is None
    ):
        ap.error(
            "--different-gpu-instance-profile-id and "
            "--different-compute-instance-profile-id must be given together"
        )
    if args.max_runtime_s <= 0:
        ap.error("--max-runtime-s must be positive")
    if not args.fake_runtime and not args.exclusive_possession_attestation:
        ap.error(
            "--exclusive-possession-attestation is required against real "
            "hardware: MIG successor measurements are shared by default "
            "(MigTemporalProbe), and disabling that safeguard requires "
            "stating how sole tenancy was confirmed"
        )

    try:
        key_source = key_source_from_options(
            args.signing_key,
            unsafe_development_ephemeral=args.unsafe_development_ephemeral,
        )
        signer = key_source.load()
    except (OSError, TypeError, ValueError) as exc:
        ap.error(str(exc))
        return 2  # pragma: no cover - ap.error() already exits

    exclusivity_evidence = {
        "source": "operator-attestation",
        "reference": args.exclusive_possession_attestation or "fake-runtime rehearsal",
        "verification_method": args.exclusivity_verification_method,
    }

    print()
    print("GPU-SEAL §9.12 MIG temporal-isolation experiment")
    print("=" * 62)
    print(f"  signing key       {signer.verify_key.fingerprint}")
    if not key_source.provenance_suitable:
        print("  WARNING            UNSAFE DEVELOPMENT KEY: not provenance evidence")

    runtime: MigRuntime
    if args.fake_runtime:
        runtime = FakeMigRuntime()
        print("  runtime           FakeMigRuntime (no hardware, rehearsal only)")
    else:
        try:
            runtime = NvmlMigRuntime(device_index=args.device_index)
        except MigLifecycleError as exc:
            print(f"  REFUSED: {exc}")
            return 1
        print(f"  runtime           NvmlMigRuntime(device_index={args.device_index})")

    experiment_id = uuid.uuid4()
    canary_set = CanarySet.create(experiment_id=experiment_id)
    campaign = CampaignControl.create()
    budget = RunBudget.start(args.max_runtime_s)
    size_bytes = args.size_mib * MIB

    boundary_plan: list[tuple[Boundary, tuple[int, int], tuple[int, int]]] = [
        (
            Boundary.MIG_SAME_PROFILE,
            (args.gpu_instance_profile_id, args.compute_instance_profile_id),
            (args.gpu_instance_profile_id, args.compute_instance_profile_id),
        )
    ]
    if args.different_gpu_instance_profile_id is not None:
        boundary_plan.append(
            (
                Boundary.MIG_DIFFERENT_PROFILE,
                (args.gpu_instance_profile_id, args.compute_instance_profile_id),
                (
                    args.different_gpu_instance_profile_id,
                    args.different_compute_instance_profile_id,
                ),
            )
        )

    results: list[MigBoundaryResult] = []
    lifecycle_log: list[dict[str, Any]] = []
    incomplete_reason: str | None = None
    mode_change: MigModeChange | None = None
    mode_restore: MigModeChange | None = None

    try:
        # -- Step 1 -----------------------------------------------------
        try:
            _assert_capability(runtime)
        except MigUnavailable as exc:
            print(f"  REFUSED: {exc}")
            if not args.fake_runtime:
                runtime.close()  # type: ignore[attr-defined]
            return 1
        print("  capability        MIG-capable, proceeding")

        # -- Step 2 -------------------------------------------------------
        mode_change = runtime.set_mig_mode(True)
        print(
            f"  MIG mode          before={mode_change.before} "
            f"after={mode_change.after}"
        )

        try:
            for boundary, predecessor_profile, successor_profile in boundary_plan:
                print()
                print(f"  -- {boundary.name} " + "-" * (50 - len(boundary.name)))
                for cycle_index in range(args.cycles):
                    campaign.check()
                    budget.check()
                    result, destroy_recreate = run_boundary_cycle(
                        runtime,
                        experiment_id=experiment_id,
                        canary_key=canary_set._key,
                        boundary=boundary,
                        predecessor_profile=predecessor_profile,
                        successor_profile=successor_profile,
                        size_bytes=size_bytes,
                        exclusivity_evidence=exclusivity_evidence,
                        nvml_mig_enabled=True,
                        simulate=args.simulate or args.fake_runtime,
                        timeout_s=args.tenant_timeout_s,
                    )
                    results.append(result)
                    lifecycle_log.append(destroy_recreate.to_dict())
                    print(
                        f"    cycle={cycle_index + 1} "
                        f"canary_recovered={result.canary_recovered} "
                        f"safety_stop={result.safety_stop} "
                        f"error={result.error_code}"
                    )
                    if result.safety_stop:
                        print("    SAFETY STOP: campaign terminated, no further reads")
                        break
        except CampaignTerminated:
            print("  campaign already terminated by a prior safety stop")
        except RunBudgetExceeded as exc:
            incomplete_reason = (
                f"--max-runtime-s budget of {args.max_runtime_s}s exceeded: {exc}"
            )
            print(f"  BUDGET EXCEEDED: {incomplete_reason}")
    finally:
        # -- Step 8: restore MIG mode, even on failure ---------------------
        if mode_change is not None:
            try:
                mode_restore = runtime.set_mig_mode(bool(mode_change.before))
                print(
                    f"  MIG mode restored before={mode_restore.before} "
                    f"after={mode_restore.after}"
                )
            except Exception as exc:  # noqa: BLE001 - report, do not mask the run
                print(f"  WARNING: failed to restore MIG mode: {exc}")
        if not args.fake_runtime:
            runtime.close()  # type: ignore[attr-defined]

    # -- Summary and evidence ---------------------------------------------
    print()
    print("§9.12 summary (per boundary, never pooled)")
    print("-" * 42)
    summary = summarise_mig(results)
    for boundary_name, stats in summary.items():
        print(f"  {boundary_name}: {stats}")

    probes = [r.observation for r in results if r.observation is not None]
    provider_code = (
        "fake-runtime-rehearsal" if args.fake_runtime else "researcher-owned"
    )
    product_claim = (
        "fake-runtime rehearsal" if args.fake_runtime else "A100/H100 MIG"
    )
    bundle = ResultBundle(
        experiment_id=f"exp_mig_{experiment_id.hex[:12]}",
        run_id=f"run_mig_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
        provider_code=provider_code,
        region_claim="n/a",
        product_claim=product_claim,
        tool=ToolProvenance(version=__version__, commit="unknown"),
        probes=probes,
        environment={
            "mig_lifecycle": lifecycle_log,
            "mig_mode_change": mode_change.to_dict() if mode_change else None,
            "mig_mode_restore": mode_restore.to_dict() if mode_restore else None,
            "exclusivity_evidence": {
                "source": exclusivity_evidence["source"],
                "verification_method": exclusivity_evidence["verification_method"],
            },
        },
        run_incomplete=incomplete_reason is not None,
        incomplete_reason=incomplete_reason,
    )
    bundle.environment["signing"] = signing_metadata(key_source, signer)
    stored = EvidenceStore(args.out).write(bundle, signer)
    print()
    print(f"  probe records     {len(probes)}")
    print(f"  signature valid   {stored.signature_verified}")
    print(f"  written to        {stored.path}")
    print(f"  publishable       {'yes' if stored.publishable else 'no'}")
    if stored.refusal:
        print(f"    reason: {stored.refusal.split(':', 1)[-1].strip()[:200]}")

    ok = bool(results) and incomplete_reason is None
    print()
    print("  RESULT:", "PASS" if ok else "FAIL")
    print()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
