"""Memory Probe B behaviour — CHARTER.md §9.3.

Runs against the simulated backend, which models a non-zeroing allocator with
a reuse pool. That is enough to test probe *logic*: does the read-before-write
ordering hold, does a planted canary get recovered when memory is reused, and
does it correctly NOT get recovered when memory is scrubbed.

It tests our code, not the world. Real conclusions require silicon.
"""

from __future__ import annotations

import pytest

from gpu_seal.cuda import SimulatedBackend
from gpu_seal.probes import GlobalMemoryProbe, summarise
from gpu_seal.safety import Boundary, CanarySet, live_buffer_count

MIB = 1 << 20


@pytest.fixture
def leaky_backend():
    """Models a provider that does NOT sanitise between allocations."""
    with SimulatedBackend(sanitises_on_free=False, pool_bytes=16 * MIB) as b:
        yield b


@pytest.fixture
def scrubbing_backend():
    """Models a provider that DOES sanitise on release."""
    with SimulatedBackend(sanitises_on_free=True, pool_bytes=16 * MIB) as b:
        yield b


def _probe(backend, stride=MIB):
    return GlobalMemoryProbe(backend, CanarySet.create(), canary_stride=stride)


# ---------------------------------------------------------------------------
# Positive control — the harness can detect a surviving canary
# ---------------------------------------------------------------------------


def test_canary_recovered_when_allocator_reuses_memory(leaky_backend):
    """CHARTER.md §11: without a working positive control, a negative cloud
    result proves nothing about the provider — only that we cannot detect."""
    probe = _probe(leaky_backend)
    cycle = probe.same_process_reuse_cycle(4 * MIB)

    assert cycle.usable, f"cycle excluded: {cycle.error_code}"
    assert cycle.canaries_planted >= 4
    assert cycle.canary_recovered, (
        "A non-sanitising allocator returned reused memory and the probe did "
        "not recover its own canary. The probe cannot detect residue, so no "
        "negative result from it means anything."
    )
    assert cycle.observation.owned_canary_exact_matches >= 1


def test_recovery_is_repeatable(leaky_backend):
    probe = _probe(leaky_backend)
    cycles = probe.run_cycles(MIB, repetitions=6, mode="reuse")
    stats = summarise(cycles)

    assert stats["cycles_usable"] == 6
    assert stats["recovery_rate"] == 1.0
    assert stats["cycles_excluded"] == 0


# ---------------------------------------------------------------------------
# Negative control — no false positives
# ---------------------------------------------------------------------------


def test_canary_not_recovered_when_memory_is_scrubbed(scrubbing_backend):
    probe = _probe(scrubbing_backend)
    cycle = probe.same_process_reuse_cycle(4 * MIB, expect_zeroed=False)

    assert cycle.usable, f"cycle excluded: {cycle.error_code}"
    assert cycle.canaries_planted >= 4
    assert not cycle.canary_recovered, (
        "Canary recovered from a scrubbed allocation — the probe reports false "
        "positives and every other result is void (CHARTER.md §19)."
    )
    assert cycle.observation.zero_fraction == pytest.approx(1.0)


def test_explicit_zeroisation_negative_control(leaky_backend):
    """Even on a leaky allocator, explicit zeroing must defeat recovery."""
    probe = _probe(leaky_backend)
    cycle = probe.zeroed_reuse_cycle(4 * MIB)

    assert cycle.usable, f"cycle excluded: {cycle.error_code}"
    assert cycle.canaries_planted >= 4
    assert not cycle.canary_recovered
    assert cycle.observation.zero_fraction == pytest.approx(1.0)


def test_negative_control_is_repeatable(scrubbing_backend):
    probe = _probe(scrubbing_backend)
    stats = summarise(probe.run_cycles(MIB, repetitions=6, mode="reuse"))
    assert stats["recovery_rate"] == 0.0


def test_foreign_canary_is_not_recovered(leaky_backend):
    """Another experiment's marker sitting in reused memory stays invisible.

    This is the canary-only guarantee tested end-to-end through the probe,
    not just at the CanarySet level.
    """
    foreign = CanarySet.create()
    foreign_marker = foreign.mint(Boundary.SEPARATE_PROCESS)

    alloc = leaky_backend.malloc(2 * MIB)
    leaky_backend.write_to_device(alloc, 0, foreign_marker.blob)
    leaky_backend.free(alloc)

    probe = _probe(leaky_backend)
    cycle = probe.fresh_allocation_observation(2 * MIB)

    assert cycle.usable
    assert not cycle.canary_recovered
    assert cycle.observation.owned_canary_exact_matches == 0


# ---------------------------------------------------------------------------
# Read-before-write discipline
# ---------------------------------------------------------------------------


def test_measurement_records_provenance_and_boundary(leaky_backend):
    probe = _probe(leaky_backend)
    cycle = probe.same_process_reuse_cycle(MIB, boundary=Boundary.SEPARATE_CONTEXT)
    md = cycle.observation.driver_metadata

    assert md["backend"] == "simulated"
    assert md["backend_is_real"] == "false"
    assert md["boundary"] == "SEPARATE_CONTEXT"
    assert cycle.observation.probe_name == "memory_global_read_before_write"
    assert cycle.observation.timing_ns is not None


def test_no_buffers_leak_after_a_campaign(leaky_backend):
    probe = _probe(leaky_backend)
    probe.run_cycles(MIB, repetitions=5, mode="reuse")
    assert live_buffer_count() == 0


def test_allocations_are_freed_even_when_a_cycle_fails(leaky_backend):
    """Pool exhaustion must not strand allocations, or later cycles all fail."""
    probe = _probe(leaky_backend)
    huge = probe.same_process_reuse_cycle(64 * MIB)  # larger than the pool
    assert not huge.usable
    assert huge.error_code == "MemoryError"

    # The pool must still be usable afterwards.
    ok = probe.same_process_reuse_cycle(2 * MIB)
    assert ok.usable, f"pool was left in a bad state: {ok.error_code}"


# ---------------------------------------------------------------------------
# Statistics and exclusions
# ---------------------------------------------------------------------------


def test_summarise_separates_excluded_cycles(leaky_backend):
    """CHARTER.md §12: report sample, success, failure, error, exclusion counts."""
    probe = _probe(leaky_backend)
    cycles = probe.run_cycles(MIB, repetitions=3, mode="reuse")
    cycles += [probe.same_process_reuse_cycle(64 * MIB)]  # will fail

    stats = summarise(cycles)
    assert stats["cycles_attempted"] == 4
    assert stats["cycles_usable"] == 3
    assert stats["cycles_excluded"] == 1
    assert stats["exclusion_reasons"] == ["MemoryError"]
    # Recovery rate is over USABLE cycles, never over attempted.
    assert stats["recovery_rate"] == 1.0


def test_summarise_handles_zero_usable_cycles():
    backend = SimulatedBackend(pool_bytes=MIB)
    probe = _probe(backend)
    stats = summarise(probe.run_cycles(64 * MIB, repetitions=2, mode="reuse"))
    assert stats["cycles_usable"] == 0
    assert stats["recovery_rate"] is None  # not 0.0 — undefined, not zero


def test_unknown_mode_is_rejected(leaky_backend):
    with pytest.raises(ValueError):
        _probe(leaky_backend).run_cycles(MIB, 1, mode="whatever")


# ---------------------------------------------------------------------------
# Safety stop integration
# ---------------------------------------------------------------------------


def test_safety_stop_is_captured_not_swallowed(leaky_backend):
    """A §7.3 stop must surface as a flagged cycle, not an exception or a loss."""
    probe = _probe(leaky_backend)
    # expect_zeroed on a leaky pool with no canary planted -> unexpected content
    cycle = probe.fresh_allocation_observation(2 * MIB, expect_zeroed=True)

    assert cycle.safety_stop
    assert cycle.observation is not None
    assert cycle.observation.sensitive_observation
    assert cycle.observation.unknown_raw_retained is False
