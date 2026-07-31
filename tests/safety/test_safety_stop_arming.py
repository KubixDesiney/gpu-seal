"""The §7.3 safety stop has two independent triggers, armed differently.

Added after a bug found by actually running the Phase 1 battery: the entropy
trigger was armed unconditionally, so every baseline measurement halted. Since
NVIDIA documents that ``cudaMalloc`` does not clear memory, a fresh allocation
returning high-entropy bytes is *expected* — it is the phenomenon the project
exists to measure, not an incident.

An always-on entropy stop would have made GPU-SEAL unable to take its own
primary measurement. These tests pin the corrected semantics so it cannot
regress in either direction: too loose (we sit on a stranger's data) or too
tight (we cannot measure anything).
"""

from __future__ import annotations

import os

import pytest

from gpu_seal.safety import (
    Boundary,
    CanarySet,
    SafeBuffer,
    SensitiveObservation,
    aggregate,
)

pytestmark = pytest.mark.safety


def _buf(payload: bytes) -> SafeBuffer:
    buf = SafeBuffer.acquire(max(len(payload), 4096), provenance="test:synthetic")
    buf.__enter__()
    buf.fill_via(lambda view: view.__setitem__(slice(0, len(payload)), payload))
    return buf


def _measure(payload: bytes, **kwargs):
    buf = _buf(payload)
    try:
        return aggregate(buf, None, probe_name="t", probe_version="0", **kwargs)
    finally:
        buf.destroy()


# ---------------------------------------------------------------------------
# Trigger 1: expect_zeroed — armed everywhere, because we made the assertion
# ---------------------------------------------------------------------------


def test_expect_zeroed_fires_on_shared_infrastructure():
    with pytest.raises(SensitiveObservation):
        _measure(os.urandom(4096), expect_zeroed=True, shared_infrastructure=True)


def test_expect_zeroed_fires_on_exclusive_hardware_too():
    """We asserted this should be clean. It is not. That is worth stopping for
    regardless of whose machine it is — a failed negative control means the
    probe is unreliable."""
    with pytest.raises(SensitiveObservation):
        _measure(os.urandom(4096), expect_zeroed=True, shared_infrastructure=False)


def test_expect_zeroed_does_not_fire_on_a_clean_buffer():
    rec = _measure(bytes(4096), expect_zeroed=True, shared_infrastructure=True)
    assert rec.sensitive_observation is False
    assert rec.zero_fraction == 1.0


# ---------------------------------------------------------------------------
# Trigger 2: entropy — armed ONLY on shared infrastructure
# ---------------------------------------------------------------------------


def test_entropy_trigger_fires_on_rented_infrastructure():
    """On a rented instance, high-entropy content we cannot account for means
    we may be holding someone else's data. Stop."""
    with pytest.raises(SensitiveObservation) as exc:
        _measure(os.urandom(65536), shared_infrastructure=True)
    assert "entropy_estimate" in str(exc.value)


def test_entropy_trigger_does_not_fire_on_exclusive_hardware():
    """The bug this test exists for.

    On the researcher's own workstation, high-entropy residue is the
    researcher's own previous kernel. Halting here measures nothing and blocks
    the baseline the project depends on.
    """
    rec = _measure(os.urandom(65536), shared_infrastructure=False)
    assert rec.sensitive_observation is False
    assert rec.entropy_estimate > 0.9  # genuinely high entropy, and allowed


def test_default_is_the_safe_value():
    """Forgetting the flag must err toward stopping, not toward proceeding."""
    with pytest.raises(SensitiveObservation):
        _measure(os.urandom(65536))  # no shared_infrastructure passed


# ---------------------------------------------------------------------------
# Owned canaries always win
# ---------------------------------------------------------------------------


def test_owned_canary_suppresses_both_triggers():
    """Finding our own marker is the experiment succeeding.

    Even on shared infrastructure, even with expect_zeroed set, a buffer whose
    contents we can authenticate as ours is not a sensitive observation.
    """
    cs = CanarySet.create()
    c = cs.mint(Boundary.SEQUENTIAL_ALLOCATION)
    payload = c.blob + os.urandom(65536)

    buf = _buf(payload)
    try:
        rec = aggregate(
            buf, cs,
            probe_name="t", probe_version="0",
            expect_zeroed=True,
            shared_infrastructure=True,
        )
    finally:
        buf.destroy()

    assert rec.owned_canary_match is True
    assert rec.sensitive_observation is False


# ---------------------------------------------------------------------------
# Probe-level plumbing
# ---------------------------------------------------------------------------


def test_probe_defaults_to_shared_infrastructure():
    from gpu_seal.cuda import SimulatedBackend
    from gpu_seal.probes import GlobalMemoryProbe

    backend = SimulatedBackend(pool_bytes=4 << 20)
    probe = GlobalMemoryProbe(backend, CanarySet.create())
    cycle = probe.fresh_allocation_observation(1 << 20)

    assert cycle.observation is not None
    assert cycle.observation.driver_metadata["shared_infrastructure"] == "true"
    # High-entropy simulated background on "shared" infra -> stop fires.
    assert cycle.safety_stop


def test_probe_records_the_flag_in_metadata():
    """The flag must be visible in the result, so a reader can see which
    stop conditions were armed when the measurement was taken."""
    from gpu_seal.cuda import SimulatedBackend
    from gpu_seal.probes import GlobalMemoryProbe

    backend = SimulatedBackend(pool_bytes=4 << 20)
    probe = GlobalMemoryProbe(
        backend, CanarySet.create(), shared_infrastructure=False
    )
    cycle = probe.fresh_allocation_observation(1 << 20)

    assert cycle.observation is not None
    assert cycle.observation.driver_metadata["shared_infrastructure"] == "false"
    assert not cycle.safety_stop
