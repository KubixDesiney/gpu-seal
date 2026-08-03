"""Framework allocator probe behaviour — CHARTER.md §9.4.

Runs against the simulated backend (a free-list pool, which is what §9.4
measures on real hardware too: a caching allocator that never tells the
driver about a free). Tests probe *logic* only -- real evidence that a
caching allocator behaves this way requires ``PooledCupyBackend`` on silicon.
"""

from __future__ import annotations

import pytest

from gpu_seal.cuda import CudaBackend, SimulatedBackend
from gpu_seal.probes import FrameworkAllocatorProbe
from gpu_seal.probes.framework_allocator import summarise
from gpu_seal.safety import Boundary, CanarySet, live_buffer_count

MIB = 1 << 20


@pytest.fixture
def pooled_backend():
    """A caching allocator that does not sanitise on free -- the behaviour
    §9.4 exists to demonstrate the harness can detect."""
    with SimulatedBackend(sanitises_on_free=False, pool_bytes=16 * MIB) as b:
        yield b


def _probe(backend, stride=MIB):
    return FrameworkAllocatorProbe(
        backend, CanarySet.create(), canary_stride=stride, shared_infrastructure=False
    )


# ---------------------------------------------------------------------------
# The backend guard -- §9.4 must not silently run against a non-pooled backend
# ---------------------------------------------------------------------------


def test_rejects_non_pooled_backend():
    class RawBackend(CudaBackend):
        name = "raw"
        is_real = True
        pooled = False  # explicit, mirrors CupyBackend

        def device_info(self):
            return {}

        def malloc(self, size):
            raise NotImplementedError

        def free(self, alloc):
            raise NotImplementedError

        def copy_to_host(self, alloc, view):
            raise NotImplementedError

        def write_to_device(self, alloc, offset, data):
            raise NotImplementedError

        def fill_device(self, alloc, value):
            raise NotImplementedError

    with pytest.raises(ValueError, match="not a pooled"):
        FrameworkAllocatorProbe(
            RawBackend(), CanarySet.create(), shared_infrastructure=False
        )


def test_shared_infrastructure_has_no_default(pooled_backend):
    """A silent default to the value that disarms the entropy safety stop is
    exactly the kind of thing that must require a conscious choice."""
    with pytest.raises(TypeError, match="shared_infrastructure"):
        FrameworkAllocatorProbe(pooled_backend, CanarySet.create())


# ---------------------------------------------------------------------------
# Detection-capability control — the whole point of §9.4
# ---------------------------------------------------------------------------


def test_canary_recovered_through_the_pool(pooled_backend):
    probe = _probe(pooled_backend)
    cycle = probe.pooled_reuse_cycle(4 * MIB)

    assert cycle.usable, f"cycle excluded: {cycle.error_code}"
    assert cycle.canaries_planted >= 4
    assert cycle.canary_recovered, (
        "A caching allocator that never returns freed blocks to the driver "
        "did not hand back a recoverable canary. This is the harness's own "
        "detection-capability control (CHARTER.md §11) -- if it fails, no "
        "negative §9.3 result on a scrubbing platform means anything."
    )
    assert cycle.ptr_reused is True
    assert cycle.observation.owned_canary_exact_matches >= 1


def test_recovery_is_repeatable(pooled_backend):
    probe = _probe(pooled_backend)
    cycles = probe.run_cycles(MIB, repetitions=6)
    stats = summarise(cycles)

    assert stats["cycles_usable"] == 6
    assert stats["recovery_rate"] == 1.0
    assert stats["buffer_reuse_rate"] == 1.0
    assert stats["cycles_excluded"] == 0


def test_measurement_records_provenance_and_boundary(pooled_backend):
    probe = _probe(pooled_backend)
    cycle = probe.pooled_reuse_cycle(MIB, boundary=Boundary.SEPARATE_CONTEXT)
    md = cycle.observation.driver_metadata

    assert md["backend"] == "simulated"
    assert md["boundary"] == "SEPARATE_CONTEXT"

    # This assertion previously read `== "memory_global_read_before_write"`,
    # which codified the mislabelling as expected behaviour — the defect
    # shipped into a signed, publication-cleared bundle with a green test
    # covering it. A test that writes down the wrong expectation is worse
    # than no test: it converts a bug into a guarantee.
    assert cycle.observation.probe_name == "framework_allocator_reuse"

    # `simulated`, not `framework_pooled`: this fixture is a host-side model,
    # and provenance outranks allocator semantics. Both values are ungradeable
    # under the §13.1 measurement-path gate, but `simulated` is the more
    # truthful one — it says the record came from no hardware at all.
    # `framework_pooled` on real silicon is covered in
    # tests/safety/test_probe_identity_labelling.py.
    assert md["measurement_path"] == "simulated"


def test_no_buffers_leak_after_a_campaign(pooled_backend):
    probe = _probe(pooled_backend)
    probe.run_cycles(MIB, repetitions=5)
    assert live_buffer_count() == 0


def test_allocations_are_freed_even_when_a_cycle_fails(pooled_backend):
    probe = _probe(pooled_backend)
    huge = probe.pooled_reuse_cycle(64 * MIB)  # larger than the pool
    assert not huge.usable
    assert huge.error_code == "MemoryError"

    ok = probe.pooled_reuse_cycle(2 * MIB)
    assert ok.usable, f"pool was left in a bad state: {ok.error_code}"


def test_summarise_separates_excluded_cycles(pooled_backend):
    probe = _probe(pooled_backend)
    cycles = probe.run_cycles(MIB, repetitions=3)
    cycles += [probe.pooled_reuse_cycle(64 * MIB)]  # will fail

    stats = summarise(cycles)
    assert stats["cycles_attempted"] == 4
    assert stats["cycles_usable"] == 3
    assert stats["cycles_excluded"] == 1
    assert stats["exclusion_reasons"] == ["MemoryError"]
    assert stats["recovery_rate"] == 1.0


def test_summarise_handles_zero_usable_cycles():
    backend = SimulatedBackend(pool_bytes=MIB)
    probe = _probe(backend)
    stats = summarise(probe.run_cycles(64 * MIB, repetitions=2))
    assert stats["cycles_usable"] == 0
    assert stats["recovery_rate"] is None
    assert stats["buffer_reuse_rate"] is None
