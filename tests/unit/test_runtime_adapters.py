"""Meaningful software-only coverage for runtime-facing probe adapters."""

from __future__ import annotations

from pathlib import Path

import pytest

import gpu_seal.cuda.nvml as nvml_module
import gpu_seal.probes.device_exposure as exposure_module
import gpu_seal.probes.environment as environment_module
from gpu_seal.cuda import SimulatedBackend
from gpu_seal.cuda.nvml import NvmlSnapshot
from gpu_seal.probes.device_exposure import DeviceExposureProbe
from gpu_seal.probes.environment import EnvironmentInventoryProbe, ProviderClaims
from gpu_seal.probes.memory_local import LocalMemoryProbe, SharedMemoryLaunch
from gpu_seal.safety import CampaignContextRequired, CampaignControl, CanarySet


class _RecordingSharedMemoryLaunch(SharedMemoryLaunch):
    def __init__(self, backend: SimulatedBackend) -> None:
        self._backend = backend
        self._marker = b""
        self.plant_calls = 0
        self.read_calls = 0

    def plant(self, marker: bytes, *, blocks: int, shared_bytes: int) -> None:
        del blocks, shared_bytes
        self._marker = marker
        self.plant_calls += 1

    def read_back(self, out, *, blocks: int, shared_bytes: int) -> None:  # type: ignore[no-untyped-def]
        del blocks, shared_bytes
        self._backend.write_to_device(out, 0, self._marker)
        self.read_calls += 1


def test_memory_local_positive_control_copies_only_into_safe_buffer():
    backend = SimulatedBackend(pool_bytes=2 << 20)
    launcher = _RecordingSharedMemoryLaunch(backend)
    probe = LocalMemoryProbe(
        backend,
        CanarySet.create(),
        launcher,
        shared_infrastructure=False,
        campaign=CampaignControl.create(),
    )

    cycle = probe.run_positive_control(shared_bytes=1024, blocks=1)

    assert cycle.usable
    assert cycle.canary_recovered
    assert launcher.plant_calls == 1
    assert launcher.read_calls == 1


def test_memory_local_shared_path_requires_campaign_context():
    with pytest.raises(CampaignContextRequired):
        LocalMemoryProbe(
            SimulatedBackend(pool_bytes=2 << 20),
            CanarySet.create(),
            SharedMemoryLaunch(),
            shared_infrastructure=True,
        )


class _DeviceInfoBackend(SimulatedBackend):
    def device_info(self) -> dict[str, str]:
        return {**super().device_info(), "device_id": "0"}


def test_environment_inventory_hashes_account_and_uses_backend_visibility(
    monkeypatch,
):
    monkeypatch.setattr(environment_module, "_PROC", Path("C:/missing-proc"))
    probe = EnvironmentInventoryProbe(
        _DeviceInfoBackend(pool_bytes=2 << 20),
        claims=ProviderClaims(
            provider_code="provider-test",
            product_name="test product",
            advertised_region="test-region",
            advertised_gpu="test-gpu",
        ),
        nvml=NvmlSnapshot(available=True, device_count=None, mig_enabled=None),
        campaign=CampaignControl.create(),
    )

    inventory = probe.collect(
        experiment_id="env-test",
        tool_version="test",
        tool_commit="test-commit",
        researcher_account_id="account-secret",
    )
    observations = probe.observations(inventory)

    assert inventory.provider["provider_code"] == "provider-test"
    assert inventory.system["containerised"] is None
    assert inventory.gpu["visible_device_count"] == 1
    assert inventory.experiment["researcher_account_id_hash"].startswith("sha256:")
    assert "account-secret" not in str(inventory)
    by_subject = {record.subject: record for record in observations}
    assert by_subject["containerised"].classification == "not_testable"
    assert by_subject["mig_mode"].classification == "not_testable"


def test_device_exposure_reports_confinement_and_hashed_runtime_requests(
    monkeypatch, tmp_path: Path
):
    proc_self = tmp_path / "proc-self"
    (proc_self / "attr").mkdir(parents=True)
    (proc_self / "status").write_text(
        "CapEff:\t0000000000000000\nSeccomp:\t2\n", encoding="ascii"
    )
    (proc_self / "attr" / "current").write_text("unconfined\n", encoding="ascii")
    monkeypatch.setattr(exposure_module, "_DEV", tmp_path / "missing-dev")
    monkeypatch.setattr(exposure_module, "_PROC_SELF", proc_self)
    monkeypatch.setenv("NVIDIA_VISIBLE_DEVICES", "GPU-test-uuid")
    monkeypatch.setenv("NVIDIA_DRIVER_CAPABILITIES", "all")

    records = DeviceExposureProbe(
        nvml=NvmlSnapshot(
            available=True,
            device_count=2,
            mig_enabled=False,
            compute_process_count=3,
        ),
        cuda_visible_device_count=1,
        campaign=CampaignControl.create(),
    ).collect()
    by_subject = {record.subject: record for record in records}

    assert by_subject["device_nodes"].classification == "not_testable"
    assert by_subject[
        "management_visibility_exceeds_compute_visibility"
    ].value is True
    assert by_subject["effective_capabilities"].value == []
    assert by_subject["effective_capabilities"].classification == "secure_restriction"
    assert by_subject["seccomp_mode"].value == "filter"
    assert by_subject["mandatory_access_control_applied"].value is False
    assert by_subject["container_visible_devices_request_gpu_uuid_hash"].value.startswith(
        "sha256:"
    )
    assert by_subject["container_driver_capabilities_grant"].classification == (
        "unexpected_visibility"
    )


class _FakeNvml:
    def __init__(self) -> None:
        self.shutdown_calls = 0

    def nvmlInit_v2(self) -> int:
        return 0

    def nvmlShutdown(self) -> None:
        self.shutdown_calls += 1

    def nvmlDeviceGetCount_v2(self, count) -> int:  # type: ignore[no-untyped-def]
        count._obj.value = 2
        return 0

    def nvmlDeviceGetHandleByIndex_v2(self, index, handle) -> int:  # type: ignore[no-untyped-def]
        del index
        handle._obj.value = 7
        return 0

    def nvmlDeviceGetMigMode(self, handle, current, pending) -> int:  # type: ignore[no-untyped-def]
        del handle
        current._obj.value = 1
        pending._obj.value = 1
        return 0

    def nvmlDeviceGetUUID(self, handle, buffer, size) -> int:  # type: ignore[no-untyped-def]
        del handle, size
        buffer.value = b"GPU-test-uuid"
        return 0

    def nvmlDeviceGetComputeRunningProcesses_v3(self, handle, count, processes) -> int:  # type: ignore[no-untyped-def]
        del handle, processes
        count._obj.value = 3
        return 0


def test_nvml_adapter_returns_typed_redacted_snapshot(monkeypatch):
    fake = _FakeNvml()
    monkeypatch.setattr(nvml_module, "_load_library", lambda: fake)

    snapshot = nvml_module.read_nvml()

    assert snapshot == NvmlSnapshot(
        available=True,
        device_count=2,
        mig_enabled=True,
        gpu_uuid_hash=snapshot.gpu_uuid_hash,
        compute_process_count=3,
    )
    assert snapshot.gpu_uuid_hash is not None
    assert "GPU-test-uuid" not in snapshot.gpu_uuid_hash
    assert fake.shutdown_calls == 1


def test_nvml_adapter_degrades_when_library_or_initialisation_is_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(nvml_module, "_load_library", lambda: None)
    assert nvml_module.read_nvml().available is False

    class _InitRefused:
        def nvmlInit_v2(self) -> int:
            return 1

    monkeypatch.setattr(nvml_module, "_load_library", lambda: _InitRefused())
    refused = nvml_module.read_nvml()
    assert refused.available is False
    assert "declined" in (refused.unavailable_reason or "")
