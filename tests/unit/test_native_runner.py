"""Controller tests for the provider-ready native execution boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest

from gpu_seal.controller import (
    BudgetLedger,
    ExperimentPlan,
    NativeCommandResult,
    NativeExecutionError,
    NativeProviderRunner,
    NativeRunConfig,
    ProviderPolicy,
    ProviderPolicyMatrix,
    Scheduler,
    SpendLimits,
)
from gpu_seal.controller.evidence_store import EvidenceStore
from gpu_seal.evidence import SigningKey

TODAY = date(2026, 8, 3)


def _policy_matrix() -> ProviderPolicyMatrix:
    return ProviderPolicyMatrix(
        policies={
            "provider-a": ProviderPolicy(
                provider_code="provider-a",
                classification="full-probe-ok",
                policy_sources=["test policy"],
                reviewed_on=date(2026, 8, 1),
                reviewed_by="test reviewer",
                policy_version="test",
            )
        }
    )


def _scheduler() -> tuple[Scheduler, BudgetLedger]:
    ledger = BudgetLedger(
        limits=SpendLimits(
            per_run=10, per_provider=100, per_day=100, per_campaign=1000
        )
    )
    return Scheduler(policy_matrix=_policy_matrix(), ledger=ledger), ledger


def _plan(**overrides: object) -> ExperimentPlan:
    values: dict[str, object] = {
        "experiment_id": "exp_native_0001",
        "provider_code": "provider-a",
        "probe_name": "memory_global_read_before_write",
        "ownership_confirmation": "provider allocation owned by this account",
        "confirmed_by": "researcher",
        "estimated_cost": 2.0,
        "product_claim": "test-gpu",
    }
    values.update(overrides)
    return ExperimentPlan(**values)


def _native_output(cycles: int) -> str:
    lines: list[str] = []
    for _ in range(cycles):
        lines.append(
            json.dumps(
                {
                    "kind": "aggregate",
                    "probe_name": "native_driver_direct",
                    "probe_version": "0.1.0-native",
                    "buffer_size_bytes": 256,
                    "block_size_bytes": 16,
                    "measurement_hash": "sha256:" + "a" * 64,
                    "zero_fraction": 1.0,
                    "fixed_pattern_fraction": 1.0,
                    "entropy_estimate": 0.0,
                    "repeated_block_count": 15,
                    "distinct_block_count": 1,
                    "byte_histogram": [256] + [0] * 255,
                    "owned_canary_match": False,
                    "owned_canary_exact_matches": 0,
                    "owned_canary_longest_prefix": 0,
                    "driver_metadata": {
                        "backend": "gpu-seal-native",
                        "backend_is_real": "true",
                        "measurement_path": "driver_direct",
                        "device_name": "test-gpu",
                        "cuda_runtime_version": "12060",
                        "cuda_driver_version": "13010",
                    },
                    "timing_ns": 1,
                }
            )
        )
    lines.append(json.dumps({"kind": "summary", "mode": "reuse", "cycles": cycles}))
    return "\n".join(lines)


@dataclass
class FakeRuntime:
    stdout: str
    returncode: int = 0
    launched: list[ExperimentPlan] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)
    terminated: list[object] = field(default_factory=list)

    def launch(self, plan: ExperimentPlan) -> object:
        self.launched.append(plan)
        return object()

    def execute(
        self, allocation: object, command: list[str], timeout_s: int
    ) -> NativeCommandResult:
        self.commands.append(command)
        assert timeout_s == 3600
        return NativeCommandResult(self.returncode, self.stdout)

    def terminate(self, allocation: object) -> float:
        self.terminated.append(allocation)
        return 1.25


def test_provider_command_is_shared_scope_and_never_local_only():
    command = NativeRunConfig(binary=Path("/native/gpu-seal-native")).command()

    assert "--shared-infrastructure" in command
    assert "--local-only" not in command


def test_native_provider_run_is_gated_and_terminated_with_actual_cost():
    scheduler, ledger = _scheduler()
    runtime = FakeRuntime(stdout=_native_output(2))
    runner = NativeProviderRunner(scheduler, runtime)

    record, execution = runner.run(
        _plan(), NativeRunConfig(binary=Path("/native"), cycles=2),
        run_id="run_native_0001", today=TODAY
    )

    assert record.completed is True
    assert record.actual_cost == 1.25
    assert execution is not None
    assert len(execution.records) == 2
    assert len(runtime.launched) == 1
    assert len(runtime.terminated) == 1
    assert ledger.summary()["committed_total"] == 1.25


def test_native_failure_still_terminates_and_settles_cost():
    scheduler, ledger = _scheduler()
    runtime = FakeRuntime(stdout="", returncode=7)
    runner = NativeProviderRunner(scheduler, runtime)

    with pytest.raises(NativeExecutionError, match="exit code 7"):
        runner.run(
            _plan(), NativeRunConfig(binary=Path("/native")),
            run_id="run_native_0002", today=TODAY
        )

    assert len(runtime.terminated) == 1
    assert ledger.summary()["committed_total"] == 1.25


def test_provider_run_can_write_a_pinned_signed_bundle(tmp_path):
    scheduler, _ = _scheduler()
    runtime = FakeRuntime(stdout=_native_output(1))
    runner = NativeProviderRunner(scheduler, runtime)
    config = NativeRunConfig(
        binary=Path("/native"),
        cycles=1,
        container_digest="sha256:" + "b" * 64,
        git_commit="test-commit",
    )

    record, execution, stored = runner.run_and_store(
        _plan(),
        config,
        run_id="run_native_0003",
        key=SigningKey.generate(),
        store=EvidenceStore(tmp_path),
        today=TODAY,
    )

    assert record.completed is True
    assert execution.records[0].driver_metadata["container_profile"] == "pinned"
    assert stored.signature_verified is True
    assert stored.publishable is True
