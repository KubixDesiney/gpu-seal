"""Simulated and unpinned-container results can never be published.

Not a charter-numbered test — an addition made while building the backend.
The simulated backend exists so probe logic can be tested without a GPU, and
it can be configured to *always* return residue. Publishing that as a finding
would be fabrication.

The guard is mechanical rather than a matter of remembering, because "we would
never do that" is not a control.
"""

from __future__ import annotations

import pytest

from gpu_seal.cuda import SimulatedBackend
from gpu_seal.evidence import ResultBundle, SigningKey
from gpu_seal.evidence.result import ToolProvenance
from gpu_seal.probes import GlobalMemoryProbe
from gpu_seal.safety import CanarySet, EgressViolation

pytestmark = pytest.mark.safety

MIB = 1 << 20


def _bundle(*probes):
    return ResultBundle(
        experiment_id="exp_test",
        run_id="run_test",
        provider_code="provider-a",
        region_claim="region-1",
        product_claim="gpu-product-x",
        tool=ToolProvenance(version="0.1.0", commit="sha256:" + "ab" * 32),
        probes=list(probes),
    )


def _simulated_record():
    backend = SimulatedBackend(sanitises_on_free=False, pool_bytes=8 * MIB)
    probe = GlobalMemoryProbe(backend, CanarySet.create(), canary_stride=MIB)
    cycle = probe.same_process_reuse_cycle(2 * MIB)
    assert cycle.observation is not None
    return cycle.observation


def test_simulated_backend_is_marked_not_real():
    rec = _simulated_record()
    assert rec.driver_metadata["backend_is_real"] == "false"


def test_bundle_with_simulated_probe_cannot_be_published():
    rec = _simulated_record()
    bundle = _bundle(rec)
    assert bundle.simulated_probes == ["memory_global_read_before_write"]
    with pytest.raises(EgressViolation) as exc:
        bundle.clear_for_publication()
    assert "simulated backend" in str(exc.value)


def test_simulated_bundle_still_signs_and_verifies():
    """Unpublishable is not the same as unusable.

    A simulated bundle must still sign and verify so that local test runs
    exercise the full pipeline. It simply cannot be cleared for publication.
    """
    signed = _bundle(_simulated_record()).sign(SigningKey.generate())
    assert ResultBundle.verify(signed)
    assert signed["safety"]["automatic_publication_allowed"] is False


def test_unpinned_container_probe_cannot_be_published(monkeypatch):
    monkeypatch.setenv("GPU_SEAL_CONTAINER_PROFILE", "dev-unpinned")
    rec = _simulated_record()
    assert rec.driver_metadata["container_profile"] == "dev-unpinned"

    bundle = _bundle(rec)
    with pytest.raises(EgressViolation) as exc:
        bundle.clear_for_publication()
    # Simulation is checked first; both grounds are disqualifying.
    assert "simulated backend" in str(exc.value) or "unpinned" in str(exc.value)


def test_a_real_looking_record_in_a_pinned_container_can_be_published():
    """Negative control on the guard itself: it must not block everything."""
    rec = _simulated_record()
    clean = type(rec)(
        **{
            **rec.to_dict(),
            "driver_metadata": {
                "backend": "cupy",
                "backend_is_real": "true",
                "container_profile": "release",
            },
        }
    )
    bundle = _bundle(clean)
    bundle.clear_for_publication()  # must not raise
    assert bundle.sign(SigningKey.generate())["safety"][
        "automatic_publication_allowed"
    ]
