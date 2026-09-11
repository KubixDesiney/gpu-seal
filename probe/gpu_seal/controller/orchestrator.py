"""Repository-owned orchestration for bounded provider campaigns.

This module owns sequencing and failure policy, not a cloud integration. A
real adapter must be supplied by the owner after selecting a provider and
authorising its credentials and permission scope. The orchestrator accepts
only the small :class:`ProviderRuntime` contract and shares one campaign
context across every run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..evidence.signing import Signer, SigningKeySource
from ..safety.campaign import CampaignControl
from ..safety.errors import CampaignContextRequired
from .evidence_store import EvidenceStore, StoredBundle
from .native_runner import (
    NativeExecution,
    NativeProviderRunner,
    NativeRunConfig,
    ProviderRuntime,
)
from .scheduler import ExperimentPlan, ExperimentRun, Scheduler

__all__ = [
    "CampaignRunSpec",
    "CampaignRunOutcome",
    "CampaignExecution",
    "CampaignOrchestrator",
]


@dataclass(frozen=True)
class CampaignRunSpec:
    """One bounded provider execution in a logical campaign."""

    plan: ExperimentPlan
    config: NativeRunConfig
    run_id: str


@dataclass(frozen=True)
class CampaignRunOutcome:
    """Safe status for one attempted or deliberately skipped run."""

    run_id: str
    record: ExperimentRun | None = None
    execution: NativeExecution | None = None
    stored: StoredBundle | None = None
    error_type: str | None = None
    error: str | None = None

    @property
    def completed(self) -> bool:
        return self.record is not None and self.record.completed

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "completed": self.completed,
            "stopped": bool(self.execution and self.execution.stopped),
            "stored": self.stored.to_dict() if self.stored else None,
            "error_type": self.error_type,
            "error": self.error,
        }


@dataclass(frozen=True)
class CampaignExecution:
    """The result of a campaign, with no native stdout or raw memory."""

    outcomes: tuple[CampaignRunOutcome, ...]
    skipped_run_ids: tuple[str, ...] = ()

    @property
    def stopped(self) -> bool:
        return any(
            outcome.execution is not None and outcome.execution.stopped
            for outcome in self.outcomes
        )

    @property
    def failed(self) -> bool:
        return bool(self.skipped_run_ids) or any(
            outcome.error_type is not None or not outcome.completed
            for outcome in self.outcomes
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
            "skipped_run_ids": list(self.skipped_run_ids),
            "stopped": self.stopped,
            "failed": self.failed,
        }


class CampaignOrchestrator:
    """Run provider-native work under one explicit campaign context."""

    def __init__(
        self,
        scheduler: Scheduler,
        runtime: ProviderRuntime,
        *,
        campaign: CampaignControl | None,
    ) -> None:
        if campaign is None:
            raise CampaignContextRequired(
                "campaign orchestration requires a root-owned campaign context"
            )
        self._scheduler = scheduler
        self._runtime = runtime
        self._campaign = campaign
        self._last_signer: Signer | None = None

    @property
    def signing_fingerprint(self) -> str | None:
        """Return only the public fingerprint of the signer used last."""
        return (
            self._last_signer.verify_key.fingerprint
            if self._last_signer is not None
            else None
        )

    def run(
        self, specs: list[CampaignRunSpec] | tuple[CampaignRunSpec, ...]
    ) -> CampaignExecution:
        """Run specs in order and stop scheduling after a terminal failure.

        Policy violations and safety stops retain their fail-closed exception
        semantics. Ordinary provider/command failures are represented in the
        returned outcome and prevent later allocations from being attempted.
        Cleanup reconciliation is delegated to :class:`Scheduler`; an
        unknown reconciliation therefore remains visible as an open ledger
        reservation rather than being converted to a successful run.
        """
        self._campaign.check()
        outcomes: list[CampaignRunOutcome] = []
        skipped: list[str] = []
        for index, spec in enumerate(specs):
            self._campaign.check()
            runner = NativeProviderRunner(
                self._scheduler, self._runtime, campaign=self._campaign
            )
            try:
                record, execution = runner.run(spec.plan, spec.config, run_id=spec.run_id)
            except Exception as exc:  # noqa: BLE001 - campaign reports provider failure
                outcomes.append(
                    CampaignRunOutcome(
                        run_id=spec.run_id,
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
                )
                skipped.extend(item.run_id for item in specs[index + 1 :])
                break
            outcomes.append(
                CampaignRunOutcome(
                    run_id=spec.run_id, record=record, execution=execution
                )
            )
            if execution is not None and execution.stopped:
                skipped.extend(item.run_id for item in specs[index + 1 :])
                break
        return CampaignExecution(tuple(outcomes), tuple(skipped))

    def run_and_store(
        self,
        specs: list[CampaignRunSpec] | tuple[CampaignRunSpec, ...],
        *,
        store: EvidenceStore,
        key_source: SigningKeySource,
    ) -> CampaignExecution:
        """Run and store each result with one explicitly selected signer."""
        self._campaign.check()
        signer: Signer = key_source.load()
        self._last_signer = signer
        outcomes: list[CampaignRunOutcome] = []
        skipped: list[str] = []
        for index, spec in enumerate(specs):
            self._campaign.check()
            runner = NativeProviderRunner(
                self._scheduler, self._runtime, campaign=self._campaign
            )
            try:
                record, execution, stored = runner.run_and_store(
                    spec.plan,
                    spec.config,
                    run_id=spec.run_id,
                    key=signer,
                    store=store,
                )
            except Exception as exc:  # noqa: BLE001 - campaign reports provider failure
                outcomes.append(
                    CampaignRunOutcome(
                        run_id=spec.run_id,
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
                )
                skipped.extend(item.run_id for item in specs[index + 1 :])
                break
            outcomes.append(
                CampaignRunOutcome(
                    run_id=spec.run_id,
                    record=record,
                    execution=execution,
                    stored=stored,
                )
            )
            if execution.stopped:
                skipped.extend(item.run_id for item in specs[index + 1 :])
                break
        return CampaignExecution(tuple(outcomes), tuple(skipped))
