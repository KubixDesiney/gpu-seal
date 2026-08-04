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

from ..evidence import ResultBundle, SigningKey
from ..evidence.result import ToolProvenance
from ..safety.aggregation import AggregateRecord
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


@dataclass(frozen=True)
class NativeCommandResult:
    """Output returned by a provider adapter after running the native binary."""

    returncode: int
    stdout: str
    stderr: str = ""


class ProviderRuntime(Protocol):
    """The narrow provider adapter contract.

    launch must create only the researcher's own allocation. execute must
    enforce the supplied timeout. terminate must be idempotent and must return
    the provider's final measured cost, including failed runs.
    """

    def launch(self, plan: ExperimentPlan) -> Any:
        """Create and return a provider-specific allocation handle."""

    def execute(
        self, allocation: Any, command: list[str], timeout_s: int
    ) -> NativeCommandResult:
        """Run the command inside the allocation with a hard timeout."""

    def terminate(self, allocation: Any) -> float:
        """Destroy the allocation and return the final actual cost."""


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

    records: tuple[AggregateRecord, ...]
    summary: dict[str, Any]


class NativeExecutionError(RuntimeError):
    """The native command failed without exposing raw device output."""


def parse_native_output(stdout: str, *, expected_cycles: int) -> NativeExecution:
    """Parse aggregate-only native output and reject ambiguous records."""
    records: list[AggregateRecord] = []
    summary: dict[str, Any] | None = None
    for line in stdout.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        kind = payload.pop("kind", None)
        if kind == "aggregate":
            records.append(AggregateRecord(**payload))
        elif kind == "summary" and summary is None:
            summary = payload
        else:
            raise NativeExecutionError("native output contained an unknown record kind")

    if summary is None or int(summary.get("cycles", -1)) != expected_cycles:
        raise NativeExecutionError(
            "native output summary did not match the requested cycles"
        )
    if len(records) != expected_cycles:
        raise NativeExecutionError(
            f"native returned {len(records)} aggregates, expected {expected_cycles}"
        )
    return NativeExecution(records=tuple(records), summary=summary)


class NativeProviderRunner:
    """Run the native agent only after the controller gates the experiment."""

    def __init__(self, scheduler: Scheduler, runtime: ProviderRuntime) -> None:
        self._scheduler = scheduler
        self._runtime = runtime

    def run(
        self,
        plan: ExperimentPlan,
        config: NativeRunConfig,
        *,
        run_id: str,
        today: date | None = None,
    ) -> tuple[ExperimentRun, NativeExecution | None]:
        """Launch, execute, and always terminate one native provider run."""
        allocation: Any = None
        final_cost = 0.0

        def work() -> NativeExecution:
            nonlocal allocation, final_cost
            allocation = self._runtime.launch(plan)
            try:
                completed = self._runtime.execute(
                    allocation, config.command(), plan.max_duration_s
                )
                if completed.returncode != 0:
                    raise NativeExecutionError(
                        f"native command failed with exit code {completed.returncode}"
                    )
                return parse_native_output(
                    completed.stdout, expected_cycles=config.cycles
                )
            finally:
                final_cost = self._runtime.terminate(allocation)

        return self._scheduler.run(
            plan,
            work,
            run_id=run_id,
            today=today,
            actual_cost=lambda: final_cost,
        )

    def run_and_store(
        self,
        plan: ExperimentPlan,
        config: NativeRunConfig,
        *,
        run_id: str,
        key: SigningKey,
        store: EvidenceStore,
        today: date | None = None,
    ) -> tuple[ExperimentRun, NativeExecution, StoredBundle]:
        """Run a provider battery and write it through the publication gate."""
        record, execution = self.run(
            plan, config, run_id=run_id, today=today
        )
        if execution is None:
            raise NativeExecutionError("native run returned no execution result")

        first_metadata = dict(execution.records[0].driver_metadata or {})
        records = tuple(
            replace(
                item,
                driver_metadata={
                    **dict(item.driver_metadata or {}),
                    "container_profile": config.container_profile,
                },
            )
            for item in execution.records
        )
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
