"""The enforced-safe layer.

Everything GPU-SEAL knows about memory it did not write passes through this
package. See CHARTER.md §7 (ethics model) and §8 (design principle: "safety is
centralised; all buffer handling passes through one enforced-safe layer; only
statistics leave a probe").

Import surface is deliberately small. If a probe needs something not exported
here, that is a design conversation, not an import.
"""

from .aggregation import AggregateRecord, aggregate
from .buffer import SafeBuffer, live_buffer_count
from .canary import Boundary, Canary, CanaryMatch, CanarySet
from .errors import (
    BufferLifecycleError,
    EgressViolation,
    ForeignCanaryError,
    LimitExceeded,
    PolicyViolation,
    SensitiveObservation,
    UnknownMemoryRenderError,
    UnknownMemoryRetentionError,
)

__all__ = [
    "AggregateRecord",
    "aggregate",
    "SafeBuffer",
    "live_buffer_count",
    "Boundary",
    "Canary",
    "CanaryMatch",
    "CanarySet",
    "PolicyViolation",
    "UnknownMemoryRenderError",
    "UnknownMemoryRetentionError",
    "BufferLifecycleError",
    "ForeignCanaryError",
    "LimitExceeded",
    "SensitiveObservation",
    "EgressViolation",
]
