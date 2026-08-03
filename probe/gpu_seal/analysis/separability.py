"""Same-model die separation — CHARTER.md §9.8b, contribution **D5**.

This is the open problem Alpay & Alpay handed the project. Their §12 says it
plainly:

    "The cross-die identity experiment separates two different Blackwell
     *products*. Same-model die separation is left to prior GPU
     fingerprinting."

They can tell a B200 from a 5090. They have not shown they can tell *your*
H100 from *another* H100 — and §9.5's self-vs-self canary does not work
without that, because a clean result across two allocations of the same
advertised model is equally consistent with "the provider sanitised" and "the
provider gave us a different chip." D1's strongest result is inconclusive
until this is resolved either way.

**What this module is.** The evaluation half of D5: given a set of topology
certificates with known device labels, it measures whether they separate.
Pairwise distances, leave-one-out nearest-neighbour classification, and an
ROC/AUC over same-device versus different-device pairs.

**What this module is not.** It is not the study. §9.8b requires N rented
instances of a single advertised model, and that is Phase 2b work needing a
budget this project does not yet have. What exists here is the instrument that
will grade the data when it arrives, tested against synthetic certificates
with known ground truth so that it is known to work before it is pointed at
anything expensive.

**A negative result is a result.** §9.8b: *"Report honestly if it fails.
'Same-model die separation is not achievable at tenant privilege under
conditions X, Y, Z' is itself a publishable, useful negative that bounds the
whole research area."* :meth:`SeparabilityReport.verdict` is written to make
that outcome as easy to state as the positive one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..probes.topology import TopologyCertificate

__all__ = [
    "SeparabilityReport",
    "certificate_distance",
    "evaluate_separability",
]

#: Leave-one-out accuracy at or above which the classifier is treated as
#: usable for gating §9.5 conclusions. Set at the level the source paper
#: reached for cross-*product* separation (100%), discounted for the harder
#: same-model case: below this, §13.1 grade A stays unreachable.
#:
#: This is a pre-registered threshold (§12 "pre-register scoring"). It is set
#: here, before any same-model data exists, precisely so it cannot be chosen
#: after seeing the result.
VALIDATION_ACCURACY_THRESHOLD = 0.95

#: And the AUC it must clear alongside accuracy. Accuracy alone can be carried
#: by an unbalanced pair set.
VALIDATION_AUC_THRESHOLD = 0.98


def certificate_distance(a: TopologyCertificate, b: TopologyCertificate) -> float:
    """Mean absolute distance between two row-normalised fingerprints.

    Shape-only, matching the source paper's shape-only classification: absolute
    latency tracks clock and thermal state, and comparing raw cycles would
    separate a warm chip from a cold one rather than one die from another.

    Returns ``inf`` for certificates that are not comparable at all — different
    kernels, or different matrix geometry. Infinity rather than a large finite
    number so an incomparable pair can never be silently averaged into a
    distance distribution.
    """
    if a.kernel_hash != b.kernel_hash:
        return float("inf")
    fa, fb = a.shape_features, b.shape_features
    if not fa or len(fa) != len(fb):
        return float("inf")
    return sum(abs(x - y) for x, y in zip(fa, fb, strict=True)) / len(fa)


@dataclass(frozen=True)
class SeparabilityReport:
    """Whether same-model dies separated, and under what conditions."""

    #: Certificates evaluated, and how many distinct physical devices they
    #: came from. Both matter: 20 certificates from 2 dies is a much weaker
    #: study than 20 from 10, and the numbers must travel together.
    certificates: int
    devices: int

    same_device_pairs: int
    different_device_pairs: int

    #: Distance distributions, which are the actual finding. Overlap between
    #: them is what "does not separate" means.
    same_device_distances: list[float]
    different_device_distances: list[float]

    #: Leave-one-out nearest-neighbour accuracy over device labels.
    leave_one_out_accuracy: float
    #: Area under the ROC for the same-vs-different decision.
    auc: float
    #: Distance threshold maximising Youden's J, and its error rates.
    best_threshold: float
    false_positive_rate: float
    false_negative_rate: float

    #: Conditions the study ran under. Named explicitly so that the negative
    #: result, if that is what this is, is bounded rather than universal.
    conditions: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.conditions is None:
            object.__setattr__(self, "conditions", [])

    @property
    def validated(self) -> bool:
        """Whether D5 has landed well enough to gate §9.5 on.

        Read by :class:`gpu_seal.reporting.MemoryHygieneEvidence` as
        ``same_model_classifier_validated``. Both thresholds are
        pre-registered above; neither is adjustable from a result.
        """
        return (
            self.leave_one_out_accuracy >= VALIDATION_ACCURACY_THRESHOLD
            and self.auc >= VALIDATION_AUC_THRESHOLD
            and self.devices >= 2
            and self.same_device_pairs > 0
            and self.different_device_pairs > 0
        )

    def verdict(self) -> str:
        """One sentence, publishable either way."""
        if self.devices < 2:
            return (
                f"Not evaluable: {self.certificates} certificate(s) from "
                f"{self.devices} device(s). Same-model separation requires at "
                f"least two physical dies of one advertised model (§9.8b)."
            )
        if self.validated:
            return (
                f"Same-model die separation achieved at tenant privilege: "
                f"leave-one-out accuracy {self.leave_one_out_accuracy:.1%}, "
                f"AUC {self.auc:.3f}, over {self.devices} dies and "
                f"{self.certificates} certificates. §9.5 conclusions are no "
                f"longer gated (CHARTER.md §13.1)."
            )
        return (
            f"Same-model die separation NOT achieved under these conditions: "
            f"leave-one-out accuracy {self.leave_one_out_accuracy:.1%} "
            f"(pre-registered threshold {VALIDATION_ACCURACY_THRESHOLD:.0%}), "
            f"AUC {self.auc:.3f} (threshold {VALIDATION_AUC_THRESHOLD}). "
            f"Conditions: {'; '.join(self.conditions) or 'unstated'}. This is a "
            f"bounded negative result, not a universal one — it constrains "
            f"§9.5 and §13.1 grade A, which remain capped at U."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "certificates": self.certificates,
            "devices": self.devices,
            "same_device_pairs": self.same_device_pairs,
            "different_device_pairs": self.different_device_pairs,
            "leave_one_out_accuracy": round(self.leave_one_out_accuracy, 4),
            "auc": round(self.auc, 4),
            "best_threshold": round(self.best_threshold, 6),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "false_negative_rate": round(self.false_negative_rate, 4),
            "validated": self.validated,
            "pre_registered_thresholds": {
                "leave_one_out_accuracy": VALIDATION_ACCURACY_THRESHOLD,
                "auc": VALIDATION_AUC_THRESHOLD,
            },
            "conditions": self.conditions,
            "verdict": self.verdict(),
        }


def evaluate_separability(
    labelled: Sequence[tuple[str, TopologyCertificate]],
    *,
    conditions: Sequence[str] = (),
) -> SeparabilityReport:
    """Evaluate whether certificates separate by physical device.

    Args:
        labelled: ``(device_label, certificate)`` pairs. The label is ground
            truth — which physical die the certificate came from — and in a
            real §9.8b study it comes from the researcher's own record of
            which instance was rented when, not from the instrument.
        conditions: what the study held fixed (model, driver version, region,
            load state). Carried into the verdict so a negative result is
            bounded by the conditions that produced it.
    """
    if len(labelled) < 2:
        raise ValueError("separability needs at least two certificates")

    labels = [label for label, _ in labelled]
    certs = [cert for _, cert in labelled]
    devices = len(set(labels))

    same: list[float] = []
    different: list[float] = []
    for i in range(len(certs)):
        for j in range(i + 1, len(certs)):
            distance = certificate_distance(certs[i], certs[j])
            if distance == float("inf"):
                # Incomparable pairs are dropped, not scored. Including them
                # would inflate separation with certificates that were never
                # measuring the same thing.
                continue
            (same if labels[i] == labels[j] else different).append(distance)

    accuracy = _leave_one_out_accuracy(labels, certs)
    auc = _auc(same, different)
    threshold, fpr, fnr = _best_threshold(same, different)

    return SeparabilityReport(
        certificates=len(certs),
        devices=devices,
        same_device_pairs=len(same),
        different_device_pairs=len(different),
        same_device_distances=same,
        different_device_distances=different,
        leave_one_out_accuracy=accuracy,
        auc=auc,
        best_threshold=threshold,
        false_positive_rate=fpr,
        false_negative_rate=fnr,
        conditions=list(conditions),
    )


# ---------------------------------------------------------------------------


def _leave_one_out_accuracy(
    labels: Sequence[str], certs: Sequence[TopologyCertificate]
) -> float:
    """Nearest-neighbour accuracy, holding each certificate out in turn.

    The metric the source paper reports (100% across Blackwell dies), so that
    a same-model number is directly comparable to their cross-product one.
    """
    correct = 0
    scored = 0
    for i in range(len(certs)):
        best_distance = float("inf")
        best_label: str | None = None
        for j in range(len(certs)):
            if i == j:
                continue
            distance = certificate_distance(certs[i], certs[j])
            if distance < best_distance:
                best_distance, best_label = distance, labels[j]
        if best_label is None:
            continue
        scored += 1
        if best_label == labels[i]:
            correct += 1
    return (correct / scored) if scored else 0.0


def _auc(same: Sequence[float], different: Sequence[float]) -> float:
    """Probability a random different-device pair is farther than a same one.

    Computed directly from the Mann-Whitney U interpretation rather than by
    integrating a sampled ROC curve — exact on small samples, which is what
    §9.8b will have.
    """
    if not same or not different:
        return 0.0
    wins = 0.0
    for s in same:
        for d in different:
            if d > s:
                wins += 1.0
            elif d == s:
                wins += 0.5
    return wins / (len(same) * len(different))


def _best_threshold(
    same: Sequence[float], different: Sequence[float]
) -> tuple[float, float, float]:
    """Threshold maximising Youden's J, with the error rates it produces.

    Reported rather than tuned away: the false-positive rate here is the rate
    at which two *different* dies would be called the same one, which is
    exactly the error that would turn "the provider gave us a fresh GPU" into
    a false claim of physical continuity.
    """
    if not same or not different:
        return 0.0, 1.0, 1.0

    candidates = sorted(set(list(same) + list(different)))
    best = (0.0, 1.0, 1.0)
    best_j = -1.0
    for threshold in candidates:
        true_positive = sum(1 for s in same if s <= threshold) / len(same)
        false_positive = sum(1 for d in different if d <= threshold) / len(different)
        j = true_positive - false_positive
        if j > best_j:
            best_j = j
            best = (threshold, false_positive, 1 - true_positive)
    return best
