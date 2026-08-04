"""CHARTER.md §16 test 16 — grade A requires usable same-device evidence.

This is the v2 amendment (A3) expressed as a test. Alpay & Alpay (2026) §12
explicitly defer same-model die separation, so until §9.8b lands, GPU-SEAL
cannot distinguish "the same H100" from "a different H100". A clean canary
result across two allocations of the same advertised model is therefore not
evidence of sanitisation — the provider may simply have handed us a different,
freshly-booted chip.

Without this gate the grader would quietly hand out As for that.
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


def _ev(**overrides) -> MemoryHygieneEvidence:
    base = dict(
        cycles=20,
        canary_recovered_cycles=0,
        ambiguous_cycles=0,
        same_device_evidence=True,
        same_advertised_model=False,
        same_model_classifier_validated=False,
        inconsistent_across_runs=False,
        measurement_path=MeasurementPath.DRIVER_DIRECT,
    )
    base.update(overrides)
    return MemoryHygieneEvidence(**base)


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_grade_a_requires_same_device_evidence():
    grade, why = grade_memory_hygiene(_ev(same_device_evidence=False))
    assert grade is Grade.U
    assert "same-physical-device" in why


def test_same_model_without_validated_classifier_caps_at_u():
    """The D5 dependency. This is the test the amendment exists for."""
    grade, why = grade_memory_hygiene(
        _ev(same_advertised_model=True, same_model_classifier_validated=False)
    )
    assert grade is Grade.U, (
        "A clean result across two allocations of the same advertised model "
        "must not earn an A while same-model die separation is unvalidated."
    )
    assert "same-model die separation" in why
    assert "9.8b" in why or "D5" in why


def test_same_model_with_validated_classifier_can_reach_a():
    grade, _ = grade_memory_hygiene(
        _ev(same_advertised_model=True, same_model_classifier_validated=True)
    )
    assert grade is Grade.A


def test_different_models_with_device_evidence_reaches_a():
    grade, why = grade_memory_hygiene(_ev())
    assert grade is Grade.A
    assert "same-physical-device evidence" in why


# ---------------------------------------------------------------------------
# The rest of the §13.1 ladder
# ---------------------------------------------------------------------------


def test_recovered_canary_is_grade_d():
    grade, why = grade_memory_hygiene(_ev(canary_recovered_cycles=3))
    assert grade is Grade.D
    assert "disclosure" in why.lower()


def test_recovered_canary_outranks_missing_device_evidence():
    """A positive finding is a finding regardless of continuity evidence.

    Recovering our own marker where it should have been scrubbed is
    informative even if we cannot prove it was the same chip — arguably more
    so, since it means the marker survived somewhere.
    """
    grade, _ = grade_memory_hygiene(
        _ev(canary_recovered_cycles=1, same_device_evidence=False)
    )
    assert grade is Grade.D


def test_ambiguous_content_is_grade_b():
    grade, _ = grade_memory_hygiene(_ev(ambiguous_cycles=4))
    assert grade is Grade.B


def test_inconsistent_runs_are_grade_c():
    grade, _ = grade_memory_hygiene(_ev(inconsistent_across_runs=True))
    assert grade is Grade.C


def test_insufficient_cycles_is_grade_u():
    grade, why = grade_memory_hygiene(_ev(cycles=3))
    assert grade is Grade.U
    assert "cycles" in why


def test_zero_cycles_is_grade_u():
    grade, _ = grade_memory_hygiene(_ev(cycles=0))
    assert grade is Grade.U


def test_every_grade_carries_a_rationale():
    """An ungrounded grade is not publishable."""
    cases = [
        _ev(),
        _ev(cycles=0),
        _ev(cycles=2),
        _ev(canary_recovered_cycles=1),
        _ev(ambiguous_cycles=1),
        _ev(inconsistent_across_runs=True),
        _ev(same_device_evidence=False),
        _ev(same_advertised_model=True),
    ]
    for ev in cases:
        grade, why = grade_memory_hygiene(ev)
        assert isinstance(grade, Grade)
        assert why and len(why) > 20, f"grade {grade} had a thin rationale: {why!r}"
