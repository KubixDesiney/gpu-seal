"""Allocation-model classifier — CHARTER.md §9.7, contribution D3.

    "Classify the allocation model **before interpreting anything**."

This is the probe that makes the others mean something. NVIDIA's own GPU
Operator documentation states plainly that time-slicing provides **no memory
or fault isolation** between replicas. A customer sold a "fractional H100"
cannot tell from the invoice whether they bought hardware-partitioned MIG or
an unisolated time-slice — and the same canary result means opposite things
under the two. A clean §9.3 measurement under MIG is evidence about hardware
partitioning; the identical measurement under time-slicing is evidence about
nothing at all, because the boundary the canary crossed was never claimed to
exist.

So the classifier runs first, and its output gates the interpretation of
everything downstream.

**What this is not.** It is not a claim about what the provider is doing. It
is an inference from tenant-visible signals, and §9.7 is explicit: never
present inference as provider-confirmed fact. Every result carries a
confidence, the evidence it was built from, and the evidence that contradicts
it. Where the signals do not separate the candidates, the answer is
``shared_unknown`` or ``undocumented`` — both of which are *results*, and the
`undocumented` rate in the wild is itself one of the §18 evaluation metrics.

**Calibration status.** The weights below are priors, chosen from the
documented behaviour of each model, not fitted to data. §18 requires
classification accuracy against ground truth on researcher-configured
hardware, and that requires hardware this project does not yet have (MIG needs
A100/H100-class silicon). Until that lands, confidences are ordinal — they
rank hypotheses correctly — but they are not calibrated probabilities, and
:data:`CALIBRATION_STATUS` says so in every bundle that carries a
classification.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from collections.abc import Sequence

from ..cuda.backend import CudaBackend
from ..evidence.observation import ObservationRecord
from ..safety.campaign import CampaignControl
from ..safety.policy import ALLOCATION_MODEL_CLASSES

__all__ = [
    "AllocationEvidence",
    "AllocationModelClassifier",
    "Classification",
    "measure_scheduling_gaps",
    "CALIBRATION_STATUS",
    "PROBE_NAME",
    "PROBE_VERSION",
]

PROBE_NAME = "allocation_model_classifier"
PROBE_VERSION = "0.2.0"

#: Recorded alongside every classification. See the module docstring.
CALIBRATION_STATUS = (
    "uncalibrated: weights are documented-behaviour priors, not fitted to "
    "ground truth. Confidences rank hypotheses; they are not probabilities. "
    "Calibration requires MIG-capable hardware (CHARTER.md §18, §20)."
)

#: Above this ratio of tail-to-median inter-operation latency, the device is
#: being taken away from us periodically. That is what a time-slice looks like
#: from inside: our work is correct, and it stops for a while.
#:
#: Chosen conservatively. A busy device with our own queued work also stalls,
#: so this signal supports a hypothesis and never establishes one alone.
SCHEDULING_STALL_RATIO = 4.0


@dataclass(frozen=True)
class AllocationEvidence:
    """Tenant-visible signals feeding the classification.

    Every field is optional. A signal that could not be collected is ``None``
    and contributes nothing — it never counts against a hypothesis, because
    "we could not look" is not evidence of absence.
    """

    #: What the provider documents, if anything. The strongest single signal
    #: and the only one that is not an inference — but §13.5 grade D exists
    #: precisely for the case where it is contradicted by measurement.
    documented_model: str | None = None

    mig_enabled: bool | None = None
    #: True when the device handed to us is itself a MIG instance rather than
    #: a whole GPU (the management library reports these distinctly).
    mig_instance_visible: bool | None = None

    visible_memory_bytes: int | None = None
    #: Memory the advertised model ships with. Supplied by the operator from
    #: the vendor specification, not measured — measuring it is the thing we
    #: are checking against.
    advertised_model_memory_bytes: int | None = None

    visible_device_count: int | None = None
    virtualisation_indicators: Sequence[str] = field(default_factory=tuple)
    containerised: bool | None = None

    #: Compute processes the management library was willing to describe.
    neighbour_process_count: int | None = None

    #: True when a multi-process service control interface is configured.
    mps_control_configured: bool | None = None

    #: Tail-to-median latency ratio from :func:`measure_scheduling_gaps`.
    scheduling_stall_ratio: float | None = None

    #: Device name as reported by the runtime, lowercased by the classifier.
    reported_model: str | None = None

    @property
    def memory_fraction(self) -> float | None:
        """Visible memory as a fraction of the advertised model's capacity."""
        if not self.visible_memory_bytes or not self.advertised_model_memory_bytes:
            return None
        return self.visible_memory_bytes / self.advertised_model_memory_bytes


@dataclass(frozen=True)
class Classification:
    """One classification result with its full reasoning."""

    classification: str
    confidence: float
    evidence: list[str]
    contradicting: list[str]
    limitations: list[str]
    #: Every hypothesis and its score, so a reader can see how close the
    #: runner-up was. A 0.51/0.49 split and a 0.95/0.02 split are different
    #: results and must not look the same in the dataset.
    ranked: list[tuple[str, float]]

    def __post_init__(self) -> None:
        if self.classification not in ALLOCATION_MODEL_CLASSES:
            raise ValueError(
                f"{self.classification!r} is not one of the CHARTER.md §9.7 "
                f"classes: {sorted(ALLOCATION_MODEL_CLASSES)}"
            )


class AllocationModelClassifier:
    """Infer the allocation model from tenant-visible signals."""

    NAME = PROBE_NAME
    VERSION = PROBE_VERSION

    #: Minimum margin between the top two hypotheses before the top one is
    #: reported. Below this the signals did not separate them, and the honest
    #: answer is the corresponding "unknown" class rather than a coin flip.
    SEPARATION_MARGIN = 0.15

    def __init__(self, *, campaign: CampaignControl | None = None) -> None:
        self._campaign = campaign or CampaignControl.create()

    def classify(self, ev: AllocationEvidence) -> Classification:
        self._campaign.check()
        scores: dict[str, float] = {}
        evidence: dict[str, list[str]] = {}
        contradicting: list[str] = []

        for name, score, why in self._score_hypotheses(ev):
            scores[name] = score
            evidence[name] = why

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top, top_score = ranked[0]
        runner_up_score = ranked[1][1] if len(ranked) > 1 else 0.0

        limitations = [
            CALIBRATION_STATUS,
            "inference from tenant-visible signals; not confirmed by the "
            "provider (CHARTER.md §9.7)",
        ]

        if ev.documented_model:
            documented = _normalise(ev.documented_model)
            if documented in ALLOCATION_MODEL_CLASSES and documented != top:
                contradicting.append(
                    f"the provider documents {documented!r}; measurement "
                    f"favours {top!r}"
                )

        # Not separated — say so rather than reporting the winner of a
        # near-tie as though the signals had decided it.
        if top_score <= 0.0 or (top_score - runner_up_score) < self.SEPARATION_MARGIN:
            unknown = self._unknown_class(ev)
            return Classification(
                classification=unknown,
                confidence=min(top_score, 0.4),
                evidence=[
                    f"no hypothesis separated from the field by the required "
                    f"margin of {self.SEPARATION_MARGIN}",
                    f"leading hypothesis {top!r} scored {top_score:.2f}; "
                    f"runner-up scored {runner_up_score:.2f}",
                ]
                + evidence.get(top, []),
                contradicting=contradicting,
                limitations=limitations
                + [
                    "reported as unclassified rather than as the leading "
                    "hypothesis; §18 counts this toward the `undocumented` rate"
                ],
                ranked=ranked,
            )

        return Classification(
            classification=top,
            confidence=min(top_score, 0.95),
            evidence=evidence.get(top, []),
            contradicting=contradicting,
            limitations=limitations,
            ranked=ranked,
        )

    def observation(self, result: Classification) -> ObservationRecord:
        """Wrap a classification as a bundle-ready record."""
        self._campaign.check()
        return ObservationRecord(
            probe_name=self.NAME,
            probe_version=self.VERSION,
            subject="allocation_model",
            category="allocation_model",
            classification=result.classification,
            value={name: round(score, 4) for name, score in result.ranked},
            confidence=result.confidence,
            evidence=result.evidence + result.contradicting,
            limitations=result.limitations,
        )

    # ------------------------------------------------------------------
    # Hypotheses. Each returns (class, score in 0..1, supporting evidence).
    # ------------------------------------------------------------------

    def _score_hypotheses(
        self, ev: AllocationEvidence
    ) -> list[tuple[str, float, list[str]]]:
        return [
            self._score_mig(ev),
            self._score_time_slicing(ev),
            self._score_mps(ev),
            self._score_vgpu(ev),
            self._score_passthrough(ev),
            self._score_software_fractional(ev),
        ]

    def _score_mig(self, ev: AllocationEvidence) -> tuple[str, float, list[str]]:
        score = 0.0
        why: list[str] = []

        if ev.mig_instance_visible:
            score += 0.6
            why.append("the device handed to this tenant is a MIG instance")
        if ev.mig_enabled:
            score += 0.25
            why.append("MIG mode is enabled on the parent device")
        elif ev.mig_enabled is False:
            score -= 0.5
            why.append("MIG mode is reported disabled on the parent device")

        fraction = ev.memory_fraction
        if fraction is not None and fraction < 0.95:
            score += 0.15
            why.append(
                f"visible memory is {fraction:.0%} of the advertised model's "
                f"capacity, consistent with a partition"
            )

        model = _normalise(ev.reported_model or "")
        if "mig" in model.split("_"):
            score += 0.2
            why.append("the reported device name identifies a MIG profile")

        return "mig_instance", _clamp(score), why

    def _score_time_slicing(
        self, ev: AllocationEvidence
    ) -> tuple[str, float, list[str]]:
        """The important one, and the hardest.

        A time-slice looks like a whole GPU: full memory, one device, MIG off.
        The only tenant-visible tells are that somebody else's work runs on it
        and that ours periodically stops. Neither is conclusive, which is why
        this hypothesis is deliberately hard to push above the separation
        margin — and why a provider selling "fractional GPU" without saying
        which kind is a §13.5 finding regardless of what this scores.
        """
        score = 0.0
        why: list[str] = []

        if ev.mig_enabled is False:
            score += 0.15
            why.append("MIG is disabled, so any sharing is not hardware-partitioned")

        fraction = ev.memory_fraction
        if fraction is not None and fraction >= 0.95:
            score += 0.2
            why.append(
                "the full memory of the advertised model is visible, which "
                "rules out a memory-partitioned model"
            )

        if ev.neighbour_process_count:
            score += 0.3
            why.append(
                f"the management library described "
                f"{ev.neighbour_process_count} compute process(es) on this "
                f"device"
            )

        if ev.scheduling_stall_ratio is not None:
            if ev.scheduling_stall_ratio >= SCHEDULING_STALL_RATIO:
                score += 0.3
                why.append(
                    f"inter-operation latency tail is "
                    f"{ev.scheduling_stall_ratio:.1f}x the median, consistent "
                    f"with the device being scheduled away periodically"
                )
            else:
                score -= 0.2
                why.append(
                    f"inter-operation latency tail is only "
                    f"{ev.scheduling_stall_ratio:.1f}x the median; no "
                    f"scheduling interruption observed"
                )

        if ev.mps_control_configured:
            # MPS also shares a full device, and explains neighbours without
            # time-slicing. Push the two apart rather than letting both float.
            score -= 0.25
            why.append(
                "a multi-process service control interface is configured, "
                "which explains device sharing without time-slicing"
            )

        return "time_sliced_full_gpu", _clamp(score), why

    def _score_mps(self, ev: AllocationEvidence) -> tuple[str, float, list[str]]:
        score = 0.0
        why: list[str] = []
        if ev.mps_control_configured:
            score += 0.7
            why.append("a multi-process service control interface is configured")
        elif ev.mps_control_configured is False:
            score -= 0.3
            why.append("no multi-process service control interface is configured")
        if ev.neighbour_process_count:
            score += 0.15
            why.append("other compute processes are visible on this device")
        return "mps", _clamp(score), why

    def _score_vgpu(self, ev: AllocationEvidence) -> tuple[str, float, list[str]]:
        score = 0.0
        why: list[str] = []

        model = _normalise(ev.reported_model or "")
        if "grid" in model.split("_") or "vgpu" in model.split("_"):
            score += 0.65
            why.append("the reported device name identifies a virtual GPU profile")

        if ev.virtualisation_indicators:
            score += 0.2
            why.append(
                f"{len(ev.virtualisation_indicators)} virtualisation "
                f"indicator(s) present in the guest"
            )

        fraction = ev.memory_fraction
        if fraction is not None and fraction < 0.95:
            score += 0.1
            why.append("visible memory is below the advertised model's capacity")

        return "dedicated_virtual_gpu", _clamp(score), why

    def _score_passthrough(
        self, ev: AllocationEvidence
    ) -> tuple[str, float, list[str]]:
        score = 0.0
        why: list[str] = []

        fraction = ev.memory_fraction
        if fraction is not None and fraction >= 0.95:
            score += 0.35
            why.append("the full memory of the advertised model is visible")

        if ev.mig_enabled is False:
            score += 0.2
            why.append("MIG mode is disabled")

        if ev.neighbour_process_count == 0:
            score += 0.3
            why.append("no other compute process is visible on this device")
        elif ev.neighbour_process_count:
            score -= 0.4
            why.append(
                "other compute processes are visible, which is not consistent "
                "with an exclusively-held device"
            )

        if ev.scheduling_stall_ratio is not None:
            if ev.scheduling_stall_ratio < SCHEDULING_STALL_RATIO:
                score += 0.15
                why.append("no scheduling interruption observed")
            else:
                score -= 0.3
                why.append("the device is periodically scheduled away from us")

        model = _normalise(ev.reported_model or "")
        if "grid" in model.split("_") or "vgpu" in model.split("_"):
            score -= 0.5
            why.append("the reported device name identifies a virtual GPU profile")

        return "dedicated_physical_passthrough", _clamp(score), why

    def _score_software_fractional(
        self, ev: AllocationEvidence
    ) -> tuple[str, float, list[str]]:
        """Memory smaller than the model ships with, and nothing explains it.

        Software-fractional platforms intercept the allocator to enforce a
        quota. From inside, that looks like a GPU with the wrong amount of
        memory and no partitioning mechanism to account for it.
        """
        score = 0.0
        why: list[str] = []

        fraction = ev.memory_fraction
        if fraction is None:
            return "software_fractional_gpu", 0.0, why

        if fraction < 0.95:
            score += 0.4
            why.append(
                f"visible memory is {fraction:.0%} of the advertised model's "
                f"capacity"
            )
            if ev.mig_enabled is False:
                score += 0.3
                why.append(
                    "MIG is disabled, so the reduction is not a hardware partition"
                )
            if not ev.virtualisation_indicators:
                score += 0.15
                why.append(
                    "no virtualisation indicators, so the reduction is not a "
                    "virtual GPU profile"
                )
        else:
            score -= 0.4
            why.append("the full memory of the advertised model is visible")

        return "software_fractional_gpu", _clamp(score), why

    # ------------------------------------------------------------------

    def _unknown_class(self, ev: AllocationEvidence) -> str:
        """Which flavour of "we do not know" applies.

        The distinction matters to §13.5: a provider who documented nothing
        and a provider whose documentation we simply could not separate from
        the measurement are different findings.
        """
        if ev.documented_model is None:
            return "undocumented"
        if ev.neighbour_process_count:
            return "shared_unknown"
        return "dedicated_unknown"


# ---------------------------------------------------------------------------
# Timing signal
# ---------------------------------------------------------------------------


def measure_scheduling_gaps(
    backend: CudaBackend,
    *,
    samples: int = 200,
    probe_bytes: int = 4096,
    campaign: CampaignControl | None = None,
) -> float | None:
    """Tail-to-median ratio of inter-operation latency on the device.

    Issues a long series of tiny device operations and times each one. Under
    exclusive access the distribution is tight. Under time-slicing our work is
    correct but periodically suspended, so the tail separates from the median
    while the median itself barely moves — which is the shape this returns.

    Deliberately built from allocation and host-to-device copies rather than a
    compiled kernel: it must run wherever the memory probes run, including
    hosts with no runtime compiler available, and it needs no kernel source to
    hash into the bundle.

    Returns ``None`` if the measurement could not be taken. The classifier
    treats that as no signal, never as a negative one.

    **Not a side channel.** Only our own operations are timed, and only their
    aggregate distribution is retained. This measures whether *we* were
    scheduled, not what anybody else did — CHARTER.md §6 lists cache and TLB
    side channels as explicitly out of scope.
    """
    if samples < 8:
        raise ValueError("need at least 8 samples for a tail estimate")

    marker = b"\x00" * min(probe_bytes, 4096)
    timings: list[int] = []
    alloc = None
    try:
        alloc = backend.malloc(probe_bytes)
        for _ in range(samples):
            if campaign is not None:
                campaign.check()
            started = time.perf_counter_ns()
            backend.write_to_device(alloc, 0, marker)
            timings.append(time.perf_counter_ns() - started)
    except (MemoryError, ValueError, RuntimeError):
        return None
    finally:
        if alloc is not None:
            try:
                backend.free(alloc)
            except Exception:  # noqa: BLE001 - teardown must not mask
                pass

    ordered = sorted(timings)
    median = ordered[len(ordered) // 2]
    if median <= 0:
        return None
    tail = ordered[int(len(ordered) * 0.99)]
    return tail / median


# ---------------------------------------------------------------------------


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalise(text: str) -> str:
    """Lowercase, with separators folded to underscores.

    Used for comparing device names and documented model strings without
    importing a regex engine (§16 test 5).
    """
    folded = text.strip().lower()
    for separator in (" ", "-", ".", "/"):
        folded = folded.replace(separator, "_")
    return folded
