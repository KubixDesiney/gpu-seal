"""The single safe egress door for memory measurements.

The Python implementation is intentionally limited to exclusive hardware and
the host-only simulation backend. Real shared-infrastructure acquisition and
aggregation belongs to the native agent, whose opaque buffer is explicitly
zeroized. This boundary prevents Python or NumPy from retaining an immutable
copy of unknown device memory.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from collections.abc import Container, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from .budget import RunBudget
from .buffer import SafeBuffer
from .canary import Boundary, CanaryMatch, CanarySet
from .errors import EgressViolation, NativeSafePathRequired, SensitiveObservation
from .policy import (
    ANALYSIS_BLOCK_SIZE,
    ENTROPY_STOP_THRESHOLD,
    EXPECTED_ZERO_FRACTION_FLOOR,
    MIN_SAFE_MEASUREMENT_BYTES,
    SAFE_AGGREGATE_KEYS,
    SAFE_STOP_METADATA_KEYS,
    SAFE_STOP_REASON_CODES,
    SAFE_STOP_SIZE_BUCKETS,
)

REDACTED_STOP_KEYS = frozenset(
    {
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
)

#: Bound on how much of a span is ever read in one slice during measurement.
#: Must be a multiple of ANALYSIS_BLOCK_SIZE so a chunk boundary always falls
#: on the same block grid a single unbounded pass would use -- see
#: ``_chunk_bounds``. This is an engineering knob, not an ethics constant
#: (contrast ``gpu_seal.safety.policy``): it bounds how much of a buffer is
#: converted to a NumPy view at once, not what GPU-SEAL is permitted to do.
ANALYSIS_CHUNK_BYTES = 8 * 1024 * 1024

__all__ = [
    "AggregateRecord",
    "CanaryOnlyRecord",
    "RedactedStopRecord",
    "REDACTED_STOP_KEYS",
    "aggregate",
]

CANARY_ONLY_KEYS = frozenset(
    {
        "probe_name",
        "probe_version",
        "boundary",
        "owned_canary_match",
        "owned_canary_exact_matches",
        "owned_canary_longest_prefix",
        "operational_metadata",
        "sensitive_observation",
        "unknown_raw_retained",
        "unknown_memory_rendered",
        "canary_only_search",
    }
)


@dataclass(frozen=True)
class AggregateRecord:
    """Safe statistics from all non-canary spans of an allocation."""

    probe_name: str
    probe_version: str
    buffer_size_bytes: int
    block_size_bytes: int
    measurement_hash: str
    zero_fraction: float
    fixed_pattern_fraction: float
    entropy_estimate: float
    repeated_block_count: int
    distinct_block_count: int
    byte_histogram: list[int]
    owned_canary_match: bool
    owned_canary_exact_matches: int
    owned_canary_longest_prefix: int
    sensitive_observation: bool = False
    unknown_raw_retained: bool = False
    unknown_memory_rendered: bool = False
    canary_only_search: bool = True
    driver_metadata: dict[str, str] | None = None
    error_code: str | None = None
    timing_ns: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise only the reviewed normal aggregate shape."""
        payload = {
            "probe_name": self.probe_name,
            "probe_version": self.probe_version,
            "buffer_size_bytes": self.buffer_size_bytes,
            "block_size_bytes": self.block_size_bytes,
            "measurement_hash": self.measurement_hash,
            "zero_fraction": self.zero_fraction,
            "fixed_pattern_fraction": self.fixed_pattern_fraction,
            "entropy_estimate": self.entropy_estimate,
            "repeated_block_count": self.repeated_block_count,
            "distinct_block_count": self.distinct_block_count,
            "byte_histogram": list(self.byte_histogram),
            "owned_canary_match": self.owned_canary_match,
            "owned_canary_exact_matches": self.owned_canary_exact_matches,
            "owned_canary_longest_prefix": self.owned_canary_longest_prefix,
            "sensitive_observation": self.sensitive_observation,
            "unknown_raw_retained": self.unknown_raw_retained,
            "unknown_memory_rendered": self.unknown_memory_rendered,
            "canary_only_search": self.canary_only_search,
            "driver_metadata": self.driver_metadata,
            "error_code": self.error_code,
            "timing_ns": self.timing_ns,
        }
        offending = set(payload) - SAFE_AGGREGATE_KEYS
        if offending:
            raise EgressViolation(
                f"Refusing to emit non-allowlisted keys {sorted(offending)}. "
                "Adding an egress field requires an ethics review."
            )
        return payload


@dataclass(frozen=True)
class CanaryOnlyRecord:
    """Normal MIG self-canary output with no unknown-memory statistics."""

    probe_name: str
    probe_version: str
    boundary: str
    owned_canary_match: bool
    owned_canary_exact_matches: int
    owned_canary_longest_prefix: int
    operational_metadata: dict[str, str]
    sensitive_observation: bool = False
    unknown_raw_retained: bool = False
    unknown_memory_rendered: bool = False
    canary_only_search: bool = True

    def __post_init__(self) -> None:
        if not self.probe_name or not self.probe_version:
            raise ValueError("canary-only identity is required")
        if self.boundary not in {item.name for item in Boundary}:
            raise ValueError("canary-only boundary must be a known boundary")
        if self.owned_canary_exact_matches < 0 or self.owned_canary_longest_prefix < 0:
            raise ValueError("canary-only match counts cannot be negative")
        if self.sensitive_observation is not False:
            raise ValueError("canary-only output cannot represent a safety stop")
        if self.unknown_raw_retained or self.unknown_memory_rendered:
            raise EgressViolation("canary-only output cannot retain unknown memory")
        if not self.canary_only_search:
            raise EgressViolation("canary-only output must retain its search claim")
        self._validate_operational_metadata()

    def _validate_operational_metadata(self) -> None:
        invalid = set(self.operational_metadata) - SAFE_STOP_METADATA_KEYS
        if invalid:
            raise EgressViolation(
                f"canary-only metadata contains non-operational fields: {sorted(invalid)}"
            )
        if any(
            not isinstance(value, str) for value in self.operational_metadata.values()
        ):
            raise EgressViolation("canary-only metadata values must be strings")

    @classmethod
    def from_aggregate(
        cls, record: AggregateRecord, *, boundary: Boundary
    ) -> CanaryOnlyRecord:
        metadata = {
            key: str(value)
            for key, value in (record.driver_metadata or {}).items()
            if key in SAFE_STOP_METADATA_KEYS
        }
        return cls(
            probe_name=record.probe_name,
            probe_version=record.probe_version,
            boundary=boundary.name,
            owned_canary_match=record.owned_canary_match,
            owned_canary_exact_matches=record.owned_canary_exact_matches,
            owned_canary_longest_prefix=record.owned_canary_longest_prefix,
            operational_metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        self._validate_operational_metadata()
        payload = {
            "probe_name": self.probe_name,
            "probe_version": self.probe_version,
            "boundary": self.boundary,
            "owned_canary_match": self.owned_canary_match,
            "owned_canary_exact_matches": self.owned_canary_exact_matches,
            "owned_canary_longest_prefix": self.owned_canary_longest_prefix,
            "operational_metadata": dict(self.operational_metadata),
            "sensitive_observation": False,
            "unknown_raw_retained": False,
            "unknown_memory_rendered": False,
            "canary_only_search": True,
        }
        if frozenset(payload) != CANARY_ONLY_KEYS:
            raise EgressViolation("canary-only shape changed without a policy review")
        return payload


@dataclass(frozen=True)
class RedactedStopRecord:
    """The only evidence that survives a sensitive observation.

    This type is deliberately not an ``AggregateRecord``. It has no histogram,
    digest, entropy, block information, canary count, or exact size. Those
    fields can reconstruct or confirm unknown content and must disappear before
    the stop leaves the safe layer.
    """

    probe_name: str
    probe_version: str
    reason_code: str
    size_bucket: str
    boundary: str
    operational_metadata: dict[str, str]
    sensitive_observation: bool = True
    unknown_raw_retained: bool = False
    unknown_memory_rendered: bool = False
    canary_only_search: bool = True

    def __post_init__(self) -> None:
        if self.reason_code not in SAFE_STOP_REASON_CODES:
            raise ValueError(f"unknown redacted stop reason {self.reason_code!r}")
        if self.sensitive_observation is not True:
            raise ValueError("a redacted stop record must be sensitive")
        if self.unknown_raw_retained or self.unknown_memory_rendered:
            raise EgressViolation("a stop record cannot claim a raw-memory leak")
        if not self.canary_only_search:
            raise EgressViolation("a stop record must retain the canary-only claim")
        if not self.probe_name or not self.probe_version:
            raise ValueError("redacted stop identity and size bucket are required")
        if self.size_bucket not in SAFE_STOP_SIZE_BUCKETS:
            raise ValueError("redacted stop size bucket is not a safe bucket")
        if self.boundary not in {item.name for item in Boundary}:
            raise ValueError("redacted stop boundary must be a known boundary")
        self._validate_operational_metadata()

    def _validate_operational_metadata(self) -> None:
        invalid = set(self.operational_metadata) - SAFE_STOP_METADATA_KEYS
        if invalid:
            raise EgressViolation(
                f"stop metadata contains non-operational fields: {sorted(invalid)}"
            )
        if any(
            not isinstance(value, str) for value in self.operational_metadata.values()
        ):
            raise EgressViolation("stop metadata values must be strings")

    def to_dict(self) -> dict[str, Any]:
        """Return exactly the redacted stop schema, never a normal record."""
        self._validate_operational_metadata()
        payload = {
            "probe_name": self.probe_name,
            "probe_version": self.probe_version,
            "reason_code": self.reason_code,
            "size_bucket": self.size_bucket,
            "boundary": self.boundary,
            "operational_metadata": dict(self.operational_metadata),
            "sensitive_observation": True,
            "unknown_raw_retained": False,
            "unknown_memory_rendered": False,
            "canary_only_search": True,
        }
        if frozenset(payload) != REDACTED_STOP_KEYS:
            raise EgressViolation("redacted stop shape changed without a policy review")
        return payload


@dataclass(frozen=True)
class _SpanSafety:
    size: int
    zero_fraction: float
    entropy: float


class _SensitiveSpan(Exception):
    """Internal control flow: stop before any later span is read."""

    def __init__(self, reason_code: str, size: int) -> None:
        self.reason_code = reason_code
        self.size = size


def aggregate(
    buf: SafeBuffer,
    owned_canaries: CanarySet | None = None,
    *,
    probe_name: str,
    probe_version: str,
    expect_zeroed: bool = False,
    shared_infrastructure: bool = True,
    driver_metadata: dict[str, str] | None = None,
    timing_ns: int | None = None,
    expected_allocation_ids: Container[uuid.UUID] | None = None,
    budget: RunBudget | None = None,
    _simulation_only: bool = False,
) -> AggregateRecord:
    """Reduce a SafeBuffer without copying unknown bytes.

    ``_simulation_only`` is private and is set only by ``GlobalMemoryProbe``
    for the host model. A real shared-infrastructure caller must use the native
    acquisition path; rejecting before ``_unsafe_view`` is the fail-closed
    guarantee.

    ``budget``, when supplied, is checked at every chunk boundary of the read
    path below (``_chunk_histogram`` and the block-fingerprint loop) so a hung
    or unexpectedly slow scan of a large allocation cannot run past the
    caller's wall-clock ceiling. A ``RunBudgetExceeded`` raised here is not
    caught: it propagates out of this function and destroys ``buf`` via the
    caller's ``with SafeBuffer.acquire(...)`` block, exactly like any other
    exception raised while filling or reading a buffer.
    """
    if shared_infrastructure and not _simulation_only:
        raise NativeSafePathRequired(
            "Python cannot safely process unknown memory on shared infrastructure; "
            "use the opaque native acquisition-and-aggregation path."
        )

    view = buf._unsafe_view("gpu_seal.safety.aggregation")
    try:
        matches: list[CanaryMatch] = []
        if owned_canaries is not None:
            matches = owned_canaries.search(
                view, allocation_id_scope=expected_allocation_ids
            )
        owned_spans = _merge_spans(
            span for match in matches for span in match.authenticated_spans
        )
        remaining_spans = _remaining_spans(len(view), owned_spans)
        try:
            stats = _measure(
                view,
                remaining_spans,
                expect_zeroed=expect_zeroed,
                shared_infrastructure=shared_infrastructure,
                budget=budget,
            )
        except _SensitiveSpan as sensitive:
            stop = _redacted_stop_record(
                probe_name=probe_name,
                probe_version=probe_version,
                reason_code=sensitive.reason_code,
                smallest_span=sensitive.size,
                driver_metadata=driver_metadata,
            )
            # Destroy before raising. The only retained object is ``stop``;
            # stats contain counts and fingerprints, never raw block values.
            buf.destroy()
            raise SensitiveObservation(stop_record=stop) from None

        exact = sum(1 for match in matches if match.exact)
        longest = max(
            (match.longest_prefix_bytes for match in matches), default=0
        )
        record = AggregateRecord(
            probe_name=probe_name,
            probe_version=probe_version,
            buffer_size_bytes=len(buf),
            block_size_bytes=ANALYSIS_BLOCK_SIZE,
            measurement_hash=_hash_spans(view, remaining_spans),
            zero_fraction=stats["zero_fraction"],
            fixed_pattern_fraction=stats["fixed_pattern_fraction"],
            entropy_estimate=stats["entropy_estimate"],
            repeated_block_count=stats["repeated_block_count"],
            distinct_block_count=stats["distinct_block_count"],
            byte_histogram=stats["byte_histogram"],
            owned_canary_match=exact > 0,
            owned_canary_exact_matches=exact,
            owned_canary_longest_prefix=longest,
            driver_metadata=driver_metadata,
            timing_ns=timing_ns,
        )
        return record
    finally:
        view.release()


def _merge_spans(spans: Any) -> tuple[tuple[int, int], ...]:
    ordered = sorted((start, end) for start, end in spans if start < end)
    merged: list[tuple[int, int]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _remaining_spans(
    size: int, owned_spans: Sequence[tuple[int, int]]
) -> tuple[tuple[int, int], ...]:
    remaining: list[tuple[int, int]] = []
    cursor = 0
    for start, end in owned_spans:
        start = max(0, min(size, start))
        end = max(start, min(size, end))
        if cursor < start:
            remaining.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < size:
        remaining.append((cursor, size))
    return tuple(remaining)


def _safety_stop_reason(
    spans: Sequence[_SpanSafety],
    *,
    expect_zeroed: bool,
    shared_infrastructure: bool,
) -> str | None:
    """Evaluate every remaining span independently.

    A canary only removes its authenticated range. It never authenticates the
    rest of an allocation, and a short tail remains subject to the minimum
    size guard even when the complete allocation is large.
    """
    for item in spans:
        if expect_zeroed and item.zero_fraction < EXPECTED_ZERO_FRACTION_FLOOR:
            return "unexpected_content"
        if shared_infrastructure and item.entropy > ENTROPY_STOP_THRESHOLD:
            return "high_entropy_content"
        if shared_infrastructure and item.size < MIN_SAFE_MEASUREMENT_BYTES:
            return "measurement_below_minimum"
    return None


def _redacted_stop_record(
    *,
    probe_name: str,
    probe_version: str,
    reason_code: str,
    smallest_span: int,
    driver_metadata: dict[str, str] | None,
) -> RedactedStopRecord:
    metadata = {
        key: str(value)
        for key, value in (driver_metadata or {}).items()
        if key in SAFE_STOP_METADATA_KEYS
    }
    boundary = (driver_metadata or {}).get("boundary", Boundary.UNSPECIFIED.name)
    if boundary not in {item.name for item in Boundary}:
        boundary = Boundary.UNSPECIFIED.name
    return RedactedStopRecord(
        probe_name=probe_name,
        probe_version=probe_version,
        reason_code=reason_code,
        size_bucket=_size_bucket(smallest_span),
        boundary=boundary,
        operational_metadata=metadata,
    )


def _size_bucket(size: int) -> str:
    if size < MIN_SAFE_MEASUREMENT_BYTES:
        return "lt-256"
    if size < 4096:
        return "256-4095"
    if size < 1 << 20:
        return "4k-lt-1m"
    return "gte-1m"


# --------------------------------------------------------------------------
# Zero-copy measurement primitives
# --------------------------------------------------------------------------


def _chunk_bounds(start: int, end: int, chunk_bytes: int) -> Iterator[tuple[int, int]]:
    """Bounded ``(chunk_start, chunk_end)`` pairs covering ``[start, end)``.

    Every chunk before the last is exactly ``chunk_bytes`` long, so each
    boundary sits on a multiple of ``chunk_bytes`` from ``start`` -- and,
    since ``chunk_bytes`` is itself a multiple of ``ANALYSIS_BLOCK_SIZE``, on
    the same block grid a single unbounded scan would use. Only the final
    chunk of a span may be short, and only its trailing remainder (fewer
    than ``ANALYSIS_BLOCK_SIZE`` bytes) falls outside any block -- exactly
    the remainder an unchunked pass already excluded from block analysis.
    """
    cursor = start
    while cursor < end:
        nxt = min(cursor + chunk_bytes, end)
        yield cursor, nxt
        cursor = nxt


def _chunk_histogram(
    view: memoryview,
    start: int,
    end: int,
    chunk_bytes: int,
    *,
    budget: RunBudget | None = None,
) -> Any:
    """Byte-value counts over ``view[start:end]``, one bounded chunk at a time.

    ``numpy.frombuffer`` is zero-copy: each chunk shares the SafeBuffer's own
    backing store rather than duplicating it, and at most one chunk-sized
    slice is ever live. No full-size copy of the span is created regardless
    of how large it is.

    ``budget`` is checked at every chunk boundary, before that chunk is
    touched, so a wall-clock stop never happens mid-chunk.
    """
    histogram = np.zeros(256, dtype=np.int64)
    for chunk_start, chunk_end in _chunk_bounds(start, end, chunk_bytes):
        if budget is not None:
            budget.check()
        chunk = view[chunk_start:chunk_end]
        try:
            histogram += np.bincount(np.frombuffer(chunk, dtype=np.uint8), minlength=256)
        finally:
            chunk.release()
    return histogram


def _chunk_blocks(
    view: memoryview, chunk_start: int, chunk_end: int
) -> tuple[int, int, list[bytes]]:
    """Block-fixed count and one-way fingerprints for one bounded chunk.

    Blocks are compared and hashed as fixed-size (``ANALYSIS_BLOCK_SIZE``)
    views, never assembled into a larger raw copy. Fingerprints -- not raw
    blocks -- are what leaves this function (CHARTER.md §7.2: "never a raw
    block").
    """
    chunk = view[chunk_start:chunk_end]
    try:
        arr = np.frombuffer(chunk, dtype=np.uint8)
        n_blocks = len(arr) // ANALYSIS_BLOCK_SIZE
        if not n_blocks:
            return 0, 0, []
        blocks = arr[: n_blocks * ANALYSIS_BLOCK_SIZE].reshape(
            n_blocks, ANALYSIS_BLOCK_SIZE
        )
        fixed = int(np.count_nonzero(np.all(blocks == blocks[:, :1], axis=1)))
        fingerprints = [
            hashlib.blake2b(blocks[i], digest_size=16).digest() for i in range(n_blocks)
        ]
        return n_blocks, fixed, fingerprints
    finally:
        chunk.release()


def _measure(
    view: memoryview,
    spans: Sequence[tuple[int, int]],
    *,
    expect_zeroed: bool = False,
    shared_infrastructure: bool = False,
    chunk_bytes: int = ANALYSIS_CHUNK_BYTES,
    budget: RunBudget | None = None,
) -> dict[str, Any]:
    """Reduce ``view`` over ``spans`` to safe aggregate statistics.

    Every read happens in bounded ``chunk_bytes`` segments -- never one
    monolithic pass over an arbitrarily large span. ``_chunk_histogram`` and
    ``_chunk_blocks`` each touch at most one chunk-sized slice of ``view`` at
    a time and are accumulated into running totals, so no full-size host
    buffer beyond the SafeBuffer's own backing store is ever materialised,
    regardless of how large the measured allocation is.

    ``budget``, when supplied, is checked at every chunk boundary in both
    passes below, so a wall-clock run budget cannot be blown by a single very
    large allocation.
    """
    if chunk_bytes <= 0 or chunk_bytes % ANALYSIS_BLOCK_SIZE:
        raise ValueError(
            f"chunk_bytes must be a positive multiple of ANALYSIS_BLOCK_SIZE "
            f"({ANALYSIS_BLOCK_SIZE}), got {chunk_bytes}"
        )

    # Safety is a separate first pass. No digest, block fingerprint, or
    # aggregate detail is created until every remaining span has passed all
    # guards. Therefore a later sensitive span cannot leave earlier derived
    # measurement objects behind when the stop unwinds. Each span's
    # histogram is accumulated incrementally, chunk by chunk, rather than
    # read twice -- it is reused below to build the combined histogram
    # instead of re-scanning every span a second time.
    checked_spans: list[_SpanSafety] = []
    span_histograms: list[Any] = []
    for start, end in spans:
        span_size = end - start
        if shared_infrastructure and span_size < MIN_SAFE_MEASUREMENT_BYTES:
            raise _SensitiveSpan("measurement_below_minimum", span_size)

        span_histogram = _chunk_histogram(view, start, end, chunk_bytes, budget=budget)
        span_histograms.append(span_histogram)

        safety = _SpanSafety(
            size=span_size,
            zero_fraction=(float(span_histogram[0]) / span_size) if span_size else 0.0,
            entropy=_shannon_from_hist(span_histogram.tolist(), span_size),
        )
        checked_spans.append(safety)
        reason = _safety_stop_reason(
            checked_spans,
            expect_zeroed=expect_zeroed,
            shared_infrastructure=shared_infrastructure,
        )
        if reason is not None:
            raise _SensitiveSpan(reason, span_size)

    histogram = np.zeros(256, dtype=np.int64)
    for span_histogram in span_histograms:
        histogram += span_histogram

    seen_fingerprints: set[bytes] = set()
    fixed_blocks = 0
    block_count = 0
    for start, end in spans:
        for chunk_start, chunk_end in _chunk_bounds(start, end, chunk_bytes):
            if budget is not None:
                budget.check()
            n_blocks, chunk_fixed, fingerprints = _chunk_blocks(
                view, chunk_start, chunk_end
            )
            block_count += n_blocks
            fixed_blocks += chunk_fixed
            seen_fingerprints.update(fingerprints)

    total = sum(end - start for start, end in spans)
    byte_histogram = histogram.tolist()
    return {
        "zero_fraction": (float(histogram[0]) / total) if total else 0.0,
        "fixed_pattern_fraction": (fixed_blocks / block_count)
        if block_count
        else 0.0,
        "entropy_estimate": _shannon_from_hist(byte_histogram, total),
        "repeated_block_count": block_count - len(seen_fingerprints),
        "distinct_block_count": len(seen_fingerprints),
        "byte_histogram": byte_histogram,
    }


def _hash_spans(view: memoryview, spans: Sequence[tuple[int, int]]) -> str:
    digest = hashlib.sha256()
    for start, end in spans:
        part = view[start:end]
        try:
            digest.update(part)
        finally:
            part.release()
    return "sha256:" + digest.hexdigest()


def _shannon_from_hist(hist: Sequence[int], n: int) -> float:
    """Normalised Shannon entropy in [0, 1]; 1.0 == uniform bytes."""
    if n <= 0:
        return 0.0
    acc = 0.0
    for count in hist:
        if count:
            probability = count / n
            acc -= probability * math.log2(probability)
    return acc / 8.0
