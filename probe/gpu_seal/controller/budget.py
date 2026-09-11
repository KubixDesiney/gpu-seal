"""Budget controls — CHARTER.md §20.

    "Controls: per-run max duration, per-provider spend limit, automatic
     shutdown, quota monitoring, failed-deployment cleanup, cost recorded in
     each result, daily + campaign caps."

Rented H100 time is the one resource in this project that can be consumed
faster than a mistake can be noticed. A loop that forgets to destroy an
instance costs money every hour until somebody reads an invoice.

The ledger is deliberately pessimistic in two ways:

**Cost is reserved before the run, not billed after it.** A run that starts is
already charged against the cap at its worst-case estimate. Reconciliation
against the real figure happens on completion. Booking the estimate afterwards
would let a hundred runs start simultaneously under a cap of one.

**A crashed run stays reserved until reconciled.** The instance it leaked is
still costing money, so the ledger keeps counting it. Releasing the reservation
on an exception would make the cap look healthy at precisely the moment it is
being breached.

Currency is not modelled. Amounts are in whatever unit the operator set the
caps in, and mixing units is the operator's problem — a currency conversion
inside a spend guard is a source of error nobody would find until it mattered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
import math

from ..safety.errors import PolicyViolation

__all__ = [
    "SpendLimits",
    "BudgetLedger",
    "BudgetExceeded",
    "Reservation",
    "CleanupState",
    "TerminationResult",
]


class BudgetExceeded(PolicyViolation):
    """A spend cap would be breached. Raised before the spend, never after."""


class CleanupState(str, Enum):
    """The only states in which a provider run may reconcile its reservation."""

    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TerminationResult:
    """Provider cleanup and billing reconciliation, without a fake cost default."""

    state: CleanupState
    actual_cost: float | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.state is CleanupState.SUCCESS:
            if self.actual_cost is None or not math.isfinite(self.actual_cost):
                raise ValueError("successful termination requires a finite cost")
            if self.actual_cost < 0:
                raise ValueError("actual_cost cannot be negative")
            if self.error is not None:
                raise ValueError("successful termination cannot contain an error")
        elif self.actual_cost is not None:
            raise ValueError("failed or unknown termination cannot contain a cost")

    @classmethod
    def success(cls, actual_cost: float) -> TerminationResult:
        return cls(CleanupState.SUCCESS, actual_cost=actual_cost)

    @classmethod
    def failed(cls, error: str) -> TerminationResult:
        return cls(CleanupState.FAILED, error=error)

    @classmethod
    def unknown(cls, error: str) -> TerminationResult:
        return cls(CleanupState.UNKNOWN, error=error)

    @property
    def confirmed(self) -> bool:
        return self.state is CleanupState.SUCCESS


@dataclass(frozen=True)
class SpendLimits:
    """Caps, in the operator's own currency unit."""

    per_run: float
    per_provider: float
    per_day: float
    per_campaign: float

    def __post_init__(self) -> None:
        for name in ("per_run", "per_provider", "per_day", "per_campaign"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.per_run > self.per_campaign:
            raise ValueError(
                "per_run exceeds per_campaign: a single run could consume the "
                "whole campaign budget, which makes the campaign cap decorative"
            )


@dataclass(frozen=True)
class Reservation:
    """One booked run. Held until reconciled against the real cost."""

    run_id: str
    provider_code: str
    estimated_cost: float
    booked_on: date


@dataclass
class BudgetLedger:
    """Tracks reservations and actuals against :class:`SpendLimits`."""

    limits: SpendLimits
    _open: dict[str, Reservation] = field(default_factory=dict, repr=False)
    _settled: list[tuple[Reservation, float]] = field(
        default_factory=list, repr=False
    )
    _open_errors: dict[str, str] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------

    def committed_total(self) -> float:
        """Everything spent or reserved. The number the campaign cap sees."""
        return sum(r.estimated_cost for r in self._open.values()) + sum(
            actual for _, actual in self._settled
        )

    def committed_for_provider(self, provider_code: str) -> float:
        return sum(
            r.estimated_cost
            for r in self._open.values()
            if r.provider_code == provider_code
        ) + sum(
            actual
            for reservation, actual in self._settled
            if reservation.provider_code == provider_code
        )

    def committed_on(self, day: date) -> float:
        return sum(
            r.estimated_cost for r in self._open.values() if r.booked_on == day
        ) + sum(
            actual
            for reservation, actual in self._settled
            if reservation.booked_on == day
        )

    # ------------------------------------------------------------------

    def reserve(
        self,
        *,
        run_id: str,
        provider_code: str,
        estimated_cost: float,
        today: date | None = None,
    ) -> Reservation:
        """Book a run against the caps, or refuse it."""
        if estimated_cost < 0:
            raise ValueError("estimated_cost cannot be negative")
        if run_id in self._open:
            raise ValueError(f"run {run_id!r} is already reserved")

        day = today or date.today()

        if estimated_cost > self.limits.per_run:
            raise BudgetExceeded(
                f"run {run_id!r} is estimated at {estimated_cost:.2f}, above "
                f"the per-run cap of {self.limits.per_run:.2f}."
            )

        checks = (
            (
                "per-provider",
                self.committed_for_provider(provider_code) + estimated_cost,
                self.limits.per_provider,
            ),
            ("daily", self.committed_on(day) + estimated_cost, self.limits.per_day),
            (
                "campaign",
                self.committed_total() + estimated_cost,
                self.limits.per_campaign,
            ),
        )
        for label, projected, cap in checks:
            if projected > cap:
                raise BudgetExceeded(
                    f"run {run_id!r} would take {label} spend to "
                    f"{projected:.2f}, above the cap of {cap:.2f}. Refusing "
                    f"before the instance is created (CHARTER.md §20)."
                )

        reservation = Reservation(
            run_id=run_id,
            provider_code=provider_code,
            estimated_cost=estimated_cost,
            booked_on=day,
        )
        self._open[run_id] = reservation
        self._open_errors.pop(run_id, None)
        return reservation

    def _settle_confirmed(self, run_id: str, actual_cost: float) -> None:
        """Release a reservation after explicit cleanup confirmation."""
        reservation = self._open.pop(run_id, None)
        if reservation is None:
            raise ValueError(f"run {run_id!r} was never reserved")
        if actual_cost < 0:
            raise ValueError("actual_cost cannot be negative")
        self._settled.append((reservation, actual_cost))
        self._open_errors.pop(run_id, None)

    def settle_termination(self, run_id: str, result: TerminationResult) -> None:
        """Release only after provider cleanup and cost are both confirmed.

        A failed or unknown reconciliation deliberately leaves the original
        reservation open. That keeps caps pessimistic and makes the leak
        visible to the operator instead of converting it into a zero-cost
        settled run.
        """
        if result.confirmed:
            actual_cost = result.actual_cost
            if actual_cost is None:  # defensive invariant; __post_init__ rejects it
                raise ValueError("confirmed termination has no reconciled cost")
            self._settle_confirmed(run_id, actual_cost)
            return
        if run_id not in self._open:
            raise ValueError(f"run {run_id!r} was never reserved")
        detail = result.error or f"termination state: {result.state.value}"
        self._open_errors[run_id] = detail

    def open_run_errors(self) -> dict[str, str]:
        """Return operator-facing errors for reservations still held open."""
        return dict(sorted(self._open_errors.items()))

    def open_runs(self) -> list[str]:
        """Reservations never settled. Each is a possible leaked instance."""
        return sorted(self._open)

    def summary(self) -> dict[str, object]:
        return {
            "committed_total": round(self.committed_total(), 4),
            "campaign_cap": self.limits.per_campaign,
            "settled_runs": len(self._settled),
            "open_runs": self.open_runs(),
            "open_run_errors": self.open_run_errors(),
        }
