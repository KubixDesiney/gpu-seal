"""Statistical requirements — CHARTER.md §12.

    "For each conclusion report sample / success / failure / error / exclusion
     counts, confidence interval (bootstrap CIs where appropriate), variance,
     fingerprint stability, classifier confidence."

The important function here is the least interesting one.
:class:`ObservationCounts` exists so that a result cannot be reported without
its denominator. "No canary recovered" over 3 usable cycles out of 10 attempted
is a different claim from the same sentence over 10 out of 10, and the second
number is the one that goes missing when people write prose instead of
carrying a struct around.

Deliberately dependency-light: NumPy is used when present for speed, and the
pure-Python path gives identical answers, because a statistic that only
computes inside one environment is not reproducible either.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ObservationCounts",
    "bootstrap_ci",
    "proportion_ci",
]


@dataclass(frozen=True)
class ObservationCounts:
    """The denominator, carried alongside every conclusion."""

    attempted: int
    usable: int
    positive: int
    errored: int = 0
    excluded: int = 0
    exclusion_reasons: Sequence[str] = ()

    def __post_init__(self) -> None:
        if self.usable > self.attempted:
            raise ValueError(
                f"usable ({self.usable}) exceeds attempted ({self.attempted})"
            )
        if self.positive > self.usable:
            raise ValueError(
                f"positive ({self.positive}) exceeds usable ({self.usable})"
            )

    @property
    def rate(self) -> float | None:
        """Positive rate over *usable* cycles. ``None`` when nothing is usable.

        Returning ``None`` rather than 0.0 is the whole point: a run where
        every cycle errored has a positive rate of *unknown*, and reporting it
        as zero would turn a failed measurement into a clean result.
        """
        return (self.positive / self.usable) if self.usable else None

    def confidence_interval(self, confidence: float = 0.95) -> tuple[float, float] | None:
        if not self.usable:
            return None
        return proportion_ci(self.positive, self.usable, confidence=confidence)

    def to_dict(self) -> dict[str, Any]:
        interval = self.confidence_interval()
        return {
            "attempted": self.attempted,
            "usable": self.usable,
            "positive": self.positive,
            "errored": self.errored,
            "excluded": self.excluded,
            "exclusion_reasons": list(self.exclusion_reasons),
            "rate": self.rate,
            "confidence_interval_95": list(interval) if interval else None,
        }


def proportion_ci(
    successes: int, trials: int, *, confidence: float = 0.95
) -> tuple[float, float]:
    """Wilson score interval for a proportion.

    Wilson rather than the normal approximation because GPU-SEAL's headline
    results are proportions near zero over small samples — 0 canaries in 10
    cycles — and the normal approximation returns the degenerate interval
    [0, 0] there. Claiming a 95% CI of exactly zero from ten observations is
    the precise overclaim §12 exists to prevent. Wilson gives [0, 0.28], which
    is the honest answer and a considerably less exciting one.
    """
    if trials <= 0:
        raise ValueError("trials must be positive")
    if not 0 <= successes <= trials:
        raise ValueError("successes must be within [0, trials]")

    z = _z_for(confidence)
    phat = successes / trials
    denominator = 1 + z * z / trials
    centre = (phat + z * z / (2 * trials)) / denominator
    margin = (
        z
        * math.sqrt(phat * (1 - phat) / trials + z * z / (4 * trials * trials))
        / denominator
    )
    return max(0.0, centre - margin), min(1.0, centre + margin)


def bootstrap_ci(
    samples: Sequence[float],
    *,
    statistic: Callable[[Sequence[float]], float] | None = None,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0x5EA1,
) -> tuple[float, float]:
    """Percentile bootstrap CI for an arbitrary statistic.

    Used for fingerprint stability and timing distributions, where the
    sampling distribution has no closed form worth trusting. Seeded, because
    a confidence interval that moves between runs of the analysis is not a
    reproducible result (§10 reproducibility fields).
    """
    if not samples:
        raise ValueError("cannot bootstrap an empty sample")

    values = list(samples)
    estimator = statistic or _mean
    # A seeded Mersenne Twister, on purpose: resampling an already-collected
    # sample is a numerical procedure, not a security one, and it has to be
    # reproducible. A cryptographic generator would make the confidence
    # interval move between runs of the same analysis.
    rng = random.Random(seed)  # noqa: S311
    n = len(values)

    estimates = [
        estimator([values[rng.randrange(n)] for _ in range(n)])
        for _ in range(resamples)
    ]
    estimates.sort()

    tail = (1 - confidence) / 2
    lower = estimates[int(tail * resamples)]
    upper = estimates[min(int((1 - tail) * resamples), resamples - 1)]
    return lower, upper


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


#: Two-sided z scores. A lookup rather than an inverse-normal implementation:
#: only these three levels are ever reported, and a table cannot be subtly
#: wrong in a way that survives review.
_Z_SCORES = {0.90: 1.6449, 0.95: 1.9600, 0.99: 2.5758}


def _z_for(confidence: float) -> float:
    try:
        return _Z_SCORES[round(confidence, 2)]
    except KeyError:
        raise ValueError(
            f"confidence must be one of {sorted(_Z_SCORES)}; got {confidence}. "
            f"Reporting an unusual level invites the reader to wonder which "
            f"one was chosen after seeing the data."
        ) from None
