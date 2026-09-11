"""Controller-owned execution of the native CUDA agent.

The native executable owns the only path that allocates, releases, and reads
device memory. This module owns everything around it: provider policy, budget,
ownership attestation, cleanup, timeout delegation, and signed evidence.

Provider integrations implement ProviderRuntime. Keeping that interface small
means a hyperscaler, specialist-cloud, or marketplace adapter can be tested without
importing a cloud SDK into the memory-touching binary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from ..evidence import ResultBundle, Signer
from ..evidence.result import ToolProvenance
from ..safety.aggregation import AggregateRecord, RedactedStopRecord
from ..safety.campaign import CampaignControl
from ..safety.errors import CampaignContextRequired
from .budget import TerminationResult
from .evidence_store import EvidenceStore, StoredBundle
from .scheduler import ExperimentPlan, ExperimentRun, Scheduler

__all__ = [
    "NativeCommandResult",
    "NativeExecution",
    "NativeExecutionError",
    "NativeProviderRunner",
    "NativeRunConfig",
    "ProviderRuntime",
    "parse_native_output",
]

ProbeRecord = AggregateRecord | RedactedStopRecord


@dataclass(frozen=True)
class NativeCommandResult:
    """Output returned by a provider adapter after running the native binary."""

    returncode: int
    stdout: str
    stderr: str = ""
    timed_out: bool = False


class ProviderRuntime(Protocol):
    """The narrow provider adapter contract.

    launch must create only the researcher's own allocation. execute must
    enforce the supplied timeout. terminate must be idempotent and must return
    an explicit cleanup and billing reconciliation state, including failed runs.
    """

    def launch(self, plan: ExperimentPlan) -> Any:
        """Create and return a provider-specific allocation handle."""

    def execute(
        self, allocation: Any, command: list[str], timeout_s: int
    ) -> NativeCommandResult:
        """Run the command inside the allocation with a hard timeout."""

    def terminate(self, allocation: Any) -> TerminationResult:
        """Destroy the allocation and reconcile final cost explicitly."""


@dataclass(frozen=True)
class NativeRunConfig:
    """A bounded native battery configuration."""

    binary: Path
    size_mib: int = 64
    cycles: int = 10
    stride_mib: int = 1
    mode: str = "reuse"
    container_profile: str = "pinned"
    container_digest: str | None = None
    tool_version: str = "0.1.0-native"
    git_commit: str = "unknown"

    def __post_init__(self) -> None:
        if self.size_mib <= 0 or self.cycles <= 0 or self.stride_mib <= 0:
            raise ValueError("size_mib, cycles, and stride_mib must be positive")
        if self.mode not in {"reuse", "fresh", "zeroed"}:
            raise ValueError("mode must be reuse, fresh, or zeroed")
        if self.stride_mib * 1024 * 1024 < 128:
            raise ValueError("stride_mib must leave room for a 128-byte canary")

    def command(self) -> list[str]:
        """Build the shared-infrastructure command.

        The explicit scope flag is intentional. The native binary refuses an
        ambiguous run, and this controller never uses its local-only mode.
        """
        return [
            str(self.binary),
            "--run",
            "--shared-infrastructure",
            "--json",
            "--mode",
            self.mode,
            "--size-mib",
            str(self.size_mib),
            "--cycles",
            str(self.cycles),
            "--stride-mib",
            str(self.stride_mib),
        ]


@dataclass(frozen=True)
class NativeExecution:
    """Parsed native output plus the summary emitted by the binary."""

    records: tuple[ProbeRecord, ...]
    summary: dict[str, Any]

    @property
    def stopped(self) -> bool:
        return bool(self.records and isinstance(self.records[-1], RedactedStopRecord))


class NativeExecutionError(RuntimeError):
    """The native command failed without exposing raw device output."""


def parse_native_output(stdout: str, *, expected_cycles: int) -> NativeExecution:
    """Parse native output, including one terminal redacted stop record."""
    records: list[ProbeRecord] = []
    summary: dict[str, Any] | None = None
    saw_stop = False
    saw_summary = False
    for line in stdout.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        kind = payload.pop("kind", None)
        if saw_summary:
            raise NativeExecutionError("native output continued after its summary")
        if kind == "aggregate":
            if saw_stop:
                raise NativeExecutionError("native output continued after a safety stop")
            record = AggregateRecord(**payload)
            if record.sensitive_observation:
                raise NativeExecutionError(
                    "native encoded a sensitive observation as a reconstructive "
                    "aggregate; only a redacted terminal stop is accepted"
                )
            records.append(record)
        elif kind == "stop":
            if saw_stop:
                raise NativeExecutionError("native output contained two stop records")
            saw_stop = True
            records.append(RedactedStopRecord(**payload))
        elif kind == "summary" and summary is None:
            summary = payload
            saw_summary = True
        else:
            raise NativeExecutionError("native output contained an unknown record kind")

    if summary is None:
        raise NativeExecutionError(
            "native output did not contain a summary"
        )
    stopped = bool(records and isinstance(records[-1], RedactedStopRecord))
    if stopped:
        if not summary.get("terminated_early", False):
            raise NativeExecutionError(
                "native stop record was not accompanied by terminal summary metadata"
            )
        if len(records) > expected_cycles:
            raise NativeExecutionError(
                "native returned more records than the requested cycles"
            )
    elif len(records) != expected_cycles:
        raise NativeExecutionError(
            f"native returned {len(records)} aggregates, expected {expected_cycles}"
        )
    if int(summary.get("cycles", -1)) != len(records):
        raise NativeExecutionError(
            "native output summary cycle count did not match emitted records"
        )
    if any(
        isinstance(record, RedactedStopRecord)
        for record in records[:-1]
    ):
        raise NativeExecutionError("native output continued after a safety stop")
    return NativeExecution(records=tuple(records), summary=summary)


class NativeProviderRunner:
    """Run the native agent only after the controller gates the experiment."""

    def __init__(
        self,
        scheduler: Scheduler,
        runtime: ProviderRuntime,
        campaign: CampaignControl | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._runtime = runtime
        self._campaign = campaign

    def _require_campaign(self) -> CampaignControl:
        if self._campaign is None:
            raise CampaignContextRequired(
                "shared-infrastructure provider execution requires the "
                "root-owned campaign context; pass campaign=CampaignControl.create()"
            )
        return self._campaign

    def run(
        self,
        plan: ExperimentPlan,
        config: NativeRunConfig,
        *,
        run_id: str,
        today: date | None = None,
    ) -> tuple[ExperimentRun, NativeExecution | None]:
        """Launch, execute, and always terminate one native provider run."""
        campaign = self._require_campaign()
        campaign.check()
        allocation: Any = None
        termination: TerminationResult | float | None = None

        def work() -> NativeExecution:
            nonlocal allocation, termination
            campaign.check()
            allocation = self._runtime.launch(plan)
            try:
                campaign.check()
                try:
                    completed = self._runtime.execute(
                        allocation, config.command(), plan.max_duration_s
                    )
                except TimeoutError:
                    raise NativeExecutionError(
                        f"native command exceeded timeout of {plan.max_duration_s}s"
                    ) from None
                if completed.timed_out:
                    raise NativeExecutionError(
                        f"native command exceeded timeout of {plan.max_duration_s}s"
                    )
                if completed.returncode != 0:
                    raise NativeExecutionError(
                        f"native command failed with exit code {completed.returncode}"
                    )
                campaign.check()
                execution = parse_native_output(
                    completed.stdout, expected_cycles=config.cycles
                )
                if execution.stopped:
                    campaign.terminate(execution.records[-1])
                return execution
            finally:
                try:
                    termination = self._runtime.terminate(allocation)
                except Exception as exc:  # noqa: BLE001 - keep reservation open
                    termination = TerminationResult.unknown(
                        f"provider terminate raised {type(exc).__name__}"
                    )
                    raise

        def reconcile() -> TerminationResult | float:
            if termination is None:
                return TerminationResult.unknown(
                    "provider allocation was not confirmed terminated"
                )
            return termination

        record, execution = self._scheduler.run(
            plan,
            work,
            run_id=run_id,
            today=today,
            actual_cost=reconcile,
        )
        if execution is not None and execution.stopped:
            campaign.terminate(execution.records[-1])
            record.completed = False
            record.aborted_reason = (
                "native campaign terminated after a sensitive observation; "
                "excluded from statistics"
            )
        return record, execution

    def run_and_store(
        self,
        plan: ExperimentPlan,
        config: NativeRunConfig,
        *,
        run_id: str,
        key: Signer,
        store: EvidenceStore,
        today: date | None = None,
    ) -> tuple[ExperimentRun, NativeExecution, StoredBundle]:
        """Run a provider battery and write it through the publication gate."""
        record, execution = self.run(
            plan, config, run_id=run_id, today=today
        )
        if execution is None:
            raise NativeExecutionError("native run returned no execution result")

        first = execution.records[0]
        first_metadata = (
            dict(first.operational_metadata)
            if isinstance(first, RedactedStopRecord)
            else dict(first.driver_metadata or {})
        )
        records: tuple[ProbeRecord, ...] = tuple(
            replace(
                item,
                driver_metadata={
                    **dict(item.driver_metadata or {}),
                    "container_profile": config.container_profile,
                },
            )
            for item in execution.records
            if isinstance(item, AggregateRecord)
        )
        # Preserve a terminal stop record exactly. Normal aggregates may carry
        # the controller-only container profile; a redacted record may not gain
        # any new field after the stop.
        if execution.stopped:
            records = records + (execution.records[-1],)
        execution = NativeExecution(records=records, summary=execution.summary)
        tool = ToolProvenance(
            version=config.tool_version,
            commit=config.git_commit,
            container_digest=config.container_digest,
            cuda_runtime_version=first_metadata.get("cuda_runtime_version"),
            cuda_driver_version=first_metadata.get("cuda_driver_version"),
        )
        bundle = ResultBundle(
            experiment_id=plan.experiment_id,
            run_id=run_id,
            provider_code=plan.provider_code,
            region_claim=plan.region_claim,
            product_claim=plan.product_claim
            if plan.product_claim != "n/a"
            else first_metadata.get("device_name", "unknown"),
            tool=tool,
            probes=list(records),
            environment={
                "native_execution": {
                    "mode": config.mode,
                    "cycles": config.cycles,
                    "size_mib": config.size_mib,
                    "stride_mib": config.stride_mib,
                    "policy_basis": record.policy_basis,
                    "ownership_confirmed_by": plan.confirmed_by,
                }
            },
            allocation_model={},
        )
        stored = store.write(bundle, key)
        return record, execution, stored
