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

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "Grade",
    "MeasurementPath",
    "MemoryHygieneEvidence",
    "grade_memory_hygiene",
    "grade_tenant_exposure",
    "grade_hardware_claim",
    "grade_location_claim",
    "grade_allocation_transparency",
    "attestation_field_report",
    "ReportCard",
    "build_report_card",
]


class Grade(str, Enum):
    """CHARTER.md §13 grades. U is not a failing grade — it means unproven."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    U = "U"  # insufficient evidence / unsupported by the method


class MeasurementPath(str, Enum):
    """How the memory under a canary result was allocated and freed.

    This determines whether a result says anything about a *provider* at all,
    and getting it wrong is the most dangerous error this project can make.

    A canary recovered through a caching allocator (§9.4) is the harness
    working correctly: the pool never called ``cudaFree``, so the driver was
    never told the memory was released and had no opportunity to scrub it.
    Recovering the marker there proves detection capability and nothing else.

    A canary recovered through the raw runtime API (§9.3), where the driver
    *was* told and the memory came back anyway, is a finding about the
    platform.

    The numbers are identical. Only the path distinguishes a working control
    from an accusation.
    """

    #: §9.3 — cudaMalloc/cudaFree. The driver saw the free. Gradeable.
    DRIVER_DIRECT = "driver_direct"

    #: §9.4 — caching allocator; the driver was never told. Control only.
    FRAMEWORK_POOLED = "framework_pooled"

    #: Host-side model. Never evidence about anything.
    SIMULATED = "simulated"

    #: Not stated. Treated as ungradeable, deliberately.
    UNKNOWN = "unknown"


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

    #: How the memory was allocated and freed. Defaults to UNKNOWN, which is
    #: ungradeable — forgetting to state the path yields U, never a D.
    measurement_path: MeasurementPath = MeasurementPath.UNKNOWN

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

    # --- Measurement-path gate. MUST precede the D branch. ---
    #
    # A canary recovered through a caching allocator is the §9.4 control
    # working, not a provider failing. The counts are indistinguishable, so
    # the path has to be checked before any grade is assigned — otherwise a
    # successful control becomes a grade D and a disclosure email.
    if ev.measurement_path is not MeasurementPath.DRIVER_DIRECT:
        detail = {
            MeasurementPath.FRAMEWORK_POOLED: (
                "the allocation was freed to a caching allocator's pool, so the "
                "driver was never told the memory was released and had no "
                "opportunity to sanitise it. Recovering a canary here is the "
                "§9.4 detection-capability control succeeding — it says nothing "
                "about the provider"
            ),
            MeasurementPath.SIMULATED: (
                "the measurement came from the host-side allocator model, which "
                "is not evidence about any hardware"
            ),
            MeasurementPath.UNKNOWN: (
                "the measurement path was not stated, so it cannot be "
                "established whether the driver ever had an opportunity to "
                "sanitise the memory"
            ),
        }[ev.measurement_path]
        return (
            Grade.U,
            f"Not gradeable for memory lifecycle hygiene: {detail}. Only "
            f"driver-direct measurements (§9.3) support a §13.1 grade "
            f"(CHARTER.md §9.3, §9.4).",
        )

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


# ===========================================================================
# §13.2 Tenant exposure
# ===========================================================================


def grade_tenant_exposure(
    classifications: Mapping[str, int],
    *,
    neighbour_metadata_visible: bool = False,
) -> tuple[Grade, str]:
    """Grade §13.2 from §9.6's interpretation counts.

    The ordering matters and is not the obvious one. ``secure_restriction``
    counts are *good* — an interface that correctly requires privilege and
    refuses us is the system working. A grader that treated every restricted
    interface as a missing capability would rank the most locked-down provider
    worst, which is the failure mode §9.6 warns about in its own words: "not
    every unavailable interface is a failure".

    Args:
        neighbour_metadata_visible: reserved for grade D, which requires
            demonstrated cross-boundary visibility of *researcher-controlled*
            neighbour metadata. Inferring D from a bare process count would
            convert an ambiguous observation into an accusation, so it takes a
            controlled two-instance experiment to set this.
    """
    total = sum(classifications.values())
    if total == 0:
        return Grade.U, "No exposure observations were collected."

    testable = total - classifications.get("not_testable", 0)
    if testable == 0:
        return (
            Grade.U,
            f"All {total} exposure observations were not testable in this "
            f"environment.",
        )

    unexpected = classifications.get("unexpected_visibility", 0)
    ambiguous = classifications.get("ambiguous", 0)

    if neighbour_metadata_visible:
        return (
            Grade.D,
            "Metadata belonging to a researcher-controlled neighbour was "
            "visible across the tenancy boundary. Pending private disclosure "
            "and provider response (CHARTER.md §7.5).",
        )

    if unexpected:
        return (
            Grade.C,
            f"{unexpected} of {testable} testable observations showed "
            f"visibility beyond what the workload requires, with no "
            f"justification available from inside the instance.",
        )

    if ambiguous:
        return (
            Grade.B,
            f"No unexpected visibility across {testable} testable "
            f"observations, but {ambiguous} were ambiguous — extra visibility "
            f"with a plausible operational justification.",
        )

    return (
        Grade.A,
        f"Minimal expected exposure across {testable} testable observations; "
        f"{classifications.get('secure_restriction', 0)} interface(s) "
        f"correctly refused this tenant.",
    )


# ===========================================================================
# §13.3 Hardware claim consistency  (instrument-dependent)
# ===========================================================================

#: Appended to every §13.3 and §13.4 rationale. CHARTER.md §13.3: "Cite the
#: reproduced instrument and its limitations with every grade."
_INSTRUMENT_CITATION = (
    " Instrument: topology certificate reproduced from Alpay & Alpay 2026 "
    "(arXiv:2606.24934); it recovers a hardware *class* signature, does not "
    "recover a model number, and does not separate two dies of one model "
    "(contribution D5, open)."
)


def grade_hardware_claim(
    *,
    certificates: int,
    fingerprint_stable: bool,
    consistent_with_advertised_class: bool | None,
    repeated_inconsistency: bool = False,
    instrument_is_evidence: bool = True,
) -> tuple[Grade, str]:
    """Grade §13.3. Instrument-dependent, and says so every time."""
    if not instrument_is_evidence:
        return (
            Grade.U,
            "The topology certificate came from a model rather than silicon "
            "and is not evidence about hardware." + _INSTRUMENT_CITATION,
        )
    if certificates == 0:
        return Grade.U, "No topology certificate was collected." + _INSTRUMENT_CITATION

    if repeated_inconsistency:
        return (
            Grade.D,
            f"Across {certificates} certificates the observed topology was "
            f"repeatedly inconsistent with the advertised class."
            + _INSTRUMENT_CITATION,
        )

    if consistent_with_advertised_class is None:
        return (
            Grade.U,
            f"The classifier did not support a class judgement over "
            f"{certificates} certificate(s)." + _INSTRUMENT_CITATION,
        )

    if not consistent_with_advertised_class:
        return (
            Grade.C,
            f"Observed topology is ambiguous against the advertised class over "
            f"{certificates} certificate(s)." + _INSTRUMENT_CITATION,
        )

    if not fingerprint_stable:
        return (
            Grade.B,
            f"Observed topology is consistent with the advertised class, but "
            f"per-cell jitter over {certificates} certificate(s) is elevated, "
            f"so confidence is limited." + _INSTRUMENT_CITATION,
        )

    return (
        Grade.A,
        f"Observed topology is strongly consistent with the advertised class "
        f"across {certificates} stable certificate(s)." + _INSTRUMENT_CITATION,
    )


# ===========================================================================
# §13.4 Location claim consistency  (instrument-dependent)
# ===========================================================================

#: The resolution bound, restated with every §13.4 grade as §13.4 requires.
_LOCATION_BOUND = (
    " Resolution bound: metropolitan-to-continental only. This grade cannot "
    "support a claim about a datacentre, a campus, or a rack."
)

#: Consistency band → grade. A direct mapping rather than a rule, because the
#: bands were designed against these grades and any logic in between would be
#: a second place for the two to drift apart.
_BAND_TO_GRADE = {
    "consistent": Grade.A,
    "probably_consistent": Grade.B,
    "ambiguous": Grade.C,
    "probably_inconsistent": Grade.C,
    "inconsistent": Grade.D,
    "not_testable": Grade.U,
}


def grade_location_claim(
    band: str, *, repeated_measurements: int = 1
) -> tuple[Grade, str]:
    """Grade §13.4 from a §9.9 consistency band."""
    if band not in _BAND_TO_GRADE:
        raise ValueError(f"{band!r} is not a CHARTER.md §9.9 consistency band")

    grade = _BAND_TO_GRADE[band]

    # A single measurement cannot establish an inconsistency. Routing,
    # congestion, and traffic engineering all move on the timescale of one
    # observation, and §12 forbids provider-wide conclusions from one sample.
    if grade is Grade.D and repeated_measurements < 3:
        return (
            Grade.C,
            f"Observed position appears inconsistent with the advertised "
            f"region, but only {repeated_measurements} measurement(s) were "
            f"taken. Downgraded from D to C: routing and congestion move on "
            f"this timescale (CHARTER.md §12)." + _LOCATION_BOUND,
        )

    return (
        grade,
        f"Observed network position is {band.replace('_', ' ')} with the "
        f"advertised region over {repeated_measurements} measurement(s)."
        + _LOCATION_BOUND,
    )


# ===========================================================================
# §13.5 Allocation-model transparency
# ===========================================================================


def grade_allocation_transparency(
    *,
    documented_model: str | None,
    measured_model: str,
    confidence: float,
    contradicted: bool = False,
) -> tuple[Grade, str]:
    """Grade §13.5 — new in charter v2, amendment A6.

    The grade that catches the "fractional GPU" problem. A provider who
    documents the model and is corroborated by measurement gets an A; one
    whose documentation is *contradicted* gets a D. Between them sit the two
    cases that are commercially common and currently invisible: documented but
    unverifiable, and undocumented but inferable.
    """
    if contradicted and documented_model:
        return (
            Grade.D,
            f"The provider documents {documented_model!r}; measurement "
            f"indicates {measured_model!r} at confidence {confidence:.2f}. A "
            f"documented claim contradicted by measurement. Pending private "
            f"disclosure and provider response (CHARTER.md §7.5).",
        )

    unclassified = measured_model in (
        "undocumented",
        "shared_unknown",
        "dedicated_unknown",
    )

    if documented_model:
        if unclassified:
            return (
                Grade.B,
                f"The provider documents {documented_model!r}, but "
                f"tenant-visible signals did not separate the candidate models "
                f"(reported {measured_model!r}). Documented, measurement "
                f"ambiguous.",
            )
        return (
            Grade.A,
            f"The provider documents {documented_model!r} and measurement "
            f"agrees ({measured_model!r}, confidence {confidence:.2f}).",
        )

    if unclassified:
        return (
            Grade.U,
            f"The allocation model is undocumented by the provider and was not "
            f"classifiable from inside the instance (reported "
            f"{measured_model!r}). This counts toward the §18 `undocumented` "
            f"rate.",
        )

    return (
        Grade.C,
        f"The allocation model is undocumented by the provider but inferable "
        f"from inside the instance as {measured_model!r} at confidence "
        f"{confidence:.2f}. A customer cannot learn from the invoice what "
        f"isolation they bought.",
    )


# ===========================================================================
# §13.6 Attestation — a field report, deliberately NOT a grade
# ===========================================================================


def attestation_field_report(fields: Mapping[str, object]) -> dict[str, object]:
    """Return §13.6's fields, refusing to reduce them to one value.

    CHARTER.md §13.6 lists separate fields "(not a grade)". The refusal is
    implemented rather than documented: there is no code path here that emits
    a letter, so a caller wanting `attestation: A` has to write that logic
    themselves and be seen doing it.

    The reason is CVE-2026-33697. Evidence can be signed, chain-valid, fresh,
    measurement-matched — and still not bound to the connection carrying your
    traffic. Any single value that averages those together hides exactly the
    property that matters.
    """
    return {
        "note": (
            "CHARTER.md §13.6 reports separate fields, not a grade. Attestation "
            "assurance does not reduce to one value: evidence can be valid and "
            "still not bound to the application channel (CVE-2026-33697)."
        ),
        "fields": dict(fields),
    }


# ===========================================================================
# The card
# ===========================================================================


@dataclass(frozen=True)
class ReportCard:
    """All §13 categories, independently graded. **No composite score.**

    CHARTER.md §13: "Avoid 62/100." A single number invites a league table,
    and a league table built on five categories with different evidence
    strengths is a fiction. There is deliberately no ``total`` property, and
    adding one should be treated as an ethics change rather than a feature.
    """

    memory_hygiene: tuple[Grade, str]
    tenant_exposure: tuple[Grade, str]
    hardware_claim: tuple[Grade, str]
    location_claim: tuple[Grade, str]
    allocation_transparency: tuple[Grade, str]
    attestation: dict[str, object]

    provider_code: str = "provider-a"

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_code": self.provider_code,
            "note": (
                "Independent category grades, no composite score (CHARTER.md "
                "§13). U means unproven, not failing."
            ),
            "memory_lifecycle_hygiene": _category(self.memory_hygiene),
            "tenant_exposure": _category(self.tenant_exposure),
            "hardware_claim_consistency": _category(self.hardware_claim),
            "location_claim_consistency": _category(self.location_claim),
            "allocation_model_transparency": _category(self.allocation_transparency),
            "attestation_assurance": self.attestation,
        }

    @property
    def requires_disclosure_before_publication(self) -> bool:
        """True when any category asserts a provider failure.

        Grade D is the only grade that accuses. CHARTER.md §7.5 requires
        private contact and a remediation window before a D leaves the
        machine, and §7.6 forbids naming a provider until that has happened.
        """
        return any(
            grade is Grade.D
            for grade, _ in (
                self.memory_hygiene,
                self.tenant_exposure,
                self.hardware_claim,
                self.location_claim,
                self.allocation_transparency,
            )
        )


def _category(graded: tuple[Grade, str]) -> dict[str, str]:
    grade, rationale = graded
    return {"grade": grade.value, "basis": rationale}


def build_report_card(
    *,
    provider_code: str,
    memory: MemoryHygieneEvidence,
    exposure_classifications: Mapping[str, int],
    topology_certificates: int,
    topology_stable: bool,
    topology_consistent: bool | None,
    topology_is_evidence: bool,
    location_band: str,
    location_measurements: int,
    documented_allocation_model: str | None,
    measured_allocation_model: str,
    allocation_confidence: float,
    allocation_contradicted: bool,
    attestation_fields: Mapping[str, object],
    neighbour_metadata_visible: bool = False,
) -> ReportCard:
    """Assemble the full card. Every category is graded from its own evidence."""
    return ReportCard(
        provider_code=provider_code,
        memory_hygiene=grade_memory_hygiene(memory),
        tenant_exposure=grade_tenant_exposure(
            exposure_classifications,
            neighbour_metadata_visible=neighbour_metadata_visible,
        ),
        hardware_claim=grade_hardware_claim(
            certificates=topology_certificates,
            fingerprint_stable=topology_stable,
            consistent_with_advertised_class=topology_consistent,
            instrument_is_evidence=topology_is_evidence,
        ),
        location_claim=grade_location_claim(
            location_band, repeated_measurements=location_measurements
        ),
        allocation_transparency=grade_allocation_transparency(
            documented_model=documented_allocation_model,
            measured_model=measured_allocation_model,
            confidence=allocation_confidence,
            contradicted=allocation_contradicted,
        ),
        attestation=attestation_field_report(attestation_fields),
    )
