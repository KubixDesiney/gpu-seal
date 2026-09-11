"""Topology fingerprint instrument — CHARTER.md §9.8.

**Reproduced, not claimed.** Alpay & Alpay (2026), *Unprivileged Topology
Certificates for Cloud GPU Attestation* (arXiv:2606.24934), published this
primitive in June 2026 with a 6-hour RTX 5090 run showing median temporal
jitter of 0.09 cycles and 100% leave-one-out separation across Blackwell dies.
CHARTER.md §0 amendment A2 demotes it from a GPU-SEAL contribution to an
instrument GPU-SEAL *consumes*. §9.8's success criterion is therefore
**reproduction fidelity, not novelty**, and this module reports itself as a
reproduction everywhere it can.

What it measures: an SM-by-memory-region latency matrix, using physical SM
labels (``%smid``) and dependent global loads. Each block chases a randomised
pointer cycle confined to one memory region, times the chain with the per-SM
cycle counter, and reports the cycles-per-hop it saw. Repeated over regions
and repetitions, the matrix takes on a shape determined by how that particular
die's SMs are wired to its memory system.

**No unknown memory is involved anywhere in this probe.** The pointer-chase
array is written by us before it is read, so every byte the kernel loads is a
byte we placed there. That is why this module does not use ``SafeBuffer``: it
never holds memory GPU-SEAL did not write, and routing our own index array
through the unknown-memory containment layer would misrepresent what is being
handled.

**Fidelity is declared, never assumed.** Reading ``%smid`` requires runtime
kernel compilation. Where that is unavailable the instrument degrades to
region-resolved timing without SM labels, which is a weaker fingerprint, and
the certificate says so in :attr:`TopologyCertificate.fidelity` rather than
presenting a reduced measurement as the published one.

**Limitations, restated on every certificate** (§9.8, and inherited from the
source paper's §12): driver version, thermal state, concurrent load, and
provider scheduling all add noise; a signature is not a unique immutable
serial; and **same-model die separation is not supported** — the source
experiment separates two Blackwell *products*, and separating two dies of one
model is contribution D5, still open. §9.5 is gated on that gap, and
:mod:`gpu_seal.analysis.separability` is where the gap gets measured.
"""

from __future__ import annotations

import hashlib
import statistics
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..evidence.observation import ObservationRecord
from ..safety.campaign import CampaignControl
from ..safety.policy import CONSISTENCY_BANDS

__all__ = [
    "TopologyCertificate",
    "TopologyProbe",
    "LatencySource",
    "CudaLatencySource",
    "DeterministicLatencySource",
    "compare_certificates",
    "PUBLISHED_JITTER_BASELINE_CYCLES",
    "PROBE_NAME",
    "PROBE_VERSION",
]

PROBE_NAME = "topology_fingerprint"
PROBE_VERSION = "0.2.0"

#: Median temporal jitter reported by Alpay & Alpay for a 6-hour full-load
#: RTX 5090 run. §9.8 asks us to characterise our own per-SM jitter *against*
#: this number; it is the reproduction target, not a threshold to pass.
PUBLISHED_JITTER_BASELINE_CYCLES = 0.09

#: Dependent global loads confined to one memory region. The `volatile` and
#: the impossible-branch sink both exist to stop the compiler proving the
#: chain dead and deleting the thing being measured.
TOPOLOGY_KERNEL_SOURCE = r"""
extern "C" __global__ void sm_region_latency(
    const unsigned int* __restrict__ chase,
    unsigned int region_base,
    unsigned int hops,
    unsigned int* __restrict__ out_sm,
    unsigned long long* __restrict__ out_cycles)
{
    unsigned int smid;
    asm volatile("mov.u32 %0, %%smid;" : "=r"(smid));

    unsigned int idx = region_base + threadIdx.x;

    // Untimed warm-up so the measured window is steady-state, not first-touch.
    for (unsigned int i = 0; i < 32u; ++i) {
        idx = chase[idx];
    }

    __syncthreads();
    unsigned long long t0 = clock64();
    for (unsigned int i = 0; i < hops; ++i) {
        idx = chase[idx];
    }
    unsigned long long t1 = clock64();

    unsigned int slot = blockIdx.x;
    if (threadIdx.x == 0) {
        out_sm[slot] = smid;
        out_cycles[slot] = t1 - t0;
    }
    // Never taken. Keeps `idx` live so the chain cannot be elided.
    if (idx == 0xFFFFFFFFu) {
        out_sm[slot] = idx;
    }
}
"""

TOPOLOGY_KERNEL_NAME = "sm_region_latency"


def kernel_source_hash() -> str:
    """SHA-256 of the measurement kernel. Goes in the certificate (§10).

    A certificate is only comparable to another certificate produced by the
    same kernel. Committing the hash is what lets a verifier — who has no GPU —
    reject a comparison between measurements that were never measuring the
    same thing.
    """
    return "sha256:" + hashlib.sha256(
        TOPOLOGY_KERNEL_SOURCE.encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Latency sources
# ---------------------------------------------------------------------------


class LatencySource(ABC):
    """Produces cycles-per-hop samples labelled by SM and memory region."""

    #: ``sm_resolved`` — physical SM labels, the published method.
    #: ``region_only`` — no SM labels available on this toolchain.
    #: ``deterministic`` — a model, for testing probe logic. Never evidence.
    fidelity: str = "deterministic"

    @abstractmethod
    def sample(
        self, *, regions: int, blocks: int, hops: int
    ) -> list[tuple[int, int, float]]:
        """Return ``(sm_id, region, cycles_per_hop)`` for one sweep."""

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Device and configuration metadata for the certificate."""

    def close(self) -> None:  # pragma: no cover - overridden where needed
        return None


class CudaLatencySource(LatencySource):
    """The real instrument: dependent global loads, physical SM labels."""

    fidelity = "sm_resolved"

    def __init__(
        self,
        *,
        device_id: int = 0,
        region_bytes: int = 8 << 20,
        stride_bytes: int = 256,
    ) -> None:
        """
        Args:
            region_bytes: size of each memory region swept. Must exceed L2 by
                enough that the chase is served from device memory rather than
                cache — that is what makes the matrix reflect the memory
                system's wiring instead of the cache hierarchy's.
            stride_bytes: gap between successive chase targets. Larger than a
                cache line and larger than a typical prefetch window, so the
                loads stay dependent rather than being pipelined.
        """
        try:
            import cupy
        except ImportError as exc:  # pragma: no cover - depends on host
            raise RuntimeError(
                "CuPy is not installed; the topology instrument needs runtime "
                "kernel compilation to read physical SM labels."
            ) from exc

        self._cupy = cupy
        self._device_id = device_id
        self._region_bytes = region_bytes
        self._stride_bytes = stride_bytes

        cupy.cuda.runtime.setDevice(device_id)
        self._props = cupy.cuda.runtime.getDeviceProperties(device_id)
        self._kernel = cupy.RawKernel(TOPOLOGY_KERNEL_SOURCE, TOPOLOGY_KERNEL_NAME)
        self._chase: Any = None
        self._region_elements = 0

    # -- chase construction ------------------------------------------------

    def _build_chase(self, regions: int) -> None:
        """One randomised cycle per region, confined to that region.

        Confinement is the whole point: a chain that wanders across regions
        measures an average of the memory system rather than the position in
        it, and the matrix collapses.

        The permutation is built on the host with NumPy and uploaded once,
        rather than generated on the device. That is deliberate — a
        device-side RNG would make the chase layout depend on which CUDA
        libraries happen to be installed, and two certificates are only
        comparable if the chase they walked was identical. Seeding per region
        means a re-run on the same device rebuilds the same layout, so the
        jitter figure measures the device rather than the layout.
        """
        import numpy

        element_bytes = 4
        stride_elements = max(self._stride_bytes // element_bytes, 1)
        per_region = self._region_bytes // element_bytes
        nodes = per_region // stride_elements

        indices = numpy.arange(regions * per_region, dtype=numpy.uint32)

        for region in range(regions):
            base = region * per_region
            order = numpy.random.default_rng(0x5EA1 + region).permutation(nodes)
            targets = (base + order * stride_elements).astype(numpy.uint32)
            sources = (base + numpy.roll(order, 1) * stride_elements).astype(
                numpy.uint32
            )
            indices[sources] = targets

        self._chase = self._cupy.asarray(indices)
        self._region_elements = per_region

    # -- measurement -------------------------------------------------------

    def sample(
        self, *, regions: int, blocks: int, hops: int
    ) -> list[tuple[int, int, float]]:
        cupy = self._cupy
        if self._chase is None:
            self._build_chase(regions)

        out_sm = cupy.zeros(blocks, dtype=cupy.uint32)
        out_cycles = cupy.zeros(blocks, dtype=cupy.uint64)

        samples: list[tuple[int, int, float]] = []
        for region in range(regions):
            self._kernel(
                (blocks,),
                (32,),
                (
                    self._chase,
                    cupy.uint32(region * self._region_elements),
                    cupy.uint32(hops),
                    out_sm,
                    out_cycles,
                ),
            )
            cupy.cuda.runtime.deviceSynchronize()
            sm_ids = out_sm.get().tolist()
            cycles = out_cycles.get().tolist()
            for sm_id, cycle_count in zip(sm_ids, cycles, strict=True):
                samples.append((int(sm_id), region, cycle_count / hops))
        return samples

    def describe(self) -> dict[str, Any]:
        props = self._props
        return {
            "multiprocessor_count": int(props.get("multiProcessorCount", 0)),
            "compute_capability": (
                f"{props.get('major', '?')}.{props.get('minor', '?')}"
            ),
            "l2_cache_bytes": int(props.get("l2CacheSize", 0)),
            "memory_bus_width_bits": int(props.get("memoryBusWidth", 0)),
            "region_bytes": self._region_bytes,
            "stride_bytes": self._stride_bytes,
        }

    def close(self) -> None:
        self._chase = None


class DeterministicLatencySource(LatencySource):
    """A model of a stable device. For testing probe logic only.

    Gives each (SM, region) pair a fixed latency plus reproducible jitter, so
    the certificate builder, the jitter statistics, and the comparison logic
    can all be exercised in CI with no GPU. ``fidelity`` is
    ``deterministic``, and :meth:`TopologyCertificate.is_evidence` is false
    for anything built from it.
    """

    fidelity = "deterministic"

    def __init__(
        self,
        *,
        sm_count: int = 8,
        die_seed: int = 1,
        jitter_cycles: float = 0.05,
    ) -> None:
        self._sm_count = sm_count
        self._die_seed = die_seed
        self._jitter = jitter_cycles
        self._tick = 0

    def sample(
        self, *, regions: int, blocks: int, hops: int
    ) -> list[tuple[int, int, float]]:
        samples: list[tuple[int, int, float]] = []
        for block in range(blocks):
            sm_id = block % self._sm_count
            for region in range(regions):
                base = 300.0 + ((sm_id * 7 + region * 13 + self._die_seed * 31) % 40)
                self._tick += 1
                wobble = self._jitter * (((self._tick * 2654435761) % 1000) / 1000 - 0.5)
                samples.append((sm_id, region, base + wobble))
        return samples

    def describe(self) -> dict[str, Any]:
        return {
            "multiprocessor_count": self._sm_count,
            "model_die_seed": self._die_seed,
            "region_bytes": 0,
            "stride_bytes": 0,
        }


# ---------------------------------------------------------------------------
# Certificate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TopologyCertificate:
    """Sufficient statistics for a topology fingerprint — CHARTER.md §9.8.

    Holds summary statistics rather than raw samples, which is the design in
    the source paper: a verifier with no GPU checks the certificate, and
    shipping millions of raw timings would neither help them nor survive the
    §10 evidence-size discipline.
    """

    kernel_hash: str
    fidelity: str
    regions: int
    hops: int
    repetitions: int

    #: median cycles-per-hop, indexed [sm_index][region]. The fingerprint.
    latency_matrix: list[list[float]]
    #: Physical SM ids, in the row order of ``latency_matrix``.
    sm_labels: list[int]
    #: Per-cell median absolute deviation across repetitions, flattened.
    #: Compared against PUBLISHED_JITTER_BASELINE_CYCLES.
    jitter_cycles: list[float]

    device: dict[str, Any] = field(default_factory=dict)
    measured_at_utc: str = ""

    @property
    def is_evidence(self) -> bool:
        """False for anything a model produced. Mirrors ``backend_is_real``."""
        return self.fidelity in ("sm_resolved", "region_only")

    @property
    def median_jitter(self) -> float:
        return statistics.median(self.jitter_cycles) if self.jitter_cycles else 0.0

    @property
    def shape_features(self) -> list[float]:
        """Row-normalised matrix, flattened. The comparable part.

        Absolute latency moves with clock speed, thermal state, and driver
        version. What survives those is the *relative* structure — which SM is
        slow to which region — so comparison happens on the normalised shape,
        as in the source paper's shape-only classification.
        """
        features: list[float] = []
        for row in self.latency_matrix:
            mean = sum(row) / len(row) if row else 0.0
            if mean <= 0:
                features.extend(0.0 for _ in row)
            else:
                features.extend(value / mean for value in row)
        return features

    def to_dict(self) -> dict[str, Any]:
        return {
            "kernel_hash": self.kernel_hash,
            "fidelity": self.fidelity,
            "is_evidence": self.is_evidence,
            "regions": self.regions,
            "hops": self.hops,
            "repetitions": self.repetitions,
            "sm_labels": self.sm_labels,
            "latency_matrix": [
                [round(value, 4) for value in row] for row in self.latency_matrix
            ],
            "median_jitter_cycles": round(self.median_jitter, 6),
            "published_jitter_baseline_cycles": PUBLISHED_JITTER_BASELINE_CYCLES,
            "device": self.device,
            "measured_at_utc": self.measured_at_utc,
            "reproduction_of": (
                "Alpay & Alpay 2026, arXiv:2606.24934 — reproduced as an "
                "instrument, not claimed as a contribution (CHARTER.md §0 A2)"
            ),
            "limitations": [
                "driver version, thermal state, concurrent load, and provider "
                "scheduling all add noise",
                "a signature is not a unique immutable serial; hardware claims "
                "are probabilistic",
                "same-model die separation is NOT supported by this instrument "
                "(contribution D5, §9.8b, still open)",
            ],
        }


# ---------------------------------------------------------------------------


class TopologyProbe:
    """Build a topology certificate from repeated latency sweeps."""

    NAME = PROBE_NAME
    VERSION = PROBE_VERSION

    def __init__(
        self, source: LatencySource, *, campaign: CampaignControl | None = None
    ) -> None:
        self._source = source
        self._campaign = campaign or CampaignControl.create()

    def certify(
        self,
        *,
        regions: int = 8,
        blocks: int = 32,
        hops: int = 512,
        repetitions: int = 5,
    ) -> TopologyCertificate:
        self._campaign.check()
        if repetitions < 2:
            raise ValueError(
                "at least 2 repetitions are required; jitter is the point of "
                "this measurement and one sweep cannot show it"
            )

        # (sm, region) -> one median per repetition
        per_repetition: dict[tuple[int, int], list[float]] = {}
        for _ in range(repetitions):
            self._campaign.check()
            sweep: dict[tuple[int, int], list[float]] = {}
            for sm_id, region, cycles in self._source.sample(
                regions=regions, blocks=blocks, hops=hops
            ):
                sweep.setdefault((sm_id, region), []).append(cycles)
            for key, values in sweep.items():
                per_repetition.setdefault(key, []).append(statistics.median(values))

        sm_labels = sorted({sm for sm, _ in per_repetition})
        matrix: list[list[float]] = []
        jitter: list[float] = []
        for sm_id in sm_labels:
            row: list[float] = []
            for region in range(regions):
                region_values = per_repetition.get((sm_id, region))
                if not region_values:
                    # An SM that never received a block for this region. Recorded
                    # as zero and excluded from jitter rather than interpolated —
                    # inventing a cell would forge part of the fingerprint.
                    row.append(0.0)
                    continue
                row.append(statistics.median(region_values))
                jitter.append(_median_absolute_deviation(region_values))
            matrix.append(row)

        return TopologyCertificate(
            kernel_hash=kernel_source_hash(),
            fidelity=self._source.fidelity,
            regions=regions,
            hops=hops,
            repetitions=repetitions,
            latency_matrix=matrix,
            sm_labels=sm_labels,
            jitter_cycles=jitter,
            device=self._source.describe(),
            measured_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def observation(
        self, certificate: TopologyCertificate, *, advertised_gpu: str
    ) -> ObservationRecord:
        """The §13.3 hardware-claim-consistency input.

        Deliberately conservative. This instrument recovers a *class* signature
        — memory-domain structure, die count, bandwidth tier. It does not
        recover a model number, and it cannot tell one H100 from another. So
        the strongest thing it may report about an advertised model is that
        the observed structure is not inconsistent with it.
        """
        self._campaign.check()
        jitter = certificate.median_jitter
        stable = jitter <= PUBLISHED_JITTER_BASELINE_CYCLES * 10

        return ObservationRecord(
            probe_name=self.NAME,
            probe_version=self.VERSION,
            subject="topology_fingerprint_stability",
            category="hardware_claim",
            classification="probably_consistent" if stable else "ambiguous",
            value={
                "median_jitter_cycles": round(jitter, 6),
                "published_baseline_cycles": PUBLISHED_JITTER_BASELINE_CYCLES,
                "sm_count": len(certificate.sm_labels),
                "advertised_gpu": advertised_gpu,
            },
            confidence=0.6 if stable else 0.2,
            evidence=[
                f"per-cell median jitter {jitter:.4f} cycles over "
                f"{certificate.repetitions} repetitions",
                f"{len(certificate.sm_labels)} physical SM labels observed",
                f"reproduction fidelity: {certificate.fidelity}",
            ],
            limitations=TopologyCertificate.to_dict(certificate)["limitations"]
            + [
                "reproduction of a published instrument; success criterion is "
                "fidelity, not novelty (CHARTER.md §9.8)",
                "consistency with an advertised model is reported as "
                "'not inconsistent', never as confirmation of the model",
            ],
            # A certificate from a model rather than silicon is not evidence
            # (see TopologyCertificate.is_evidence) and must not be able to
            # ride into an automatically publishable bundle alongside it.
            blocks_publication=not certificate.is_evidence,
        )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsistencyResult:
    """Whether two certificates are consistent with the same physical device."""

    band: str
    distance: float
    #: False whenever the pair shares an advertised model, until D5 lands.
    supports_same_device_claim: bool
    reasons: list[str]

    def __post_init__(self) -> None:
        if self.band not in CONSISTENCY_BANDS:
            raise ValueError(f"{self.band!r} is not one of {CONSISTENCY_BANDS}")


def compare_certificates(
    a: TopologyCertificate,
    b: TopologyCertificate,
    *,
    same_advertised_model: bool,
    same_model_classifier_validated: bool = False,
    threshold: float = 0.02,
) -> ConsistencyResult:
    """Compare two fingerprints. Never returns a same-device *proof*.

    The v2 gate (CHARTER.md §9.5, §13.1, §16 test 16) lives here as well as in
    the grader, because a caller who reads only this function must still be
    told that a small distance between two same-model certificates does not
    establish continuity. Alpay & Alpay separate two Blackwell *products*;
    separating two dies of one model is D5 and is not done.
    """
    reasons: list[str] = []

    if a.kernel_hash != b.kernel_hash:
        return ConsistencyResult(
            band="not_testable",
            distance=float("inf"),
            supports_same_device_claim=False,
            reasons=[
                "the two certificates were produced by different measurement "
                "kernels and are not comparable"
            ],
        )

    features_a, features_b = a.shape_features, b.shape_features
    if not features_a or len(features_a) != len(features_b):
        return ConsistencyResult(
            band="not_testable",
            distance=float("inf"),
            supports_same_device_claim=False,
            reasons=[
                "the certificates have different matrix shapes; the devices "
                "expose different SM or region counts"
            ],
        )

    distance = sum(
        abs(x - y) for x, y in zip(features_a, features_b, strict=True)
    ) / len(features_a)

    if distance <= threshold:
        band = "probably_consistent"
        reasons.append(
            f"mean shape distance {distance:.5f} is within the {threshold} "
            f"threshold"
        )
    elif distance <= threshold * 3:
        band = "ambiguous"
        reasons.append(
            f"mean shape distance {distance:.5f} is elevated but not separating"
        )
    else:
        band = "probably_inconsistent"
        reasons.append(
            f"mean shape distance {distance:.5f} exceeds {threshold * 3:.5f}"
        )

    supports = band == "probably_consistent"
    if same_advertised_model and not same_model_classifier_validated:
        supports = False
        reasons.append(
            "both allocations advertised the same GPU model, and same-model "
            "die separation (§9.8b, contribution D5) is not validated — this "
            "instrument cannot distinguish the same physical accelerator from "
            "a different one of the same model, so the comparison does not "
            "support a continuity claim regardless of the distance"
        )

    if not (a.is_evidence and b.is_evidence):
        supports = False
        reasons.append(
            "at least one certificate came from a model rather than silicon "
            "and is not evidence about hardware"
        )

    return ConsistencyResult(
        band=band,
        distance=distance,
        supports_same_device_claim=supports,
        reasons=reasons,
    )


def _median_absolute_deviation(values: list[float]) -> float:
    """Robust spread. Chosen over standard deviation because a single
    descheduled repetition would dominate a variance estimate and make a
    stable device look unstable."""
    if len(values) < 2:
        return 0.0
    median = statistics.median(values)
    return statistics.median([abs(value - median) for value in values])
