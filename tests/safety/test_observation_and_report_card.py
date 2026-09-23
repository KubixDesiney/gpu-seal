"""The non-memory egress door and the full §13 report card.

`ObservationRecord` is the second egress door in the project. The first
(`AggregateRecord`) guards statistics over memory we did not write; this one
guards *description of the rented environment*, which carries CHARTER.md §10's
never-published identifiers. Both are allowlists enforced on the way out.
"""

from __future__ import annotations

import pytest
from gpu_seal.evidence.observation import (
    ObservationRecord,
    summarise_classifications,
)
from gpu_seal.reporting import (
    NOT_CLASSIFIED,
    Grade,
    MeasurementPath,
    MemoryHygieneEvidence,
    build_report_card,
    grade_allocation_transparency,
    grade_hardware_claim,
    grade_location_claim,
    grade_tenant_exposure,
)
from gpu_seal.safety.errors import EgressViolation
from gpu_seal.safety.metadata import stable_hash

pytestmark = pytest.mark.safety


def record(**overrides) -> ObservationRecord:
    base = dict(
        probe_name="device_exposure_inventory",
        probe_version="0.2.0",
        subject="nvidia_device_node_count",
        category="device_exposure",
        classification="expected_visibility",
        value=2,
        confidence=0.9,
        evidence=["two character device nodes visible"],
        limitations=["node names are a driver convention"],
    )
    base.update(overrides)
    return ObservationRecord(**base)


# ---------------------------------------------------------------------------
# The observation egress door
# ---------------------------------------------------------------------------


def test_refuses_to_emit_an_unhashed_never_published_identifier():
    """CHARTER.md §10: stable GPU UUIDs are never published."""
    with pytest.raises(EgressViolation, match="never-published identifier"):
        record(subject="gpu_uuid", value="GPU-1234-5678").to_dict()


def test_accepts_the_hashed_form_of_the_same_identifier():
    payload = record(
        subject="gpu_uuid_hash", value=stable_hash("GPU-1234-5678", domain="gpu_uuid")
    ).to_dict()
    assert payload["value"].startswith("sha256:")


def test_refuses_a_hash_named_field_carrying_a_clear_value():
    """The `_hash` suffix is not a magic word that launders a raw identifier."""
    with pytest.raises(EgressViolation, match="never-published identifier"):
        record(subject="hostname_hash", value="gpu-node-07.internal").to_dict()


def test_refuses_a_not_testable_classification_with_no_reason():
    """Otherwise a deliberate non-measurement looks like a silent failure."""
    with pytest.raises(ValueError, match="not_testable_reason"):
        record(classification="not_testable", not_testable_reason=None)


def test_refuses_a_confidence_outside_the_unit_interval():
    with pytest.raises(ValueError, match="confidence must be"):
        record(confidence=1.5)


def test_hash_domains_are_separated():
    """One disclosed mapping must not leak another."""
    assert stable_hash("abc", domain="gpu_uuid") != stable_hash(
        "abc", domain="account_id"
    )


def test_summarise_counts_by_classification():
    counts = summarise_classifications(
        [
            record(),
            record(classification="secure_restriction"),
            record(classification="secure_restriction"),
        ]
    )
    assert counts == {"expected_visibility": 1, "secure_restriction": 2}


# ---------------------------------------------------------------------------
# §13.2 Tenant exposure
# ---------------------------------------------------------------------------


def test_secure_restrictions_do_not_count_against_a_provider():
    """§9.6: "not every unavailable interface is a failure"."""
    grade, _ = grade_tenant_exposure(
        {"secure_restriction": 6, "expected_visibility": 3}
    )
    assert grade is Grade.A


def test_unexpected_visibility_caps_the_exposure_grade_at_c():
    grade, basis = grade_tenant_exposure(
        {"secure_restriction": 5, "unexpected_visibility": 1}
    )
    assert grade is Grade.C
    assert "beyond what the workload requires" in basis


def test_exposure_grade_d_requires_a_controlled_neighbour_experiment():
    """A bare process count must never become an accusation."""
    grade, _ = grade_tenant_exposure({"ambiguous": 3})
    assert grade is Grade.B

    grade, _ = grade_tenant_exposure(
        {"ambiguous": 3}, neighbour_metadata_visible=True
    )
    assert grade is Grade.D


def test_all_not_testable_yields_u_not_a():
    grade, _ = grade_tenant_exposure({"not_testable": 8})
    assert grade is Grade.U


# ---------------------------------------------------------------------------
# §13.3 / §13.4 — instrument-dependent grades cite the instrument
# ---------------------------------------------------------------------------


def test_hardware_grade_always_cites_the_instrument_and_its_limits():
    for kwargs in (
        dict(
            certificates=0,
            fingerprint_stable=True,
            consistent_with_advertised_class=None,
        ),
        dict(
            certificates=5,
            fingerprint_stable=True,
            consistent_with_advertised_class=True,
        ),
        dict(
            certificates=5,
            fingerprint_stable=True,
            consistent_with_advertised_class=True,
            repeated_inconsistency=True,
        ),
    ):
        _, basis = grade_hardware_claim(**kwargs)
        assert "arXiv:2606.24934" in basis
        assert "does not separate two dies of one model" in basis


def test_a_modelled_certificate_can_never_grade_hardware():
    grade, basis = grade_hardware_claim(
        certificates=10,
        fingerprint_stable=True,
        consistent_with_advertised_class=True,
        instrument_is_evidence=False,
    )
    assert grade is Grade.U
    assert "model rather than silicon" in basis


def test_location_grade_always_states_the_resolution_bound():
    for band in ("consistent", "ambiguous", "not_testable", "inconsistent"):
        _, basis = grade_location_claim(band, repeated_measurements=5)
        assert "metropolitan-to-continental" in basis


def test_a_single_location_measurement_cannot_produce_grade_d():
    """Routing and congestion move on the timescale of one observation."""
    grade, basis = grade_location_claim("inconsistent", repeated_measurements=1)
    assert grade is Grade.C
    assert "Downgraded from D to C" in basis

    grade, _ = grade_location_claim("inconsistent", repeated_measurements=5)
    assert grade is Grade.D


def test_rejects_a_band_outside_the_charter_vocabulary():
    with pytest.raises(ValueError, match="§9.9 consistency band"):
        grade_location_claim("looks_fine")


# ---------------------------------------------------------------------------
# §13.5 Allocation-model transparency
# ---------------------------------------------------------------------------


def test_documented_and_corroborated_earns_an_a():
    grade, _ = grade_allocation_transparency(
        documented_model="mig_instance",
        measured_model="mig_instance",
        confidence=0.9,
    )
    assert grade is Grade.A


def test_documentation_contradicted_by_measurement_is_grade_d():
    grade, basis = grade_allocation_transparency(
        documented_model="mig_instance",
        measured_model="time_sliced_full_gpu",
        confidence=0.8,
        contradicted=True,
    )
    assert grade is Grade.D
    assert "§7.5" in basis


def test_undocumented_but_inferable_is_the_c_that_names_the_real_problem():
    grade, basis = grade_allocation_transparency(
        documented_model=None,
        measured_model="time_sliced_full_gpu",
        confidence=0.7,
    )
    assert grade is Grade.C
    assert "cannot learn from the invoice" in basis


def test_undocumented_and_unclassifiable_is_u_and_feeds_the_metric():
    grade, basis = grade_allocation_transparency(
        documented_model=None, measured_model="undocumented", confidence=0.2
    )
    assert grade is Grade.U
    assert "`undocumented` rate" in basis


def test_not_classified_is_u_with_a_basis_naming_the_gap_not_the_result():
    grade, basis = grade_allocation_transparency(
        documented_model=None, measured_model=NOT_CLASSIFIED, confidence=0.0
    )
    assert grade is Grade.U
    assert "wasn't attempted" in basis


def test_not_classified_stays_u_even_with_a_documented_claim():
    # NOT_CLASSIFIED means the tool never looked, regardless of what the
    # provider documents -- it must never be read as "documented, measurement
    # ambiguous" (grade B), which would imply a measurement was attempted.
    grade, basis = grade_allocation_transparency(
        documented_model="mig_instance",
        measured_model=NOT_CLASSIFIED,
        confidence=0.0,
    )
    assert grade is Grade.U
    assert "wasn't attempted" in basis


# ---------------------------------------------------------------------------
# The card
# ---------------------------------------------------------------------------


def full_card(**overrides):
    base = dict(
        provider_code="provider-a",
        memory=MemoryHygieneEvidence(
            cycles=10,
            canary_recovered_cycles=0,
            ambiguous_cycles=0,
            same_device_evidence=True,
            same_advertised_model=False,
            measurement_path=MeasurementPath.DRIVER_DIRECT,
        ),
        exposure_classifications={"secure_restriction": 5},
        topology_certificates=5,
        topology_stable=True,
        topology_consistent=True,
        topology_is_evidence=True,
        location_band="consistent",
        location_measurements=5,
        documented_allocation_model="mig_instance",
        measured_allocation_model="mig_instance",
        allocation_confidence=0.9,
        allocation_contradicted=False,
        attestation_fields={"attestation_available": False},
    )
    base.update(overrides)
    return build_report_card(**base)


def test_the_card_has_no_composite_score():
    """CHARTER.md §13: "Avoid 62/100." A total invites a league table."""
    card = full_card()
    payload = card.to_dict()
    assert not hasattr(card, "total")
    assert "score" not in payload
    assert all(
        not isinstance(value, (int, float))
        for key, value in payload.items()
        if key != "provider_code"
    )


def test_attestation_is_a_field_report_not_a_grade():
    """§13.6 lists separate fields "(not a grade)"."""
    attestation = full_card().to_dict()["attestation_assurance"]
    assert "grade" not in attestation
    assert "CVE-2026-33697" in attestation["note"]


def test_any_grade_d_blocks_publication_pending_disclosure():
    clean = full_card()
    assert clean.requires_disclosure_before_publication is False

    accusing = full_card(
        documented_allocation_model="mig_instance",
        measured_allocation_model="time_sliced_full_gpu",
        allocation_contradicted=True,
    )
    assert accusing.requires_disclosure_before_publication is True
