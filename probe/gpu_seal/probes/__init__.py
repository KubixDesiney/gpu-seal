"""Probe families — CHARTER.md §9.

All thirteen families now have an implementation. What differs between them is
what the *hardware* permits, and that distinction is deliberately visible here
rather than buried:

Runs on the local RTX 3050 lab:
    §9.1  Environment inventory                  (environment)
    §9.2  Local / shared memory sanitisation     (memory_local)
    §9.3  Device-global VRAM read-before-write   (memory_global)
    §9.4  Framework allocator behaviour          (framework_allocator)
    §9.6  Device & namespace exposure inventory  (device_exposure)
    §9.7  Allocation-model classifier            (allocation_model)
    §9.8  Topology fingerprint instrument        (topology)

Implemented, but needs rented or specialised hardware to produce evidence:
    §9.5  Self-vs-self sequential canary   — needs two rentals; gated on D5
    §9.8b Same-model die separation        — needs N instances of one model
          (evaluation lives in gpu_seal.analysis.separability)
    §9.9  Coarse location consistency      — needs an instance with a network
                                             position worth checking
    §9.10 Attestation availability         — needs H100-class CC silicon
    §9.11 Application-channel binding      — controlled lab, owned endpoints
    §9.12 MIG temporal isolation           — needs A100/H100-class silicon

A probe in the second group refuses to produce a result on hardware that
cannot support it, rather than producing one that would have to be caveated
into meaninglessness. `MigTemporalProbe` raising `MigUnavailable` on a
consumer card is the design working.
"""

from .allocation_model import (
    AllocationEvidence,
    AllocationModelClassifier,
    Classification,
    measure_scheduling_gaps,
)
from .attestation import (
    AttestationEvidence,
    AttestationProbe,
    ChannelBindingAssessment,
    assess_channel_binding,
)
from .device_exposure import DeviceExposureProbe
from .device_exposure import PROBE_NAME as DEVICE_EXPOSURE_PROBE_NAME
from .environment import (
    EnvironmentInventory,
    EnvironmentInventoryProbe,
    ProviderClaims,
)
from .framework_allocator import FrameworkAllocatorProbe, PooledReuseCycle
from .framework_allocator import PROBE_NAME as FRAMEWORK_ALLOCATOR_PROBE_NAME
from .framework_allocator import PROBE_VERSION as FRAMEWORK_ALLOCATOR_PROBE_VERSION
from .framework_allocator import summarise as summarise_framework_allocator
from .location import Landmark, LocationProbe, RttSource, TcpRttSource
from .memory_global import (
    PROBE_NAME,
    PROBE_VERSION,
    GlobalMemoryProbe,
    ReuseCycle,
    summarise,
)
from .memory_local import LocalMemoryCycle, LocalMemoryProbe, SharedMemoryLaunch
from .mig_temporal import MigTemporalProbe, MigUnavailable
from .self_canary import AllocationLeg, SelfCanaryResult, interpret
from .topology import (
    CudaLatencySource,
    DeterministicLatencySource,
    TopologyCertificate,
    TopologyProbe,
    compare_certificates,
)

__all__ = [
    # §9.1
    "EnvironmentInventoryProbe",
    "EnvironmentInventory",
    "ProviderClaims",
    # §9.2
    "LocalMemoryProbe",
    "LocalMemoryCycle",
    "SharedMemoryLaunch",
    # §9.3
    "GlobalMemoryProbe",
    "ReuseCycle",
    "summarise",
    "PROBE_NAME",
    "PROBE_VERSION",
    # §9.4
    "FrameworkAllocatorProbe",
    "PooledReuseCycle",
    "summarise_framework_allocator",
    "FRAMEWORK_ALLOCATOR_PROBE_NAME",
    "FRAMEWORK_ALLOCATOR_PROBE_VERSION",
    # §9.5
    "AllocationLeg",
    "SelfCanaryResult",
    "interpret",
    # §9.6
    "DeviceExposureProbe",
    "DEVICE_EXPOSURE_PROBE_NAME",
    # §9.7
    "AllocationModelClassifier",
    "AllocationEvidence",
    "Classification",
    "measure_scheduling_gaps",
    # §9.8
    "TopologyProbe",
    "TopologyCertificate",
    "CudaLatencySource",
    "DeterministicLatencySource",
    "compare_certificates",
    # §9.9
    "LocationProbe",
    "Landmark",
    "RttSource",
    "TcpRttSource",
    # §9.10 / §9.11
    "AttestationProbe",
    "AttestationEvidence",
    "ChannelBindingAssessment",
    "assess_channel_binding",
    # §9.12
    "MigTemporalProbe",
    "MigUnavailable",
]
