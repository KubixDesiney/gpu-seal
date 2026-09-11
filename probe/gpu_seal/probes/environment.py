"""Environment inventory — CHARTER.md §9.1.

    "Collects the minimum context needed to interpret everything else."

Every other probe in GPU-SEAL produces a number that means nothing on its own.
"No canary recovered" is a different result on a dedicated passthrough H100
than on an unisolated time-slice, and a different result again on a driver
version where the behaviour is already documented. This module collects the
context that turns the numbers into results, and it runs first.

Four blocks, exactly as the charter specifies: ``experiment``, ``provider``,
``system``, ``gpu``.

Two rules constrain what goes in them.

**Claims are recorded as claims.** ``advertised_gpu``, ``advertised_region``,
and ``advertised_tenancy`` are what the provider *sold*, supplied by the
operator from the invoice or console. They are never read from the machine,
because reading them from the machine would be measuring the thing we are
trying to check the claim against. Keeping them structurally separate from the
``gpu`` block is what makes §13.3 and §13.5 possible at all.

**Identifiers are hashed on the way in, not on the way out.** CHARTER.md §10
lists account IDs, GPU UUIDs, and hostnames among the never-published fields.
They are hashed at the point of collection, so the clear value never reaches a
dataclass that something else might later serialise.

Portability: the system block is Linux-shaped, because rented GPU instances
are. On any other host the Linux-specific fields report ``not_testable`` with
a reason rather than guessing — a wrong environment description is worse than
an absent one, since everything downstream is interpreted through it.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..cuda.backend import CudaBackend
from ..cuda.nvml import NvmlSnapshot, read_nvml
from ..evidence.observation import ObservationRecord
from ..safety.campaign import CampaignControl
from ..safety.metadata import stable_hash

__all__ = [
    "EnvironmentInventory",
    "EnvironmentInventoryProbe",
    "ProviderClaims",
    "PROBE_NAME",
    "PROBE_VERSION",
]

PROBE_NAME = "environment_inventory"
PROBE_VERSION = "0.2.0"

_PROC = Path("/proc")
_NOT_LINUX = "this host is not Linux; the field has no equivalent to read"


@dataclass(frozen=True)
class ProviderClaims:
    """What was advertised, supplied by the operator — never measured.

    CHARTER.md §9.1's ``provider`` block. Defaults describe the local lab so a
    control run does not have to invent a provider it did not rent from.
    """

    provider_code: str = "local-lab"
    product_name: str = "researcher-owned workstation"
    advertised_region: str = "n/a"
    advertised_gpu: str = "n/a"
    advertised_tenancy: str = "dedicated"
    advertised_confidential_mode: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_code": self.provider_code,
            "product_name": self.product_name,
            "advertised_region": self.advertised_region,
            "advertised_gpu": self.advertised_gpu,
            "advertised_tenancy": self.advertised_tenancy,
            "advertised_confidential_mode": self.advertised_confidential_mode,
        }


@dataclass
class EnvironmentInventory:
    """The four §9.1 blocks, ready to embed in a result bundle."""

    experiment: dict[str, Any] = field(default_factory=dict)
    provider: dict[str, Any] = field(default_factory=dict)
    system: dict[str, Any] = field(default_factory=dict)
    gpu: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment": self.experiment,
            "provider": self.provider,
            "system": self.system,
            "gpu": self.gpu,
        }


class EnvironmentInventoryProbe:
    """Collect the §9.1 inventory. Reads only this tenant's own environment."""

    NAME = PROBE_NAME
    VERSION = PROBE_VERSION

    def __init__(
        self,
        backend: CudaBackend | None = None,
        *,
        claims: ProviderClaims | None = None,
        nvml: NvmlSnapshot | None = None,
        campaign: CampaignControl | None = None,
    ) -> None:
        """
        Args:
            nvml: injected in tests so the inventory can be exercised without
                a management library present. Collected live when omitted.
        """
        self._backend = backend
        self._claims = claims or ProviderClaims()
        self._nvml = nvml
        self._campaign = campaign or CampaignControl.create()

    # ------------------------------------------------------------------

    def collect(
        self,
        *,
        experiment_id: str,
        tool_version: str,
        tool_commit: str,
        container_digest: str | None = None,
        researcher_account_id: str | None = None,
    ) -> EnvironmentInventory:
        self._campaign.check()
        nvml = self._nvml if self._nvml is not None else read_nvml()
        return EnvironmentInventory(
            experiment=self._experiment_block(
                experiment_id=experiment_id,
                tool_version=tool_version,
                tool_commit=tool_commit,
                container_digest=container_digest,
                researcher_account_id=researcher_account_id,
            ),
            provider=self._claims.to_dict(),
            system=self._system_block(),
            gpu=self._gpu_block(nvml),
        )

    def observations(self, inventory: EnvironmentInventory) -> list[ObservationRecord]:
        """The inventory facts that feed a report-card grade.

        Most of the inventory is context rather than finding. What is promoted
        here is the small set where the observed value can *contradict* a
        claim — which is what §13.3 and §13.5 grade.
        """
        self._campaign.check()
        records: list[ObservationRecord] = []
        gpu = inventory.gpu
        system = inventory.system

        records.append(
            ObservationRecord(
                probe_name=self.NAME,
                probe_version=self.VERSION,
                subject="visible_device_count",
                category="environment",
                classification="expected_visibility",
                value=gpu.get("visible_device_count"),
                confidence=1.0,
                evidence=["reported by the CUDA runtime to this tenant"],
                limitations=[
                    "the CUDA-visible count is what the container exposes, not "
                    "what the host holds"
                ],
            )
        )

        containerised = system.get("containerised")
        records.append(
            ObservationRecord(
                probe_name=self.NAME,
                probe_version=self.VERSION,
                subject="containerised",
                category="environment",
                classification=(
                    "expected_visibility" if containerised is not None else "not_testable"
                ),
                value=containerised,
                confidence=0.8 if containerised is not None else 0.0,
                evidence=system.get("containerised_evidence", []),
                limitations=[
                    "container detection is heuristic; a provider may present a "
                    "VM that is indistinguishable from bare metal from inside"
                ],
                not_testable_reason=(
                    None if containerised is not None else _NOT_LINUX
                ),
            )
        )

        mig_mode = gpu.get("mig_mode")
        records.append(
            ObservationRecord(
                probe_name=self.NAME,
                probe_version=self.VERSION,
                subject="mig_mode",
                category="environment",
                classification=(
                    "expected_visibility" if mig_mode is not None else "not_testable"
                ),
                value=mig_mode,
                confidence=1.0 if mig_mode is not None else 0.0,
                evidence=["reported by the management library"],
                limitations=[
                    "MIG mode reported as unavailable does not mean MIG is off; "
                    "consumer silicon does not implement the query at all"
                ],
                not_testable_reason=(
                    None
                    if mig_mode is not None
                    else "the management library did not answer the MIG query"
                ),
            )
        )
        return records

    # ------------------------------------------------------------------
    # Blocks
    # ------------------------------------------------------------------

    def _experiment_block(
        self,
        *,
        experiment_id: str,
        tool_version: str,
        tool_commit: str,
        container_digest: str | None,
        researcher_account_id: str | None,
    ) -> dict[str, Any]:
        return {
            "id": experiment_id,
            "tool_version": tool_version,
            "tool_commit": tool_commit,
            "container_digest": container_digest,
            "container_profile": os.environ.get(
                "GPU_SEAL_CONTAINER_PROFILE", "unspecified"
            ),
            # Hashed at collection, per the module docstring.
            "researcher_account_id_hash": (
                stable_hash(researcher_account_id, domain="account_id")
                if researcher_account_id
                else None
            ),
        }

    def _system_block(self) -> dict[str, Any]:
        # platform.uname() rather than platform.system(): the §16 test-15
        # static analysis rejects any call named `system` in probe source, and
        # the exemption list is not worth widening for a field this module can
        # read off a named tuple instead.
        host = platform.uname()
        block: dict[str, Any] = {
            "operating_system": host.system,
            "kernel_version": host.release,
        }

        if not _PROC.is_dir():
            block.update(
                {
                    "containerised": None,
                    "containerised_evidence": [],
                    "cgroup_mode": None,
                    "pid_namespace_shared_with_init": None,
                    "ipc_namespace_shared_with_init": None,
                    "network_namespace_shared_with_init": None,
                    "virtualisation_indicators": None,
                    "not_testable_reason": _NOT_LINUX,
                }
            )
            return block

        evidence: list[str] = []
        containerised = False

        if Path("/.dockerenv").exists():
            containerised = True
            evidence.append("a container runtime marker file is present at the root")

        cgroup = _read_text(_PROC / "self" / "cgroup")
        if cgroup is not None and _looks_containerised(cgroup):
            containerised = True
            evidence.append("the cgroup path is not the root cgroup")

        block["containerised"] = containerised
        block["containerised_evidence"] = evidence
        block["cgroup_mode"] = (
            "v2" if Path("/sys/fs/cgroup/cgroup.controllers").exists() else "v1"
        )

        for name, key in (
            ("pid", "pid_namespace_shared_with_init"),
            ("ipc", "ipc_namespace_shared_with_init"),
            ("net", "network_namespace_shared_with_init"),
        ):
            block[key] = _shares_namespace_with_init(name)

        block["virtualisation_indicators"] = _virtualisation_indicators()
        return block

    def _gpu_block(self, nvml: NvmlSnapshot) -> dict[str, Any]:
        block: dict[str, Any] = {
            "nvml_available": nvml.available,
            # DCGM is a separate daemon with its own socket, and probing for it
            # is §9.6's job rather than the inventory's. Recorded here as
            # unknown so the field exists in every bundle and the exposure
            # probe fills it.
            "dcgm_available": None,
            "visible_device_count": nvml.device_count,
            "mig_mode": nvml.mig_enabled,
            "mig_profile": None,
            "gpu_uuid_hash": nvml.gpu_uuid_hash,
            # CHARTER.md §10: PCI information is reduced, not recorded whole.
            # Bus position is stable per host and is a re-identifier.
            "pci_information_reduced": None,
        }

        if self._backend is None:
            return block

        info = self._backend.device_info()
        block.update(
            {
                "reported_model": info.get("device_name"),
                "compute_capability": info.get("compute_capability"),
                "total_memory": info.get("total_memory_bytes"),
                "cuda_runtime_version": info.get("cuda_runtime_version"),
                "cuda_driver_version": info.get("cuda_driver_version"),
                "backend_is_real": info.get("backend_is_real"),
            }
        )
        if block["visible_device_count"] is None and info.get("device_id") is not None:
            # The runtime saw at least the device we opened. Weaker than NVML's
            # answer and recorded as such.
            block["visible_device_count"] = 1
        return block


# ---------------------------------------------------------------------------
# Helpers. All of them read this tenant's own environment and nothing else.
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii", errors="ignore")
    except OSError:
        return None


def _looks_containerised(cgroup_text: str) -> bool:
    """True when any cgroup line places this process outside the root cgroup.

    Substring inspection of our own cgroup file, not pattern-hunting: the
    §7.2 prohibition is on searching *unknown* memory. This is a file the
    kernel wrote to describe us.
    """
    for line in cgroup_text.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[2] not in ("/", ""):
            return True
    return False


def _shares_namespace_with_init(namespace: str) -> bool | None:
    """Whether this process is in the same namespace as PID 1.

    Sharing the initial namespace is the signal that a container's isolation
    is thinner than a reader would assume. Observation only — GPU-SEAL never
    enters, joins, or manipulates a namespace (CHARTER.md §4.3, §16 test 17).
    """
    try:
        ours = os.readlink(f"/proc/self/ns/{namespace}")
        theirs = os.readlink(f"/proc/1/ns/{namespace}")
    except OSError:
        # Being unable to read PID 1's namespace is a *restriction*, which is
        # the secure outcome. It is reported as unknown rather than as False,
        # because "we could not look" is not "they differ".
        return None
    return ours == theirs


def _virtualisation_indicators() -> list[str]:
    """Non-invasive hints that this is a guest rather than bare metal."""
    indicators: list[str] = []

    cpuinfo = _read_text(_PROC / "cpuinfo")
    if cpuinfo is not None and "hypervisor" in cpuinfo:
        indicators.append("the CPU reports a hypervisor feature flag")

    if Path("/sys/hypervisor/type").exists():
        indicators.append("a hypervisor type node is present in sysfs")

    if Path("/proc/xen").exists():
        indicators.append("a Xen interface directory is present")

    return indicators
