"""Signed result bundles — CHARTER.md §10.

A bundle is the unit of evidence. It carries the measurement, everything
needed to reproduce it, an explicit safety declaration, and an Ed25519
signature over a canonicalised payload.

Three invariants are enforced here rather than left to reviewer discipline:

1. **Safety declaration is structural, not documentary.** ``safety`` is a
   required object with required booleans. A bundle cannot be built without
   asserting, in machine-readable form, that no raw unknown memory was
   retained or rendered and that only owned canaries were searched for.

2. **Publication is gated, not defaulted.** ``automatic_publication_allowed``
   starts false and can only become true via
   :meth:`ResultBundle.clear_for_publication`, which refuses if any probe in
   the bundle carries a ``sensitive_observation`` flag (§7.3, §16 test 7).

3. **An incomplete run can never look completed.** A caller that stops a run
   early because a wall-clock budget expired sets ``run_incomplete``, which
   ``clear_for_publication`` refuses unconditionally and which
   ``automatic_publication_allowed`` folds into its own computation directly
   -- a truncated run cannot pass the gate no matter how it got here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..safety.aggregation import (
    AggregateRecord,
    CanaryOnlyRecord,
    RedactedStopRecord,
)
from ..safety.errors import EgressViolation
from .observation import ObservationRecord
from ..safety.policy import (
    PUBLISHABLE_CONTAINER_PROFILES,
)
from .signing import (
    SIGNATURE_ALGORITHM,
    Signer,
    VerifyKey,
    canonical_bytes,
    sign_payload,
    verify_payload,
)

__all__ = ["ResultBundle", "ToolProvenance", "canonical_payload_hash"]

SCHEMA_VERSION = "gpu-seal-result-v1"


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


_HEX_DIGITS = frozenset("0123456789abcdef")


def _probe_metadata(
    probe: AggregateRecord | CanaryOnlyRecord | RedactedStopRecord,
) -> dict[str, str]:
    """Return only the non-sensitive operational metadata for either wire type."""
    if isinstance(probe, (RedactedStopRecord, CanaryOnlyRecord)):
        return probe.operational_metadata
    return probe.driver_metadata or {}


def _is_well_formed_sha256_digest(value: str | None) -> bool:
    """Same shape as the schema's `payload_hash` pattern (`^sha256:[0-9a-f]{64}$`),
    checked with plain string operations rather than `re` — the probe-safety
    static analysis forbids importing `re` anywhere under `probe/`, this
    module included."""
    if not isinstance(value, str):
        return False
    prefix = "sha256:"
    if not value.startswith(prefix):
        return False
    hex_part = value[len(prefix) :]
    return len(hex_part) == 64 and all(c in _HEX_DIGITS for c in hex_part)


@dataclass(frozen=True)
class ToolProvenance:
    """Everything needed to rebuild the exact tool that produced a result."""

    version: str
    commit: str
    container_digest: str | None = None
    kernel_bundle_hash: str | None = None
    cuda_runtime_version: str | None = None
    cuda_driver_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "commit": self.commit,
            "container_digest": self.container_digest,
            "kernel_bundle_hash": self.kernel_bundle_hash,
            "cuda_runtime_version": self.cuda_runtime_version,
            "cuda_driver_version": self.cuda_driver_version,
        }


@dataclass
class ResultBundle:
    """One signed measurement bundle."""

    experiment_id: str
    run_id: str
    provider_code: str
    region_claim: str
    product_claim: str
    tool: ToolProvenance

    probes: list[AggregateRecord | CanaryOnlyRecord | RedactedStopRecord] = field(
        default_factory=list
    )
    environment: dict[str, Any] = field(default_factory=dict)
    allocation_model: dict[str, Any] = field(default_factory=dict)

    #: Findings from probes that do not read unknown memory — §9.1, §9.6,
    #: §9.7, §9.8, §9.9, §9.10, §9.11. Kept in a separate list from ``probes``
    #: rather than coerced into ``AggregateRecord``, because the two have
    #: different disclosure hazards and therefore different allowlists: one
    #: guards statistics over memory we did not write, the other guards
    #: description of the rented environment (CHARTER.md §10).
    observations: list[ObservationRecord] = field(default_factory=list)

    #: The §13 report card, when one has been built for this run.
    report_card: dict[str, Any] = field(default_factory=dict)

    #: True when a caller-supplied wall-clock run budget (``--max-runtime-s``
    #: on the local-runner scripts) expired before every planned cycle
    #: completed. Set by the caller, never inferred here, because only the
    #: caller knows whether it stopped a run early. A budget-cut run is not a
    #: measurement, successful or otherwise, and must never be mistaken for
    #: -- or allowed to pass the publication gate as -- a completed one; see
    #: ``clear_for_publication`` and the ``safety.automatic_publication_allowed``
    #: computation in ``payload``.
    run_incomplete: bool = False
    #: Human-readable reason the run was cut short, e.g. which budget and
    #: which stage. ``None`` for a completed run.
    incomplete_reason: str | None = None

    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    _publication_cleared: bool = field(default=False, repr=False)

    # ------------------------------------------------------------------

    @property
    def has_sensitive_observation(self) -> bool:
        """True if anything in this bundle requires manual disclosure review
        before publication (CHARTER.md §7.3, §7.5) — checked across all three
        places that can carry such a finding, not just memory probes:

        1. an ``AggregateRecord`` with its own automatic safety stop fired;
        2. an ``ObservationRecord`` flagged ``blocks_publication`` (e.g. a
           positive self-canary recovery, or a modelled/non-evidence
           instrument reading — neither of these touches unknown memory, so
           neither sets a probe's ``sensitive_observation``, but both are
           exactly the kind of finding §7.5 requires disclosure for first);
        3. a report-card category graded D — the only grade that asserts a
           provider failure (see ``ReportCard.requires_disclosure_before_publication``).
        """
        if any(p.sensitive_observation for p in self.probes):
            return True
        if any(o.blocks_publication for o in self.observations):
            return True
        if any(
            isinstance(category, dict) and category.get("grade") == "D"
            for category in self.report_card.values()
        ):
            return True
        return False

    @property
    def simulated_probes(self) -> list[str]:
        """Distinct probe names whose measurements came from a non-real backend."""
        return sorted(
            {
                p.probe_name
                for p in self.probes
                if _probe_metadata(p).get("backend_is_real") == "false"
            }
        )

    @property
    def unpinned_container_probes(self) -> list[str]:
        """Distinct probe names not measured inside a reproducible container.

        An **allowlist** (:data:`PUBLISHABLE_CONTAINER_PROFILES`), not a check
        for the known-bad ``dev-unpinned`` string. The earlier version tested
        for that one value, which meant a run outside any container at all —
        ``container_profile: "unspecified"``, which is what every local
        ``run_phase1.py`` run on a bare workstation produces — sailed through
        the guard while being just as unreproducible as the dev image the
        guard was written to catch.

        The policy call behind the allowlist: CHARTER.md §10 requires a
        container digest among the reproducibility fields, and a run that
        cannot name its image cannot supply one. Local control runs still
        happen and are still signed; they are simply not publishable evidence,
        which is the accurate description of them.
        """
        return sorted(
            {
                p.probe_name
                for p in self.probes
                if _probe_metadata(p).get("container_profile")
                not in PUBLISHABLE_CONTAINER_PROFILES
            }
        )

    def clear_for_publication(self) -> None:
        """Permit automatic publication. Refuses on any of five grounds.

        0. **Incomplete run** — a caller-supplied wall-clock budget expired
           before the run finished (``run_incomplete``). An incomplete run
           measured nothing to completion and must never be published as if
           it had.
        1. **Sensitive observation** (CHARTER.md §7.3 / §16 test 7) — the
           automatic safety stop fired; manual disclosure review is required.
        2. **Simulated backend** — the measurement came from the host-side
           allocator model, not from silicon. Publishing simulated residue as
           a finding would be fabrication, so the guard is mechanical rather
           than a matter of remembering.
        3. **Not a reproducible container** (CHARTER.md §10, §14) — the dev
           image resolves dependencies at build time, and a bare-metal run
           has no image at all. Neither can supply the container digest §10
           requires, so neither can function as evidence.
        4. **"pinned" claimed without a matching digest** — `container_profile`
           is a plain string in probe-supplied `driver_metadata`; nothing
           stops a producer from writing `"pinned"` there without the run
           ever having happened inside the audited image. `tool.container_digest`
           is what actually binds the claim to a rebuildable image (CHARTER.md
           §10, §14), so a "pinned" claim with no matching digest is treated
           the same as an unpinned one.
        """
        if self.run_incomplete:
            reason = self.incomplete_reason or "reason not recorded"
            raise EgressViolation(
                "Refusing to clear this bundle for publication: the run "
                f"stopped before completion ({reason}). An incomplete run is "
                "not a measurement, successful or otherwise, and must never "
                "be published as one."
            )
        if self.has_sensitive_observation:
            raise EgressViolation(
                "Refusing to clear this bundle for publication: it contains a "
                "probe or observation flagged `sensitive_observation` / "
                "`blocks_publication`, or a report-card category graded D. "
                "CHARTER.md §7.3 requires manual disclosure review, and §7.5 "
                "requires provider coordination, before any of this leaves "
                "the evidence store."
            )
        simulated = self.simulated_probes
        if simulated:
            raise EgressViolation(
                f"Refusing to clear this bundle for publication: probes "
                f"{simulated} ran against the simulated backend, which models "
                f"a non-zeroing allocator on the host and measures nothing "
                f"about real hardware. Simulated results are for testing probe "
                f"logic only."
            )
        unpinned = self.unpinned_container_probes
        if unpinned:
            profiles = sorted(
                {
                    str(_probe_metadata(p).get("container_profile"))
                    for p in self.probes
                    if p.probe_name in set(unpinned)
                }
            )
            raise EgressViolation(
                f"Refusing to clear this bundle for publication: probes "
                f"{unpinned} ran under container profile(s) {profiles}, and "
                f"only {sorted(PUBLISHABLE_CONTAINER_PROFILES)} is "
                f"reproducible. A `dev-unpinned` run resolves dependencies at "
                f"build time; an `unspecified` run had no container at all and "
                f"cannot supply the container digest CHARTER.md §10 requires. "
                f"Rebuild with infrastructure/containers/Dockerfile "
                f"(hash-pinned) before producing publishable evidence "
                f"(CHARTER.md §10, §14)."
            )
        if self.probes and not _is_well_formed_sha256_digest(self.tool.container_digest):
            raise EgressViolation(
                f"Refusing to clear this bundle for publication: every probe "
                f"claims container_profile 'pinned', but tool.container_digest "
                f"is {self.tool.container_digest!r} rather than a well-formed "
                f"'sha256:<64 hex>' digest. 'pinned' is a self-reported string "
                f"in driver_metadata; the digest is what actually binds the "
                f"claim to a rebuildable image (CHARTER.md §10, §14). Pass the "
                f"digest `docker image inspect --format='{{{{.Id}}}}'` reports "
                f"for the image this run executed in."
            )
        self._publication_cleared = True

    # ------------------------------------------------------------------

    def payload(self) -> dict[str, Any]:
        """The signable, publishable body of the bundle."""
        for probe in self.probes:
            if isinstance(probe, AggregateRecord) and probe.sensitive_observation:
                raise EgressViolation(
                    "A sensitive memory observation must use RedactedStopRecord; "
                    "reconstructive aggregate fields cannot survive a stop."
                )
            if not isinstance(
                probe, (AggregateRecord, CanaryOnlyRecord, RedactedStopRecord)
            ):
                raise EgressViolation(
                    "Unknown memory probe record type refused by the egress gate."
                )
        probe_payloads = [p.to_dict() for p in self.probes]

        raw_retained = any(p.unknown_raw_retained for p in self.probes)
        rendered = any(p.unknown_memory_rendered for p in self.probes)
        canary_only = (
            all(p.canary_only_search for p in self.probes) if self.probes else True
        )

        # Structural assertion, not a comment. If a probe ever sets one of
        # these, the bundle records it and the reader can see it.
        if raw_retained or rendered:
            raise EgressViolation(
                "A probe in this bundle declared that raw unknown memory was "
                "retained or rendered. That is a bug in the probe, not a "
                "finding. Refusing to emit the bundle (CHARTER.md §7.2)."
            )

        return {
            "schema_version": SCHEMA_VERSION,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "timestamp_utc": self.timestamp_utc,
            "provider_code": self.provider_code,
            "region_claim": self.region_claim,
            "product_claim": self.product_claim,
            "tool": self.tool.to_dict(),
            "environment": self.environment,
            "allocation_model": self.allocation_model,
            "probes": probe_payloads,
            # to_dict() enforces the §10 never-published check on each record,
            # so a bundle carrying an unhashed identifier fails to serialise
            # rather than serialising and leaking.
            "observations": [o.to_dict() for o in self.observations],
            "report_card": self.report_card,
            "safety": {
                "raw_unknown_memory_retained": raw_retained,
                "unknown_memory_rendered": rendered,
                "canary_only_search": canary_only,
                "sensitive_observation": self.has_sensitive_observation,
                "run_incomplete": self.run_incomplete,
                "incomplete_reason": self.incomplete_reason,
                # Structural, not just enforced by clear_for_publication():
                # even if a caller sets `_publication_cleared` some other
                # way, an incomplete or sensitive run can never compute True
                # here.
                "automatic_publication_allowed": self._publication_cleared
                and not self.has_sensitive_observation
                and not self.run_incomplete,
            },
        }

    def sign(self, key: Signer) -> dict[str, Any]:
        """Produce the complete signed bundle, ready to write to the store."""
        body = self.payload()
        return {
            **body,
            "integrity": {
                "payload_hash": canonical_payload_hash(body),
                "signature_algorithm": SIGNATURE_ALGORITHM,
                "signature": sign_payload(body, key),
                "public_key": key.verify_key.hex,
                "public_key_fingerprint": key.verify_key.fingerprint,
            },
        }

    # ------------------------------------------------------------------

    @staticmethod
    def verify(bundle: dict[str, Any], key: VerifyKey | None = None) -> bool:
        """Verify a signed bundle's hash and signature.

        If ``key`` is omitted, the embedded public key is used. That confirms
        internal consistency only — a third party checking provenance must
        supply the key they obtained out of band.
        """
        integrity = bundle.get("integrity")
        if not isinstance(integrity, dict):
            return False

        body = {k: v for k, v in bundle.items() if k != "integrity"}

        if canonical_payload_hash(body) != integrity.get("payload_hash"):
            return False
        if integrity.get("signature_algorithm") != SIGNATURE_ALGORITHM:
            return False

        verify_key = key
        if verify_key is None:
            embedded = integrity.get("public_key")
            if not isinstance(embedded, str):
                return False
            try:
                verify_key = VerifyKey.from_hex(embedded)
            except ValueError:
                return False

        signature = integrity.get("signature")
        if not isinstance(signature, str):
            return False
        return verify_payload(body, signature, verify_key)
