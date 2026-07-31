"""Assurance report card — CHARTER.md §13.

Per-category letter grades, deliberately no single composite score. A
"62/100" invites a league table; independent category grades force the reader
to look at what was actually measured.

The v2 constraint implemented here (charter §13.1, §16 test 16) is the
important one:

    Grade A requires valid same-device evidence. Until same-model die
    separation (§9.8b / contribution D5) is validated, two allocations that
    share an advertised model cannot be shown to be the same physical GPU —
    so a clean canary result across them proves nothing and caps at U.

This is the difference between "we found no residue" and "we found no residue
on the same chip." Only the second is a finding. Without the constraint the
grader would quietly award an A to a provider that simply handed us a
different, freshly-booted GPU the second time.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

__all__ = ["Grade", "MemoryHygieneEvidence", "grade_memory_hygiene"]


class Grade(str, Enum):
    """CHARTER.md §13 grades. U is not a failing grade — it means unproven."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    U = "U"  # insufficient evidence / unsupported by the method


@dataclass(frozen=True)
class MemoryHygieneEvidence:
    """Inputs to the §13.1 memory lifecycle hygiene grade."""

    #: Number of completed allocation-pair cycles measured.
    cycles: int
    #: Cycles in which an owned canary was recovered where it should have been sanitised.
    canary_recovered_cycles: int
    #: Cycles showing non-zero or otherwise ambiguous content, no canary match.
    ambiguous_cycles: int
    #: True when topology evidence supports the two allocations being the same
    #: physical accelerator. See §9.8 / §9.8b.
    same_device_evidence: bool
    #: True when both allocations shared an advertised GPU model, which requires
    #: same-model die separation (D5) to make `same_device_evidence` meaningful.
    same_advertised_model: bool
    #: True once §9.8b has produced a calibrated same-model classifier.
    same_model_classifier_validated: bool = False
    #: Results varied across boundary, product, or run.
    inconsistent_across_runs: bool = False

    @property
    def same_device_evidence_is_usable(self) -> bool:
        """Same-device evidence only counts if the classifier can support it.

        If both allocations advertised the same model and D5 has not landed,
        the topology instrument cannot distinguish "same H100" from "a
        different H100" — so its claim of continuity is not usable evidence,
        regardless of what confidence score it emitted.
        """
        if not self.same_device_evidence:
            return False
        if self.same_advertised_model and not self.same_model_classifier_validated:
            return False
        return True


def grade_memory_hygiene(
    ev: MemoryHygieneEvidence, *, minimum_cycles: int = 10
) -> tuple[Grade, str]:
    """Grade §13.1 memory lifecycle hygiene. Returns (grade, rationale).

    Rationale is always populated: a grade without a stated basis is not
    publishable, and the string goes straight into the report.
    """
    if ev.cycles <= 0:
        return Grade.U, "No completed measurement cycles."

    # D — the only grade that asserts a failure. Requires a positive finding.
    if ev.canary_recovered_cycles > 0:
        return (
            Grade.D,
            f"An owned canary was recovered in {ev.canary_recovered_cycles} of "
            f"{ev.cycles} cycles across a boundary where sanitisation was "
            f"expected. Pending private disclosure and provider response "
            f"(CHARTER.md §7.5).",
        )

    if ev.inconsistent_across_runs:
        return (
            Grade.C,
            f"Behaviour varied across boundary, product, or run over "
            f"{ev.cycles} cycles. Not a stable property.",
        )

    if ev.cycles < minimum_cycles:
        return (
            Grade.U,
            f"Only {ev.cycles} cycles completed; {minimum_cycles} required "
            f"before a hygiene grade is supportable (CHARTER.md §12).",
        )

    # --- The v2 gate. CI test 16 enforces that this cannot be bypassed. ---
    if not ev.same_device_evidence_is_usable:
        if ev.same_advertised_model and not ev.same_model_classifier_validated:
            reason = (
                "both allocations advertised the same GPU model, and same-model "
                "die separation (§9.8b, contribution D5) is not yet validated — "
                "so the topology instrument cannot distinguish the same physical "
                "accelerator from a different one of the same model"
            )
        else:
            reason = "no topology evidence supports same-physical-device continuity"
        return (
            Grade.U,
            f"No owned canaries were recovered across {ev.cycles} cycles, but "
            f"{reason}. A clean result on an unknown-possibly-different chip is "
            f"not evidence of sanitisation. Capping at U rather than A "
            f"(CHARTER.md §13.1).",
        )

    if ev.ambiguous_cycles > 0:
        return (
            Grade.B,
            f"No owned canaries recovered across {ev.cycles} cycles with valid "
            f"same-device evidence, but {ev.ambiguous_cycles} cycles showed "
            f"non-zero or ambiguous content.",
        )

    return (
        Grade.A,
        f"No owned canaries recovered across {ev.cycles} cycles, with repeated "
        f"valid same-physical-device evidence and no ambiguous content.",
    )
