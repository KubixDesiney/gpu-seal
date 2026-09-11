"""Campaign-wide terminal state for safety stops.

The context is owned by the campaign root and passed to probes and runners.
No process-global lookup is used, so separately constructed objects in one
logical campaign still share the same terminal stop.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .errors import CampaignTerminated, EgressViolation, CampaignContextRequired

__all__ = ["CampaignContext", "CampaignControl", "bind_campaign"]


@dataclass
class CampaignControl:
    """Share the first redacted stop across probe loops.

    The control retains only a redacted stop record. It deliberately has no
    operation that accepts or stores a raw buffer, measurement, or exception
    detail.
    """

    _stop_record: object | None = None
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False, compare=False
    )

    @classmethod
    def create(cls) -> CampaignControl:
        """Create the root-owned context for one logical campaign."""
        return cls()

    @property
    def terminated(self) -> bool:
        with self._lock:
            return self._stop_record is not None

    @property
    def stop_record(self) -> object | None:
        with self._lock:
            return self._stop_record

    def terminate(self, stop_record: object) -> None:
        """Publish the first stop and make the campaign terminal."""
        from .aggregation import RedactedStopRecord

        if not isinstance(stop_record, RedactedStopRecord):
            raise EgressViolation(
                "campaign termination requires a redacted stop record"
            )
        with self._lock:
            if self._stop_record is None:
                self._stop_record = stop_record

    def check(self) -> None:
        """Refuse every operation after the first sensitive observation."""
        with self._lock:
            stop_record = self._stop_record
        if stop_record is not None:
            raise CampaignTerminated(stop_record)


# Descriptive public name; retain CampaignControl for compatibility.
CampaignContext = CampaignControl


def bind_campaign(
    campaign: CampaignControl | None,
    *,
    shared_infrastructure: bool,
) -> CampaignControl:
    """Bind a supplied context, or create a standalone exclusive one.

    Shared-infrastructure work must be wired from the campaign root. Creating
    a private context there would let a later runner continue after a stop.
    """
    if campaign is not None:
        return campaign
    if shared_infrastructure:
        raise CampaignContextRequired(
            "shared-infrastructure execution requires the root-owned campaign "
            "context; pass campaign=CampaignControl.create()"
        )
    return CampaignControl.create()
