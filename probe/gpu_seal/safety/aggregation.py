"""The single egress door — CHARTER.md §7.2.

Statistics leave a probe. Bytes do not.

``aggregate()`` is the only function in GPU-SEAL that reads the contents of a
:class:`~gpu_seal.safety.buffer.SafeBuffer`, and it returns a record whose
every field is on the :data:`~gpu_seal.safety.policy.SAFE_AGGREGATE_KEYS`
allowlist. The allowlist is enforced on the way out, so a future contributor
who adds a field to the dataclass without adding it to the policy gets a
failing test rather than a data leak.

It also implements the automatic safety stop (§7.3): if the buffer contains
something inconsistent with expected allocation behaviour, analysis halts, the
raw bytes are destroyed, and only the aggregate record survives — flagged
``sensitive_observation`` and blocked from automatic publication.

What deliberately is NOT here, and must never be added:

    * n-gram or natural-language analysis
    * UTF-8 / ASCII / any text decoding
    * float or token-ID structure detection  (removed in charter v1→v2, §0)
    * credential, key, or secret pattern matching
    * classification of content as weights / prompts / activations / images

Those all cross from *measuring* into *interpreting another tenant's data*.
See CHARTER.md §4.3 (non-goals) and §16 (CI tests 4 and 5).

Module naming note: this file is ``aggregation.py``, not ``aggregate.py``, so
that the module does not shadow the ``aggregate()`` function when both are
reachable from :mod:`gpu_seal.safety`. The shadowing version produced a
confusing ``AttributeError`` on ``gpu_seal.safety.aggregate.SAFE_AGGREGATE_KEYS``
during development.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .buffer import SafeBuffer
from .canary import CanaryMatch, CanarySet
from .errors import EgressViolation, SensitiveObservation
from .policy import (
    ANALYSIS_BLOCK_SIZE,
    ENTROPY_STOP_THRESHOLD,
    EXPECTED_ZERO_FRACTION_FLOOR,
    SAFE_AGGREGATE_KEYS,
)

try:  # numpy is an optional accelerator, not a requirement
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None  # type: ignore[assignment]

__all__ = ["AggregateRecord", "aggregate"]


@dataclass(frozen=True)
class AggregateRecord:
    """Everything GPU-SEAL is permitted to know about unknown memory.

    Every field name must appear in ``SAFE_AGGREGATE_KEYS``; this is checked
    by :meth:`to_dict` and by ``tests/safety/test_egress_allowlist.py``.
    """

    # Provenance
    probe_name: str
    probe_version: str
    buffer_size_bytes: int
    block_size_bytes: int
    measurement_hash: str

    # Distribution over unknown bytes
    zero_fraction: float
    fixed_pattern_fraction: float
    entropy_estimate: float
    repeated_block_count: int
    distinct_block_count: int
    byte_histogram: List[int]

    # Owned-canary matching only
    owned_canary_match: bool
    owned_canary_exact_matches: int
    owned_canary_longest_prefix: int

    # Safety bookkeeping
    sensitive_observation: bool = False
    unknown_raw_retained: bool = False
    unknown_memory_rendered: bool = False
    canary_only_search: bool = True

    # Optional diagnostics
    driver_metadata: Optional[Dict[str, str]] = None
    error_code: Optional[str] = None
    timing_ns: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialise, refusing any key not on the §7.2 allowlist."""
        payload = asdict(self)
        offending = set(payload) - SAFE_AGGREGATE_KEYS
        if offending:
            raise EgressViolation(
                f"Refusing to emit non-allowlisted keys {sorted(offending)}. "
                f"CHARTER.md §7.2 enumerates exactly what may leave a probe; "
                f"adding a field requires an ethics review, not just a code "
                f"change."
            )
        return payload


def aggregate(
    buf: SafeBuffer,
    owned_canaries: Optional[CanarySet] = None,
    *,
    probe_name: str,
    probe_version: str,
    expect_zeroed: bool = False,
    shared_infrastructure: bool = True,
    driver_metadata: Optional[Dict[str, str]] = None,
    timing_ns: Optional[int] = None,
) -> AggregateRecord:
    """Reduce a SafeBuffer to permitted statistics.

    Args:
        buf: the buffer to measure. Not modified; not retained.
        owned_canaries: this experiment's canary set. If ``None``, no search is
            performed at all — there is no way to search for anything else.
        expect_zeroed: set ``True`` when the allocation *should* be clean (e.g.
            a negative control, or a boundary the provider claims to sanitise).
            Arms the zero-floor safety stop.
        shared_infrastructure: ``True`` (default) when the memory could belong
            to someone else — any rented instance. Arms the entropy safety
            stop. Set ``False`` **only** for hardware the researcher owns
            exclusively, where residue is the researcher's own and stopping on
            it is noise rather than protection.

    Raises:
        SensitiveObservation: the §7.3 safety stop fired. The exception carries
            the aggregate record; the raw bytes are already gone.
    """
    view = buf._unsafe_view("gpu_seal.safety.aggregation")
    try:
        stats = _measure(view)
    finally:
        view.release()

    matches: List[CanaryMatch] = []
    if owned_canaries is not None:
        # The ONLY search performed anywhere in GPU-SEAL.
        raw = buf._unsafe_view("gpu_seal.safety.aggregation")
        try:
            matches = owned_canaries.search(raw)
        finally:
            raw.release()

    exact = sum(1 for m in matches if m.exact)
    longest = max((m.longest_prefix_bytes for m in matches), default=0)

    record = AggregateRecord(
        probe_name=probe_name,
        probe_version=probe_version,
        buffer_size_bytes=len(buf),
        block_size_bytes=ANALYSIS_BLOCK_SIZE,
        measurement_hash=buf.digest(),
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

    _check_safety_stop(
        record,
        expect_zeroed=expect_zeroed,
        shared_infrastructure=shared_infrastructure,
        buf=buf,
    )
    return record


def _check_safety_stop(
    record: AggregateRecord,
    *,
    expect_zeroed: bool,
    shared_infrastructure: bool,
    buf: SafeBuffer,
) -> None:
    """Automatic safety stop — CHARTER.md §7.3.

    Fires when the buffer holds unknown content inconsistent with expected
    allocation behaviour AND that content is not ours. Destroys the raw buffer
    immediately, preserves only the aggregate record, and marks the run for
    manual disclosure review.

    Note the ordering: we never decide *what* the content is. We only decide
    that it is not what we expected and not ours, and therefore that we stop
    looking. Deciding what it is would be the §4.3 violation.

    Two independent triggers, and the distinction between them matters:

    ``expect_zeroed`` — we asserted this allocation should be clean, and it is
        not. Always armed when set, on any hardware, because the assertion was
        ours to make.

    ``shared_infrastructure`` — high-entropy content on hardware that might
        hold someone else's data. **Only armed on rented infrastructure.**

    That second condition is load-bearing, and getting it wrong makes the tool
    useless. NVIDIA documents that ``cudaMalloc`` does not clear memory, so a
    fresh allocation returning high-entropy bytes is *expected* behaviour, not
    an incident. Arming the entropy stop unconditionally halts every baseline
    measurement the project exists to take. Arming it only on shared
    infrastructure keeps the protection where it belongs: we stop when we might
    be sitting on a stranger's data, not when we are looking at residue from
    our own previous kernel on our own desk.
    """
    if record.owned_canary_match:
        return  # It's ours. Expected, and the whole point of the experiment.

    unexpected_content = (
        expect_zeroed and record.zero_fraction < EXPECTED_ZERO_FRACTION_FLOOR
    )
    high_information = (
        shared_infrastructure and record.entropy_estimate > ENTROPY_STOP_THRESHOLD
    )

    if not (unexpected_content or high_information):
        return

    flagged = AggregateRecord(
        **{**record.to_dict(), "sensitive_observation": True}
    )
    buf.destroy()

    reason = (
        f"zero_fraction={record.zero_fraction:.6f} below floor "
        f"{EXPECTED_ZERO_FRACTION_FLOOR}"
        if unexpected_content
        else f"entropy_estimate={record.entropy_estimate:.4f} above threshold "
        f"{ENTROPY_STOP_THRESHOLD}"
    )
    raise SensitiveObservation(
        f"Automatic safety stop (CHARTER.md §7.3): {reason}, and no owned "
        f"canary matched. Raw buffer destroyed. Only aggregate statistics "
        f"retained. This run is blocked from automatic publication and "
        f"requires manual disclosure review before any further action.",
        aggregate_record=flagged,
    )


# --------------------------------------------------------------------------
# Measurement primitives
# --------------------------------------------------------------------------


def _measure(view: memoryview) -> Dict[str, Any]:
    if _np is not None:
        return _measure_numpy(view)
    return _measure_pure(view)  # pragma: no cover - fallback path


def _measure_numpy(view: memoryview) -> Dict[str, Any]:
    arr = _np.frombuffer(view, dtype=_np.uint8)
    n = arr.size
    hist = _np.bincount(arr, minlength=256)

    zero_fraction = float(hist[0]) / n if n else 0.0
    entropy = _shannon_from_hist(hist.tolist(), n)

    bs = ANALYSIS_BLOCK_SIZE
    n_blocks = n // bs
    repeated = distinct = 0
    fixed_blocks = 0
    if n_blocks:
        blocks = arr[: n_blocks * bs].reshape(n_blocks, bs)
        # A block is "fixed pattern" if every byte in it is identical.
        fixed_blocks = int(_np.count_nonzero((blocks == blocks[:, :1]).all(axis=1)))
        # Distinct blocks via row-wise void view — exact, no hashing collisions.
        contiguous = _np.ascontiguousarray(blocks)
        as_void = contiguous.view([("", contiguous.dtype)] * bs)
        distinct = int(_np.unique(as_void).size)
        repeated = n_blocks - distinct

    return {
        "zero_fraction": zero_fraction,
        "fixed_pattern_fraction": (fixed_blocks / n_blocks) if n_blocks else 0.0,
        "entropy_estimate": entropy,
        "repeated_block_count": repeated,
        "distinct_block_count": distinct,
        "byte_histogram": [int(x) for x in hist],
    }


def _measure_pure(view: memoryview) -> Dict[str, Any]:  # pragma: no cover
    data = bytes(view)
    n = len(data)
    hist = [0] * 256
    for b in data:
        hist[b] += 1

    bs = ANALYSIS_BLOCK_SIZE
    n_blocks = n // bs
    seen = set()
    fixed_blocks = 0
    for i in range(n_blocks):
        blk = data[i * bs : (i + 1) * bs]
        seen.add(blk)
        if blk.count(blk[:1]) == bs:
            fixed_blocks += 1

    return {
        "zero_fraction": (hist[0] / n) if n else 0.0,
        "fixed_pattern_fraction": (fixed_blocks / n_blocks) if n_blocks else 0.0,
        "entropy_estimate": _shannon_from_hist(hist, n),
        "repeated_block_count": n_blocks - len(seen),
        "distinct_block_count": len(seen),
        "byte_histogram": hist,
    }


def _shannon_from_hist(hist: List[int], n: int) -> float:
    """Normalised Shannon entropy in [0, 1]; 1.0 == uniform over 256 values."""
    if n <= 0:
        return 0.0
    acc = 0.0
    for count in hist:
        if count:
            p = count / n
            acc -= p * math.log2(p)
    return acc / 8.0
