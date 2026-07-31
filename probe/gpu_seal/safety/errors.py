"""Exceptions raised when the safety policy is violated.

Every exception in this module represents a *bug in GPU-SEAL itself*, not a
research finding. If one of these is raised in production, a probe attempted
something the ethics model (CHARTER.md §7) forbids, and the run must be
treated as invalid.

These are deliberately NOT subclasses of anything a caller is likely to catch
by accident. `PolicyViolation` inherits from `BaseException`, not `Exception`,
so a stray `except Exception:` in probe code cannot swallow a safety failure.
"""

from __future__ import annotations


class PolicyViolation(BaseException):
    """Base: an operation forbidden by CHARTER.md §7 was attempted.

    Inherits BaseException so that broad `except Exception` handlers in probe
    code cannot silently suppress a safety violation.
    """


class UnknownMemoryRenderError(PolicyViolation):
    """Attempted to render, print, decode, or otherwise materialise unknown bytes.

    CHARTER.md §7.2: the system must never print unknown bytes, render them as
    text, attempt UTF-8 decoding, or include raw unknown buffers in logs.
    """


class UnknownMemoryRetentionError(PolicyViolation):
    """Attempted to persist, serialise, or copy unknown bytes out of the safe layer.

    CHARTER.md §7.2: the system must never store raw unknown buffers.
    """


class BufferLifecycleError(PolicyViolation):
    """A SafeBuffer was used outside its managed lifetime.

    Either used after destruction, or allowed to escape its context manager
    without being destroyed.
    """


class ForeignCanaryError(PolicyViolation):
    """The canary matcher was given a canary this experiment does not own.

    CHARTER.md §7.1: GPU-SEAL may search only for canaries the operator
    generated. Matching against anything else is out of policy.
    """


class LimitExceeded(PolicyViolation):
    """A hard operational limit was exceeded (allocation size, duration, etc.)."""


class SensitiveObservation(PolicyViolation):
    """The automatic safety stop fired (CHARTER.md §7.3).

    Raised when a probe observes unknown content inconsistent with expected
    allocation behaviour. Further memory analysis must stop, the raw buffer is
    destroyed, only aggregate statistics survive, and the run is blocked from
    automatic publication pending manual disclosure review.
    """

    def __init__(self, message: str, aggregate_record: object | None = None) -> None:
        super().__init__(message)
        # Only ever an already-aggregated, policy-clean record. Never raw bytes.
        self.aggregate_record = aggregate_record


class EgressViolation(PolicyViolation):
    """A result payload contained a key not on the safe-egress allowlist.

    CHARTER.md §7.2 enumerates exactly what may leave a probe. Anything else
    is refused rather than filtered, so that adding a field is a deliberate,
    reviewed act.
    """
