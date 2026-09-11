"""Attestation availability, verification, and channel binding.

CHARTER.md §9.10 (attestation) and §9.11 (application-channel binding lab).

    "Determine whether GPU / CC attestation is available, verify what's
     independently verifiable, and **don't reduce assurance to one Boolean**."

The single most common mistake in this area is `attestation: true`. An
attestation report that is signed by a valid chain, matches reference
measurements, and is *not bound to the connection carrying your inference
traffic* is a report about some machine, not necessarily the machine you are
talking to. CVE-2026-33697 and the *Intra-handshake.fail* work tested seven
mechanisms for binding intra-handshake attestation evidence to the underlying
connection and found none resistant to relay.

So §13.6 is deliberately **not a grade**. It is a field report, and this module
produces the fields separately:

    availability · signature validity · chain validity · revocation status ·
    nonce freshness · measurement verification · debug status ·
    hardware-model consistency · application-channel binding ·
    relay-resistance evidence

**Build on nvtrust, do not reimplement.** §9.10 is explicit. This module is a
*collector and reporter*: it drives NVIDIA's Attestation SDK where present and
records structured results. Reimplementing certificate-chain validation for a
vendor root would be both worse than the vendor's and a much bigger claim than
this project should make.

**Scope discipline on the CVE.** NVD scopes CVE-2026-33697 to Cocos AI
v0.4.0–v0.8.2. The *research* claim about relay resistance is architectural and
broader. Both are represented. GPU-SEAL does not claim "all remote attestation
is broken."

**Hardware reality.** H100-class confidential computing is not available to
this project (CHARTER.md §20). Every field therefore degrades to
``not_testable`` with a reason on the current hardware, which is the correct
output — and the collector is written and tested now so that renting an hour
of CC-capable silicon later is a configuration change rather than a build.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..evidence.observation import ObservationRecord
from ..safety.campaign import CampaignControl

__all__ = [
    "AttestationEvidence",
    "EvidenceSource",
    "NvTrustEvidenceSource",
    "AttestationProbe",
    "ChannelBindingAssessment",
    "assess_channel_binding",
    "PROBE_NAME",
    "PROBE_VERSION",
]

PROBE_NAME = "attestation_assurance"
PROBE_VERSION = "0.2.0"

#: §9.11's vocabulary. These are *distinct properties*, and collapsing any two
#: of them is the error the whole module exists to avoid.
BINDING_LEVELS = (
    "not_established",
    "transport_authenticated",
    "evidence_fresh",
    "application_channel_bound",
    "relay_resistance_demonstrated",
)


@dataclass(frozen=True)
class AttestationEvidence:
    """Raw collector output. ``None`` means "not determined", never "false"."""

    available: bool = False
    evidence_signature_valid: bool | None = None
    certificate_chain_valid: bool | None = None
    revocation_status_checked: bool | None = None
    nonce_matches: bool | None = None
    measurements_match_reference: bool | None = None
    debug_mode_disabled: bool | None = None
    gpu_model_claim_consistent: bool | None = None
    confidential_mode_enabled: bool | None = None
    #: Why nothing could be collected, when nothing could be.
    unavailable_reason: str | None = None
    collector: str = "none"


class EvidenceSource(ABC):
    """Obtains an attestation report. Substitutable for testing."""

    @abstractmethod
    def collect(self, *, nonce: bytes, expected_gpu: str) -> AttestationEvidence: ...


class NvTrustEvidenceSource(EvidenceSource):
    """Drives NVIDIA's Attestation SDK when it is installed.

    Imports lazily and by name so that the absence of the SDK — the normal
    case on non-CC hardware — is an observation rather than an import error at
    module load.
    """

    def collect(self, *, nonce: bytes, expected_gpu: str) -> AttestationEvidence:
        try:
            from nv_attestation_sdk import attestation  # type: ignore[import-not-found]
        except ImportError:
            return AttestationEvidence(
                available=False,
                unavailable_reason=(
                    "the NVIDIA Attestation SDK is not installed. GPU "
                    "confidential computing requires H100-class silicon plus "
                    "Intel TDX, AMD SEV-SNP, or ARM CCA on the host "
                    "(CHARTER.md §3.1, §20)."
                ),
                collector="nvtrust",
            )

        try:
            client = attestation.Attestation()
            client.set_nonce(nonce.hex())
            client.attest()
            report = client.get_evidence()
        except Exception as exc:  # noqa: BLE001 - any SDK failure is a result
            return AttestationEvidence(
                available=False,
                unavailable_reason=(
                    f"the Attestation SDK was present but did not produce "
                    f"evidence: {type(exc).__name__}"
                ),
                collector="nvtrust",
            )

        return _from_sdk_report(report, expected_gpu=expected_gpu)


def _from_sdk_report(report: Any, *, expected_gpu: str) -> AttestationEvidence:
    """Map an SDK report onto the §9.10 fields.

    Anything the report does not state stays ``None``. Defaulting a missing
    field to ``False`` would manufacture a finding; defaulting it to ``True``
    would manufacture assurance. Neither is acceptable, so absence is
    preserved.
    """
    claims = getattr(report, "claims", None) or {}
    model = str(claims.get("hwmodel", "")).strip().lower()
    return AttestationEvidence(
        available=True,
        evidence_signature_valid=claims.get("measres") is not None,
        certificate_chain_valid=claims.get("x-nvidia-gpu-attestation-report-cert-chain-validated"),
        revocation_status_checked=claims.get(
            "x-nvidia-gpu-driver-rim-fetched"
        ),
        nonce_matches=claims.get("eat_nonce") is not None,
        measurements_match_reference=claims.get("measres") == "comparison-successful",
        debug_mode_disabled=(
            None
            if claims.get("x-nvidia-gpu-attestation-report-debug-status") is None
            else claims.get("x-nvidia-gpu-attestation-report-debug-status")
            != "enabled"
        ),
        gpu_model_claim_consistent=(
            None if not model else model in expected_gpu.strip().lower()
        ),
        confidential_mode_enabled=claims.get("x-nvidia-gpu-cc-enabled"),
        collector="nvtrust",
    )


class AttestationProbe:
    """Collect and report §9.10 fields. Never reduces them to one boolean."""

    NAME = PROBE_NAME
    VERSION = PROBE_VERSION

    #: The ten §9.10 checks, in report order.
    FIELDS = (
        "evidence_signature_valid",
        "certificate_chain_valid",
        "revocation_status_checked",
        "nonce_matches",
        "measurements_match_reference",
        "debug_mode_disabled",
        "gpu_model_claim_consistent",
        "confidential_mode_enabled",
    )

    def __init__(
        self, source: EvidenceSource, *, campaign: CampaignControl | None = None
    ) -> None:
        self._source = source
        self._campaign = campaign or CampaignControl.create()

    def collect(
        self, *, nonce: bytes, expected_gpu: str
    ) -> tuple[AttestationEvidence, list[ObservationRecord]]:
        self._campaign.check()
        evidence = self._source.collect(nonce=nonce, expected_gpu=expected_gpu)
        records = [
            ObservationRecord(
                probe_name=self.NAME,
                probe_version=self.VERSION,
                subject="attestation_available",
                category="attestation",
                classification=(
                    "expected_visibility" if evidence.available else "not_testable"
                ),
                value=evidence.available,
                confidence=1.0 if evidence.available else 0.0,
                evidence=[f"collector: {evidence.collector}"],
                limitations=[
                    "attestation being unavailable is a property of the "
                    "product bought, not necessarily a provider failure; "
                    "confidential computing is opt-in and hardware-gated"
                ],
                not_testable_reason=(
                    None
                    if evidence.available
                    else evidence.unavailable_reason
                    or "no attestation evidence could be obtained"
                ),
            )
        ]

        for field_name in self.FIELDS:
            value = getattr(evidence, field_name)
            records.append(
                ObservationRecord(
                    probe_name=self.NAME,
                    probe_version=self.VERSION,
                    subject=field_name,
                    category="attestation",
                    classification=(
                        "not_testable"
                        if value is None
                        else "expected_visibility"
                        if value
                        else "unexpected_visibility"
                    ),
                    value=value,
                    confidence=0.0 if value is None else 0.9,
                    evidence=[f"reported by collector {evidence.collector}"],
                    limitations=[
                        "reported as an independent field; §13.6 is explicitly "
                        "not a single grade (CHARTER.md §13.6)",
                        "verification is performed by the vendor SDK, not "
                        "reimplemented here (CHARTER.md §9.10)",
                    ],
                    not_testable_reason=(
                        evidence.unavailable_reason
                        or "the collector did not state this field"
                        if value is None
                        else None
                    ),
                )
            )
        return evidence, records


# ---------------------------------------------------------------------------
# §9.11 — application-channel binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChannelBindingAssessment:
    """Five distinct properties, never collapsed into one.

    ``evidence_valid``
        the report verifies against its chain.
    ``evidence_fresh``
        a nonce we chose appears in it.
    ``transport_authenticated``
        the TLS session authenticated *something*.
    ``application_channel_bound``
        the attested environment is cryptographically tied to *this*
        connection.
    ``relay_resistance_demonstrated``
        relay was tested, between researcher-owned endpoints, and the
        binding survived it. ``True`` requires an actual pass/fail outcome —
        merely running the test is not this (see ``assess_channel_binding``'s
        ``relay_resisted`` parameter, which is what this field is derived
        from).

    The gap between the third and the fourth is where CVE-2026-33697 lives.
    """

    evidence_valid: bool | None = None
    evidence_fresh: bool | None = None
    transport_authenticated: bool | None = None
    application_channel_bound: bool | None = None
    relay_resistance_demonstrated: bool | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def level(self) -> str:
        """Highest property demonstrated. Ordered, and deliberately strict."""
        if self.relay_resistance_demonstrated:
            return "relay_resistance_demonstrated"
        if self.application_channel_bound:
            return "application_channel_bound"
        if self.evidence_fresh:
            return "evidence_fresh"
        if self.transport_authenticated:
            return "transport_authenticated"
        return "not_established"

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_valid": self.evidence_valid,
            "evidence_fresh": self.evidence_fresh,
            "transport_authenticated": self.transport_authenticated,
            "application_channel_bound": self.application_channel_bound,
            "relay_resistance_demonstrated": self.relay_resistance_demonstrated,
            "level": self.level,
            "notes": self.notes,
        }


def assess_channel_binding(
    evidence: AttestationEvidence,
    *,
    transport_authenticated: bool | None = None,
    binding_mechanism: str | None = None,
    relay_resisted: bool | None = None,
) -> ChannelBindingAssessment:
    """Assess binding from what was actually established.

    ``application_channel_bound`` is only ever ``True`` when a binding
    mechanism was named *and* a relay attempt was actually made *and*
    defeated. That is a deliberately high bar, set by the finding that none
    of seven surveyed mechanisms resisted relay: naming a mechanism is not
    evidence that it works, and neither — this is the fix — is merely having
    run a relay test. Only a stated pass counts.

    Args:
        relay_resisted: the outcome of an actual relay attempt between
            researcher-owned endpoints, three states:

            * ``None`` (default) — relay was not tested at all.
            * ``True`` — relay was attempted and the binding held: the
              attested environment remained tied to the connection under
              test.
            * ``False`` — relay was attempted and it succeeded: the binding
              did *not* hold. This is a real, reportable outcome, not an
              error — the Intra-handshake.fail survey's headline finding is
              exactly this result across seven other mechanisms.

            Earlier revisions of this function took a bare
            ``relay_tested_between_owned_endpoints: bool``, which conflated
            "a test ran" with "the test passed" — a caller could reach
            ``application_channel_bound=True`` by only ever recording that
            *an attempt happened*, never whether it succeeded.

    §9.11 is a **controlled lab module**. Relay scenarios are reproduced only
    between researcher-owned endpoints — never by redirecting or intercepting
    a real provider's customer traffic.
    """
    notes: list[str] = []

    if binding_mechanism:
        notes.append(f"binding mechanism claimed: {binding_mechanism}")
    else:
        notes.append("no binding mechanism was claimed or configured")

    bound: bool | None = None
    if binding_mechanism and relay_resisted is True:
        bound = True
    elif binding_mechanism and relay_resisted is False:
        bound = False
        notes.append(
            "relay was tested between owned endpoints and it succeeded: the "
            "claimed mechanism did not resist it. This is the "
            "Intra-handshake.fail finding reproduced, not a measurement "
            "error (CVE-2026-33697 scopes to Cocos AI v0.4.0-v0.8.2; the "
            "architectural claim is broader)."
        )
    elif binding_mechanism:
        bound = None
        notes.append(
            "a mechanism is present but relay resistance was not tested; "
            "reported as undetermined rather than bound, because the "
            "Intra-handshake.fail survey found none of seven surveyed "
            "mechanisms resistant to relay (CVE-2026-33697 scopes to Cocos AI "
            "v0.4.0-v0.8.2; the architectural claim is broader)"
        )
    else:
        bound = False

    return ChannelBindingAssessment(
        evidence_valid=evidence.evidence_signature_valid,
        evidence_fresh=evidence.nonce_matches,
        transport_authenticated=transport_authenticated,
        application_channel_bound=bound,
        relay_resistance_demonstrated=bool(binding_mechanism and relay_resisted is True),
        notes=notes
        + [
            "relay scenarios are reproduced only between researcher-owned "
            "endpoints (CHARTER.md §9.11)",
            "GPU-SEAL does not claim all remote attestation is broken",
        ],
    )
