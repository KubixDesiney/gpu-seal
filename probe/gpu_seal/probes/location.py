"""Coarse location consistency — CHARTER.md §9.9, reframed by A8 as **D7**.

    "Is the observed network location consistent with the advertised region?"

Demoted from a contribution to a reproduced instrument (amendment A2), then
given a new job by amendment A8. At metropolitan-to-continental resolution
this cannot find a rack — but it can distinguish *in the EU* from *not in the
EU*, and that is precisely the granularity GDPR, NIS2, DORA, and the EU AI Act
care about. An organisation being audited on where its accelerator physically
sits currently answers with the provider's word. This turns that into a
measurement.

**The resolution bound is stated on every result.** Not in a footnote, not in
the methodology section — in the record, every time
(:data:`RESOLUTION_BOUND`). Alpay & Alpay place a B200 within 44 km of its
claimed datacentre while rejecting all 11 decoy sites; they are candid that
the network alibi localises to metropolitan-to-continental scale. Inherited
directly.

**Never published:** exact server coordinates, raw traceroutes, public IPs
(CHARTER.md §10). Landmarks are referred to by pseudonymous code and claimed
metro area. The record carries round-trip times and a consistency band — not
a position.

**ICMP is not used.** Rented instances routinely do not answer it; the source
paper uses TCP-reachable ports and so does this. Connecting to a public
service port and immediately closing is ordinary client behaviour, well inside
§6's tenant position.
"""

from __future__ import annotations

import socket
import statistics
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..evidence.observation import ObservationRecord
from ..safety.policy import CONSISTENCY_BANDS

__all__ = [
    "Landmark",
    "RttSource",
    "TcpRttSource",
    "LocationProbe",
    "RESOLUTION_BOUND",
    "PROBE_NAME",
    "PROBE_VERSION",
]

PROBE_NAME = "coarse_location_consistency"
PROBE_VERSION = "0.2.0"

RESOLUTION_BOUND = (
    "metropolitan-to-continental resolution only. This instrument cannot "
    "localise to a rack, a datacentre campus, or a city block, and a result "
    "here never supports a claim finer than the region it was measured at "
    "(CHARTER.md §9.9, inherited from arXiv:2606.24934 §12)."
)

#: Speed of light in fibre is roughly 200 km/ms one way, so a round trip
#: covers ~100 km per millisecond. Used only as a *lower bound* on distance:
#: a short RTT cannot prove proximity (the path may be short and the endpoint
#: elsewhere), but a long RTT does bound how close the endpoint can be.
KM_PER_MS_ROUND_TRIP = 100.0


@dataclass(frozen=True)
class Landmark:
    """A public endpoint with a known metro area.

    Identified by pseudonymous code, never by address, in anything that gets
    recorded. The address lives in the operator's configuration; the record
    sees ``landmark_code`` and ``metro``.
    """

    code: str
    metro: str
    #: Continental grouping used for the sovereignty question (§9.9 / A8).
    jurisdiction: str
    host: str
    port: int = 443


class RttSource(ABC):
    """Measures round-trip time to a landmark. Substitutable for testing."""

    @abstractmethod
    def measure(self, landmark: Landmark, *, samples: int) -> list[float]:
        """Round-trip times in milliseconds. Empty when unreachable."""


class TcpRttSource(RttSource):
    """TCP connect-time RTT. No ICMP, no traceroute, no raw sockets."""

    def __init__(self, *, timeout_s: float = 2.0) -> None:
        self._timeout = timeout_s

    def measure(self, landmark: Landmark, *, samples: int) -> list[float]:
        times: list[float] = []
        for _ in range(samples):
            started = time.perf_counter()
            try:
                connection = socket.create_connection(
                    (landmark.host, landmark.port), timeout=self._timeout
                )
            except OSError:
                # Unreachable landmarks are dropped, not recorded as slow. A
                # timeout is not a distance.
                continue
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            connection.close()
            times.append(elapsed_ms)
        return times


class LocationProbe:
    """Consistency of observed network position with an advertised region."""

    NAME = PROBE_NAME
    VERSION = PROBE_VERSION

    def __init__(self, source: RttSource, landmarks: Sequence[Landmark]) -> None:
        if not landmarks:
            raise ValueError("at least one landmark is required")
        self._source = source
        self._landmarks = tuple(landmarks)

    def assess(
        self,
        *,
        advertised_jurisdiction: str,
        samples: int = 5,
    ) -> ObservationRecord:
        """Measure, then band. Returns a record, never a position."""
        per_landmark: dict[str, dict[str, Any]] = {}
        for landmark in self._landmarks:
            times = self._source.measure(landmark, samples=samples)
            if not times:
                per_landmark[landmark.code] = {
                    "metro": landmark.metro,
                    "jurisdiction": landmark.jurisdiction,
                    "reachable": False,
                }
                continue
            # Minimum, not mean: the floor is the closest thing to a
            # propagation-delay estimate, and every source of error in a
            # network measurement adds time rather than removing it.
            per_landmark[landmark.code] = {
                "metro": landmark.metro,
                "jurisdiction": landmark.jurisdiction,
                "reachable": True,
                "min_rtt_ms": round(min(times), 3),
                "median_rtt_ms": round(statistics.median(times), 3),
                "samples": len(times),
                "min_distance_km_lower_bound": round(
                    min(times) * KM_PER_MS_ROUND_TRIP / 2, 1
                ),
            }

        band, confidence, evidence = self._band(
            per_landmark, advertised_jurisdiction=advertised_jurisdiction
        )

        return ObservationRecord(
            probe_name=self.NAME,
            probe_version=self.VERSION,
            subject="coarse_location_consistency",
            category="location_claim",
            classification=band,
            value={
                "advertised_jurisdiction": advertised_jurisdiction,
                "landmarks": per_landmark,
            },
            confidence=confidence,
            evidence=evidence,
            limitations=[
                RESOLUTION_BOUND,
                "anycast, tunnelling, backbone routing, congestion, traffic "
                "engineering, reseller infrastructure, and region-border "
                "ambiguity all confound this measurement",
                "a short round-trip time does not prove proximity; only a long "
                "one bounds distance from below",
                "no exact coordinates, public addresses, or raw traceroutes are "
                "recorded (CHARTER.md §10)",
            ],
            not_testable_reason=(
                "no landmark was reachable from this instance"
                if band == "not_testable"
                else None
            ),
        )

    # ------------------------------------------------------------------

    def _band(
        self, per_landmark: dict[str, dict[str, Any]], *, advertised_jurisdiction: str
    ) -> tuple[str, float, list[str]]:
        reachable = {
            code: data for code, data in per_landmark.items() if data["reachable"]
        }
        if not reachable:
            return "not_testable", 0.0, []

        in_jurisdiction = [
            data["min_rtt_ms"]
            for data in reachable.values()
            if data["jurisdiction"] == advertised_jurisdiction
        ]
        out_jurisdiction = [
            data["min_rtt_ms"]
            for data in reachable.values()
            if data["jurisdiction"] != advertised_jurisdiction
        ]

        if not in_jurisdiction:
            return (
                "not_testable",
                0.0,
                [
                    f"no reachable landmark is inside the advertised "
                    f"jurisdiction {advertised_jurisdiction!r}"
                ],
            )

        nearest_in = min(in_jurisdiction)
        evidence = [
            f"nearest reachable landmark inside {advertised_jurisdiction!r}: "
            f"{nearest_in:.1f} ms round trip",
            f"{len(reachable)} of {len(per_landmark)} landmarks reachable",
        ]

        if not out_jurisdiction:
            # Nothing to compare against. A single-sided measurement cannot
            # separate "close to the claim" from "close to everything".
            return "ambiguous", 0.2, evidence + [
                "no reachable landmark outside the advertised jurisdiction, so "
                "the measurement has no contrast"
            ]

        nearest_out = min(out_jurisdiction)
        evidence.append(
            f"nearest reachable landmark outside it: {nearest_out:.1f} ms"
        )

        # Continental separation shows up as tens of milliseconds. The bands
        # are deliberately coarse — finer thresholds would imply a resolution
        # this instrument does not have.
        if nearest_in < 10.0 and nearest_out > nearest_in * 3:
            return "consistent", 0.75, evidence
        if nearest_in < 30.0 and nearest_out > nearest_in * 1.5:
            return "probably_consistent", 0.55, evidence
        if nearest_out * 1.5 < nearest_in:
            return "probably_inconsistent", 0.5, evidence + [
                "a landmark outside the advertised jurisdiction is "
                "substantially closer than any inside it"
            ]
        return "ambiguous", 0.25, evidence


def band_is_valid(band: str) -> bool:
    return band in CONSISTENCY_BANDS
