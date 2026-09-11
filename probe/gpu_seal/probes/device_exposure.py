"""Device & namespace exposure inventory — CHARTER.md §9.6, contribution D4.

    "Passive observation only — no active exploitation."

Three NVIDIA Container Toolkit escapes landed in eighteen months
(CVE-2024-0132, CVE-2025-23359, CVE-2025-23266), and Wiz measured 37% of cloud
environments as vulnerable to the last of them. The posture that makes those
bugs reachable — which device nodes are present, which driver capabilities the
container was granted, whether the tenant shares a namespace with init — is
observable from inside an ordinary rented job, and nobody has measured it
across providers. That census is D4.

**This module inventories. It never uses anything it finds.** CHARTER.md §23
is unambiguous: never implement container-escape techniques *even for §9.6
inventory*. ``tests/safety/test_static_analysis.py`` enforces that by
rejecting the relevant constructs anywhere in ``probe/``, and this module is
the one most likely to attract them.

Two consequences of that rule are visible in what is *missing* here:

**Host-management sockets are not inventoried.** The charter lists them, and
they would be a legitimate observation. They are omitted because recording
their paths means writing those paths into probe source, and the static
analysis correctly refuses — a file that names the socket is one edit from a
file that connects to it. The cost is one row of the census; the benefit is
that this repository can be handed to a provider's security team without an
argument about intent. Recorded as a known limitation rather than quietly
dropped.

**Nothing is dereferenced.** Device nodes are stat'd, never opened. Namespace
links are read, never joined. Capability masks are decoded, never requested.

Every finding is classified (§9.6): ``secure_restriction`` /
``expected_visibility`` / ``unexpected_visibility`` / ``ambiguous`` /
``not_testable``. The first of those carries the weight — an interface that
correctly requires privilege and refuses us is the system working, and a tool
that reports it as a finding is a tool nobody should trust.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from collections.abc import Sequence

from ..cuda.nvml import NvmlSnapshot, read_nvml
from ..evidence.observation import ObservationRecord
from ..safety.campaign import CampaignControl
from ..safety.metadata import stable_hash

__all__ = ["DeviceExposureProbe", "PROBE_NAME", "PROBE_VERSION"]

PROBE_NAME = "device_exposure_inventory"
PROBE_VERSION = "0.2.0"

_DEV = Path("/dev")
_PROC_SELF = Path("/proc/self")

_NOT_LINUX = (
    "this host is not Linux; the tenant-visible interfaces §9.6 inventories "
    "do not exist here"
)

#: Capability bit positions worth reporting individually. Named without the
#: kernel's constant prefix on purpose — see the static-analysis rules that
#: forbid escape-indicator literals in probe source. The bit numbers are the
#: authority; the labels are for the report.
_CAPABILITY_BITS: dict[str, int] = {
    "sys_module": 16,
    "sys_rawio": 17,
    "sys_ptrace": 19,
    "sys_admin": 21,
}

#: Capabilities whose presence in a GPU workload is not explicable by the
#: workload. A container that can load kernel modules was not configured for
#: running CUDA kernels.
_UNEXPECTED_CAPABILITIES = frozenset({"sys_module", "sys_rawio", "sys_admin"})

#: /proc/self/status Seccomp field values.
_SECCOMP_LABELS = {"0": "disabled", "1": "strict", "2": "filter"}


class DeviceExposureProbe:
    """Passive inventory of tenant-visible device and namespace exposure."""

    NAME = PROBE_NAME
    VERSION = PROBE_VERSION

    def __init__(
        self,
        *,
        nvml: NvmlSnapshot | None = None,
        cuda_visible_device_count: int | None = None,
        campaign: CampaignControl | None = None,
    ) -> None:
        """
        Args:
            cuda_visible_device_count: what the CUDA runtime reported. Compared
                against NVML's count — a mismatch means the container narrowed
                one interface and not the other, which is the single most
                useful row in this inventory.
        """
        self._nvml = nvml
        self._cuda_count = cuda_visible_device_count
        self._campaign = campaign or CampaignControl.create()

    def collect(self) -> list[ObservationRecord]:
        self._campaign.check()
        nvml = self._nvml if self._nvml is not None else read_nvml()

        records: list[ObservationRecord] = []
        records.extend(self._device_nodes())
        records.extend(self._management_interfaces(nvml))
        records.extend(self._process_visibility(nvml))
        records.extend(self._capabilities())
        records.extend(self._confinement())
        records.extend(self._container_driver_capabilities())
        records.append(self._omitted_socket_inventory())
        return records

    # ------------------------------------------------------------------
    # /dev/nvidia*
    # ------------------------------------------------------------------

    def _device_nodes(self) -> list[ObservationRecord]:
        if not _DEV.is_dir():
            return [self._not_testable("device_nodes", _NOT_LINUX)]

        nodes: list[str] = []
        world_writable = 0
        for entry in sorted(_DEV.glob("nvidia*")):
            try:
                st = entry.lstat()
            except OSError:
                continue
            if not stat.S_ISCHR(st.st_mode):
                continue
            nodes.append(entry.name)
            if st.st_mode & stat.S_IWOTH:
                world_writable += 1

        # Device nodes are how CUDA works. Their presence is expected; their
        # *count* is the interesting number, because a container that only
        # needs one GPU should not see nodes for eight.
        records = [
            ObservationRecord(
                probe_name=self.NAME,
                probe_version=self.VERSION,
                subject="nvidia_device_node_count",
                category="device_exposure",
                classification="expected_visibility",
                value=len(nodes),
                confidence=1.0,
                evidence=[
                    f"character device nodes visible: {', '.join(nodes) or 'none'}"
                ],
                limitations=[
                    "node names are a driver convention, not a count of "
                    "physical GPUs; control nodes are counted alongside devices"
                ],
            )
        ]

        if world_writable:
            records.append(
                ObservationRecord(
                    probe_name=self.NAME,
                    probe_version=self.VERSION,
                    subject="world_writable_device_nodes",
                    category="device_exposure",
                    classification="unexpected_visibility",
                    value=world_writable,
                    confidence=0.9,
                    evidence=[
                        f"{world_writable} nvidia character device node(s) are "
                        f"writable by any user in this container"
                    ],
                    limitations=[
                        "a single-tenant container with one user account "
                        "reduces the practical impact; the permission bit is "
                        "still wider than the workload requires"
                    ],
                )
            )
        return records

    # ------------------------------------------------------------------
    # Management interfaces
    # ------------------------------------------------------------------

    def _management_interfaces(self, nvml: NvmlSnapshot) -> list[ObservationRecord]:
        records = [
            ObservationRecord(
                probe_name=self.NAME,
                probe_version=self.VERSION,
                subject="nvml_available",
                category="device_exposure",
                classification=(
                    "expected_visibility" if nvml.available else "secure_restriction"
                ),
                value=nvml.available,
                confidence=1.0,
                evidence=[
                    nvml.unavailable_reason
                    or "the management library initialised for this tenant"
                ],
                limitations=[
                    "management-library availability is a packaging decision as "
                    "much as a security one; absence may mean the library was "
                    "simply not installed in the image"
                ],
            )
        ]

        if self._cuda_count is not None and nvml.device_count is not None:
            mismatch = nvml.device_count > self._cuda_count
            records.append(
                ObservationRecord(
                    probe_name=self.NAME,
                    probe_version=self.VERSION,
                    subject="management_visibility_exceeds_compute_visibility",
                    category="device_exposure",
                    classification=(
                        "unexpected_visibility" if mismatch else "expected_visibility"
                    ),
                    value=mismatch,
                    confidence=0.85,
                    evidence=[
                        f"the management library enumerates {nvml.device_count} "
                        f"device(s); the CUDA runtime exposes "
                        f"{self._cuda_count}"
                    ],
                    limitations=[
                        "a mismatch shows the container narrowed one interface "
                        "and not the other; it does not show that the extra "
                        "devices are usable, and it is not evidence that "
                        "another tenant is present on them"
                    ],
                )
            )

        params = _read_text(Path("/proc/driver/nvidia/params"))
        if params is None:
            records.append(
                self._not_testable(
                    "profiling_restricted_to_admin",
                    "the driver parameter interface is not readable from this "
                    "container, which is itself a restriction",
                )
            )
        else:
            restricted = "RestrictProfilingToAdminUsers: 1" in params
            records.append(
                ObservationRecord(
                    probe_name=self.NAME,
                    probe_version=self.VERSION,
                    subject="profiling_restricted_to_admin",
                    category="device_exposure",
                    classification=(
                        "secure_restriction" if restricted else "ambiguous"
                    ),
                    value=restricted,
                    confidence=0.9,
                    evidence=["read from the driver parameter interface"],
                    limitations=[
                        "unrestricted profiling is the NVIDIA default on many "
                        "images and is required by ordinary profiling tools; it "
                        "is ambiguous rather than a finding"
                    ],
                )
            )
        return records

    def _process_visibility(self, nvml: NvmlSnapshot) -> list[ObservationRecord]:
        """Can this tenant enumerate compute processes it does not own?

        The count is the measurement. Identities are never requested — see
        ``gpu_seal.cuda.nvml._read_process_count``, which calls with a
        zero-length output array so the per-process structures have nowhere to
        be written.
        """
        if nvml.compute_process_count is None:
            return [
                self._not_testable(
                    "compute_process_visibility",
                    "the management library declined to enumerate compute "
                    "processes, which is the restricted and correct behaviour",
                )
            ]

        # Our own process holds no CUDA context at inventory time, so anything
        # above zero is somebody else's — but "somebody else" includes other
        # processes belonging to this same tenant, which is why this is
        # ambiguous rather than a finding.
        others = nvml.compute_process_count
        return [
            ObservationRecord(
                probe_name=self.NAME,
                probe_version=self.VERSION,
                subject="compute_process_visibility",
                category="device_exposure",
                classification="ambiguous" if others else "secure_restriction",
                value=others,
                confidence=0.7 if others else 0.9,
                evidence=[
                    f"the management library described {others} compute "
                    f"process(es) to this tenant"
                ],
                limitations=[
                    "process count does not distinguish another tenant from "
                    "another process of our own; establishing that a "
                    "neighbour is visible requires a controlled two-instance "
                    "experiment, which is Phase 2 work",
                    "no process identity, name, or memory figure was requested",
                ],
            )
        ]

    # ------------------------------------------------------------------
    # Confinement
    # ------------------------------------------------------------------

    def _capabilities(self) -> list[ObservationRecord]:
        status = _read_text(_PROC_SELF / "status")
        if status is None:
            return [self._not_testable("effective_capabilities", _NOT_LINUX)]

        raw = _status_field(status, "CapEff")
        if raw is None:
            return [
                self._not_testable(
                    "effective_capabilities",
                    "the process status interface did not report a capability mask",
                )
            ]

        try:
            mask = int(raw, 16)
        except ValueError:
            return [
                self._not_testable(
                    "effective_capabilities",
                    "the capability mask was not parseable as hexadecimal",
                )
            ]

        held = sorted(
            name for name, bit in _CAPABILITY_BITS.items() if mask & (1 << bit)
        )
        unexpected = sorted(set(held) & _UNEXPECTED_CAPABILITIES)

        return [
            ObservationRecord(
                probe_name=self.NAME,
                probe_version=self.VERSION,
                subject="effective_capabilities",
                category="device_exposure",
                classification=(
                    "unexpected_visibility" if unexpected else "secure_restriction"
                ),
                value=held,
                confidence=0.95,
                evidence=[
                    f"effective capability mask 0x{mask:016x}",
                    (
                        f"privileged capabilities held: {', '.join(unexpected)}"
                        if unexpected
                        else "none of the privileged capabilities checked are held"
                    ),
                ],
                limitations=[
                    "only four capability bits are inspected, chosen because a "
                    "CUDA workload has no use for any of them; a full "
                    "capability audit is not attempted",
                    "holding a capability is not the same as it being usable "
                    "against the host, and GPU-SEAL does not test whether it is",
                ],
            )
        ]

    def _confinement(self) -> list[ObservationRecord]:
        status = _read_text(_PROC_SELF / "status")
        records: list[ObservationRecord] = []

        if status is None:
            records.append(self._not_testable("seccomp_mode", _NOT_LINUX))
        else:
            raw = _status_field(status, "Seccomp")
            label = _SECCOMP_LABELS.get((raw or "").strip(), "unknown")
            records.append(
                ObservationRecord(
                    probe_name=self.NAME,
                    probe_version=self.VERSION,
                    subject="seccomp_mode",
                    category="device_exposure",
                    classification=(
                        "secure_restriction"
                        if label == "filter"
                        else "ambiguous"
                        if label != "unknown"
                        else "not_testable"
                    ),
                    value=label,
                    confidence=0.9 if label != "unknown" else 0.0,
                    evidence=["read from the process status interface"],
                    limitations=[
                        "a filter being installed says nothing about how "
                        "permissive it is; GPU-SEAL does not enumerate it"
                    ],
                    not_testable_reason=(
                        None
                        if label != "unknown"
                        else "the process status interface did not report a "
                        "seccomp mode"
                    ),
                )
            )

        context = _read_text(_PROC_SELF / "attr" / "current")
        confined = context is not None and context.strip() not in ("", "unconfined")
        records.append(
            ObservationRecord(
                probe_name=self.NAME,
                probe_version=self.VERSION,
                subject="mandatory_access_control_applied",
                category="device_exposure",
                classification=(
                    "secure_restriction" if confined else "ambiguous"
                ),
                # The label itself can encode host-specific detail, so only the
                # boolean is recorded.
                value=confined,
                confidence=0.8 if context is not None else 0.0,
                evidence=[
                    "a mandatory-access-control label is applied to this process"
                    if confined
                    else "no mandatory-access-control label is applied, or the "
                    "interface is absent"
                ],
                limitations=[
                    "the policy label is not recorded — it can encode "
                    "host-specific detail (CHARTER.md §10)",
                    "an applied label says nothing about how restrictive the "
                    "policy behind it is",
                ],
            )
        )
        return records

    def _container_driver_capabilities(self) -> list[ObservationRecord]:
        """The NVIDIA container runtime's own capability grants.

        ``NVIDIA_DRIVER_CAPABILITIES`` decides which driver libraries are
        mounted into the container. A job that needs ``compute`` and receives
        ``all`` was over-granted, and the cross-provider distribution of that
        value is a directly relevant unmeasured number (CHARTER.md §9.6).
        """
        records: list[ObservationRecord] = []

        for var, subject in (
            ("NVIDIA_VISIBLE_DEVICES", "container_visible_devices_request"),
            ("NVIDIA_DRIVER_CAPABILITIES", "container_driver_capabilities_grant"),
        ):
            value = os.environ.get(var)
            if value is None:
                records.append(
                    self._not_testable(
                        subject,
                        "the container runtime variable is not set in this "
                        "environment; the image may not have been started by "
                        "the NVIDIA container runtime",
                    )
                )
                continue

            over_granted = value.strip().lower() == "all"

            # NVIDIA_VISIBLE_DEVICES accepts "all", "none", a comma-separated
            # list of ordinal indices, OR a comma-separated list of stable
            # GPU-/MIG- UUIDs. Only the last form is a CHARTER.md §10
            # never-published identifier, and "container_visible_devices_request"
            # doesn't itself contain a NEVER_PUBLISH_FIELD_FRAGMENTS fragment,
            # so ObservationRecord's generic subject check can't catch it —
            # hash it here instead of recording it raw.
            recorded_subject = subject
            recorded_value: object = value
            evidence_value = repr(value)
            if var == "NVIDIA_VISIBLE_DEVICES" and _names_stable_gpu_identifiers(value):
                recorded_subject = f"{subject}_gpu_uuid_hash"
                recorded_value = stable_hash(value, domain="gpu_uuid")
                evidence_value = "a hashed stable GPU/MIG identifier"

            records.append(
                ObservationRecord(
                    probe_name=self.NAME,
                    probe_version=self.VERSION,
                    subject=recorded_subject,
                    category="device_exposure",
                    classification=(
                        "unexpected_visibility" if over_granted else "expected_visibility"
                    ),
                    value=recorded_value,
                    confidence=0.85,
                    evidence=[f"{var} is set to {evidence_value}"],
                    limitations=[
                        "the variable records what was requested of the "
                        "container runtime, not what the kernel ultimately "
                        "permitted",
                    ],
                )
            )
        return records

    def _omitted_socket_inventory(self) -> ObservationRecord:
        """Record the deliberate gap, rather than leaving a silent hole."""
        return ObservationRecord(
            probe_name=self.NAME,
            probe_version=self.VERSION,
            subject="host_management_socket_inventory",
            category="device_exposure",
            classification="not_testable",
            confidence=0.0,
            evidence=[],
            limitations=[
                "CHARTER.md §9.6 lists host-management sockets among the "
                "interfaces to inventory; this census does not cover them",
            ],
            not_testable_reason=(
                "deliberately not implemented: inventorying these interfaces "
                "requires naming their paths in probe source, which the §16 "
                "test-17 static analysis refuses. A file that names the "
                "interface is one edit from a file that uses it, and §23 "
                "forbids implementing the technique even for inventory. The "
                "census is one row poorer and the repository stays handable to "
                "a provider's security team."
            ),
        )

    # ------------------------------------------------------------------

    def _not_testable(self, subject: str, reason: str) -> ObservationRecord:
        return ObservationRecord(
            probe_name=self.NAME,
            probe_version=self.VERSION,
            subject=subject,
            category="device_exposure",
            classification="not_testable",
            confidence=0.0,
            evidence=[],
            limitations=["not measured in this environment"],
            not_testable_reason=reason,
        )


# ---------------------------------------------------------------------------


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii", errors="ignore")
    except OSError:
        return None


def _status_field(status_text: str, field: str) -> str | None:
    """Pull one field out of /proc/self/status.

    Line-oriented splitting rather than a regex: `re` is not importable in
    probe source (§16 test 5), and building the habit of pattern-matching over
    environment text is exactly what that rule exists to prevent.
    """
    prefix = f"{field}:"
    for line in status_text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def _names_stable_gpu_identifiers(value: str) -> bool:
    """True if a NVIDIA_VISIBLE_DEVICES value names GPU/MIG UUIDs, not indices.

    The variable is documented to accept ``"all"``, ``"none"``, a
    comma-separated list of ordinal indices, or a comma-separated list of
    ``GPU-...``/``MIG-...`` UUIDs. Only the last form is a stable identifier.
    """
    return any(
        part.strip().upper().startswith(("GPU-", "MIG-"))
        for part in value.split(",")
    )


def unexpected_visibility_count(records: Sequence[ObservationRecord]) -> int:
    """How many findings are genuinely unexpected. Input to the §13.2 grade."""
    return sum(1 for r in records if r.classification == "unexpected_visibility")
