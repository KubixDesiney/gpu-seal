"""§9.1, §9.5, §9.6, §9.9, §9.10, §9.11, §9.12 and the §12 statistics.

Grouped because each family's testable surface here is small: most of them are
gated on hardware this project does not have, and the property worth pinning
is that they *refuse correctly* rather than producing a caveated number.
"""

from __future__ import annotations

import dataclasses

import pytest
from gpu_seal.analysis.separability import SeparabilityReport, evaluate_separability
from gpu_seal.analysis.statistics import ObservationCounts, bootstrap_ci, proportion_ci
from gpu_seal.cuda.nvml import NvmlSnapshot
from gpu_seal.probes.attestation import (
    AttestationEvidence,
    AttestationProbe,
    EvidenceSource,
    assess_channel_binding,
)
from gpu_seal.probes.device_exposure import DeviceExposureProbe
from gpu_seal.probes.environment import EnvironmentInventoryProbe, ProviderClaims
from gpu_seal.probes.location import Landmark, LocationProbe, RttSource
from gpu_seal.probes.mig_temporal import (
    MigTemporalProbe,
    MigUnavailable,
    PlantReceipt,
    summarise,
)
from gpu_seal.probes.self_canary import AllocationLeg, interpret
from gpu_seal.probes.topology import DeterministicLatencySource, TopologyProbe
from gpu_seal.safety.canary import Boundary, CanarySet
from gpu_seal.safety.policy import EXPOSURE_CLASSIFICATIONS


def certificate(die_seed: int = 1, *, as_evidence: bool = False):
    """A topology certificate.

    ``as_evidence`` forges the fidelity stamp so the D5 gate can be tested on
    its own. Two independent gates guard a same-device claim — the D5 one and
    the is-this-real-silicon one — and a test that leaves both closed cannot
    show which of them did the refusing.
    """
    cert = TopologyProbe(
        DeterministicLatencySource(die_seed=die_seed, jitter_cycles=0.001)
    ).certify(regions=4, blocks=8, hops=64, repetitions=3)
    if as_evidence:
        cert = dataclasses.replace(cert, fidelity="sm_resolved")
    return cert


def validated_separability_report() -> SeparabilityReport:
    """A genuinely-validated §9.8b evaluation, for exercising the D5 gate.

    Built the same way ``interpret()`` requires it be built in real use — via
    ``evaluate_separability()`` on certificates from two well-separated dies
    — rather than a bare ``d5_validated=True`` assertion.
    """
    labelled = [("die-a", certificate(die_seed=1)) for _ in range(4)]
    labelled += [("die-b", certificate(die_seed=40)) for _ in range(4)]
    report = evaluate_separability(labelled, conditions=["test fixture"])
    assert report.validated is True, (
        "fixture must validate, or the tests using it mean nothing"
    )
    return report


# ---------------------------------------------------------------------------
# §9.1 environment inventory
# ---------------------------------------------------------------------------


def test_inventory_produces_the_four_charter_blocks():
    inventory = EnvironmentInventoryProbe(
        claims=ProviderClaims(provider_code="provider-a", advertised_gpu="H100 SXM"),
        nvml=NvmlSnapshot(available=False, unavailable_reason="not present"),
    ).collect(experiment_id="exp_1", tool_version="0.1.0", tool_commit="sha256:abc")
    assert set(inventory.to_dict()) == {"experiment", "provider", "system", "gpu"}


def test_inventory_hashes_the_account_identifier_at_collection():
    """CHARTER.md §10: the clear value never reaches a serialisable field."""
    inventory = EnvironmentInventoryProbe(
        nvml=NvmlSnapshot(available=False, unavailable_reason="not present")
    ).collect(
        experiment_id="exp_1",
        tool_version="0.1.0",
        tool_commit="sha256:abc",
        researcher_account_id="acct-999999",
    )
    hashed = inventory.experiment["researcher_account_id_hash"]
    assert hashed.startswith("sha256:")
    assert "acct-999999" not in str(inventory.to_dict())


def test_inventory_keeps_claims_separate_from_measurements():
    """Reading the advertised model off the machine would defeat §13.3."""
    inventory = EnvironmentInventoryProbe(
        claims=ProviderClaims(advertised_gpu="H100 SXM"),
        nvml=NvmlSnapshot(available=False, unavailable_reason="not present"),
    ).collect(experiment_id="exp_1", tool_version="0.1.0", tool_commit="sha256:abc")
    assert inventory.provider["advertised_gpu"] == "H100 SXM"
    assert "advertised_gpu" not in inventory.gpu


# ---------------------------------------------------------------------------
# §9.6 device exposure
# ---------------------------------------------------------------------------


def test_exposure_records_use_only_charter_classifications():
    records = DeviceExposureProbe(
        nvml=NvmlSnapshot(available=False, unavailable_reason="not present"),
        cuda_visible_device_count=1,
    ).collect()
    assert records
    for record in records:
        assert record.classification in EXPOSURE_CLASSIFICATIONS


def test_management_visibility_exceeding_compute_visibility_is_flagged():
    records = DeviceExposureProbe(
        nvml=NvmlSnapshot(available=True, device_count=8),
        cuda_visible_device_count=1,
    ).collect()
    by_subject = {r.subject: r for r in records}
    finding = by_subject["management_visibility_exceeds_compute_visibility"]
    assert finding.classification == "unexpected_visibility"
    assert any("not evidence that another tenant" in x for x in finding.limitations)


def test_a_refused_management_library_is_a_secure_restriction_not_a_finding():
    records = DeviceExposureProbe(
        nvml=NvmlSnapshot(available=False, unavailable_reason="not present")
    ).collect()
    by_subject = {r.subject: r for r in records}
    assert by_subject["nvml_available"].classification == "secure_restriction"


def test_the_omitted_socket_inventory_is_recorded_rather_than_silently_dropped():
    records = DeviceExposureProbe(
        nvml=NvmlSnapshot(available=False, unavailable_reason="not present")
    ).collect()
    by_subject = {r.subject: r for r in records}
    omitted = by_subject["host_management_socket_inventory"]
    assert omitted.classification == "not_testable"
    assert "deliberately not implemented" in omitted.not_testable_reason


def test_process_visibility_records_a_count_and_never_an_identity():
    records = DeviceExposureProbe(
        nvml=NvmlSnapshot(available=True, device_count=1, compute_process_count=4)
    ).collect()
    by_subject = {r.subject: r for r in records}
    visibility = by_subject["compute_process_visibility"]
    assert visibility.value == 4
    assert visibility.classification == "ambiguous"
    assert any("no process identity" in x for x in visibility.limitations)


# ---------------------------------------------------------------------------
# §9.5 self-vs-self canary — the D5 gate
# ---------------------------------------------------------------------------


class FakeObservation:
    def __init__(self, matched: bool) -> None:
        self.owned_canary_match = matched


def test_same_model_pair_is_inconclusive_until_d5_lands():
    result = interpret(
        AllocationLeg("A", "H100 SXM", certificate(1)),
        AllocationLeg("B", "H100 SXM", certificate(1), FakeObservation(False)),
    )
    assert result.finding == "inconclusive"
    assert "D5" in result.interpretation or "D5" in " ".join(result.limitations)


def test_same_model_pair_can_reach_a_clean_result_once_d5_is_validated():
    result = interpret(
        AllocationLeg("A", "H100 SXM", certificate(1, as_evidence=True)),
        AllocationLeg(
            "B", "H100 SXM", certificate(1, as_evidence=True), FakeObservation(False)
        ),
        same_model_classifier=validated_separability_report(),
    )
    assert result.finding == "clean_same_device"
    assert "consistent with the same physical accelerator" in result.interpretation
    assert "proved" not in result.interpretation


def test_a_modelled_certificate_is_refused_even_when_d5_is_validated():
    """The two gates are independent, and both must open."""
    result = interpret(
        AllocationLeg("A", "H100 SXM", certificate(1)),
        AllocationLeg("B", "H100 SXM", certificate(1), FakeObservation(False)),
        same_model_classifier=validated_separability_report(),
    )
    assert result.finding == "inconclusive"
    assert any("model rather than silicon" in x for x in result.limitations)


def test_an_unvalidated_report_does_not_unblock_the_d5_gate():
    """A caller must not be able to unlock the gate just by passing any
    SeparabilityReport object — it has to have actually validated."""
    unvalidated = evaluate_separability(
        [("die-a", certificate(die_seed=3, as_evidence=False)) for _ in range(2)]
        + [("die-b", certificate(die_seed=3, as_evidence=False)) for _ in range(2)],
    )
    assert unvalidated.validated is False
    result = interpret(
        AllocationLeg("A", "H100 SXM", certificate(1, as_evidence=True)),
        AllocationLeg(
            "B", "H100 SXM", certificate(1, as_evidence=True), FakeObservation(False)
        ),
        same_model_classifier=unvalidated,
    )
    assert result.finding == "inconclusive"


def test_a_recovered_canary_requires_private_disclosure_first():
    result = interpret(
        AllocationLeg("A", "H100 SXM", certificate(1)),
        AllocationLeg("B", "H100 SXM", certificate(1), FakeObservation(True)),
    )
    assert result.finding == "canary_recovered"
    assert result.requires_private_disclosure is True
    assert "§7.5" in result.interpretation


def test_a_pair_with_no_topology_evidence_is_inconclusive():
    result = interpret(
        AllocationLeg("A", "H100 SXM"),
        AllocationLeg("B", "H100 SXM", observation=FakeObservation(False)),
    )
    assert result.finding == "inconclusive"


# ---------------------------------------------------------------------------
# §9.9 coarse location
# ---------------------------------------------------------------------------


class FakeRtt(RttSource):
    def __init__(self, table: dict[str, list[float]]) -> None:
        self._table = table

    def measure(self, landmark, *, samples):
        return self._table.get(landmark.code, [])


LANDMARKS = (
    Landmark("lm-eu-1", "metro-1", "eu", "example.invalid"),
    Landmark("lm-us-1", "metro-2", "us", "example.invalid"),
)


def test_close_to_the_claimed_jurisdiction_is_consistent():
    probe = LocationProbe(
        FakeRtt({"lm-eu-1": [3.0, 3.2, 3.1], "lm-us-1": [92.0, 93.0]}), LANDMARKS
    )
    assert probe.assess(advertised_jurisdiction="eu").classification == "consistent"


def test_closer_to_somewhere_else_is_probably_inconsistent():
    probe = LocationProbe(
        FakeRtt({"lm-eu-1": [95.0, 96.0], "lm-us-1": [4.0, 4.1]}), LANDMARKS
    )
    result = probe.assess(advertised_jurisdiction="eu")
    assert result.classification == "probably_inconsistent"


def test_no_reachable_landmark_is_not_testable():
    probe = LocationProbe(FakeRtt({}), LANDMARKS)
    result = probe.assess(advertised_jurisdiction="eu")
    assert result.classification == "not_testable"
    assert result.not_testable_reason


def test_every_location_result_states_the_resolution_bound_and_hides_addresses():
    probe = LocationProbe(
        FakeRtt({"lm-eu-1": [3.0], "lm-us-1": [90.0]}), LANDMARKS
    )
    result = probe.assess(advertised_jurisdiction="eu")
    assert any("metropolitan-to-continental" in x for x in result.limitations)
    assert "example.invalid" not in str(result.to_dict())


# ---------------------------------------------------------------------------
# §9.10 / §9.11 attestation
# ---------------------------------------------------------------------------


class AbsentEvidence(EvidenceSource):
    def collect(self, *, nonce, expected_gpu):
        return AttestationEvidence(
            available=False,
            unavailable_reason="no confidential-computing hardware",
            collector="test",
        )


def test_absent_attestation_reports_every_field_as_not_testable():
    _, records = AttestationProbe(AbsentEvidence()).collect(
        nonce=b"\x00" * 32, expected_gpu="H100"
    )
    assert all(r.classification == "not_testable" for r in records)
    assert all(r.not_testable_reason for r in records)


def test_attestation_fields_are_reported_separately_not_as_one_boolean():
    _, records = AttestationProbe(AbsentEvidence()).collect(
        nonce=b"\x00" * 32, expected_gpu="H100"
    )
    subjects = {r.subject for r in records}
    assert "certificate_chain_valid" in subjects
    assert "debug_mode_disabled" in subjects
    assert len(records) == len(AttestationProbe.FIELDS) + 1


def test_a_named_binding_mechanism_alone_does_not_establish_binding():
    """A mechanism named but never relay-tested: undetermined, not bound."""
    assessment = assess_channel_binding(
        AttestationEvidence(available=True, nonce_matches=True),
        transport_authenticated=True,
        binding_mechanism="exported keying material",
        # relay_resisted omitted -> None -> not tested at all.
    )
    assert assessment.application_channel_bound is None
    assert assessment.level == "evidence_fresh"


def test_binding_is_established_only_once_relay_is_tested_and_resisted():
    assessment = assess_channel_binding(
        AttestationEvidence(available=True, nonce_matches=True),
        transport_authenticated=True,
        binding_mechanism="exported keying material",
        relay_resisted=True,
    )
    assert assessment.application_channel_bound is True
    assert assessment.level == "relay_resistance_demonstrated"


def test_relay_tested_and_defeated_is_not_bound_and_not_resistance_demonstrated():
    """The Intra-handshake.fail finding, encoded as a real outcome — not
    "untested", a positive result that the binding failed under relay.
    This is the exact bug a Codex review found in the prior boolean-only
    API: "a test ran" must not be conflated with "the test passed"."""
    assessment = assess_channel_binding(
        AttestationEvidence(available=True, nonce_matches=True),
        transport_authenticated=True,
        binding_mechanism="exported keying material",
        relay_resisted=False,
    )
    assert assessment.application_channel_bound is False
    assert assessment.relay_resistance_demonstrated is False
    assert assessment.level != "relay_resistance_demonstrated"
    assert any("succeeded" in note for note in assessment.notes)


def test_no_mechanism_at_all_is_not_established():
    assessment = assess_channel_binding(AttestationEvidence(available=True))
    assert assessment.application_channel_bound is False
    assert assessment.level == "not_established"


# ---------------------------------------------------------------------------
# §9.12 MIG temporal isolation
# ---------------------------------------------------------------------------


def test_refuses_to_run_on_hardware_without_mig():
    """The RTX 3050 case. Refusing beats producing a §9.3 result mislabelled."""
    from gpu_seal.cuda.backend import SimulatedBackend

    with pytest.raises(MigUnavailable, match="A100/H100-class"):
        MigTemporalProbe(
            SimulatedBackend(),
            CanarySet.create(),
            nvml=NvmlSnapshot(available=True, mig_enabled=False),
        )


def test_refuses_a_non_temporal_boundary():
    from gpu_seal.cuda.backend import SimulatedBackend

    probe = MigTemporalProbe(
        SimulatedBackend(),
        CanarySet.create(),
        nvml=NvmlSnapshot(available=True, mig_enabled=True),
    )
    with pytest.raises(ValueError, match="not a §9.12 temporal boundary"):
        probe.plant(4096, boundary=Boundary.SEPARATE_PROCESS)


def test_refuses_a_measurement_with_no_teardown_statement():
    """The three mechanisms are indistinguishable from inside the instance."""
    from gpu_seal.cuda.backend import SimulatedBackend

    probe = MigTemporalProbe(
        SimulatedBackend(),
        CanarySet.create(),
        nvml=NvmlSnapshot(available=True, mig_enabled=True),
    )
    with pytest.raises(ValueError, match="three different mechanisms"):
        probe.measure_successor(
            4096,
            boundary=Boundary.MIG_SAME_PROFILE,
            teardown_performed="  ",
            receipt=PlantReceipt(boundary=Boundary.MIG_SAME_PROFILE, canaries_planted=1),
        )


def test_measure_successor_refuses_a_receipt_for_a_different_boundary():
    from gpu_seal.cuda.backend import SimulatedBackend

    probe = MigTemporalProbe(
        SimulatedBackend(),
        CanarySet.create(),
        nvml=NvmlSnapshot(available=True, mig_enabled=True),
    )
    wrong_boundary_receipt = PlantReceipt(
        boundary=Boundary.GPU_RESET, canaries_planted=1
    )
    with pytest.raises(ValueError, match="receipt is for boundary"):
        probe.measure_successor(
            4096,
            boundary=Boundary.MIG_SAME_PROFILE,
            teardown_performed="destroyed and recreated the MIG instance",
            receipt=wrong_boundary_receipt,
        )


def test_measure_successor_refuses_a_receipt_with_no_canaries_planted():
    """Closes the gap where a caller could skip plant() entirely and still
    get a measurement with the entropy safety stop disarmed."""
    from gpu_seal.cuda.backend import SimulatedBackend

    probe = MigTemporalProbe(
        SimulatedBackend(),
        CanarySet.create(),
        nvml=NvmlSnapshot(available=True, mig_enabled=True),
    )
    empty_receipt = PlantReceipt(boundary=Boundary.MIG_SAME_PROFILE, canaries_planted=0)
    with pytest.raises(ValueError, match="did not actually place a canary"):
        probe.measure_successor(
            4096,
            boundary=Boundary.MIG_SAME_PROFILE,
            teardown_performed="destroyed and recreated the MIG instance",
            receipt=empty_receipt,
        )


def test_plant_then_measure_successor_is_the_only_ordinary_path():
    from gpu_seal.cuda.backend import SimulatedBackend

    backend = SimulatedBackend()
    probe = MigTemporalProbe(
        backend,
        CanarySet.create(),
        nvml=NvmlSnapshot(available=True, mig_enabled=True),
    )
    alloc, receipt = probe.plant(4096, boundary=Boundary.MIG_SAME_PROFILE)
    assert receipt.canaries_planted > 0
    assert receipt.boundary is Boundary.MIG_SAME_PROFILE

    result = probe.measure_successor(
        4096,
        boundary=Boundary.MIG_SAME_PROFILE,
        teardown_performed="destroyed and recreated the MIG instance",
        receipt=receipt,
    )
    assert result.canaries_planted == receipt.canaries_planted


def test_summary_never_pools_boundaries():
    from gpu_seal.probes.mig_temporal import MigBoundaryResult

    results = [
        MigBoundaryResult(
            boundary=Boundary.MIG_SAME_PROFILE,
            size_bytes=4096,
            teardown_performed="destroyed and recreated M1 with the same profile",
        ),
        MigBoundaryResult(
            boundary=Boundary.DRIVER_RELOAD,
            size_bytes=4096,
            teardown_performed="unloaded and reloaded the kernel driver",
        ),
    ]
    summary = summarise(results)
    assert set(summary) == {"MIG_SAME_PROFILE", "DRIVER_RELOAD"}
    assert "total" not in summary


# ---------------------------------------------------------------------------
# §12 statistics
# ---------------------------------------------------------------------------


def test_a_zero_rate_over_ten_cycles_does_not_get_a_zero_width_interval():
    """The precise overclaim §12 exists to prevent."""
    low, high = proportion_ci(0, 10)
    assert low == 0.0
    assert high > 0.25


def test_no_usable_cycles_yields_an_unknown_rate_not_a_clean_one():
    counts = ObservationCounts(attempted=10, usable=0, positive=0, errored=10)
    assert counts.rate is None
    assert counts.confidence_interval() is None


def test_counts_refuse_an_impossible_denominator():
    with pytest.raises(ValueError, match="exceeds attempted"):
        ObservationCounts(attempted=5, usable=6, positive=0)


def test_bootstrap_is_seeded_so_the_interval_is_reproducible():
    samples = [1.0, 1.1, 0.9, 1.2, 1.05, 0.95]
    assert bootstrap_ci(samples, resamples=200) == bootstrap_ci(
        samples, resamples=200
    )


def test_an_unusual_confidence_level_is_refused():
    with pytest.raises(ValueError, match="after seeing the data"):
        proportion_ci(1, 10, confidence=0.87)
