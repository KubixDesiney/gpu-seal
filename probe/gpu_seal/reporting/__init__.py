"""Assurance report card generation — CHARTER.md §13.

Five independently graded categories plus one field report, and deliberately
no composite score. See :class:`ReportCard`.
"""

from .report_card import (
    Grade,
    MeasurementPath,
    MemoryHygieneEvidence,
    ReportCard,
    attestation_field_report,
    build_report_card,
    grade_allocation_transparency,
    grade_hardware_claim,
    grade_location_claim,
    grade_memory_hygiene,
    grade_tenant_exposure,
)

__all__ = [
    "Grade",
    "MeasurementPath",
    "MemoryHygieneEvidence",
    "ReportCard",
    "build_report_card",
    "grade_memory_hygiene",
    "grade_tenant_exposure",
    "grade_hardware_claim",
    "grade_location_claim",
    "grade_allocation_transparency",
    "attestation_field_report",
]
