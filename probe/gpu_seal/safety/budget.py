"""Wall-clock run budget — a purely operational stop, not an ethics gate.

``CampaignControl`` (``campaign.py``) exists to make a *content*-triggered
safety stop terminal: once a sensitive observation fires, no later read may
ever happen for the life of the campaign. ``RunBudget`` is the same shape of
mechanism applied to *time* instead of content, so a hang, a slow chunked
read, or an unexpectedly long campaign cannot silently burn a metered or
free-tier GPU allocation past a caller-chosen wall-clock ceiling (the local
runner scripts' ``--max-runtime-s``).

It is checked at the same two granularities ``CampaignControl`` already is:
cycle boundaries (``GlobalMemoryProbe.run_cycles`` /
``FrameworkAllocatorProbe.run_cycles``) and chunk boundaries inside the read
path (``gpu_seal.safety.aggregation``), so expiry is always caught within one
cycle or one chunk's worth of work of the deadline.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .errors import RunBudgetExceeded

__all__ = ["RunBudget"]


@dataclass
class RunBudget:
    """A hard wall-clock deadline shared across a run's cycles and reads.

    Distinct from ``CampaignControl``: a campaign stop is permanent and about
    *content* -- a fresh probe must never be able to re-arm past one. A
    budget stop carries no memory of what was being measured, so constructing
    a fresh ``RunBudget`` for an unrelated run is always safe.
    """

    deadline_monotonic: float
    started_monotonic: float = field(default_factory=time.monotonic)

    @classmethod
    def start(cls, max_runtime_s: float) -> RunBudget:
        """Begin a budget of ``max_runtime_s`` seconds from now."""
        if max_runtime_s <= 0:
            raise ValueError(
                f"max_runtime_s must be positive, got {max_runtime_s!r}"
            )
        now = time.monotonic()
        return cls(deadline_monotonic=now + max_runtime_s, started_monotonic=now)

    @property
    def elapsed_s(self) -> float:
        return max(0.0, time.monotonic() - self.started_monotonic)

    @property
    def remaining_s(self) -> float:
        return self.deadline_monotonic - time.monotonic()

    @property
    def expired(self) -> bool:
        return time.monotonic() >= self.deadline_monotonic

    def check(self) -> None:
        """Raise :class:`RunBudgetExceeded` once the deadline has passed."""
        if self.expired:
            raise RunBudgetExceeded(
                f"wall-clock run budget exceeded after {self.elapsed_s:.1f}s"
            )
