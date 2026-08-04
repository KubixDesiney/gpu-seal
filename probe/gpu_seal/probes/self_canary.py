"""Self-vs-self sequential canary — CHARTER.md §9.5. **Gated on D5.**

    "The clean, fully-ethical isolation test: does a canary written in
     Allocation A appear in a later Allocation B controlled by the same
     researcher?"

Nothing in this probe ever touches data belonging to anyone else. It writes a
marker we minted, releases the allocation, rents again, and looks for our own
marker. That property makes §9.5 runnable under a provider policy of
``self-canary-only``, which is why it matters commercially as well as
scientifically.

**The gate.** §9.5's strongest result requires knowing that Allocation A and
Allocation B were the same physical accelerator. The topology instrument
(§9.8) gives evidence for that across *products* — a B200 is not a 5090 — but
Alpay & Alpay explicitly defer same-model die separation, which is contribution
D5 (§9.8b). Until D5 lands with a calibrated classifier, **every negative
result where both allocations share an advertised model must be reported
inconclusive**, and this module enforces that rather than trusting the caller
to remember.

The interpretation table from §9.5, implemented in :func:`interpret`:

===============================  =========================================
observation                      reported as
===============================  =========================================
canary matched                   strong signal; private disclosure first
no match, fingerprints differ    inconclusive
no match, fingerprints agree     useful, not absolute proof
fingerprint uncertain            inconclusive
===============================  =========================================

And the wording rule, which is not negotiable: report *"the two allocations
were consistent with the same physical accelerator under the project's
classifier"*. Never *"proved both allocations used the same physical GPU"*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..evidence.observation import ObservationRecord
from ..safety.aggregation import AggregateRecord
from .topology import ConsistencyResult, TopologyCertificate, compare_certificates

if TYPE_CHECKING:
    # Deferred to break a real import cycle: gpu_seal.analysis (package
    # __init__) imports .separability, which imports ..probes.topology,
    # which — going through the ..probes package __init__ — reaches this
    # module again before `analysis`'s own __init__ has finished. Safe as a
    # type-only import: `from __future__ import annotations` above means the
    # annotation below is never evaluated at runtime, only read by mypy.
    from ..analysis.separability import SeparabilityReport

__all__ = [
    "SelfCanaryResult",
    "AllocationLeg",
    "interpret",
    "PROBE_NAME",
    "PROBE_VERSION",
]

PROBE_NAME = "self_sequential_canary"
PROBE_VERSION = "0.2.0"


@dataclass(frozen=True)
class AllocationLeg:
    """One half of the §9.5 pair — one rental of one instance."""

    #: Operator's label for this rental. Not a provider instance id (§10).
    leg_id: str
    #: The advertised GPU model for this rental, from the invoice.
    advertised_gpu: str
    #: Topology certificate taken during this rental, if the instrument ran.
    certificate: TopologyCertificate | None = None
    #: Read-before-write measurement of leg B. ``None`` for leg A.
    #:
    #: Take it with ``GlobalMemoryProbe.read_before_write(...,
    #: expected_owned_allocation_ids={leg_a_canary.allocation_id})``, not the
    #: unscoped default. Without that, ``owned_canary_match`` is true if
    #: *any* canary this ``CanarySet`` ever minted turns up in leg B — not
    #: specifically the one planted in leg A — which matters the moment a
    #: caller reuses one CanarySet across more than one allocation, exactly
    #: what a real §9.5 campaign does across repeated A/B pairs.
    observation: AggregateRecord | None = None


@dataclass(frozen=True)
class SelfCanaryResult:
    """Outcome of one A/B pair, with its interpretation already bounded."""

    #: ``canary_recovered`` / ``clean_same_device`` / ``inconclusive`` /
    #: ``not_testable``
    finding: str
    canary_recovered: bool
    same_device: ConsistencyResult | None
    same_advertised_model: bool
    d5_validated: bool
    interpretation: str
    limitations: list[str] = field(default_factory=list)
    #: True when CHARTER.md §7.5 applies before anything leaves the machine.
    requires_private_disclosure: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding": self.finding,
            "canary_recovered": self.canary_recovered,
            "same_advertised_model": self.same_advertised_model,
            "same_model_classifier_validated": self.d5_validated,
            "physical_continuity_band": (
                self.same_device.band if self.same_device else "not_testable"
            ),
            "physical_continuity_supported": (
                self.same_device.supports_same_device_claim
                if self.same_device
                else False
            ),
            "interpretation": self.interpretation,
            "limitations": self.limitations,
            "requires_private_disclosure": self.requires_private_disclosure,
        }


def interpret(
    leg_a: AllocationLeg,
    leg_b: AllocationLeg,
    *,
    same_model_classifier: SeparabilityReport | None = None,
    threshold: float = 0.02,
) -> SelfCanaryResult:
    """Apply the §9.5 interpretation table, with the D5 gate on top.

    Args:
        same_model_classifier: the §9.8b evaluation, if one has been run —
            i.e. the actual output of
            ``gpu_seal.analysis.separability.evaluate_separability()``, not a
            bare assertion. Its ``.validated`` property is a pre-registered,
            threshold-gated computation (CHARTER.md §12); nothing here trusts
            a caller-supplied boolean claiming D5 has landed.
    """
    d5_validated = (
        same_model_classifier.validated if same_model_classifier is not None else False
    )
    same_advertised_model = (
        leg_a.advertised_gpu.strip().lower() == leg_b.advertised_gpu.strip().lower()
    )

    continuity: ConsistencyResult | None = None
    if leg_a.certificate is not None and leg_b.certificate is not None:
        continuity = compare_certificates(
            leg_a.certificate,
            leg_b.certificate,
            same_advertised_model=same_advertised_model,
            same_model_classifier_validated=d5_validated,
            threshold=threshold,
        )

    limitations = [
        "self-canary only: no data belonging to anyone else was written, "
        "searched for, or read (CHARTER.md §7.1)",
        "an all-zero second allocation does not prove sanitisation; it may be "
        "a fresh page or a zeroing runtime (CHARTER.md §9.3)",
    ]

    recovered = bool(leg_b.observation and leg_b.observation.owned_canary_match)

    # --- Positive. The one branch that asserts something happened. ---
    if recovered:
        return SelfCanaryResult(
            finding="canary_recovered",
            canary_recovered=True,
            same_device=continuity,
            same_advertised_model=same_advertised_model,
            d5_validated=d5_validated,
            interpretation=(
                "An owned canary planted in allocation "
                f"{leg_a.leg_id!r} was recovered in allocation "
                f"{leg_b.leg_id!r}. Strong signal. CHARTER.md §7.5 applies: "
                "reproduce internally, eliminate methodology error, confirm "
                "only owned canaries matched, and contact the provider "
                "privately before this leaves the machine."
            ),
            limitations=limitations
            + [
                "a recovered marker across a sequential rental is consistent "
                "with incomplete sanitisation, and also with the provider "
                "returning the same instance without releasing it; the "
                "allocation model (§9.7) must be read alongside this result"
            ],
            requires_private_disclosure=True,
        )

    if leg_b.observation is None:
        return SelfCanaryResult(
            finding="not_testable",
            canary_recovered=False,
            same_device=continuity,
            same_advertised_model=same_advertised_model,
            d5_validated=d5_validated,
            interpretation=(
                "No read-before-write measurement was taken in the second "
                "allocation, so the pair yields no observation."
            ),
            limitations=limitations,
        )

    # --- Negative. Everything below is about how little it proves. ---
    if continuity is None:
        return SelfCanaryResult(
            finding="inconclusive",
            canary_recovered=False,
            same_device=None,
            same_advertised_model=same_advertised_model,
            d5_validated=d5_validated,
            interpretation=(
                "No owned canary was recovered, and no topology evidence was "
                "collected for either allocation. A clean result on a "
                "possibly-different chip is not evidence of sanitisation. "
                "Inconclusive."
            ),
            limitations=limitations
            + ["the topology instrument (§9.8) did not run for this pair"],
        )

    if not continuity.supports_same_device_claim:
        reason = (
            "both allocations advertised the same GPU model, and same-model "
            "die separation (contribution D5, §9.8b) is not validated, so the "
            "instrument cannot distinguish the same physical accelerator from "
            "a different one of the same model"
            if same_advertised_model and not d5_validated
            else "the topology fingerprints do not support physical continuity "
            f"between the two allocations (band: {continuity.band})"
        )
        return SelfCanaryResult(
            finding="inconclusive",
            canary_recovered=False,
            same_device=continuity,
            same_advertised_model=same_advertised_model,
            d5_validated=d5_validated,
            interpretation=(
                f"No owned canary was recovered, but {reason}. Reported "
                f"inconclusive rather than as a clean result (CHARTER.md §9.5, "
                f"§13.1)."
            ),
            limitations=limitations + continuity.reasons,
        )

    return SelfCanaryResult(
        finding="clean_same_device",
        canary_recovered=False,
        same_device=continuity,
        same_advertised_model=same_advertised_model,
        d5_validated=d5_validated,
        interpretation=(
            "No owned canary was recovered, and the two allocations were "
            "consistent with the same physical accelerator under the project's "
            "classifier. Useful evidence, not absolute proof — the classifier "
            "reports consistency, not identity."
        ),
        limitations=limitations
        + continuity.reasons
        + [
            "phrasing is deliberate: 'consistent with the same physical "
            "accelerator under the project's classifier', never 'proved both "
            "allocations used the same physical GPU' (CHARTER.md §9.5)"
        ],
    )


def observation(result: SelfCanaryResult) -> ObservationRecord:
    """Bundle-ready record. Blocked from publication when disclosure applies."""
    return ObservationRecord(
        probe_name=PROBE_NAME,
        probe_version=PROBE_VERSION,
        subject="self_sequential_canary",
        category="memory_hygiene",
        classification=(
            "not_testable" if result.finding == "not_testable" else result.finding
        ),
        value=result.to_dict(),
        confidence=0.8 if result.finding == "clean_same_device" else 0.3,
        evidence=[result.interpretation],
        limitations=result.limitations,
        not_testable_reason=(
            "no read-before-write measurement was taken in the second allocation"
            if result.finding == "not_testable"
            else None
        ),
        # A recovered marker requires CHARTER.md §7.5 private disclosure
        # before anything leaves the machine — the publication gate must see
        # this even though the finding lives in `observations`, not `probes`.
        blocks_publication=result.requires_private_disclosure,
    )
