#!/usr/bin/env python3
"""Summarise signed Phase 1 result bundles into a findings document.

    python3 lab/summarize-findings.py \
        --bundle colab-t4=out/colab/run_20260915T...Z.result.json \
        --bundle kaggle-p100-t4x2=out/kaggle/run_20260915T...Z.result.json \
        --out docs/findings/F-001-linux-driver-residue.md

Every number this script prints comes from a field in a signed bundle (or, for
the "what this does not show" section, from the current text of
docs/STATUS.md and docs/scoring.md). Nothing is hand-typed. If a bundle does
not carry a field this script needs, or its shape does not match a Phase 1
battery from ``lab/local-runner/run_phase1.py`` (baseline, then the §9.4
detection-capability control, then the §9.3 driver-direct measurement, then
the negative zeroisation control, each with the same cycle count), the script
raises :class:`SummaryError` and exits non-zero rather than guessing or
emitting a placeholder. A findings document built from a script that silently
tolerated a missing field would be worse than no document at all.

A bundle carrying a sensitive-observation stop or a report-card grade D is
refused outright: CHARTER.md §7.5 requires private disclosure and provider
coordination before that kind of result leaves the machine, and this script
is not that process.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "probe"))

from gpu_seal.evidence.result import SCHEMA_VERSION, ResultBundle  # noqa: E402
from gpu_seal.reporting import (  # noqa: E402
    Grade,
    MeasurementPath,
    MemoryHygieneEvidence,
    ReportCard,
    attestation_field_report,
    grade_allocation_transparency,
    grade_hardware_claim,
    grade_location_claim,
    grade_memory_hygiene,
    grade_tenant_exposure,
)

MEMORY_PROBE_NAME = "memory_global_read_before_write"
FRAMEWORK_PROBE_NAME = "framework_allocator_reuse"

#: docs/STATUS.md §"Open claim boundaries": same-model physical-die
#: continuity (contribution D5) has not landed in this checkout. This is a
#: fact about the *instrument*, not a per-run measurement, so it is a
#: constant here rather than something read out of a bundle -- exactly as
#: lab/local-runner/run_phase2_local.py hand-sets `same_advertised_model=True`
#: for the same reason. tests/safety/test_report_card_gating.py (CHARTER.md
#: §16 test 16) is the CI test that enforces this cannot be bypassed.
SAME_MODEL_CLASSIFIER_VALIDATED = False
D5_ENFORCEMENT_TEST = "tests/safety/test_report_card_gating.py"
MEASUREMENT_PATH_GATE_TEST = "tests/safety/test_measurement_path_gate.py"


class SummaryError(RuntimeError):
    """Raised when a bundle is missing something this script needs.

    Deliberately fatal. See the module docstring: a findings document is not
    allowed to paper over a missing field with a placeholder.
    """


# ---------------------------------------------------------------------------
# Field access -- every lookup fails loudly, with the path that was missing
# ---------------------------------------------------------------------------


def require(obj: Any, path: str, *, bundle_path: Path) -> Any:
    """Navigate ``path`` (dot-separated) through nested dicts. Fail loudly."""
    node = obj
    walked: list[str] = []
    for key in path.split("."):
        walked.append(key)
        if not isinstance(node, dict) or key not in node or node[key] is None:
            raise SummaryError(
                f"{bundle_path}: missing required field "
                f"'{'.'.join(walked)}' (looking for '{path}')."
            )
        node = node[key]
    return node


def require_type(value: Any, expected: type, *, path: str, bundle_path: Path) -> Any:
    if not isinstance(value, expected):
        raise SummaryError(
            f"{bundle_path}: field '{path}' is {type(value).__name__}, "
            f"expected {expected.__name__}."
        )
    return value


# ---------------------------------------------------------------------------
# Loading and verifying a bundle
# ---------------------------------------------------------------------------


def load_bundle(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SummaryError(f"{path}: no such file.")
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SummaryError(f"{path}: not valid JSON ({exc}).") from exc
    if not isinstance(bundle, dict):
        raise SummaryError(f"{path}: top-level JSON value must be an object.")

    schema_version = require(bundle, "schema_version", bundle_path=path)
    if schema_version != SCHEMA_VERSION:
        raise SummaryError(
            f"{path}: schema_version={schema_version!r}, expected "
            f"{SCHEMA_VERSION!r}. This script has not been checked against "
            f"any other schema version."
        )

    if not ResultBundle.verify(bundle):
        raise SummaryError(
            f"{path}: signature verification FAILED (embedded public key). "
            f"Refusing to summarise a bundle that cannot verify its own "
            f"integrity."
        )

    safety = require(bundle, "safety", bundle_path=path)
    require_type(safety, dict, path="safety", bundle_path=path)
    if safety.get("sensitive_observation"):
        raise SummaryError(
            f"{path}: safety.sensitive_observation is true. This bundle "
            f"contains a redacted safety-stop record and/or a report-card "
            f"grade D. CHARTER.md §7.5 requires private disclosure and "
            f"provider coordination before this kind of result is "
            f"summarised anywhere, and this script is not that process. "
            f"Handle it by hand."
        )
    if safety.get("run_incomplete"):
        reason = safety.get("incomplete_reason", "reason not recorded")
        raise SummaryError(
            f"{path}: safety.run_incomplete is true ({reason}). An "
            f"incomplete run is not a measurement and cannot be summarised "
            f"as one."
        )

    for probe in bundle.get("probes", []):
        if "reason_code" in probe:
            raise SummaryError(
                f"{path}: probe {probe.get('probe_name')!r} carries a "
                f"redacted stop record (reason_code={probe['reason_code']!r}) "
                f"even though safety.sensitive_observation was false -- that "
                f"is itself inconsistent. Refusing to proceed."
            )

    observations = bundle.get("observations", [])
    if observations:
        raise SummaryError(
            f"{path}: bundle carries {len(observations)} non-memory "
            f"observation record(s). This script only understands a plain "
            f"Phase 1 memory battery (lab/local-runner/run_phase1.py); a "
            f"bundle with §9.6/§9.7/§9.9/etc. observations needs a different "
            f"summary, not this one."
        )

    return bundle


# ---------------------------------------------------------------------------
# Segmenting the probe list into the four Phase 1 phases
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProbeRow:
    index: int
    probe_name: str
    boundary: str
    measurement_path: str
    zero_fraction: float
    owned_canary_match: bool
    owned_canary_exact_matches: int


def _to_probe_row(probe: dict[str, Any], *, index: int, bundle_path: Path) -> ProbeRow:
    context = f"probes[{index}]"
    probe_name = require(probe, "probe_name", bundle_path=bundle_path)
    boundary = require(probe, "driver_metadata.boundary", bundle_path=bundle_path)
    measurement_path = require(
        probe, "driver_metadata.measurement_path", bundle_path=bundle_path
    )
    zero_fraction = require(probe, "zero_fraction", bundle_path=bundle_path)
    if not isinstance(zero_fraction, (int, float)) or isinstance(zero_fraction, bool):
        raise SummaryError(
            f"{bundle_path}: {context}.zero_fraction is "
            f"{type(zero_fraction).__name__}, expected a number."
        )
    owned_canary_match = require(probe, "owned_canary_match", bundle_path=bundle_path)
    owned_canary_exact_matches = require(
        probe, "owned_canary_exact_matches", bundle_path=bundle_path
    )
    return ProbeRow(
        index=index,
        probe_name=probe_name,
        boundary=boundary,
        measurement_path=measurement_path,
        zero_fraction=float(zero_fraction),
        owned_canary_match=bool(owned_canary_match),
        owned_canary_exact_matches=int(owned_canary_exact_matches),
    )


@dataclass(frozen=True)
class PhaseGroup:
    name: str
    rows: list[ProbeRow]

    @property
    def cycles(self) -> int:
        return len(self.rows)

    @property
    def recovered_cycles(self) -> int:
        return sum(1 for r in self.rows if r.owned_canary_match)

    @property
    def ambiguous_cycles(self) -> int:
        """Not recovered, but not all-zero either -- CHARTER.md §13.1's

        'non-zero or otherwise ambiguous content, no canary match'.
        """
        return sum(
            1 for r in self.rows if not r.owned_canary_match and r.zero_fraction < 1.0
        )

    @property
    def exact_matches_total(self) -> int:
        return sum(r.owned_canary_exact_matches for r in self.rows)

    @property
    def measurement_paths(self) -> set[str]:
        return {r.measurement_path for r in self.rows}

    def zero_fraction_stats(self) -> tuple[float, float, float]:
        values = [r.zero_fraction for r in self.rows]
        return min(values), max(values), statistics.fmean(values)


def segment_bundle(bundle: dict[str, Any], *, bundle_path: Path) -> tuple[PhaseGroup, PhaseGroup, PhaseGroup, PhaseGroup]:
    """Split ``bundle['probes']`` into the four Phase 1 phases.

    Relies on the fixed phase order in ``lab/local-runner/run_phase1.py``:
    baseline, §9.4 detection-capability control, §9.3 driver-direct
    measurement, negative zeroisation control -- each phase run for the same
    number of cycles and appended to the probe list in that order. The
    baseline (boundary UNSPECIFIED) and the §9.4 control (probe_name
    framework_allocator_reuse) are distinguishable by field content; the §9.3
    measurement and the negative control are NOT -- both are
    memory_global_read_before_write records with boundary SEPARATE_LAUNCH,
    because run_phase1.py never records `expect_zeroed` on the record itself.
    They are told apart only by position: the negative control's records were
    appended after the measurement's. This function checks that the recovered
    counts are internally consistent (equal cycle counts across all four
    phases) before trusting that split, and fails loudly if they are not.
    """
    probes = bundle.get("probes", [])
    if not probes:
        raise SummaryError(f"{bundle_path}: 'probes' is empty.")

    rows = [
        _to_probe_row(p, index=i, bundle_path=bundle_path) for i, p in enumerate(probes)
    ]

    baseline = [r for r in rows if r.probe_name == MEMORY_PROBE_NAME and r.boundary == "UNSPECIFIED"]
    detection = [r for r in rows if r.probe_name == FRAMEWORK_PROBE_NAME]
    separate_launch = [
        r for r in rows if r.probe_name == MEMORY_PROBE_NAME and r.boundary == "SEPARATE_LAUNCH"
    ]

    classified = len(baseline) + len(detection) + len(separate_launch)
    if classified != len(rows):
        unrecognised = [r for r in rows if r not in baseline and r not in detection and r not in separate_launch]
        names = sorted({(r.probe_name, r.boundary) for r in unrecognised})
        raise SummaryError(
            f"{bundle_path}: {len(rows) - classified} of {len(rows)} probe "
            f"record(s) do not match a recognised Phase 1 phase "
            f"(probe_name, boundary): {names}. This script only understands "
            f"the phases lab/local-runner/run_phase1.py produces."
        )

    if not baseline:
        raise SummaryError(f"{bundle_path}: no baseline (boundary=UNSPECIFIED) records found.")
    if not detection:
        raise SummaryError(
            f"{bundle_path}: no §9.4 detection-capability control "
            f"(probe_name={FRAMEWORK_PROBE_NAME!r}) records found. Without "
            f"it there is no positive control and nothing else here is "
            f"interpretable (CHARTER.md §11)."
        )
    if len(detection) != len(baseline):
        raise SummaryError(
            f"{bundle_path}: baseline has {len(baseline)} cycles but the "
            f"§9.4 control has {len(detection)}; lab/local-runner/"
            f"run_phase1.py runs all phases for the same --cycles count, so "
            f"this mismatch means the bundle was not produced by a complete "
            f"run of that script. Refusing to guess a split."
        )
    if len(separate_launch) != 2 * len(baseline):
        raise SummaryError(
            f"{bundle_path}: expected {2 * len(baseline)} SEPARATE_LAUNCH "
            f"{MEMORY_PROBE_NAME!r} records (the §9.3 measurement and the "
            f"negative control, {len(baseline)} cycles each) but found "
            f"{len(separate_launch)}. Cannot safely split the §9.3 "
            f"measurement from the negative control without this invariant "
            f"holding -- the two are otherwise indistinguishable in the "
            f"stored record."
        )

    cycles = len(baseline)
    measurement_9_3 = separate_launch[:cycles]
    negative_control = separate_launch[cycles:]

    return (
        PhaseGroup("baseline", baseline),
        PhaseGroup("detection_control_9_4", detection),
        PhaseGroup("measurement_9_3", measurement_9_3),
        PhaseGroup("negative_control", negative_control),
    )


# ---------------------------------------------------------------------------
# Per-bundle and per-host facts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BundleFacts:
    path: Path
    run_id: str
    experiment_id: str
    timestamp_utc: str
    provider_code: str
    product_claim: str
    tool_version: str
    tool_commit: str
    cuda_runtime_version: str
    cuda_driver_version: str
    container_digest: str | None
    device_name: str
    compute_capability: str
    backend: str
    container_profile: str
    cupy_version: str
    allocation_model_classification: str
    allocation_model_confidence: float
    automatic_publication_allowed: bool
    baseline: PhaseGroup
    detection: PhaseGroup
    measurement: PhaseGroup
    negative: PhaseGroup


def extract_bundle_facts(bundle: dict[str, Any], *, path: Path) -> BundleFacts:
    baseline, detection, measurement, negative = segment_bundle(bundle, bundle_path=path)

    cupy_versions = {
        require(p, "driver_metadata.framework_version", bundle_path=path)
        for p in bundle["probes"]
        if p.get("probe_name") == FRAMEWORK_PROBE_NAME
    }
    if len(cupy_versions) != 1:
        raise SummaryError(
            f"{path}: §9.4 control records disagree on CuPy version: "
            f"{sorted(cupy_versions)}."
        )

    device_names = {
        require(p, "driver_metadata.device_name", bundle_path=path)
        for p in bundle["probes"]
    }
    if len(device_names) != 1:
        raise SummaryError(
            f"{path}: more than one device_name appears in this bundle's "
            f"probe records ({sorted(device_names)}); this script assumes "
            f"one bundle measures exactly one physical device."
        )

    return BundleFacts(
        path=path,
        run_id=require(bundle, "run_id", bundle_path=path),
        experiment_id=require(bundle, "experiment_id", bundle_path=path),
        timestamp_utc=require(bundle, "timestamp_utc", bundle_path=path),
        provider_code=require(bundle, "provider_code", bundle_path=path),
        product_claim=require(bundle, "product_claim", bundle_path=path),
        tool_version=require(bundle, "tool.version", bundle_path=path),
        tool_commit=require(bundle, "tool.commit", bundle_path=path),
        cuda_runtime_version=str(require(bundle, "tool.cuda_runtime_version", bundle_path=path)),
        cuda_driver_version=str(require(bundle, "tool.cuda_driver_version", bundle_path=path)),
        container_digest=bundle["tool"].get("container_digest"),
        device_name=next(iter(device_names)),
        compute_capability=require(bundle, "environment.compute_capability", bundle_path=path),
        backend=require(bundle, "environment.backend", bundle_path=path),
        container_profile=require(bundle, "environment.container_profile", bundle_path=path),
        cupy_version=next(iter(cupy_versions)),
        allocation_model_classification=require(
            bundle, "allocation_model.classification", bundle_path=path
        ),
        allocation_model_confidence=float(
            require(bundle, "allocation_model.confidence", bundle_path=path)
        ),
        automatic_publication_allowed=bool(
            require(bundle, "safety.automatic_publication_allowed", bundle_path=path)
        ),
        baseline=baseline,
        detection=detection,
        measurement=measurement,
        negative=negative,
    )


@dataclass
class HostSummary:
    label: str
    bundles: list[BundleFacts] = field(default_factory=list)

    def add(self, facts: BundleFacts) -> None:
        if self.bundles:
            first = self.bundles[0]
            for attr in (
                "device_name", "compute_capability", "cuda_driver_version",
                "cuda_runtime_version", "cupy_version",
            ):
                if getattr(facts, attr) != getattr(first, attr):
                    raise SummaryError(
                        f"host {self.label!r}: {facts.path} reports "
                        f"{attr}={getattr(facts, attr)!r}, but {first.path} "
                        f"reported {getattr(first, attr)!r}. Bundles grouped "
                        f"under one host label must describe one stable "
                        f"machine identity."
                    )
        self.bundles.append(facts)

    @property
    def identity(self) -> BundleFacts:
        return self.bundles[0]

    def pooled(self, selector) -> list[ProbeRow]:
        rows: list[ProbeRow] = []
        for b in self.bundles:
            rows.extend(selector(b).rows)
        return rows

    def pooled_group(self, name: str, selector) -> PhaseGroup:
        return PhaseGroup(name, self.pooled(selector))


# ---------------------------------------------------------------------------
# Report card
# ---------------------------------------------------------------------------


def build_host_report_card(host: HostSummary) -> ReportCard:
    measurement = host.pooled_group("measurement_9_3", lambda b: b.measurement)

    measurement_paths = measurement.measurement_paths
    if measurement_paths == {"driver_direct"}:
        path = MeasurementPath.DRIVER_DIRECT
    else:
        path = MeasurementPath.UNKNOWN

    memory_ev = MemoryHygieneEvidence(
        cycles=measurement.cycles,
        canary_recovered_cycles=measurement.recovered_cycles,
        ambiguous_cycles=measurement.ambiguous_cycles,
        # No §9.8 topology certificate exists anywhere in a plain Phase 1
        # bundle (enforced above: a bundle with any 'observations' entries is
        # refused before we get here), so there is no instrument evidence
        # that two allocations are the same physical accelerator.
        same_device_evidence=False,
        # True by construction: every cycle's two allocations came from the
        # single visible device on this host (checked in
        # extract_bundle_facts -- one device_name per bundle).
        same_advertised_model=True,
        same_model_classifier_validated=SAME_MODEL_CLASSIFIER_VALIDATED,
        inconsistent_across_runs=False,
        measurement_path=path,
    )

    allocation_classification = host.identity.allocation_model_classification
    if allocation_classification == "local_workstation":
        # gpu_seal.safety.policy.ALLOCATION_MODEL_CLASSES documents this
        # value as kept distinct "so a local control run is never counted as
        # a provider observation" -- lab/local-runner/run_phase1.py writes it
        # unconditionally, including when the host is a rented cloud
        # instance (as both hosts here are). grade_allocation_transparency()
        # has no branch for this sentinel, and feeding it through as a real
        # classification would grade a labelling gap in the tool as if it
        # were a finding about the provider. U, honestly captioned, is what
        # this actually is.
        allocation_transparency = (
            Grade.U,
            f"allocation_model.classification is 'local_workstation' in "
            f"this bundle. lab/local-runner/run_phase1.py writes that value "
            f"unconditionally and does not attempt to classify a rented "
            f"instance's allocation model, so this is a gap in what the "
            f"tool attempted here, not evidence about {host.label}'s real "
            f"allocation model.",
        )
    else:
        allocation_transparency = grade_allocation_transparency(
            documented_model=None,
            measured_model=allocation_classification,
            confidence=host.identity.allocation_model_confidence,
            contradicted=False,
        )

    return ReportCard(
        provider_code=host.label,
        memory_hygiene=grade_memory_hygiene(memory_ev),
        tenant_exposure=grade_tenant_exposure({}),
        hardware_claim=grade_hardware_claim(
            certificates=0,
            fingerprint_stable=False,
            consistent_with_advertised_class=None,
            instrument_is_evidence=False,
        ),
        location_claim=grade_location_claim("not_testable", repeated_measurements=0),
        allocation_transparency=allocation_transparency,
        attestation=attestation_field_report({"attestation_available": False}),
    )


# ---------------------------------------------------------------------------
# docs/STATUS.md and docs/scoring.md extraction
# ---------------------------------------------------------------------------


def extract_table_section(md_path: Path, heading: str) -> list[tuple[str, str]]:
    if not md_path.is_file():
        raise SummaryError(f"{md_path}: not found.")
    lines = md_path.read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == heading)
    except StopIteration as exc:
        raise SummaryError(
            f"{md_path}: heading {heading!r} not found; cannot generate the "
            f"'what this does not show' section without it."
        ) from exc

    rows: list[tuple[str, str]] = []
    for line in lines[start + 1:]:
        if line.startswith("#"):
            break
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) != 2:
            continue
        if all(set(c) <= {"-", ":", ""} for c in cells):
            continue
        if cells[0].lower() == "claim":
            continue
        rows.append((cells[0], cells[1]))

    if not rows:
        raise SummaryError(
            f"{md_path}: found heading {heading!r} but no table rows under it."
        )
    return rows


def extract_prose_section(md_path: Path, heading: str) -> str:
    if not md_path.is_file():
        raise SummaryError(f"{md_path}: not found.")
    lines = md_path.read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == heading)
    except StopIteration as exc:
        raise SummaryError(f"{md_path}: heading {heading!r} not found.") from exc

    body: list[str] = []
    for line in lines[start + 1:]:
        if line.startswith("#") or line.strip() == "---":
            break
        body.append(line)
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    if not body:
        raise SummaryError(f"{md_path}: heading {heading!r} has no body text.")
    return "\n".join(body).strip()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def md_link(target: Path, *, out_dir: Path) -> str:
    """Relative markdown-link path from ``out_dir`` to ``target``."""
    return Path(os.path.relpath(target, out_dir)).as_posix()


def fmt_grade(card_entry: tuple[Grade, str]) -> str:
    grade, basis = card_entry
    return f"**{grade.value}** — {basis}"


def render_probe_table(groups: list[tuple[str, PhaseGroup]]) -> str:
    lines = [
        "| # | Phase | probe_name | boundary | measurement_path | zero_fraction | owned_canary_exact_matches | owned_canary_match |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for phase_name, group in groups:
        for row in group.rows:
            lines.append(
                f"| {row.index} | {phase_name} | {row.probe_name} | {row.boundary} | "
                f"{row.measurement_path} | {row.zero_fraction:.6f} | "
                f"{row.owned_canary_exact_matches} | {row.owned_canary_match} |"
            )
    return "\n".join(lines)


def render_host_section(host: HostSummary, card: ReportCard) -> str:
    b = host.identity
    baseline = host.pooled_group("baseline", lambda x: x.baseline)
    detection = host.pooled_group("detection_control_9_4", lambda x: x.detection)
    measurement = host.pooled_group("measurement_9_3", lambda x: x.measurement)
    negative = host.pooled_group("negative_control", lambda x: x.negative)

    bl_min, bl_max, bl_mean = baseline.zero_fraction_stats()
    m_min, m_max, m_mean = measurement.zero_fraction_stats()
    n_min, n_max, n_mean = negative.zero_fraction_stats()

    detection_pass = detection.cycles > 0 and detection.recovered_cycles > 0
    negative_pass = negative.recovered_cycles == 0

    m3_line = (
        f"**{measurement.recovered_cycles}/{measurement.cycles} owned canaries "
        f"recovered** across §9.3 driver-direct reuse cycles"
        f" (measurement_path: {', '.join(sorted(measurement.measurement_paths))})."
    )
    if measurement.recovered_cycles == 0 and detection_pass:
        m3_context = (
            "This null result is informative, not merely absent, because the "
            f"§9.4 detection-capability control on this host PASSED "
            f"({detection.recovered_cycles}/{detection.cycles} canaries recovered through the "
            "caching allocator): the harness is proven able to see a canary "
            "it planted, so a clean §9.3 result here means the driver did "
            "not hand this canary back, not that the harness is blind."
        )
    elif measurement.recovered_cycles == 0 and not detection_pass:
        m3_context = (
            "**This null result is NOT interpretable.** The §9.4 "
            f"detection-capability control on this host FAILED "
            f"({detection.recovered_cycles}/{detection.cycles} canaries "
            "recovered through the caching allocator): without a working "
            "positive control, CHARTER.md §11 is explicit that a clean "
            "result cannot be read as evidence the driver sanitised "
            "anything -- it is equally consistent with the harness itself "
            "being unable to see a canary it planted."
        )
    else:
        m3_context = (
            "CHARTER.md §7.5 applies before this result is disclosed or "
            "published anywhere: a canary recovered across a boundary where "
            "sanitisation was expected is the one result category this "
            "project treats as an accusation, and it requires private "
            "disclosure and provider coordination first."
        )

    bundle_ids = "; ".join(
        f"`{bf.run_id}` (`{bf.path.name}`)" for bf in host.bundles
    )

    lines = [
        f"### {host.label}",
        "",
        f"- **Bundle(s):** {bundle_ids}",
        f"- **Device:** {b.device_name}, compute capability {b.compute_capability}",
        f"- **Backend:** {b.backend}, container profile `{b.container_profile}`",
        f"- **CUDA driver / runtime version:** `{b.cuda_driver_version}` / `{b.cuda_runtime_version}`",
        f"- **CuPy version:** `{b.cupy_version}`",
        f"- **Tool version / commit:** `{b.tool_version}` / `{b.tool_commit}`",
        f"- **Container digest:** `{b.container_digest}`" if b.container_digest else "- **Container digest:** none recorded",
        f"- **automatic_publication_allowed (as signed):** {b.automatic_publication_allowed}",
        "",
        f"Baseline (fresh allocation, {baseline.cycles} cycles): "
        f"zero_fraction min={bl_min:.6f} max={bl_max:.6f} mean={bl_mean:.6f}.",
        "",
        f"- **§9.4 detection-capability control:** "
        f"{'PASS' if detection_pass else 'FAIL'} — "
        f"{detection.recovered_cycles}/{detection.cycles} canaries recovered "
        f"through the caching allocator (measurement_path: "
        f"{', '.join(sorted(detection.measurement_paths))}), "
        f"zero_fraction range {min(r.zero_fraction for r in detection.rows):.6f}"
        f"–{max(r.zero_fraction for r in detection.rows):.6f}.",
        "",
        f"- **§9.3 driver-direct measurement (headline):** {m3_line} "
        f"zero_fraction min={m_min:.6f} max={m_max:.6f} mean={m_mean:.6f}. "
        f"{m3_context}",
        "",
        f"- **Negative (explicit zeroisation) control:** "
        f"{'PASS' if negative_pass else 'FAIL'} — "
        f"{negative.recovered_cycles} false positive(s) of {negative.cycles} "
        f"cycles, zero_fraction min={n_min:.6f} max={n_max:.6f} mean={n_mean:.6f}.",
        "",
        "#### Per-probe record (zero_fraction, owned_canary_exact_matches, measurement_path)",
        "",
        render_probe_table([
            ("baseline", baseline),
            ("detection_control_9_4", detection),
            ("measurement_9_3", measurement),
            ("negative_control", negative),
        ]),
        "",
        "#### Report card (CHARTER.md §13) — basis carried through verbatim",
        "",
        f"- **§13.1 Memory lifecycle hygiene:** {fmt_grade(card.memory_hygiene)}",
        f"- **§13.2 Tenant exposure:** {fmt_grade(card.tenant_exposure)}",
        f"- **§13.3 Hardware claim consistency:** {fmt_grade(card.hardware_claim)}",
        f"- **§13.4 Location claim consistency:** {fmt_grade(card.location_claim)}",
        f"- **§13.5 Allocation-model transparency:** {fmt_grade(card.allocation_transparency)}",
        f"- **§13.6 Attestation (field report, not a grade):** {card.attestation['note']}",
        "",
    ]
    return "\n".join(lines)


def render_claim_boundaries(status_md: Path, *, out_dir: Path) -> str:
    rows = extract_table_section(status_md, "## Open claim boundaries")
    lines = [
        "Taken verbatim from "
        f"[`{status_md.relative_to(REPO_ROOT).as_posix()}`]"
        f"({md_link(status_md, out_dir=out_dir)})'s "
        "\"Open claim boundaries\" table. These two Linux-host Phase 1 "
        "bundles do not close any of them except the first, and even that "
        "one only partially:",
        "",
    ]
    for claim, evidence in rows:
        if "linux-driver" in claim.lower():
            lines.append(
                f"- **{claim}** — partially addressed, not closed. This "
                f"finding *is* two independent real-hardware Linux runs with "
                f"positive and negative controls, which is what STATUS.md "
                f"asks for as the minimum evidence (\"{evidence}\"); it is "
                f"still only two hosts, one run apiece, which is not "
                f"exhaustive coverage of Linux driver/CUDA/CuPy version "
                f"combinations."
            )
        else:
            lines.append(
                f"- **{claim}** — not addressed. Nothing in this bundle "
                f"pair speaks to it. Minimum additional evidence per "
                f"STATUS.md: \"{evidence}\""
            )
    return "\n".join(lines)


def render_memory_hygiene_ceiling(scoring_md: Path, *, out_dir: Path) -> str:
    body = extract_prose_section(scoring_md, "## U is not F")
    quoted = "\n".join(f"> {line}" if line else ">" for line in body.splitlines())
    d5_test = REPO_ROOT / D5_ENFORCEMENT_TEST
    path_test = REPO_ROOT / MEASUREMENT_PATH_GATE_TEST
    for test_path in (d5_test, path_test):
        if not test_path.is_file():
            raise SummaryError(
                f"{test_path}: expected safety test not found; cannot cite "
                f"it as the enforcement mechanism for the U ceiling."
            )
    return (
        "Every §13.1 grade above that shows U for that reason is not a "
        "weaker result than an A -- it is the correctly capped result. "
        f"[`{scoring_md.relative_to(REPO_ROOT).as_posix()}`]"
        f"({md_link(scoring_md, out_dir=out_dir)}) explains why:\n\n"
        f"{quoted}\n\n"
        "Concretely: every host below measures a single visible device end "
        "to end, so `same_advertised_model` is true for every cycle, but no "
        "§9.8 topology certificate exists in a Phase 1 bundle to supply "
        "`same_device_evidence`, and same-model die separation "
        "(§9.8b, contribution D5) has not landed in this checkout. Memory "
        "lifecycle hygiene stays capped at U on real hardware until D5 "
        f"closes that gap, and [`{D5_ENFORCEMENT_TEST}`]"
        f"({md_link(d5_test, out_dir=out_dir)}) "
        "(CHARTER.md §16 test 16) is the CI test that stops this cap from "
        "being bypassed by a future edit that forgets it. "
        f"[`{MEASUREMENT_PATH_GATE_TEST}`]({md_link(path_test, out_dir=out_dir)}) "
        "is the companion test guaranteeing that a §9.4 control result can "
        "never be graded as if it were a §9.3 provider finding."
    )


def render_document(hosts: list[HostSummary], cards: dict[str, ReportCard], *, out_dir: Path) -> str:
    total_cycles = sum(h.pooled_group("measurement_9_3", lambda x: x.measurement).cycles for h in hosts)
    total_recovered = sum(h.pooled_group("measurement_9_3", lambda x: x.measurement).recovered_cycles for h in hosts)

    host_list = ", ".join(f"**{h.label}** ({h.identity.device_name})" for h in hosts)

    headline = (
        f"Across {len(hosts)} independent Linux hosts ({host_list}) and "
        f"{total_cycles} total §9.3 driver-direct reuse cycles, "
        f"**{total_recovered}/{total_cycles} owned canaries were recovered**."
    )

    sections = [
        f"# F-001 — Linux driver memory residue: {len(hosts)}-host Phase 1 battery",
        "",
        "**Instrument:** GPU-SEAL Phase 1 control battery "
        "(`lab/local-runner/run_phase1.py`), run independently on each host "
        "below. Every figure in this document is read directly from that "
        "host's signed result bundle; see each host's subsection for the "
        "exact bundle file and run ID.",
        "",
        "## Headline",
        "",
        headline,
        "",
        (
            "Zero canaries recovered is stated here exactly as plainly as a "
            "recovery would have been, and it is not read as either a "
            "disappointment or a guarantee: see each host's §9.4 "
            "detection-capability control below for why a null result here "
            "is informative, and see \"What this does not show\" for what it "
            "does not extend to."
            if total_recovered == 0
            else
            "At least one owned canary was recovered across a boundary "
            "where sanitisation was expected. CHARTER.md §7.5's private "
            "disclosure and provider-coordination sequence applies before "
            "this leaves the machine any further than this draft."
        ),
        "",
        "## Per-host results",
        "",
    ]

    for host in hosts:
        sections.append(render_host_section(host, cards[host.label]))

    sections += [
        "## What this does not show",
        "",
        render_claim_boundaries(REPO_ROOT / "docs" / "STATUS.md", out_dir=out_dir),
        "",
        "## Why memory hygiene stays U",
        "",
        render_memory_hygiene_ceiling(REPO_ROOT / "docs" / "scoring.md", out_dir=out_dir),
        "",
    ]
    return "\n".join(sections) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_bundle_arg(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise SummaryError(
            f"--bundle {raw!r} is not in HOST=PATH form, e.g. "
            f"--bundle colab-t4=out/colab/run_....result.json"
        )
    host, _, path_str = raw.partition("=")
    host = host.strip()
    if not host:
        raise SummaryError(f"--bundle {raw!r}: empty host label.")
    return host, Path(path_str.strip())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--bundle", action="append", required=True, metavar="HOST=PATH",
        help="a signed Phase 1 result bundle and the host label to file it "
             "under; repeat for multiple bundles/hosts, or multiple times "
             "with the same host label for more than one run on that host",
    )
    ap.add_argument("--out", type=Path, required=True, help="output markdown path")
    args = ap.parse_args(argv)

    try:
        hosts: dict[str, HostSummary] = {}
        for raw in args.bundle:
            label, path = parse_bundle_arg(raw)
            bundle = load_bundle(path)
            facts = extract_bundle_facts(bundle, path=path)
            hosts.setdefault(label, HostSummary(label)).add(facts)

        if len(hosts) < 2:
            raise SummaryError(
                f"only {len(hosts)} host(s) supplied "
                f"({', '.join(hosts) or 'none'}); this finding is about "
                f"cross-host Linux driver behaviour and needs at least two."
            )

        cards = {label: build_host_report_card(host) for label, host in hosts.items()}

        document = render_document(
            list(hosts.values()), cards, out_dir=args.out.parent.resolve()
        )
    except SummaryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(document, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
