"""§9.4 control data must never be gradeable as a §9.3 provider finding.

Found by inspection immediately after §9.4 was promoted onto the critical
path. Feeding the framework-allocator control's cycle counts into the §13.1
grader produced:

    Grade D — "An owned canary was recovered in 10 of 10 cycles across a
    boundary where sanitisation was expected. Pending private disclosure and
    provider response."

That is a false accusation manufactured from a working positive control. The
pool never called ``cudaFree``, so the driver was never told the memory was
released and had no opportunity to scrub it. Recovering the marker was the
control succeeding.

The counts from §9.3 and §9.4 are numerically indistinguishable. Only the
measurement path separates a control from an accusation, so the path is now a
gate that precedes every grade — including, and especially, D.
"""

from __future__ import annotations

import pytest

from gpu_seal.reporting import (
    Grade,
    MeasurementPath,
    MemoryHygieneEvidence,
    grade_memory_hygiene,
)

pytestmark = pytest.mark.safety


def _ev(path: MeasurementPath, **overrides) -> MemoryHygieneEvidence:
    base = dict(
        cycles=10,
        canary_recovered_cycles=0,
        ambiguous_cycles=0,
        same_device_evidence=True,
        same_advertised_model=False,
        same_model_classifier_validated=False,
        inconsistent_across_runs=False,
        measurement_path=path,
    )
    base.update(overrides)
    return MemoryHygieneEvidence(**base)


# ---------------------------------------------------------------------------
# The gate itself
# ---------------------------------------------------------------------------


def test_pooled_recovery_is_not_graded_d():
    """The exact scenario that motivated this file."""
    grade, why = grade_memory_hygiene(
        _ev(MeasurementPath.FRAMEWORK_POOLED, canary_recovered_cycles=10)
    )
    assert grade is not Grade.D, (
        "A canary recovered through a caching allocator was graded as a "
        "provider sanitisation failure. That is a false accusation generated "
        "from GPU-SEAL's own positive control."
    )
    assert grade is Grade.U
    assert "caching allocator" in why
    assert "detection-capability control" in why


def test_pooled_clean_result_is_also_not_graded():
    """Not gradeable means not gradeable in either direction.

    A clean §9.4 result must not earn an A either — the driver was never given
    the chance to scrub, so the absence of a canary would be the anomaly.
    """
    grade, _ = grade_memory_hygiene(_ev(MeasurementPath.FRAMEWORK_POOLED))
    assert grade is Grade.U


def test_simulated_path_is_not_graded():
    grade, why = grade_memory_hygiene(
        _ev(MeasurementPath.SIMULATED, canary_recovered_cycles=10)
    )
    assert grade is Grade.U
    assert "host-side" in why


def test_unstated_path_defaults_to_ungradeable():
    """Forgetting the field must yield U, never D.

    The default is the safe value: a caller who does not know which path was
    used cannot accidentally produce an accusation.
    """
    ev = MemoryHygieneEvidence(
        cycles=10,
        canary_recovered_cycles=10,
        ambiguous_cycles=0,
        same_device_evidence=True,
        same_advertised_model=False,
    )
    assert ev.measurement_path is MeasurementPath.UNKNOWN
    grade, why = grade_memory_hygiene(ev)
    assert grade is Grade.U
    assert "not stated" in why


def test_driver_direct_recovery_is_still_graded_d():
    """Negative control on the gate: it must not block genuine findings.

    A canary recovered where the driver *was* told the memory was freed is a
    real finding and must still reach D.
    """
    grade, why = grade_memory_hygiene(
        _ev(MeasurementPath.DRIVER_DIRECT, canary_recovered_cycles=3)
    )
    assert grade is Grade.D
    assert "disclosure" in why.lower()


def test_driver_direct_clean_result_still_reaches_a():
    grade, _ = grade_memory_hygiene(_ev(MeasurementPath.DRIVER_DIRECT))
    assert grade is Grade.A


# ---------------------------------------------------------------------------
# Ordering — the gate must precede the D branch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        MeasurementPath.FRAMEWORK_POOLED,
        MeasurementPath.SIMULATED,
        MeasurementPath.UNKNOWN,
    ],
)
def test_no_non_driver_path_can_ever_produce_d(path):
    """Exhaustive over the conditions that would otherwise force a D.

    If the path check were moved below the recovery check, one of these would
    slip through.
    """
    for recovered in (1, 5, 10):
        for same_dev in (True, False):
            grade, _ = grade_memory_hygiene(
                _ev(
                    path,
                    canary_recovered_cycles=recovered,
                    same_device_evidence=same_dev,
                )
            )
            assert grade is Grade.U, (
                f"path={path.value} recovered={recovered} produced {grade.value}"
            )


def test_every_measurement_path_has_a_distinct_rationale():
    """A U with a generic reason is not actionable.

    The reader must be able to tell "wrong instrument" from "no data" from
    "not stated".
    """
    reasons = {}
    for path in MeasurementPath:
        if path is MeasurementPath.DRIVER_DIRECT:
            continue
        _, why = grade_memory_hygiene(_ev(path, canary_recovered_cycles=5))
        reasons[path] = why
    assert len(set(reasons.values())) == len(reasons), (
        f"measurement paths share rationale text: {reasons}"
    )
