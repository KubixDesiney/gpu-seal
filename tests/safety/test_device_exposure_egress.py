"""CHARTER.md §10 — stable GPU/MIG UUIDs in NVIDIA_VISIBLE_DEVICES must not
reach a signed bundle unhashed, even though the subject name that carries
them ("container_visible_devices_request") does not itself contain a
NEVER_PUBLISH_FIELD_FRAGMENTS fragment.
"""

from __future__ import annotations

import pytest

from gpu_seal.cuda.nvml import NvmlSnapshot
from gpu_seal.probes.device_exposure import DeviceExposureProbe

pytestmark = pytest.mark.safety


def _probe() -> DeviceExposureProbe:
    return DeviceExposureProbe(
        nvml=NvmlSnapshot(
            available=False,
            unavailable_reason="test",
            device_count=None,
            mig_enabled=None,
            gpu_uuid_hash=None,
            compute_process_count=None,
        )
    )


def _visible_devices_record(monkeypatch, value: str):
    monkeypatch.setenv("NVIDIA_VISIBLE_DEVICES", value)
    monkeypatch.delenv("NVIDIA_DRIVER_CAPABILITIES", raising=False)
    records = _probe()._container_driver_capabilities()
    return next(r for r in records if r.subject.startswith("container_visible_devices"))


def test_a_stable_gpu_uuid_is_hashed_before_recording(monkeypatch):
    uuid = "GPU-1234abcd-5678-90ef-1234-567890abcdef"
    record = _visible_devices_record(monkeypatch, uuid)
    payload = record.to_dict()
    assert payload["value"].startswith("sha256:")
    assert "GPU-1234abcd" not in str(payload)
    assert "GPU-1234abcd" not in " ".join(payload["evidence"])


def test_a_mig_uuid_is_also_hashed_before_recording(monkeypatch):
    record = _visible_devices_record(monkeypatch, "MIG-GPU-1234abcd/1/0")
    payload = record.to_dict()
    assert payload["value"].startswith("sha256:")
    assert "1234abcd" not in str(payload)


def test_the_hashed_subject_names_what_it_is():
    """So a reader can tell, from the subject alone, that the value is
    hashed — the same convention environment.py uses for gpu_uuid_hash."""
    from gpu_seal.probes.device_exposure import _names_stable_gpu_identifiers

    assert _names_stable_gpu_identifiers("GPU-1234abcd-5678-90ef-1234-567890abcdef")
    assert _names_stable_gpu_identifiers("0,GPU-1234abcd-5678-90ef-1234-567890abcdef")
    assert not _names_stable_gpu_identifiers("all")
    assert not _names_stable_gpu_identifiers("none")
    assert not _names_stable_gpu_identifiers("0,1,2")


def test_an_index_list_is_recorded_unhashed(monkeypatch):
    """Indices carry no CHARTER.md §10 disclosure hazard and stay readable —
    hashing everything indiscriminately would erase the over-granted check."""
    record = _visible_devices_record(monkeypatch, "0,1")
    payload = record.to_dict()
    assert payload["value"] == "0,1"


def test_all_is_still_recorded_unhashed_and_flagged_over_granted(monkeypatch):
    record = _visible_devices_record(monkeypatch, "all")
    payload = record.to_dict()
    assert payload["value"] == "all"
    assert payload["classification"] == "unexpected_visibility"
