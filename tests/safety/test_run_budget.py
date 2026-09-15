"""Wall-clock run budget — ``gpu_seal.safety.budget.RunBudget``.

Covers the mechanism behind ``--max-runtime-s`` on the local-runner scripts:
a hard ceiling checked at cycle boundaries (``GlobalMemoryProbe.run_cycles``,
``FrameworkAllocatorProbe.run_cycles``) and at chunk boundaries inside the
read path (``gpu_seal.safety.aggregation``), so a hang or a slow scan cannot
burn a metered GPU allocation. See CHARTER.md's publication-gating ethos:
CHARTER.md §7.3's terminal-stop shape, applied to time instead of content.
"""

from __future__ import annotations

import time

import pytest

from gpu_seal.cuda import SimulatedBackend
from gpu_seal.probes import FrameworkAllocatorProbe, GlobalMemoryProbe, summarise
from gpu_seal.probes.framework_allocator import summarise as fw_summarise
from gpu_seal.safety import CanarySet, RunBudget, RunBudgetExceeded, SafeBuffer
from gpu_seal.safety.aggregation import _chunk_histogram, _measure

pytestmark = pytest.mark.safety

MIB = 1 << 20


class _CountingBudget:
    """Test double: expires after a fixed number of ``.check()`` calls.

    Both probes and ``aggregate()``/``_measure()`` only ever call
    ``budget.check()`` -- the contract is duck-typed, not tied to
    ``RunBudget`` specifically. Counting calls makes "the budget runs out
    mid-run" deterministic instead of racing a wall clock in a unit test.
    """

    def __init__(self, calls_before_expiry: int) -> None:
        self._remaining_calls = calls_before_expiry
        self.calls_made = 0

    def check(self) -> None:
        self.calls_made += 1
        if self._remaining_calls <= 0:
            raise RunBudgetExceeded("test budget exhausted")
        self._remaining_calls -= 1

    def expire_now(self) -> None:
        """Force the next ``check()`` to raise, regardless of the counter."""
        self._remaining_calls = 0


def _buffer_containing(payload: bytes, size: int | None = None) -> SafeBuffer:
    size = size or max(len(payload), 4096)
    buf = SafeBuffer.acquire(size, provenance="test:synthetic")
    buf.__enter__()

    def writer(view):
        view[: len(payload)] = payload

    buf.fill_via(writer)
    return buf


def _leaky_backend() -> SimulatedBackend:
    """Models a provider that does NOT sanitise between allocations."""
    return SimulatedBackend(sanitises_on_free=False, pool_bytes=16 * MIB)


# ---------------------------------------------------------------------------
# RunBudget itself
# ---------------------------------------------------------------------------


def test_run_budget_rejects_a_non_positive_duration():
    with pytest.raises(ValueError):
        RunBudget.start(0)
    with pytest.raises(ValueError):
        RunBudget.start(-1)


def test_run_budget_check_passes_before_the_deadline():
    budget = RunBudget.start(3600)
    budget.check()  # must not raise
    assert budget.expired is False
    assert budget.remaining_s > 0


def test_run_budget_check_raises_once_the_deadline_has_passed():
    # Construct directly with a deadline already in the past, rather than
    # sleeping, so the test is fast and cannot flake under CI load.
    budget = RunBudget(deadline_monotonic=time.monotonic() - 1)
    assert budget.expired is True
    with pytest.raises(RunBudgetExceeded):
        budget.check()


def test_run_budget_elapsed_and_remaining_move_in_opposite_directions():
    budget = RunBudget.start(3600)
    assert budget.elapsed_s >= 0
    assert budget.remaining_s <= 3600
    assert budget.remaining_s > 3600 - 5  # generous slack for slow CI


# ---------------------------------------------------------------------------
# Chunk boundary — gpu_seal.safety.aggregation
# ---------------------------------------------------------------------------


def test_chunk_histogram_checks_the_budget_at_every_chunk_boundary():
    """Four 1024-byte chunks over a 4096-byte span; the budget expires
    exactly at the second chunk boundary."""
    buf = _buffer_containing(bytes(4096))
    try:
        view = buf._unsafe_view("gpu_seal.safety.aggregation")
        try:
            budget = _CountingBudget(calls_before_expiry=1)
            with pytest.raises(RunBudgetExceeded):
                _chunk_histogram(view, 0, 4096, 1024, budget=budget)
            # Expired on the second chunk boundary check, not the first.
            assert budget.calls_made == 2
        finally:
            view.release()
    finally:
        buf.destroy()


def test_chunk_histogram_unaffected_when_budget_never_expires():
    buf = _buffer_containing(bytes(4096))
    try:
        view = buf._unsafe_view("gpu_seal.safety.aggregation")
        try:
            budget = RunBudget.start(3600)
            histogram = _chunk_histogram(view, 0, 4096, 1024, budget=budget)
            assert int(histogram[0]) == 4096  # an all-zero buffer
        finally:
            view.release()
    finally:
        buf.destroy()


def test_measure_checks_the_budget_at_block_pass_chunk_boundaries_too():
    """The block-fingerprint pass in ``_measure`` chunks independently of the
    histogram pass; both must be guarded."""
    buf = _buffer_containing(bytes(4096))
    try:
        view = buf._unsafe_view("gpu_seal.safety.aggregation")
        try:
            # Expire only after the histogram pass's single chunk check (one
            # span, one chunk at chunk_bytes=4096) so the failure is pinned to
            # the second pass's chunk loop, not the first.
            budget = _CountingBudget(calls_before_expiry=1)
            with pytest.raises(RunBudgetExceeded):
                _measure(view, [(0, 4096)], chunk_bytes=4096, budget=budget)
        finally:
            view.release()
    finally:
        buf.destroy()


# ---------------------------------------------------------------------------
# Cycle boundary — GlobalMemoryProbe.run_cycles / FrameworkAllocatorProbe.run_cycles
# ---------------------------------------------------------------------------


def test_run_cycles_stops_before_all_repetitions_when_the_budget_runs_out():
    """Mid-run expiry: the probe must not silently run to completion."""
    budget = _CountingBudget(calls_before_expiry=3)
    probe = GlobalMemoryProbe(
        _leaky_backend(),
        CanarySet.create(),
        canary_stride=MIB,
        shared_infrastructure=False,
        budget=budget,
    )
    with pytest.raises(RunBudgetExceeded):
        probe.run_cycles(MIB, repetitions=1000, mode="reuse")
    # A handful of checks fired, not anywhere near 1000 cycles' worth.
    assert budget.calls_made <= 10


def test_run_cycles_on_cycle_callback_fires_once_per_completed_cycle():
    seen: list[int] = []
    probe = GlobalMemoryProbe(
        _leaky_backend(),
        CanarySet.create(),
        canary_stride=MIB,
        shared_infrastructure=False,
    )
    cycles = probe.run_cycles(MIB, repetitions=4, mode="reuse", on_cycle=seen.append)
    assert seen == [0, 1, 2, 3]
    assert len(cycles) == 4


def test_run_cycles_on_cycle_is_not_called_for_a_cycle_that_never_completed():
    """Let two cycles complete normally, then expire the budget from inside
    the callback itself -- independent of how many internal liveness checks
    one cycle happens to make, cycle index 2 must never be reported as seen."""
    budget = _CountingBudget(calls_before_expiry=10_000)
    seen: list[int] = []

    def on_cycle(index: int) -> None:
        seen.append(index)
        if index == 1:
            budget.expire_now()

    probe = GlobalMemoryProbe(
        _leaky_backend(),
        CanarySet.create(),
        canary_stride=MIB,
        shared_infrastructure=False,
        budget=budget,
    )
    with pytest.raises(RunBudgetExceeded):
        probe.run_cycles(MIB, repetitions=1000, mode="reuse", on_cycle=on_cycle)

    assert seen == [0, 1]


def test_framework_allocator_run_cycles_also_honours_the_budget():
    pool_backend = SimulatedBackend(sanitises_on_free=False, pool_bytes=16 * MIB)
    budget = _CountingBudget(calls_before_expiry=2)
    probe = FrameworkAllocatorProbe(
        pool_backend,
        CanarySet.create(),
        canary_stride=MIB,
        shared_infrastructure=False,
        budget=budget,
    )
    with pytest.raises(RunBudgetExceeded):
        probe.run_cycles(MIB, repetitions=1000)


# ---------------------------------------------------------------------------
# A run inside budget is unchanged
# ---------------------------------------------------------------------------


def test_a_generous_budget_does_not_change_probe_outcomes():
    """CHARTER.md's positive control (§9.4-style reasoning): passing a budget
    that will not expire must reproduce exactly what running with no budget
    at all produces."""
    backend_a = _leaky_backend()
    backend_b = _leaky_backend()

    probe_no_budget = GlobalMemoryProbe(
        backend_a, CanarySet.create(), canary_stride=MIB,
        shared_infrastructure=False,
    )
    probe_with_budget = GlobalMemoryProbe(
        backend_b, CanarySet.create(), canary_stride=MIB,
        shared_infrastructure=False, budget=RunBudget.start(3600),
    )

    cycles_no_budget = probe_no_budget.run_cycles(MIB, repetitions=6, mode="reuse")
    cycles_with_budget = probe_with_budget.run_cycles(MIB, repetitions=6, mode="reuse")
    stats_no_budget = summarise(cycles_no_budget)
    stats_with_budget = summarise(cycles_with_budget)

    assert stats_with_budget["cycles_usable"] == stats_no_budget["cycles_usable"] == 6
    assert (
        stats_with_budget["recovery_rate"]
        == stats_no_budget["recovery_rate"]
        == 1.0
    )
    assert stats_with_budget["cycles_excluded"] == 0


def test_a_generous_budget_does_not_change_framework_allocator_outcomes():
    pool_a = SimulatedBackend(sanitises_on_free=False, pool_bytes=16 * MIB)
    pool_b = SimulatedBackend(sanitises_on_free=False, pool_bytes=16 * MIB)

    probe_no_budget = FrameworkAllocatorProbe(
        pool_a, CanarySet.create(), canary_stride=MIB, shared_infrastructure=False,
    )
    probe_with_budget = FrameworkAllocatorProbe(
        pool_b, CanarySet.create(), canary_stride=MIB, shared_infrastructure=False,
        budget=RunBudget.start(3600),
    )

    a = fw_summarise(probe_no_budget.run_cycles(MIB, repetitions=5))
    b = fw_summarise(probe_with_budget.run_cycles(MIB, repetitions=5))

    assert a["cycles_usable"] == b["cycles_usable"] == 5
    assert a["canary_recovered_cycles"] == b["canary_recovered_cycles"]
