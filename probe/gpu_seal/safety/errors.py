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
    destroyed, and only a redacted stop record survives.
    """

    def __init__(
        self,
        message: str | None = None,
        aggregate_record: object | None = None,
        *,
        stop_record: object | None = None,
    ) -> None:
        # Never allow a caller supplied diagnostic to become a traceback, log,
        # or provider-facing error. In particular, a one-byte observation must
        # not confirm its value through this exception.
        del message
        super().__init__(
            "Automatic safety stop: sensitive observation. Raw memory was "
            "destroyed; only a redacted stop record is available for review."
        )
        record = stop_record if stop_record is not None else aggregate_record
        if record is None:
            raise EgressViolation(
                "a sensitive observation must carry a redacted stop record"
            )
        # Import lazily to avoid the aggregation -> errors import cycle during
        # module initialisation.  The exception is constructed only after the
        # safe aggregation module has loaded.
        from .aggregation import RedactedStopRecord

        if not isinstance(record, RedactedStopRecord):
            raise EgressViolation(
                "sensitive observations may retain only RedactedStopRecord"
            )
        # Backwards-compatible attribute name, but it is intentionally the
        # redacted record, never an AggregateRecord containing measurements.
        self.aggregate_record = record
        self.stop_record = record


class CampaignTerminated(PolicyViolation):
    """A campaign has reached its terminal safety state."""

    def __init__(self, stop_record: object | None = None) -> None:
        super().__init__(
            "Campaign terminated after a sensitive observation; no later "
            "memory operation is permitted."
        )
        self.stop_record = stop_record


class CampaignContextRequired(PolicyViolation):
    """Shared-infrastructure work lacks the root-owned campaign context."""


class NativeSafePathRequired(PolicyViolation):
    """Python cannot process real shared memory; use the native safe path."""


class EgressViolation(PolicyViolation):
    """A result payload contained a key not on the safe-egress allowlist.

    CHARTER.md §7.2 enumerates exactly what may leave a probe. Anything else
    is refused rather than filtered, so that adding a field is a deliberate,
    reviewed act.
    """
