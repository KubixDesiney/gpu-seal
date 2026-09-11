"""A record must be stamped with the probe that produced it.

Found in a signed, publication-cleared bundle from a real GPU run
(`out/run_20260731T051751Z.result.json`). `FrameworkAllocatorProbe` composes
`GlobalMemoryProbe` for the read-before-write mechanics — correct, since
re-implementing safety-relevant logic twice is worse — but the composed probe
stamped **its own** name on the record. Every §9.4 control measurement was
therefore written into evidence as `memory_global_read_before_write`.

The bundle read:

    memory_global_read_before_write   n=40   recovered=10

i.e. "§9.3 recovered canaries in 10 of 40 cycles" — a residue finding. The
truth was the exact inverse: §9.3 recovered nothing in 30 cycles, and §9.4's
control recovered 10 of 10. The bundle was signature-valid, schema-valid, and
`automatic_publication_allowed: true`.

The measurement-path gate added earlier protects the *grader*. It could not
protect this, because the mislabelling happens upstream of grading, in the
evidence itself. Composition was the right design; inheriting the label was
not.
"""

from __future__ import annotations

import pytest

from gpu_seal.cuda import SimulatedBackend
from gpu_seal.probes import FrameworkAllocatorProbe, GlobalMemoryProbe
from gpu_seal.probes.framework_allocator import PROBE_NAME as FW_NAME
from gpu_seal.probes.memory_global import PROBE_NAME as MG_NAME
from gpu_seal.safety import CanarySet

pytestmark = pytest.mark.safety

MIB = 1 << 20


class _PooledSim(SimulatedBackend):
    """Simulated backend that presents as a caching allocator."""

    pooled = True
    measurement_path = "framework_pooled"


@pytest.fixture
def pooled():
    with _PooledSim(sanitises_on_free=False, pool_bytes=32 * MIB) as b:
        yield b


@pytest.fixture
def direct():
    with SimulatedBackend(sanitises_on_free=False, pool_bytes=32 * MIB) as b:
        yield b


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_framework_probe_stamps_its_own_name(pooled):
    """The exact defect. §9.4 records must not claim to be §9.3."""
    probe = FrameworkAllocatorProbe(
        pooled, CanarySet.create(), canary_stride=MIB, shared_infrastructure=False
    )
    cycle = probe.pooled_reuse_cycle(4 * MIB)

    assert cycle.observation is not None
    assert cycle.observation.probe_name == FW_NAME
    assert cycle.observation.probe_name != MG_NAME, (
        "A §9.4 detection-capability control record was stamped with §9.3's "
        "probe name. In an evidence bundle that reads as §9.3 finding residue "
        "when in fact the control was simply working."
    )


def test_global_probe_still_stamps_its_own_name(direct):
    """Negative control on the fix: §9.3 must keep its own identity."""
    probe = GlobalMemoryProbe(
        direct, CanarySet.create(), canary_stride=MIB, shared_infrastructure=False
    )
    cycle = probe.same_process_reuse_cycle(4 * MIB)
    assert cycle.observation is not None
    assert cycle.observation.probe_name == MG_NAME


def test_the_two_probes_are_distinguishable_in_a_mixed_batch(pooled, direct):
    """A Phase 1 bundle holds both. They must never merge under one name."""
    fw = FrameworkAllocatorProbe(
        pooled, CanarySet.create(), canary_stride=MIB, shared_infrastructure=False
    )
    mg = GlobalMemoryProbe(
        direct, CanarySet.create(), canary_stride=MIB, shared_infrastructure=False
    )

    records = [c.observation for c in fw.run_cycles(2 * MIB, 3)]
    records += [c.observation for c in mg.run_cycles(2 * MIB, 3, mode="reuse")]
    records = [r for r in records if r is not None]

    names = {r.probe_name for r in records}
    assert names == {FW_NAME, MG_NAME}, (
        f"a mixed batch collapsed to {names}; each record must carry the "
        f"identity of the probe that produced it"
    )
    assert sum(1 for r in records if r.probe_name == FW_NAME) == 3
    assert sum(1 for r in records if r.probe_name == MG_NAME) == 3


# ---------------------------------------------------------------------------
# Measurement path travels with the record
# ---------------------------------------------------------------------------


def test_backend_declares_measurement_path(pooled, direct):
    """The allocator decides the path, not the probe.

    It is the allocator that determines whether the driver is ever told the
    memory was released, so it is the allocator that must declare it.
    """
    assert pooled.measurement_path == "framework_pooled"
    assert direct.measurement_path == "simulated"
    assert pooled.device_info()["measurement_path"] == "framework_pooled"


def test_measurement_path_reaches_the_record(pooled):
    probe = FrameworkAllocatorProbe(
        pooled, CanarySet.create(), canary_stride=MIB, shared_infrastructure=False
    )
    cycle = probe.pooled_reuse_cycle(2 * MIB)
    md = cycle.observation.driver_metadata
    assert md["measurement_path"] == "framework_pooled"


def test_pooled_and_direct_paths_differ_in_the_record(pooled, direct):
    fw = FrameworkAllocatorProbe(
        pooled, CanarySet.create(), canary_stride=MIB, shared_infrastructure=False
    )
    mg = GlobalMemoryProbe(
        direct, CanarySet.create(), canary_stride=MIB, shared_infrastructure=False
    )

    a = fw.pooled_reuse_cycle(2 * MIB).observation.driver_metadata
    b = mg.same_process_reuse_cycle(2 * MIB).observation.driver_metadata
    assert a["measurement_path"] != b["measurement_path"]


def test_every_real_backend_declares_a_known_path():
    """A backend that forgets to declare its path must not read as gradeable."""
    from gpu_seal.cuda import CudaBackend
    from gpu_seal.reporting import MeasurementPath

    known = {p.value for p in MeasurementPath}
    assert CudaBackend.measurement_path == "unknown", (
        "the abstract base must default to the ungradeable value, so a new "
        "backend that forgets to declare a path cannot be graded"
    )
    for cls in (SimulatedBackend, _PooledSim):
        assert cls.measurement_path in known


def test_override_is_required_not_optional(pooled):
    """If read_before_write loses the override, §9.4 silently relabels again."""
    import inspect

    params = inspect.signature(GlobalMemoryProbe.read_before_write).parameters
    assert "probe_name" in params and "probe_version" in params, (
        "GlobalMemoryProbe.read_before_write must accept an identity override, "
        "or any probe composing it will stamp the wrong name on its records"
    )
