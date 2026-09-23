"""Software-only coverage for lab/cloud-runner/run_mig_isolation.py.

No MIG hardware exists in CI or in this repository's own dev environment, so
every test here drives the orchestration through ``FakeMigRuntime`` — the
driver-level double described in the script's own module docstring, which
exercises the real ``plant()`` / ``measure_successor()`` / ``CanarySet``
round trip against ``SimulatedBackend`` rather than returning canned JSON.

The one property these tests care about most: refusing on non-MIG hardware
(step 1) must never be weakened, and must fire *before* any lifecycle call
(``create_instance``, ``set_mig_mode``) happens.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import uuid
from pathlib import Path

import pytest


def _load_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "lab"
        / "cloud-runner"
        / "run_mig_isolation.py"
    )
    spec = importlib.util.spec_from_file_location("gpu_seal_run_mig_isolation", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return _load_module()


EXCLUSIVITY = {
    "source": "operator-attestation",
    "reference": "test fixture",
    "verification_method": "test fixture",
}


# ---------------------------------------------------------------------------
# Step 1: capability assertion must refuse before any mutation
# ---------------------------------------------------------------------------


def test_assert_capability_refuses_on_non_mig_hardware(module):
    runtime = module.FakeMigRuntime(
        capability_available=False, capability_reason="consumer silicon"
    )
    with pytest.raises(module.MigUnavailable, match="consumer silicon"):
        module._assert_capability(runtime)
    # The refusal must precede any lifecycle mutation -- nothing was created
    # or mode-changed before capability was checked.
    assert runtime.created == []
    assert runtime.mode_changes == []


def test_assert_capability_passes_when_available(module):
    runtime = module.FakeMigRuntime(capability_available=True)
    module._assert_capability(runtime)  # must not raise


def test_worker_require_mig_gate_is_not_weakened(module):
    """Defense in depth: even if capability were somehow forwarded as False,
    the worker's own MigTemporalProbe(require_mig=True) must still refuse.
    This is the same guard lab/verify-safety-suite.sh mutates to prove live;
    this test proves this script never constructs it with require_mig=False.
    """
    canaries_experiment_id = uuid.uuid4()
    request = {
        "role": "plant",
        "experiment_id": str(canaries_experiment_id),
        "canary_key_hex": (b"\x00" * 32).hex(),
        "boundary": "MIG_SAME_PROFILE",
        "size_bytes": 4096,
        "simulate": True,
        "nvml_mig_enabled": False,
        "exclusivity_evidence": EXCLUSIVITY,
    }
    with pytest.raises(module.MigUnavailable):
        module._execute_worker(request)


# ---------------------------------------------------------------------------
# The canary hex round trip _execute_worker relies on to cross a process
# boundary (real subprocess) or a synthetic one (FakeMigRuntime)
# ---------------------------------------------------------------------------


def test_canary_hex_round_trip_authenticates(module):
    from gpu_seal.safety import Boundary, CanarySet
    from gpu_seal.safety.canary import Canary

    canaries = CanarySet.create()
    canary = canaries.mint(Boundary.MIG_SAME_PROFILE)

    # Serialise exactly as _execute_worker's "plant" role does.
    wire = {
        "allocation_id": str(canary.allocation_id),
        "nonce_hex": canary.nonce.hex(),
        "blob_hex": canary.blob.hex(),
    }

    # Reconstruct exactly as _execute_worker's "measure" role does, in a
    # fresh CanarySet standing in for a separate process.
    allocation_id = uuid.UUID(wire["allocation_id"])
    rebuilt = Canary(
        blob=bytes.fromhex(wire["blob_hex"]),
        experiment_id=canaries.experiment_id,
        allocation_id=allocation_id,
        boundary=Boundary.MIG_SAME_PROFILE,
        nonce=bytes.fromhex(wire["nonce_hex"]),
    )
    rehydrated = CanarySet(
        experiment_id=canaries.experiment_id,
        _key=canaries._key,
        _emitted={allocation_id: rebuilt},
    )
    assert rehydrated.owns(rebuilt.blob)
    matches = rehydrated.search(canary.blob, allocation_id_scope={allocation_id})
    assert len(matches) == 1
    assert matches[0].exact
    assert matches[0].mac_verified


# ---------------------------------------------------------------------------
# One full boundary cycle against the fake runtime
# ---------------------------------------------------------------------------


def test_run_boundary_cycle_same_profile(module):
    from gpu_seal.safety import Boundary, CanarySet

    runtime = module.FakeMigRuntime()
    canaries = CanarySet.create()

    result, destroy_recreate = module.run_boundary_cycle(
        runtime,
        experiment_id=canaries.experiment_id,
        canary_key=canaries._key,
        boundary=Boundary.MIG_SAME_PROFILE,
        predecessor_profile=(9, 0),
        successor_profile=(9, 0),
        size_bytes=4096,
        exclusivity_evidence=EXCLUSIVITY,
        nvml_mig_enabled=True,
        simulate=True,
        timeout_s=30,
    )

    assert result.usable
    assert result.error_code is None
    assert result.boundary is Boundary.MIG_SAME_PROFILE
    assert result.canaries_planted > 0
    assert result.teardown_performed  # required, non-empty

    assert destroy_recreate.boundary == "MIG_SAME_PROFILE"
    assert destroy_recreate.profile_changed is False
    assert destroy_recreate.predecessor["gpu_instance_id"] != (
        destroy_recreate.successor["gpu_instance_id"]
    )
    assert destroy_recreate.recreated_monotonic >= destroy_recreate.destroyed_monotonic

    # Both instances created for this cycle were torn down -- no live leak.
    assert len(runtime.created) == 2
    assert len(runtime.destroyed) == 2


def test_run_boundary_cycle_different_profile_marks_profile_changed(module):
    from gpu_seal.safety import Boundary, CanarySet

    runtime = module.FakeMigRuntime()
    canaries = CanarySet.create()

    _result, destroy_recreate = module.run_boundary_cycle(
        runtime,
        experiment_id=canaries.experiment_id,
        canary_key=canaries._key,
        boundary=Boundary.MIG_DIFFERENT_PROFILE,
        predecessor_profile=(9, 0),
        successor_profile=(5, 0),
        size_bytes=4096,
        exclusivity_evidence=EXCLUSIVITY,
        nvml_mig_enabled=True,
        simulate=True,
        timeout_s=30,
    )
    assert destroy_recreate.profile_changed is True


def test_destroy_recreate_boundary_to_dict_is_json_safe(module):
    from gpu_seal.safety import Boundary, CanarySet

    runtime = module.FakeMigRuntime()
    canaries = CanarySet.create()
    _result, destroy_recreate = module.run_boundary_cycle(
        runtime,
        experiment_id=canaries.experiment_id,
        canary_key=canaries._key,
        boundary=Boundary.MIG_SAME_PROFILE,
        predecessor_profile=(9, 0),
        successor_profile=(9, 0),
        size_bytes=4096,
        exclusivity_evidence=EXCLUSIVITY,
        nvml_mig_enabled=True,
        simulate=True,
        timeout_s=30,
    )
    encoded = json.dumps(destroy_recreate.to_dict())
    assert "teardown_to_recreate_seconds" in encoded
    # Never a raw UUID -- only the stable_hash form, which always starts
    # with the documented prefix.
    for handle in (destroy_recreate.predecessor, destroy_recreate.successor):
        if handle["gpu_instance_uuid_hash"] is not None:
            assert handle["gpu_instance_uuid_hash"].startswith("sha256:")


# ---------------------------------------------------------------------------
# main() end to end, through --fake-runtime
# ---------------------------------------------------------------------------


def test_main_fake_runtime_end_to_end_writes_a_signed_bundle(module, tmp_path):
    rc = module.main(
        [
            "--fake-runtime",
            "--gpu-instance-profile-id",
            "9",
            "--compute-instance-profile-id",
            "0",
            "--cycles",
            "1",
            "--unsafe-development-ephemeral",
            "--out",
            str(tmp_path),
        ]
    )
    assert rc == 0
    bundles = list(tmp_path.glob("*.result.json"))
    assert len(bundles) == 1
    payload = json.loads(bundles[0].read_text(encoding="utf-8"))
    assert payload["safety"]["canary_only_search"] is True
    assert "mig_lifecycle" in payload["environment"]
    assert len(payload["environment"]["mig_lifecycle"]) == 1
    assert payload["environment"]["mig_lifecycle"][0]["boundary"] == "MIG_SAME_PROFILE"
    # MIG mode was enabled, then always restored -- both are explicit
    # before/after records, and they are NOT the same record.
    mode_change = payload["environment"]["mig_mode_change"]
    mode_restore = payload["environment"]["mig_mode_restore"]
    assert mode_change["before"] is None and mode_change["after"] is True
    assert mode_restore["before"] is True and mode_restore["after"] is False


def test_main_refuses_without_exclusivity_attestation_on_real_path(module):
    with pytest.raises(SystemExit):
        module.main(
            [
                "--gpu-instance-profile-id",
                "9",
                "--compute-instance-profile-id",
                "0",
                "--unsafe-development-ephemeral",
            ]
        )


def test_main_requires_paired_different_profile_arguments(module):
    with pytest.raises(SystemExit):
        module.main(
            [
                "--fake-runtime",
                "--gpu-instance-profile-id",
                "9",
                "--compute-instance-profile-id",
                "0",
                "--different-gpu-instance-profile-id",
                "5",
                "--unsafe-development-ephemeral",
            ]
        )


def test_main_worker_mode_plants_via_stdin(module, monkeypatch, capsys):
    from gpu_seal.safety import CanarySet

    canaries = CanarySet.create()
    request = {
        "role": "plant",
        "experiment_id": str(canaries.experiment_id),
        "canary_key_hex": canaries._key.hex(),
        "boundary": "MIG_SAME_PROFILE",
        "size_bytes": 4096,
        "simulate": True,
        "nvml_mig_enabled": True,
        "exclusivity_evidence": EXCLUSIVITY,
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
    rc = module.main(["--worker", "plant"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["canaries_planted"] > 0
    assert len(out["canaries"]) == out["canaries_planted"]


def test_main_worker_mode_reports_failure_on_stderr_without_raising(
    module, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    rc = module.main(["--worker", "plant"])
    assert rc == 1
    assert capsys.readouterr().err  # some diagnostic was printed, not silently lost
