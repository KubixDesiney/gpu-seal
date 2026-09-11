"""Experiment scheduling — CHARTER.md §16 tests 11 and 14.

Two rules that had constants but no enforcer:

**Test 11 — max experiment duration enforced.**
:data:`~gpu_seal.safety.policy.MAX_EXPERIMENT_DURATION_S` existed and was
tested for its value. Nothing consulted it. :meth:`Scheduler.run` now does,
and a run that overruns is aborted and marked excluded rather than allowed to
finish late — an overrunning probe on rented hardware is both a cost problem
and a sign the measurement is not the one that was designed.

**Test 14 — owned-account confirmation enforced.**
CHARTER.md §4.1: "Measure only infrastructure the researcher rents." §6: the
researcher is "an ordinary authenticated customer with legitimate access."
Everything ethical about this project rests on the target being ours, and
until now that was an assumption held in the operator's head.
:class:`ExperimentPlan` cannot be constructed without an explicit ownership
attestation naming how ownership was confirmed, and the scheduler refuses to
run without one.

The confirmation is not cryptographic and does not pretend to be. It is a
recorded, signed-into-evidence statement by the operator that this instance
was rented on their own account, with the console or invoice reference that
backs it. Its value is that it is *recorded*: a run that turns out to have
targeted somebody else's instance has a written trail of who asserted
otherwise, which is what an ethics review actually needs.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, TypeVar

from ..safety.errors import LimitExceeded, PolicyViolation
from ..safety.policy import MAX_EXPERIMENT_DURATION_S
from .budget import BudgetLedger, TerminationResult
from .policy_matrix import ProviderPolicyMatrix

__all__ = [
    "ExperimentPlan",
    "ExperimentRun",
    "Scheduler",
    "OwnershipNotConfirmed",
    "CleanupReconciliationError",
]

T = TypeVar("T")


class OwnershipNotConfirmed(PolicyViolation):
    """The target was not attested as researcher-owned. CHARTER.md §16 test 14."""


class CleanupReconciliationError(RuntimeError):
    """Provider cleanup or billing reconciliation failed; reservation remains open."""


@dataclass(frozen=True)
class ExperimentPlan:
    """What is to be run, against what, on whose account, for how long."""

    experiment_id: str
    provider_code: str
    probe_name: str

    #: How the operator confirmed this instance is theirs — console reference,
    #: invoice line, order id. Free text on purpose: what constitutes proof
    #: differs per provider, and a dropdown would invite picking the nearest
    #: option rather than stating the truth.
    ownership_confirmation: str
    #: Who is making that statement.
    confirmed_by: str

    max_duration_s: int = MAX_EXPERIMENT_DURATION_S
    estimated_cost: float = 0.0
    region_claim: str = "n/a"
    product_claim: str = "n/a"

    def __post_init__(self) -> None:
        if not self.ownership_confirmation.strip():
            raise OwnershipNotConfirmed(
                f"Experiment {self.experiment_id!r} has no ownership "
                f"confirmation. CHARTER.md §4.1 restricts measurement to "
                f"infrastructure the researcher rents, and §16 test 14 "
                f"requires that to be confirmed rather than assumed. State how "
                f"ownership of this instance was established."
            )
        if not self.confirmed_by.strip():
            raise OwnershipNotConfirmed(
                f"Experiment {self.experiment_id!r}: ownership was confirmed "
                f"but nobody is named as confirming it. An unattributed "
                f"attestation is not one."
            )
        if self.max_duration_s <= 0:
            raise ValueError("max_duration_s must be positive")
        if self.max_duration_s > MAX_EXPERIMENT_DURATION_S:
            raise LimitExceeded(
                f"max_duration_s={self.max_duration_s} exceeds "
                f"MAX_EXPERIMENT_DURATION_S ({MAX_EXPERIMENT_DURATION_S}); "
                f"CHARTER.md §16 test 11. Raising the ceiling is a policy "
                f"change in gpu_seal.safety.policy, not a per-run argument."
            )


@dataclass
class ExperimentRun:
    """The record of one attempt, whatever happened to it."""

    plan: ExperimentPlan
    run_id: str
    started_at: float
    duration_s: float = 0.0
    completed: bool = False
    aborted_reason: str | None = None
    #: Why the policy matrix permitted this, recorded per CHARTER.md §7.4.
    policy_basis: str = ""
    actual_cost: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def excluded(self) -> bool:
        """Aborted runs are excluded from statistics, per CHARTER.md §12."""
        return not self.completed

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "experiment_id": self.plan.experiment_id,
            "provider_code": self.plan.provider_code,
            "probe_name": self.plan.probe_name,
            "duration_s": round(self.duration_s, 3),
            "completed": self.completed,
            "excluded": self.excluded,
            "exclusion_reason": self.aborted_reason,
            "policy_basis": self.policy_basis,
            "ownership_confirmation": self.plan.ownership_confirmation,
            "ownership_confirmed_by": self.plan.confirmed_by,
            "cost": self.actual_cost,
        }


class Scheduler:
    """Runs probes only where policy, budget, and ownership all permit it."""

    def __init__(
        self,
        *,
        policy_matrix: ProviderPolicyMatrix,
        ledger: BudgetLedger,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._matrix = policy_matrix
        self._ledger = ledger
        self._clock = clock

    def run(
        self,
        plan: ExperimentPlan,
        work: Callable[[], T],
        *,
        run_id: str,
        today: date | None = None,
        actual_cost: Callable[[], TerminationResult | float] | None = None,
    ) -> tuple[ExperimentRun, T | None]:
        """Execute ``work`` under every §16 control, or refuse to start it.

        Order matters. Policy is checked before budget, and budget before the
        instance is created, so a prohibited provider never reaches the point
        of costing anything.

        Duration is checked *after* the work returns rather than interrupting
        it. Killing a probe mid-measurement risks leaving a device allocation
        alive and a canary planted with nothing to read it back — the
        overrunning run is marked aborted and excluded, which is the outcome
        that matters for §12, and the operator's automatic-shutdown control
        (§20) is what bounds the cost. A pre-emptive kill is a change to the
        probe layer, not to the scheduler, and is noted in
        ``docs/methodology.md`` as open.
        """
        basis = self._matrix.check(plan.provider_code, plan.probe_name, today=today)

        self._ledger.reserve(
            run_id=run_id,
            provider_code=plan.provider_code,
            estimated_cost=plan.estimated_cost,
            today=today,
        )

        record = ExperimentRun(
            plan=plan,
            run_id=run_id,
            started_at=self._clock(),
            policy_basis=basis,
        )

        result: T | None = None
        try:
            result = work()
            record.completed = True
        except Exception as exc:  # noqa: BLE001 - the run is the unit of failure
            record.aborted_reason = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            record.duration_s = self._clock() - record.started_at
            if record.duration_s > plan.max_duration_s:
                record.completed = False
                record.aborted_reason = (
                    f"exceeded max_duration_s={plan.max_duration_s} "
                    f"(ran {record.duration_s:.1f}s). Excluded from statistics "
                    f"(CHARTER.md §16 test 11, §12)."
                )
            if actual_cost is None:
                # A zero-estimate local policy/control run has no provider
                # resource to clean up. Non-zero reservations still require a
                # provider result; never release those on an invented default.
                termination = (
                    TerminationResult.success(0.0)
                    if plan.estimated_cost == 0
                    else TerminationResult.unknown(
                        "no cleanup and billing reconciliation result was supplied"
                    )
                )
            else:
                try:
                    candidate = actual_cost()
                except Exception as exc:  # noqa: BLE001 - preserve reservation
                    termination = TerminationResult.unknown(
                        f"termination or billing reconciliation raised "
                        f"{type(exc).__name__}"
                    )
                else:
                    if isinstance(candidate, TerminationResult):
                        termination = candidate
                    elif isinstance(candidate, (int, float)) and not isinstance(
                        candidate, bool
                    ):
                        try:
                            termination = TerminationResult.success(float(candidate))
                        except (TypeError, ValueError, OverflowError):
                            termination = TerminationResult.unknown(
                                "provider returned an invalid reconciled cost"
                            )
                    else:
                        termination = TerminationResult.unknown(
                            "provider returned no explicit cleanup state"
                        )

            if termination.confirmed:
                actual_cost_value = termination.actual_cost
                if actual_cost_value is None:  # defensive invariant
                    raise CleanupReconciliationError(
                        "confirmed termination had no reconciled cost; "
                        "reservation remains open"
                    )
                record.actual_cost = actual_cost_value
            else:
                record.completed = False
                record.aborted_reason = (
                    "cleanup/billing reconciliation failed or is unknown; "
                    "reservation remains open (operator action required)"
                )
            self._ledger.settle_termination(run_id, termination)
            if not termination.confirmed:
                detail = termination.error or termination.state.value
                raise CleanupReconciliationError(
                    f"Run {run_id!r} could not confirm provider cleanup and "
                    f"cost reconciliation: {detail}. Reservation remains open."
                )

        return record, result
