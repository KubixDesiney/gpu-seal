"""Provider policy matrix — CHARTER.md §7.4, §16 test 13.

    "Some providers prohibit security benchmarking without permission —
     resolve this per provider before probing."

This module is the gate that makes that sentence enforceable. A provider is
not probeable because someone read its terms and remembers being satisfied; it
is probeable because a reviewed record exists in
``docs/provider-policy-review/``, and the scheduler refuses to run against a
provider that has none.

Four classifications, from §7.4:

``full-probe-ok``
    the provider publishes a research or security-testing policy that covers
    what GPU-SEAL does on infrastructure the researcher rents.
``self-canary-only``
    benchmarking is restricted, but experiments that only ever touch the
    researcher's own marker data are within terms. §9.5 and §9.12 remain
    runnable; §9.3's provider-facing interpretation does not.
``needs-written-permission``
    the policy is unclear or requires prior authorisation. Nothing runs until
    a permission record is attached.
``prohibited``
    testing is forbidden. Nothing runs, ever, and
    :class:`ProviderProhibited` is raised rather than returned so it cannot be
    ignored by a caller that forgot to check a boolean.

**Empty by default, and that is the safe state.** No provider is compiled in.
The CI gate in ``.github/workflows/safety.yml`` refuses to lift the Phase 0
no-named-provider rule while the review directory is empty or incomplete.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..safety.errors import PolicyViolation
from ..safety.policy import PROVIDER_POLICY_CLASSES, SELF_CANARY_ONLY_SAFE_PROBES

__all__ = [
    "ProviderPolicy",
    "ProviderPolicyMatrix",
    "ProviderProhibited",
    "ProviderNotReviewed",
    "load_policy_matrix",
    "DEFAULT_MATRIX_DIRECTORY",
]

DEFAULT_MATRIX_DIRECTORY = Path("docs/provider-policy-review")

#: A review older than this is stale. Provider terms change, and a policy
#: classification from two years ago is a guess wearing a citation.
REVIEW_VALIDITY_DAYS = 365


class ProviderProhibited(PolicyViolation):
    """Testing this provider is forbidden by its own terms.

    A ``PolicyViolation``, so a broad ``except Exception`` in orchestration
    code cannot swallow it.
    """


class ProviderNotReviewed(PolicyViolation):
    """No reviewed policy record exists for this provider yet."""


@dataclass(frozen=True)
class ProviderPolicy:
    """One reviewed provider record."""

    #: Pseudonymous code (``provider-a``). CHARTER.md §7.6 forbids real names
    #: in results until methodology is validated and disclosure has run.
    provider_code: str
    classification: str
    #: Where the reviewer read the terms. A classification without a source is
    #: an opinion.
    policy_sources: list[str]
    reviewed_on: date
    reviewed_by: str
    #: Version or date-stamp of the terms as read, recorded in study metadata
    #: per §7.4.
    policy_version: str
    #: Reference to written permission, where the class requires it.
    permission_reference: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.classification not in PROVIDER_POLICY_CLASSES:
            raise ValueError(
                f"{self.classification!r} is not a CHARTER.md §7.4 "
                f"classification; expected one of "
                f"{sorted(PROVIDER_POLICY_CLASSES)}"
            )
        if not self.policy_sources:
            raise ValueError(
                f"{self.provider_code}: a policy classification requires at "
                f"least one source. An unsourced classification is an opinion "
                f"(CHARTER.md §7.4)."
            )
        if (
            self.classification == "needs-written-permission"
            and not self.permission_reference
        ):
            # Not an error at load time — the record is legitimately in this
            # state while permission is being sought. It is an error at *run*
            # time, and `permits` is where that is enforced.
            pass

    def is_stale(self, *, today: date | None = None) -> bool:
        reference = today or date.today()
        return (reference - self.reviewed_on).days > REVIEW_VALIDITY_DAYS

    def permits(self, probe_name: str, *, today: date | None = None) -> tuple[bool, str]:
        """Whether this probe may run against this provider, and why."""
        if self.classification == "prohibited":
            return False, (
                f"{self.provider_code} prohibits security benchmarking. No "
                f"probe runs (CHARTER.md §7.4)."
            )

        if self.is_stale(today=today):
            return False, (
                f"the policy review for {self.provider_code} was performed on "
                f"{self.reviewed_on.isoformat()} and is older than "
                f"{REVIEW_VALIDITY_DAYS} days. Provider terms change; re-read "
                f"them before probing."
            )

        if self.classification == "needs-written-permission":
            if not self.permission_reference:
                return False, (
                    f"{self.provider_code}'s policy is unclear or requires "
                    f"prior authorisation, and no written permission is on "
                    f"record (CHARTER.md §7.4)."
                )
            return True, (
                f"written permission on record: {self.permission_reference}"
            )

        if self.classification == "self-canary-only":
            if probe_name in SELF_CANARY_ONLY_SAFE_PROBES:
                return True, (
                    f"{probe_name} only ever touches the researcher's own "
                    f"marker data, which is within {self.provider_code}'s "
                    f"restricted terms"
                )
            return False, (
                f"{self.provider_code} permits only self-canary experiments; "
                f"{probe_name} is not on the self-canary-safe list "
                f"({sorted(SELF_CANARY_ONLY_SAFE_PROBES)})."
            )

        return True, f"{self.provider_code} is classified full-probe-ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_code": self.provider_code,
            "classification": self.classification,
            "policy_sources": self.policy_sources,
            "reviewed_on": self.reviewed_on.isoformat(),
            "reviewed_by": self.reviewed_by,
            "policy_version": self.policy_version,
            "permission_reference": self.permission_reference,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ProviderPolicy:
        return cls(
            provider_code=raw["provider_code"],
            classification=raw["classification"],
            policy_sources=list(raw["policy_sources"]),
            reviewed_on=date.fromisoformat(raw["reviewed_on"]),
            reviewed_by=raw["reviewed_by"],
            policy_version=raw["policy_version"],
            permission_reference=raw.get("permission_reference"),
            notes=raw.get("notes", ""),
        )


@dataclass(frozen=True)
class ProviderPolicyMatrix:
    """Every reviewed provider. Empty is the safe default state."""

    policies: dict[str, ProviderPolicy]

    def __len__(self) -> int:
        return len(self.policies)

    @property
    def provider_codes(self) -> list[str]:
        return sorted(self.policies)

    def require(self, provider_code: str) -> ProviderPolicy:
        try:
            return self.policies[provider_code]
        except KeyError:
            raise ProviderNotReviewed(
                f"No reviewed policy record exists for {provider_code!r}. "
                f"CHARTER.md §7.4 requires reviewing the provider's acceptable "
                f"use policy, security-testing policy, and disclosure "
                f"programme before any probe runs against it. Add a record to "
                f"{DEFAULT_MATRIX_DIRECTORY}/ first. Reviewed providers: "
                f"{self.provider_codes or 'none'}."
            ) from None

    def check(
        self, provider_code: str, probe_name: str, *, today: date | None = None
    ) -> str:
        """Raise unless ``probe_name`` may run against ``provider_code``.

        Returns the reason it is permitted, which the scheduler records in the
        run's metadata — §7.4 requires the policy version and permission to be
        recorded in study metadata, not merely checked.
        """
        policy = self.require(provider_code)
        permitted, reason = policy.permits(probe_name, today=today)
        if not permitted:
            if policy.classification == "prohibited":
                raise ProviderProhibited(reason)
            raise PolicyViolation(reason)
        return reason


def load_policy_matrix(
    directory: Path | str = DEFAULT_MATRIX_DIRECTORY,
) -> ProviderPolicyMatrix:
    """Load every ``*.json`` policy record in ``directory``.

    A missing or empty directory yields an empty matrix rather than an error.
    That is the Phase 0 state, and an empty matrix already refuses everything —
    failing to load is not needed to make it safe.
    """
    path = Path(directory)
    policies: dict[str, ProviderPolicy] = {}
    if not path.is_dir():
        return ProviderPolicyMatrix(policies={})

    for record_path in sorted(path.glob("*.json")):
        raw = json.loads(record_path.read_text(encoding="utf-8"))

        # Template files describe the format rather than a provider.
        if raw.get("template"):
            continue

        # A slot that exists but has not been reviewed is not a provider that
        # may be probed. Skipping it here — rather than loading it with a
        # cautious classification — means the matrix stays *empty* until a
        # human has actually read something, and an empty matrix refuses
        # everything. The alternative, loading unreviewed records as
        # `needs-written-permission`, looks identical at the gate but makes
        # `len(matrix)` non-zero, which is what the Phase 0 CI job keys off.
        if raw.get("status") != "reviewed":
            continue

        policy = ProviderPolicy.from_dict(raw)
        if policy.provider_code in policies:
            raise ValueError(
                f"duplicate policy record for {policy.provider_code!r} in "
                f"{record_path}"
            )
        policies[policy.provider_code] = policy

    return ProviderPolicyMatrix(policies=policies)
