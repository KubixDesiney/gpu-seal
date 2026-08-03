"""§9.7 allocation-model classifier — contribution D3.

The classifier's job is to be *correct about its own uncertainty*. These tests
spend more effort on the cases where it should refuse to answer than on the
ones where it should.
"""

from __future__ import annotations

import pytest
from gpu_seal.probes.allocation_model import (
    CALIBRATION_STATUS,
    AllocationEvidence,
    AllocationModelClassifier,
    measure_scheduling_gaps,
)
from gpu_seal.safety.policy import ALLOCATION_MODEL_CLASSES

GIB = 1 << 30


def classify(**kwargs):
    return AllocationModelClassifier().classify(AllocationEvidence(**kwargs))


def test_mig_instance_is_identified_from_the_partition_signals():
    result = classify(
        mig_enabled=True,
        mig_instance_visible=True,
        visible_memory_bytes=10 * GIB,
        advertised_model_memory_bytes=80 * GIB,
        reported_model="NVIDIA A100-SXM4-80GB MIG 1g.10gb",
    )
    assert result.classification == "mig_instance"
    assert result.confidence > 0.5


def test_passthrough_is_identified_when_the_whole_device_is_ours():
    result = classify(
        mig_enabled=False,
        visible_memory_bytes=80 * GIB,
        advertised_model_memory_bytes=80 * GIB,
        neighbour_process_count=0,
        scheduling_stall_ratio=1.2,
        reported_model="NVIDIA A100-SXM4-80GB",
    )
    assert result.classification == "dedicated_physical_passthrough"


def test_time_slicing_is_identified_from_neighbours_plus_stalls():
    """The commercially important case, and the hardest one.

    A time-slice presents as a whole GPU. The only tells are somebody else's
    work on it and ours periodically stopping.
    """
    result = classify(
        mig_enabled=False,
        visible_memory_bytes=80 * GIB,
        advertised_model_memory_bytes=80 * GIB,
        neighbour_process_count=3,
        scheduling_stall_ratio=9.0,
        mps_control_configured=False,
        reported_model="NVIDIA A100-SXM4-80GB",
    )
    assert result.classification == "time_sliced_full_gpu"


def test_software_fractional_is_identified_when_memory_is_short_unexplained():
    result = classify(
        mig_enabled=False,
        mig_instance_visible=False,
        visible_memory_bytes=20 * GIB,
        advertised_model_memory_bytes=80 * GIB,
        virtualisation_indicators=(),
        reported_model="NVIDIA A100-SXM4-80GB",
    )
    assert result.classification == "software_fractional_gpu"


def test_refuses_to_pick_a_winner_when_nothing_separates():
    """No evidence at all must not produce a confident classification."""
    result = classify()
    assert result.classification in (
        "undocumented",
        "shared_unknown",
        "dedicated_unknown",
    )
    assert result.confidence <= 0.4


def test_near_tie_is_reported_as_unclassified_not_as_the_winner():
    """A 0.51/0.49 split is not a result. It must not look like one."""
    classifier = AllocationModelClassifier()
    result = classifier.classify(
        AllocationEvidence(
            documented_model="mig_instance",
            visible_memory_bytes=40 * GIB,
            advertised_model_memory_bytes=80 * GIB,
        )
    )
    top_two = [score for _, score in result.ranked[:2]]
    if top_two[0] - top_two[1] < classifier.SEPARATION_MARGIN:
        assert result.classification in (
            "undocumented",
            "shared_unknown",
            "dedicated_unknown",
        )


def test_missing_signals_never_count_against_a_hypothesis():
    """"We could not look" is not evidence of absence.

    Adding a signal must not lower a hypothesis that the signal is silent on.
    """
    without = classify(
        mig_enabled=False,
        visible_memory_bytes=80 * GIB,
        advertised_model_memory_bytes=80 * GIB,
    )
    with_zero_neighbours = classify(
        mig_enabled=False,
        visible_memory_bytes=80 * GIB,
        advertised_model_memory_bytes=80 * GIB,
        neighbour_process_count=0,
    )
    passthrough = dict(without.ranked)["dedicated_physical_passthrough"]
    passthrough_with = dict(with_zero_neighbours.ranked)[
        "dedicated_physical_passthrough"
    ]
    assert passthrough_with >= passthrough


def test_contradicting_documentation_is_recorded_not_silently_overridden():
    result = classify(
        documented_model="mig_instance",
        mig_enabled=False,
        visible_memory_bytes=80 * GIB,
        advertised_model_memory_bytes=80 * GIB,
        neighbour_process_count=0,
        scheduling_stall_ratio=1.1,
        reported_model="NVIDIA A100-SXM4-80GB",
    )
    assert result.contradicting, (
        "a documented model that disagrees with the measurement is the §13.5 "
        "grade-D case and must appear in the record"
    )


def test_every_result_carries_the_calibration_status():
    """§9.7: never present inference as provider-confirmed fact."""
    result = classify(mig_enabled=True, mig_instance_visible=True)
    assert CALIBRATION_STATUS in result.limitations


def test_classification_is_always_a_charter_class():
    result = classify(mps_control_configured=True, neighbour_process_count=2)
    assert result.classification in ALLOCATION_MODEL_CLASSES


def test_rejects_a_classification_outside_the_charter_vocabulary():
    from gpu_seal.probes.allocation_model import Classification

    with pytest.raises(ValueError, match="§9.7"):
        Classification(
            classification="definitely_dedicated_trust_me",
            confidence=1.0,
            evidence=[],
            contradicting=[],
            limitations=[],
            ranked=[],
        )


def test_scheduling_gap_measurement_needs_enough_samples_for_a_tail():
    from gpu_seal.cuda.backend import SimulatedBackend

    with pytest.raises(ValueError, match="at least 8 samples"):
        measure_scheduling_gaps(SimulatedBackend(), samples=4)


def test_scheduling_gap_measurement_returns_a_ratio_on_the_simulated_backend():
    from gpu_seal.cuda.backend import SimulatedBackend

    ratio = measure_scheduling_gaps(SimulatedBackend(), samples=64, probe_bytes=1024)
    assert ratio is None or ratio >= 1.0
