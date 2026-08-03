"""Responsible disclosure gating — CHARTER.md §7.5.

    internally reproduce → eliminate methodology errors → confirm only owned
    canaries matched → prepare a minimal technical report → contact the
    provider privately → allow a reasonable remediation window (default 90
    days) → re-test after response → publish only after coordination or
    documented non-response

That is a state machine, and writing it as one is the difference between a
policy and an intention. :class:`DisclosureGate` will not let a finding reach
publication without every prior step having happened, and it records *when*
each happened so the timeline in the paper is the real one.

The default window matches fwd:cloudsec's published policy — 90 days to patch
plus 30 to coordinate — which CHARTER.md §7.5 notes and keeps.

**Non-response is a documented state, not a loophole.** A provider who never
replies does not get an indefinite veto over publication; the gate opens when
the window expires, and the record says the provider did not respond. That is
the coordinated-disclosure norm and it is what makes the deadline meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any

from ..safety.errors import PolicyViolation

__all__ = [
    "DisclosureState",
    "DisclosureRecord",
    "DisclosureGate",
    "DisclosureNotComplete",
    "REMEDIATION_WINDOW_DAYS",
    "COORDINATION_WINDOW_DAYS",
]

REMEDIATION_WINDOW_DAYS = 90
COORDINATION_WINDOW_DAYS = 30


class DisclosureNotComplete(PolicyViolation):
    """Publication was attempted before §7.5's process finished."""


class DisclosureState(str, Enum):
    """The §7.5 pipeline, in order. Skipping a step is not representable."""

    OBSERVED = "observed"
    REPRODUCED = "reproduced"
    METHODOLOGY_CHECKED = "methodology_checked"
    OWNERSHIP_CONFIRMED = "ownership_confirmed"
    REPORT_PREPARED = "report_prepared"
    PROVIDER_CONTACTED = "provider_contacted"
    PROVIDER_RESPONDED = "provider_responded"
    RETESTED = "retested"
    PUBLICATION_CLEARED = "publication_cleared"


#: The order steps must occur in. `PROVIDER_RESPONDED` is deliberately absent
#: from the required chain — see `DisclosureRecord.may_publish`.
_ORDER = [
    DisclosureState.OBSERVED,
    DisclosureState.REPRODUCED,
    DisclosureState.METHODOLOGY_CHECKED,
    DisclosureState.OWNERSHIP_CONFIRMED,
    DisclosureState.REPORT_PREPARED,
    DisclosureState.PROVIDER_CONTACTED,
]


@dataclass
class DisclosureRecord:
    """One finding's journey from observation to publishable."""

    finding_id: str
    provider_code: str
    summary: str

    #: state → date it was reached.
    timeline: dict[DisclosureState, date] = field(default_factory=dict)
    provider_responded: bool = False
    notes: list[str] = field(default_factory=list)

    def record(self, state: DisclosureState, on: date) -> None:
        """Mark a step complete. Refuses to skip a prerequisite."""
        if state in _ORDER:
            index = _ORDER.index(state)
            missing = [s for s in _ORDER[:index] if s not in self.timeline]
            if missing:
                raise DisclosureNotComplete(
                    f"Cannot record {state.value!r} for {self.finding_id!r}: "
                    f"{[s.value for s in missing]} have not happened yet. "
                    f"CHARTER.md §7.5 is a sequence — a report prepared before "
                    f"the finding was reproduced is a report about a possible "
                    f"measurement error."
                )
        self.timeline[state] = on

    @property
    def contacted_on(self) -> date | None:
        return self.timeline.get(DisclosureState.PROVIDER_CONTACTED)

    def window_expires_on(self) -> date | None:
        contacted = self.contacted_on
        if contacted is None:
            return None
        return contacted + timedelta(
            days=REMEDIATION_WINDOW_DAYS + COORDINATION_WINDOW_DAYS
        )

    def may_publish(self, *, today: date | None = None) -> tuple[bool, str]:
        """Whether this finding may be published, and on what basis."""
        reference = today or date.today()

        missing = [s for s in _ORDER if s not in self.timeline]
        if missing:
            return False, (
                f"§7.5 steps not yet complete: {[s.value for s in missing]}."
            )

        # PROVIDER_CONTACTED is in _ORDER and the check above proved every
        # step in _ORDER is recorded, so the window has a start date.
        expiry = self.window_expires_on()
        if expiry is None:  # pragma: no cover - unreachable by construction
            return False, "the provider contact date is missing."

        if self.provider_responded:
            if DisclosureState.RETESTED not in self.timeline:
                return False, (
                    "the provider responded but the finding has not been "
                    "re-tested. §7.5 requires re-testing after a response — "
                    "publishing a finding the provider has already fixed would "
                    "be inaccurate."
                )
            return True, (
                f"coordinated: provider responded, finding re-tested on "
                f"{self.timeline[DisclosureState.RETESTED].isoformat()}."
            )

        if reference >= expiry:
            return True, (
                f"documented non-response: the provider was contacted on "
                f"{self.contacted_on.isoformat()} and the "
                f"{REMEDIATION_WINDOW_DAYS}+{COORDINATION_WINDOW_DAYS} day "
                f"window expired on {expiry.isoformat()}."
            )

        remaining = (expiry - reference).days
        return False, (
            f"the remediation window has {remaining} day(s) left (expires "
            f"{expiry.isoformat()}). CHARTER.md §7.5."
        )

    def to_dict(self) -> dict[str, Any]:
        publishable, basis = self.may_publish()
        return {
            "finding_id": self.finding_id,
            "provider_code": self.provider_code,
            "summary": self.summary,
            "timeline": {
                state.value: when.isoformat() for state, when in self.timeline.items()
            },
            "provider_responded": self.provider_responded,
            "window_expires_on": (
                self.window_expires_on().isoformat()
                if self.window_expires_on()
                else None
            ),
            "publishable": publishable,
            "basis": basis,
            "notes": self.notes,
        }


class DisclosureGate:
    """Holds findings and refuses to release the ones that are not ready."""

    def __init__(self) -> None:
        self._records: dict[str, DisclosureRecord] = {}

    def track(self, record: DisclosureRecord) -> None:
        if record.finding_id in self._records:
            raise ValueError(f"finding {record.finding_id!r} is already tracked")
        self._records[record.finding_id] = record

    def get(self, finding_id: str) -> DisclosureRecord:
        return self._records[finding_id]

    def require_publishable(
        self, finding_id: str, *, today: date | None = None
    ) -> str:
        """Raise unless this finding may be published. Returns the basis."""
        record = self._records.get(finding_id)
        if record is None:
            raise DisclosureNotComplete(
                f"No disclosure record exists for finding {finding_id!r}. A "
                f"finding with no disclosure record has not been through §7.5 "
                f"at all."
            )
        allowed, basis = record.may_publish(today=today)
        if not allowed:
            raise DisclosureNotComplete(
                f"Refusing to publish {finding_id!r}: {basis}"
            )
        return basis

    def pending(self, *, today: date | None = None) -> list[dict[str, Any]]:
        """Findings still inside their window. The operator's worklist."""
        out = []
        for record in self._records.values():
            allowed, basis = record.may_publish(today=today)
            if not allowed:
                out.append({"finding_id": record.finding_id, "basis": basis})
        return sorted(out, key=lambda item: item["finding_id"])
