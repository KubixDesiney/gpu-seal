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
    CampaignControl,
    CanarySet,
    SafeBuffer,
    SensitiveObservation,
    aggregate,
)
from gpu_seal.safety.aggregation import _SpanSafety, _safety_stop_reason
from gpu_seal.safety.errors import NativeSafePathRequired

pytestmark = pytest.mark.safety


def _buf(payload: bytes, *, size: int | None = None) -> SafeBuffer:
    buf = SafeBuffer.acquire(
        size if size is not None else max(len(payload), 4096),
        provenance="test:synthetic",
    )
    buf.__enter__()
    buf.fill_via(lambda view: view.__setitem__(slice(0, len(payload)), payload))
    return buf


def _measure(payload: bytes, **kwargs):
    buf = _buf(payload)
    try:
        # This is explicitly the host-only simulation escape hatch. Direct
        # Python shared-infrastructure callers are tested to fail closed below.
        kwargs.setdefault("_simulation_only", True)
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
    assert str(exc.value) == (
        "Automatic safety stop: sensitive observation. Raw memory was destroyed; "
        "only a redacted stop record is available for review."
    )
    assert exc.value.stop_record.to_dict()["reason_code"] == "high_entropy_content"


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


def test_direct_python_shared_memory_path_fails_closed():
    with pytest.raises(NativeSafePathRequired):
        _measure(os.urandom(4096), _simulation_only=False)


# ---------------------------------------------------------------------------
# Trigger 3: minimum size — armed ONLY on shared infrastructure, same as entropy
#
# A buffer small or low-entropy enough that the entropy trigger cannot catch
# it (a single repeated byte measures zero entropy) is still fully revealed
# by the allowlisted exact byte_histogram and measurement_hash. See
# gpu_seal.safety.policy.MIN_SAFE_MEASUREMENT_BYTES.
# ---------------------------------------------------------------------------


def test_min_size_trigger_fires_on_rented_infrastructure_for_a_tiny_buffer():
    """A one-byte allocation's exact histogram alone reveals its content."""
    buf = SafeBuffer.acquire(1, provenance="test:synthetic")
    buf.__enter__()
    buf.fill_via(lambda view: view.__setitem__(0, 0xA5))
    with pytest.raises(SensitiveObservation) as exc:
        aggregate(
            buf, None, probe_name="t", probe_version="0", _simulation_only=True
        )
    assert exc.value.stop_record.to_dict()["reason_code"] == (
        "measurement_below_minimum"
    )


def test_min_size_trigger_does_not_fire_on_exclusive_hardware():
    """Same reasoning as the entropy trigger: on the researcher's own
    workstation, a tiny buffer is the researcher's own residue."""
    buf = SafeBuffer.acquire(1, provenance="test:synthetic")
    buf.__enter__()
    buf.fill_via(lambda view: view.__setitem__(0, 0xA5))
    rec = aggregate(
        buf, None, probe_name="t", probe_version="0", shared_infrastructure=False
    )
    assert rec.sensitive_observation is False


def test_min_size_trigger_does_not_fire_above_the_threshold():
    """The trigger must not swallow ordinary, adequately-sized measurements —
    only entropy governs a buffer already at or above the size floor."""
    rec = _measure(bytes(4096), shared_infrastructure=True)
    assert rec.sensitive_observation is False


# ---------------------------------------------------------------------------
# Owned canaries always win
# ---------------------------------------------------------------------------


def test_owned_canary_suppresses_both_triggers():
    """A canary authenticates only its exact span, never the allocation tail."""
    cs = CanarySet.create()
    c = cs.mint(Boundary.SEQUENTIAL_ALLOCATION)
    payload = c.blob + os.urandom(65536)

    buf = _buf(payload)
    try:
        aggregate(
            buf, cs,
            probe_name="t", probe_version="0",
            expect_zeroed=True,
            shared_infrastructure=True,
            _simulation_only=True,
        )
    except SensitiveObservation as stop:
        assert stop.stop_record.to_dict()["reason_code"] in {
            "unexpected_content",
            "high_entropy_content",
        }
    else:
        pytest.fail("unrelated random bytes bypassed the canary span guard")
    finally:
        buf.destroy()


def test_canary_plus_tiny_unknown_tail_cannot_bypass_small_buffer_guard():
    cs = CanarySet.create()
    canary = cs.mint(Boundary.SEQUENTIAL_ALLOCATION)
    buf = _buf(canary.blob + b"\xA5", size=len(canary.blob) + 1)
    try:
        with pytest.raises(SensitiveObservation) as stop:
            aggregate(
                buf,
                cs,
                probe_name="t",
                probe_version="0",
                shared_infrastructure=True,
                _simulation_only=True,
            )
        assert stop.value.stop_record.to_dict()["reason_code"] == (
            "measurement_below_minimum"
        )
    finally:
        buf.destroy()


def test_stopped_one_byte_observation_never_confirms_the_observed_value():
    buf = SafeBuffer.acquire(1, provenance="test:synthetic")
    buf.__enter__()
    buf.fill_via(lambda view: view.__setitem__(0, 0xA5))
    try:
        with pytest.raises(SensitiveObservation) as stop:
            aggregate(
                buf, None, probe_name="t", probe_version="0", _simulation_only=True
            )
        text = str(stop.value)
        assert "A5" not in text and "165" not in text
        payload = stop.value.stop_record.to_dict()
        assert set(payload) == {
            "probe_name",
            "probe_version",
            "reason_code",
            "size_bucket",
            "boundary",
            "operational_metadata",
            "sensitive_observation",
            "unknown_raw_retained",
            "unknown_memory_rendered",
            "canary_only_search",
        }
    finally:
        buf.destroy()


# ---------------------------------------------------------------------------
# Probe-level plumbing
# ---------------------------------------------------------------------------


def test_probe_defaults_to_shared_infrastructure():
    from gpu_seal.cuda import SimulatedBackend
    from gpu_seal.probes import GlobalMemoryProbe

    backend = SimulatedBackend(pool_bytes=4 << 20)
    probe = GlobalMemoryProbe(
        backend, CanarySet.create(), campaign=CampaignControl.create()
    )
    cycle = probe.fresh_allocation_observation(1 << 20)

    assert cycle.observation is not None
    assert cycle.observation.operational_metadata["shared_infrastructure"] == "true"
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


@pytest.mark.parametrize(
    ("zero_fraction", "entropy", "size", "expect_zeroed", "shared"),
    [
        (1.0, 0.0, 256, False, True),
        (0.989999, 0.0, 256, True, False),
        (0.989999, 0.0, 256, True, True),
        (1.0, 0.850001, 256, False, True),
        (1.0, 0.85, 256, False, True),
        (1.0, 0.0, 255, False, True),
        (1.0, 0.99, 255, False, False),
    ],
)
def test_python_stop_decisions_match_native_safety_vector_reference(
    zero_fraction: float,
    entropy: float,
    size: int,
    expect_zeroed: bool,
    shared: bool,
):
    """The Python safety gate must remain equivalent to native's CLI contract."""
    native_reference = (
        (expect_zeroed and zero_fraction < 0.99)
        or (shared and entropy > 0.85)
        or (shared and size < 256)
    )
    python_reason = _safety_stop_reason(
        [_SpanSafety(size=size, zero_fraction=zero_fraction, entropy=entropy)],
        expect_zeroed=expect_zeroed,
        shared_infrastructure=shared,
    )
    assert (python_reason is not None) is native_reference
