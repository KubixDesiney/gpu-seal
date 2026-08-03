"""Structured findings from probes that do not read unknown memory.

``AggregateRecord`` is the egress door for §9.2/§9.3/§9.4/§9.12 — statistics
over bytes GPU-SEAL did not write. The inventory, classifier, topology,
location, and attestation families (§9.1, §9.6, §9.7, §9.8, §9.9, §9.10,
§9.11) never touch unknown memory at all, so that record type does not fit
them: there is no buffer, no entropy, no canary.

What they carry instead is *description of the rented environment*, which has
its own disclosure hazard. CHARTER.md §10 lists what may never be published —
account IDs, unnecessary public IPs, stable GPU UUIDs, hostnames,
provider-internal IDs, exact coordinates — and every one of those is exactly
the kind of thing an environment inventory picks up by accident.

So this record gets the same treatment as the memory one: an allowlist
enforced on the way out (:data:`SAFE_OBSERVATION_KEYS`), plus a refusal to
serialise any *value* that looks like an unhashed identifier.

Three fields do the scientific work, and CHARTER.md §12 is the reason all
three are mandatory rather than optional:

``classification``
    the interpretation, drawn from a fixed vocabulary. §9.6 is explicit that
    "not every unavailable interface is a failure" — a restricted counter that
    correctly requires privilege is a ``secure_restriction``, not a finding.

``evidence``
    what was actually observed, separately from what it was taken to mean.
    §12: "separate observation from interpretation."

``limitations``
    what this observation cannot support. An instrument-dependent result
    (§13.3, §13.4) must cite its own bound every time it is reported, and the
    only reliable way to make that happen is to refuse to construct the record
    without it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..safety.errors import EgressViolation
from ..safety.policy import (
    NEVER_PUBLISH_FIELD_FRAGMENTS,
    SAFE_OBSERVATION_KEYS,
)

__all__ = ["ObservationRecord", "summarise_classifications"]

#: Prefix written by :func:`gpu_seal.safety.metadata.stable_hash`. A value
#: carrying it has already been through the hash and is safe to record.
_HASHED_PREFIX = "sha256:"


@dataclass(frozen=True)
class ObservationRecord:
    """One interpreted, publishable observation about the environment."""

    probe_name: str
    probe_version: str

    #: What was observed, as a short stable key (``"visible_device_count"``).
    #: Becomes a column in the cross-provider dataset, so it must not encode
    #: run-specific detail.
    subject: str

    #: Probe family, for grouping in the report card (``"device_exposure"``).
    category: str

    #: One of the vocabularies in :mod:`gpu_seal.safety.policy` —
    #: ``EXPOSURE_CLASSIFICATIONS``, ``ALLOCATION_MODEL_CLASSES``, or
    #: ``CONSISTENCY_BANDS``, depending on ``category``.
    classification: str

    #: What was actually seen. Counts, booleans, and short enumerated strings
    #: only — never an identifier, never free text from the environment.
    value: Optional[Any] = None

    #: Calibrated 0..1. CHARTER.md §9.7: never present inference as
    #: provider-confirmed fact, so a classifier result without a confidence is
    #: not reportable.
    confidence: float = 0.0

    #: Observations supporting the classification, in the researcher's words.
    evidence: List[str] = field(default_factory=list)

    #: What this observation cannot support. Required — see the module
    #: docstring.
    limitations: List[str] = field(default_factory=list)

    #: Set when ``classification`` is ``not_testable``, explaining why. A
    #: ``not_testable`` with no reason is indistinguishable from a probe that
    #: silently failed.
    not_testable_reason: Optional[str] = None

    error_code: Optional[str] = None
    timing_ns: Optional[int] = None

    #: True when this observation, on its own, must block automatic
    #: publication of the bundle it rides in — e.g. a positive self-canary
    #: recovery (CHARTER.md §7.5 requires private disclosure first) or a
    #: reading from a modelled/non-evidence instrument. Mirrors
    #: ``AggregateRecord.sensitive_observation``; read by
    #: ``ResultBundle.has_sensitive_observation``, which is the only place
    #: this field is consumed.
    blocks_publication: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be in [0, 1], got {self.confidence!r}"
            )
        if self.classification == "not_testable" and not self.not_testable_reason:
            raise ValueError(
                f"{self.probe_name}/{self.subject}: a `not_testable` "
                f"classification requires `not_testable_reason`. Without it a "
                f"deliberate non-measurement is indistinguishable from a probe "
                f"that failed silently (CHARTER.md §12 exclusion criteria)."
            )

    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise, refusing anything outside the §10 disclosure policy."""
        payload = asdict(self)

        offending = set(payload) - SAFE_OBSERVATION_KEYS
        if offending:
            raise EgressViolation(
                f"Refusing to emit non-allowlisted observation keys "
                f"{sorted(offending)}. CHARTER.md §7.2 and §10 enumerate what "
                f"may leave a probe; adding a field is an ethics review, not "
                f"just a code change."
            )

        self._refuse_unhashed_identifier()
        return payload

    def _refuse_unhashed_identifier(self) -> None:
        """Block CHARTER.md §10's never-published identifiers at the door.

        The check is on ``subject``, not on ``value``, and that is deliberate:
        the probe names what it measured, so the name is where intent is
        legible. A probe recording ``gpu_uuid`` has to record
        ``gpu_uuid_hash`` instead and pass the value through
        :func:`gpu_seal.safety.metadata.stable_hash` — at which point the
        value carries the digest prefix and this passes.

        Checking values by pattern would mean pattern-matching over
        environment strings, which is the thing §7.2 forbids doing to memory
        and a bad habit to build anywhere.
        """
        lowered = self.subject.lower()
        for fragment in NEVER_PUBLISH_FIELD_FRAGMENTS:
            if fragment not in lowered:
                continue
            if lowered.endswith("_hash") and isinstance(self.value, str):
                if self.value.startswith(_HASHED_PREFIX):
                    return
            raise EgressViolation(
                f"Refusing to emit observation {self.subject!r}: it names a "
                f"CHARTER.md §10 never-published identifier ({fragment!r}). "
                f"Record it as {fragment}_hash, with the value produced by "
                f"gpu_seal.safety.metadata.stable_hash()."
            )


def summarise_classifications(
    records: Sequence[ObservationRecord],
) -> Dict[str, int]:
    """Count observations by classification. Input to the §13.2 grade.

    Interpretation-free on purpose: turning these counts into a letter is the
    report card's job, and it applies gates this function cannot evaluate.
    """
    counts: Dict[str, int] = {}
    for record in records:
        counts[record.classification] = counts.get(record.classification, 0) + 1
    return counts
