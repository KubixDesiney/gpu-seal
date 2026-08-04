"""Statistics and analysis — CHARTER.md §12, §18.

    "Don't overinterpret one allocation."

The math lives in the installable package rather than in notebooks, so that
every figure in the paper is produced by code that the test suite exercises.
A number that only exists inside a notebook cell is a number nobody can
reproduce.

Two modules:

``statistics``
    Bootstrap confidence intervals and the counts §12 requires with every
    conclusion (sample / success / failure / error / exclusion).

``separability``
    Contribution **D5** — same-model die separation (§9.8b). Pairwise
    separability, leave-one-out classification, and ROC/AUC over topology
    certificates, plus the explicit statement of when the claim fails.
"""

from .separability import (
    SeparabilityReport,
    certificate_distance,
    evaluate_separability,
)
from .statistics import (
    ObservationCounts,
    bootstrap_ci,
    proportion_ci,
)

__all__ = [
    "ObservationCounts",
    "bootstrap_ci",
    "proportion_ci",
    "SeparabilityReport",
    "certificate_distance",
    "evaluate_separability",
]
