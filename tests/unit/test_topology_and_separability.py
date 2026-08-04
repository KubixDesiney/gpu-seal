"""§9.8 topology instrument and §9.8b separability (contribution D5).

The load-bearing assertions here are the ones about what the instrument
*refuses* to claim. A fingerprint comparison that returns "same device" for
two same-model allocations would silently unblock every §13.1 grade A in the
project.
"""

from __future__ import annotations

import pytest
from gpu_seal.analysis.separability import (
    VALIDATION_ACCURACY_THRESHOLD,
    certificate_distance,
    evaluate_separability,
)
from gpu_seal.probes.topology import (
    PUBLISHED_JITTER_BASELINE_CYCLES,
    DeterministicLatencySource,
    TopologyProbe,
    compare_certificates,
    kernel_source_hash,
)


def certify(*, die_seed: int = 1, jitter: float = 0.05, sm_count: int = 8):
    source = DeterministicLatencySource(
        sm_count=sm_count, die_seed=die_seed, jitter_cycles=jitter
    )
    return TopologyProbe(source).certify(
        regions=4, blocks=sm_count, hops=128, repetitions=4
    )


# ---------------------------------------------------------------------------
# Certificate construction
# ---------------------------------------------------------------------------


def test_certificate_records_the_kernel_hash_so_comparisons_are_scoped():
    cert = certify()
    assert cert.kernel_hash == kernel_source_hash()
    assert cert.kernel_hash.startswith("sha256:")


def test_certificate_from_a_model_is_not_evidence():
    """Mirrors backend_is_real. A modelled fingerprint is never a measurement."""
    cert = certify()
    assert cert.fidelity == "deterministic"
    assert cert.is_evidence is False


def test_single_repetition_is_refused_because_jitter_is_the_point():
    source = DeterministicLatencySource()
    with pytest.raises(ValueError, match="at least 2 repetitions"):
        TopologyProbe(source).certify(repetitions=1)


def test_certificate_reports_jitter_against_the_published_baseline():
    payload = certify().to_dict()
    assert (
        payload["published_jitter_baseline_cycles"]
        == PUBLISHED_JITTER_BASELINE_CYCLES
    )
    assert payload["median_jitter_cycles"] >= 0.0


def test_certificate_always_states_the_same_model_limitation():
    """§9.8: the instrument does not separate two dies of one model."""
    limitations = " ".join(certify().to_dict()["limitations"]).lower()
    assert "same-model die separation" in limitations


def test_certificate_declares_it_is_a_reproduction_not_a_contribution():
    assert "reproduced as an instrument" in certify().to_dict()["reproduction_of"]


# ---------------------------------------------------------------------------
# Comparison — and the D5 gate
# ---------------------------------------------------------------------------


def test_same_modelled_die_compares_as_probably_consistent():
    a, b = certify(die_seed=7), certify(die_seed=7)
    result = compare_certificates(a, b, same_advertised_model=False)
    assert result.band == "probably_consistent"


def test_different_modelled_dies_separate():
    a, b = certify(die_seed=1), certify(die_seed=42)
    result = compare_certificates(a, b, same_advertised_model=False)
    assert result.band in ("ambiguous", "probably_inconsistent")
    assert result.supports_same_device_claim is False


def test_refuses_same_device_claim_for_same_advertised_model_without_d5():
    """The v2 gate. A close match on two same-model rentals proves nothing."""
    a, b = certify(die_seed=7), certify(die_seed=7)
    result = compare_certificates(a, b, same_advertised_model=True)
    assert result.band == "probably_consistent"
    assert result.supports_same_device_claim is False
    assert any("D5" in reason for reason in result.reasons)


def test_same_device_claim_unblocks_once_d5_is_validated():
    a, b = certify(die_seed=7), certify(die_seed=7)
    result = compare_certificates(
        a, b, same_advertised_model=True, same_model_classifier_validated=True
    )
    # Still refused here, because a modelled certificate is not evidence —
    # two independent gates, and both must open.
    assert result.supports_same_device_claim is False
    assert any("model rather than silicon" in r for r in result.reasons)


def test_certificates_from_different_kernels_are_not_comparable():
    a = certify()
    b = certify()
    tampered = type(b)(
        **{**b.__dict__, "kernel_hash": "sha256:" + "1" * 64}
    )
    result = compare_certificates(a, tampered, same_advertised_model=False)
    assert result.band == "not_testable"
    assert result.distance == float("inf")


def test_certificates_of_different_geometry_are_not_comparable():
    a, b = certify(sm_count=8), certify(sm_count=4)
    result = compare_certificates(a, b, same_advertised_model=False)
    assert result.band == "not_testable"


# ---------------------------------------------------------------------------
# §9.8b separability — D5
# ---------------------------------------------------------------------------


def test_separability_reports_a_negative_when_dies_do_not_separate():
    """Certificates from indistinguishable models must fail the study.

    A negative is a publishable result (§9.8b). What must never happen is a
    negative reported as a success.
    """
    labelled = [("die-a", certify(die_seed=3, jitter=8.0)) for _ in range(4)]
    labelled += [("die-b", certify(die_seed=3, jitter=8.0)) for _ in range(4)]

    report = evaluate_separability(labelled, conditions=["identical model seed"])
    assert report.devices == 2
    assert report.validated is False
    assert "NOT achieved" in report.verdict()
    assert "identical model seed" in report.verdict()


def test_separability_reports_success_when_dies_genuinely_differ():
    labelled = [("die-a", certify(die_seed=1, jitter=0.001)) for _ in range(4)]
    labelled += [("die-b", certify(die_seed=40, jitter=0.001)) for _ in range(4)]

    report = evaluate_separability(labelled, conditions=["synthetic ground truth"])
    assert report.leave_one_out_accuracy >= VALIDATION_ACCURACY_THRESHOLD
    assert report.auc >= 0.98
    assert report.validated is True
    assert "achieved" in report.verdict()


def test_separability_refuses_a_single_device_study():
    labelled = [("die-a", certify()) for _ in range(3)]
    report = evaluate_separability(labelled)
    assert report.devices == 1
    assert report.validated is False
    assert "Not evaluable" in report.verdict()


def test_separability_needs_at_least_two_certificates():
    with pytest.raises(ValueError, match="at least two certificates"):
        evaluate_separability([("die-a", certify())])


def test_incomparable_pairs_are_dropped_rather_than_scored_as_far_apart():
    a, b = certify(sm_count=8), certify(sm_count=4)
    assert certificate_distance(a, b) == float("inf")

    report = evaluate_separability([("die-a", a), ("die-b", b)])
    assert report.different_device_pairs == 0


def test_report_carries_its_pre_registered_thresholds():
    """§12: pre-register scoring. The thresholds travel with the result."""
    labelled = [("die-a", certify(die_seed=1)), ("die-b", certify(die_seed=40))]
    payload = evaluate_separability(labelled).to_dict()
    assert (
        payload["pre_registered_thresholds"]["leave_one_out_accuracy"]
        == VALIDATION_ACCURACY_THRESHOLD
    )
