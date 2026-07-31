"""Probe families — CHARTER.md §9.

Implemented:
    §9.3  Memory Probe B — device-global VRAM allocation  (memory_global)

Planned, in charter build order:
    §9.1  Environment inventory
    §9.6  Device & namespace exposure inventory
    §9.7  Allocation-model classifier
    §9.5  Self-vs-self sequential canary        (gated on §9.8b)
    §9.8  Topology fingerprint instrument       (reproduce Alpay & Alpay 2026)
    §9.8b Same-model die re-identification      (contribution D5)
    §9.12 MIG temporal isolation                (needs A100/H100-class hardware)
"""

from .memory_global import (
    PROBE_NAME,
    PROBE_VERSION,
    GlobalMemoryProbe,
    ReuseCycle,
    summarise,
)

__all__ = [
    "GlobalMemoryProbe",
    "ReuseCycle",
    "summarise",
    "PROBE_NAME",
    "PROBE_VERSION",
]
