"""Regression tests for campaign-wide stopping and provider orchestration."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from gpu_seal.controller import (
    BudgetLedger,
    CampaignOrchestrator,
    CampaignRunSpec,
    CleanupReconciliationError,
    DeterministicFakeRuntime,
    ExperimentPlan,
    NativeProviderRunner,
    NativeRunConfig,
    ProviderPolicy,
    ProviderPolicyMatrix,
    Scheduler,
    SpendLimits,
    TerminationResult,
)
from gpu_seal.controller.evidence_store import EvidenceStore
from gpu_seal.cuda import SimulatedBackend
from gpu_seal.evidence import (
    EphemeralDevelopmentKeySource,
    ExternalSigningKeySource,
    SigningKey,
    key_source_from_options,
    signing_metadata,
)
from gpu_seal.probes import GlobalMemoryProbe
from gpu_seal.safety import (
    Boundary,
    CampaignContextRequired,
    CampaignControl,
    CampaignTerminated,
    CanarySet,
    RedactedStopRecord,
)


def _scheduler() -> Scheduler:
    matrix = ProviderPolicyMatrix(
        policies={
            "provider-a": ProviderPolicy(
                provider_code="provider-a",
                classification="full-probe-ok",
                policy_sources=["unit-test policy"],
                reviewed_on=date(2026, 9, 3),
                reviewed_by="unit-test",
                policy_version="test",
            )
        }
    )
    ledger = BudgetLedger(
        limits=SpendLimits(
            per_run=10.0,
            per_provider=100.0,
            per_day=100.0,
            per_campaign=100.0,
        )
    )
    return Scheduler(policy_matrix=matrix, ledger=ledger)


def _plan(run_id: str, *, estimated_cost: float = 0.0) -> ExperimentPlan:
    return ExperimentPlan(
        experiment_id="campaign-test",
        provider_code="provider-a",
        probe_name="memory_global_read_before_write",
        ownership_confirmation="unit-test allocation owned by this account",
        confirmed_by="unit-test",
        estimated_cost=estimated_cost,
        product_claim="simulated-test-gpu",
    )


def _config() -> NativeRunConfig:
    return NativeRunConfig(binary=Path("/fake/native"), cycles=1, size_mib=1)


def _stop() -> RedactedStopRecord:
    return RedactedStopRecord(
        probe_name="native_driver_direct",
        probe_version="0.1.0-native",
        reason_code="high_entropy_content",
        size_bucket="gte-1m",
        boundary=Boundary.SEPARATE_LAUNCH.name,
        operational_metadata={
            "backend": "deterministic-fake",
            "backend_is_real": "false",
            "measurement_path": "simulated",
            "shared_infrastructure": "true",
        },
    )


def _stop_output() -> str:
    import json

    return "\n".join(
        [
            json.dumps({"kind": "stop", **_stop().to_dict()}),
            json.dumps(
                {
                    "kind": "summary",
                    "mode": "reuse",
                    "cycles": 1,
                    "terminated_early": True,
                    "terminal_reason": "sensitive_observation",
                }
            ),
        ]
    )


def test_shared_execution_requires_an_explicit_root_campaign():
    backend = SimulatedBackend(pool_bytes=2 << 20)
    with pytest.raises(CampaignContextRequired):
        GlobalMemoryProbe(backend, CanarySet.create(), shared_infrastructure=True)

    runtime = DeterministicFakeRuntime()
    runner = NativeProviderRunner(_scheduler(), runtime)
    with pytest.raises(CampaignContextRequired):
        runner.run(_plan("missing-context"), _config(), run_id="missing-context")
    assert runtime.launched == []
    assert runtime.commands == []


def test_stop_from_one_runner_blocks_a_separately_constructed_runner():
    campaign = CampaignControl.create()
    first_runtime = DeterministicFakeRuntime(stdout=_stop_output())
    first = NativeProviderRunner(_scheduler(), first_runtime, campaign=campaign)

    record, execution = first.run(
        _plan("stop-first"), _config(), run_id="stop-first"
    )

    assert not record.completed
    assert execution is not None and execution.stopped
    assert campaign.terminated

    second_runtime = DeterministicFakeRuntime()
    second = NativeProviderRunner(_scheduler(), second_runtime, campaign=campaign)
    with pytest.raises(CampaignTerminated):
        second.run(_plan("stop-second"), _config(), run_id="stop-second")
    assert second_runtime.launched == []
    assert second_runtime.commands == []
    assert second_runtime.terminated == []


def test_campaign_stop_blocks_memory_copy_even_for_an_existing_allocation():
    class CountingBackend(SimulatedBackend):
        def __init__(self) -> None:
            super().__init__(pool_bytes=2 << 20)
            self.copy_count = 0

        def copy_to_host(self, alloc, view):  # type: ignore[no-untyped-def]
            self.copy_count += 1
            super().copy_to_host(alloc, view)

    backend = CountingBackend()
    allocation = backend.malloc(1 << 20)
    campaign = CampaignControl.create()
    campaign.terminate(_stop())
    probe = GlobalMemoryProbe(
        backend,
        CanarySet.create(),
        shared_infrastructure=False,
        campaign=campaign,
    )
    try:
        with pytest.raises(CampaignTerminated):
            probe.read_before_write(
                allocation,
                boundary=Boundary.SEPARATE_LAUNCH,
            )
        assert backend.copy_count == 0
    finally:
        backend.free(allocation)


def test_orchestrator_runs_fake_runtime_and_stops_after_timeout():
    campaign = CampaignControl.create()
    runtime = DeterministicFakeRuntime(force_timeout=True)
    orchestrator = CampaignOrchestrator(
        _scheduler(), runtime, campaign=campaign
    )
    specs = tuple(
        CampaignRunSpec(plan=_plan(name), config=_config(), run_id=name)
        for name in ("timeout-one", "timeout-two")
    )

    result = orchestrator.run(specs)

    assert result.failed
    assert result.outcomes[0].error_type == "NativeExecutionError"
    assert result.skipped_run_ids == ("timeout-two",)
    assert len(runtime.launched) == 1
    assert len(runtime.commands) == 1
    assert len(runtime.terminated) == 1


def test_orchestrator_success_contract_is_deterministic():
    runtime = DeterministicFakeRuntime()
    result = CampaignOrchestrator(
        _scheduler(), runtime, campaign=CampaignControl.create()
    ).run(
        [
            CampaignRunSpec(
                plan=_plan("fake-success"), config=_config(), run_id="fake-success"
            )
        ]
    )

    assert not result.failed
    assert result.outcomes[0].completed
    execution = result.outcomes[0].execution
    assert execution is not None
    assert execution.records[0].driver_metadata["backend"] == "deterministic-fake"
    assert execution.records[0].driver_metadata["backend_is_real"] == "false"


def test_orchestrator_can_sign_and_store_simulated_validation(tmp_path: Path):
    source = EphemeralDevelopmentKeySource(unsafe_development=True)
    result = CampaignOrchestrator(
        _scheduler(), DeterministicFakeRuntime(), campaign=CampaignControl.create()
    ).run_and_store(
        [
            CampaignRunSpec(
                plan=_plan("fake-stored"), config=_config(), run_id="fake-stored"
            )
        ],
        store=EvidenceStore(tmp_path),
        key_source=source,
    )

    stored = result.outcomes[0].stored
    assert stored is not None
    assert stored.signature_verified
    assert not stored.publishable
    assert stored.path.name == "fake-stored.result.json"


def test_orchestrator_reconciles_unknown_cleanup_as_a_failure():
    runtime = DeterministicFakeRuntime(
        termination=TerminationResult.unknown("provider did not confirm termination")
    )
    result = CampaignOrchestrator(
        _scheduler(), runtime, campaign=CampaignControl.create()
    ).run(
        [CampaignRunSpec(plan=_plan("cleanup"), config=_config(), run_id="cleanup")]
    )

    assert result.failed
    assert result.outcomes[0].error_type == CleanupReconciliationError.__name__
    assert len(runtime.terminated) == 1


def test_signing_sources_are_explicit_and_metadata_contains_only_public_identity(
    tmp_path: Path,
):
    original = SigningKey.generate()
    pem_path = tmp_path / "operator-ed25519.pem"
    pem_path.write_bytes(original.to_pem())

    source = key_source_from_options(pem_path)
    signer = source.load()
    metadata = signing_metadata(source, signer)

    assert signer.verify_key.fingerprint == original.verify_key.fingerprint
    assert metadata["key_source"] == "caller-supplied-ed25519-pem"
    assert metadata["public_key_fingerprint"] == signer.verify_key.fingerprint
    assert "BEGIN PRIVATE" not in repr(metadata)

    with pytest.raises(ValueError, match="signing key is required"):
        key_source_from_options(None)
    with pytest.raises(ValueError, match="either --signing-key"):
        key_source_from_options(
            pem_path, unsafe_development_ephemeral=True
        )

    unsafe = EphemeralDevelopmentKeySource(unsafe_development=True)
    assert unsafe.provenance_suitable is False
    assert unsafe.load().verify_key.fingerprint == unsafe.load().verify_key.fingerprint
    external = ExternalSigningKeySource(
        loader=lambda: signer, source_label="test-os-key-store"
    )
    assert external.load().verify_key.fingerprint == signer.verify_key.fingerprint
