"""Deterministic provider-runtime double for contract and CLI validation.

This runtime never contacts a provider and never claims hardware evidence. It
exists to exercise controller sequencing, timeout handling, cleanup
reconciliation, and signed-bundle plumbing without credentials or spend.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .budget import TerminationResult
from .native_runner import NativeCommandResult
from .scheduler import ExperimentPlan

__all__ = ["DeterministicFakeRuntime", "fake_native_output"]


def fake_native_output(cycles: int) -> str:
    """Return safe, explicitly simulated native-shaped output."""
    record = {
        "kind": "aggregate",
        "probe_name": "native_driver_direct",
        "probe_version": "0.1.0-native",
        "buffer_size_bytes": 256,
        "block_size_bytes": 16,
        "measurement_hash": "sha256:" + "0" * 64,
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
            "backend": "deterministic-fake",
            "backend_is_real": "false",
            "measurement_path": "simulated",
            "container_profile": "simulated",
        },
        "timing_ns": 0,
    }
    return "\n".join(
        [*(json.dumps(record) for _ in range(cycles)),
         json.dumps({"kind": "summary", "mode": "reuse", "cycles": cycles})]
    )


@dataclass(frozen=True)
class FakeAllocation:
    sequence: int


@dataclass
class DeterministicFakeRuntime:
    """A predictable runtime with no network, credentials, or real GPU."""

    stdout: str | None = None
    returncode: int = 0
    simulated_duration_s: int = 0
    force_timeout: bool = False
    launch_error: Exception | None = None
    termination: TerminationResult = field(
        default_factory=lambda: TerminationResult.success(0.0)
    )
    launched: list[ExperimentPlan] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)
    terminated: list[FakeAllocation] = field(default_factory=list)
    _next_sequence: int = field(default=1, init=False, repr=False)

    def launch(self, plan: ExperimentPlan) -> FakeAllocation:
        if self.launch_error is not None:
            raise self.launch_error
        self.launched.append(plan)
        allocation = FakeAllocation(self._next_sequence)
        self._next_sequence += 1
        return allocation

    def execute(
        self, allocation: Any, command: list[str], timeout_s: int
    ) -> NativeCommandResult:
        del allocation
        self.commands.append(list(command))
        if self.force_timeout or self.simulated_duration_s > timeout_s:
            return NativeCommandResult(
                returncode=124,
                stdout="",
                stderr="deterministic fake timeout",
                timed_out=True,
            )
        cycles = int(command[command.index("--cycles") + 1])
        return NativeCommandResult(
            returncode=self.returncode,
            stdout=self.stdout if self.stdout is not None else fake_native_output(cycles),
        )

    def terminate(self, allocation: FakeAllocation) -> TerminationResult:
        self.terminated.append(allocation)
        return self.termination
