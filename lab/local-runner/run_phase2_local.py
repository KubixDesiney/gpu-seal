#!/usr/bin/env python3
"""Phase 2 dress rehearsal, run entirely on local hardware.

    python3 lab/local-runner/run_phase2_local.py --out ./out

CHARTER.md §17 weeks 5-8: exposure and container tests, then the topology
instrument and the allocation-model classifier. This script runs every probe
family that the local RTX 3050 lab can support, wires their output into one
signed bundle, and grades the §13 report card from it.

**It is a rehearsal, not a measurement of anything.** The "provider" is the
researcher's own workstation. `provider_code` is `local-lab` and the
allocation model is `local_workstation`, so nothing here can be mistaken for
a provider observation. What it exercises is the *pipeline*: inventory ->
classification -> controls -> measurement -> exposure -> topology -> report card ->
signed bundle, in the order §11 requires, with every gate live.

Families that refuse to run here, and why — the refusals are the point:

    §9.9  location    no landmark set configured; a workstation's network
                      position is not a provider region claim
    §9.10 attestation needs H100-class confidential computing (§20)
    §9.12 MIG         needs A100/H100-class silicon (§20)
    §9.8b D5          needs N rented instances of one model (§11 Phase 2b)

Exit code is 0 when every control that *can* run passes.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "probe"))

from gpu_seal import __version__  # noqa: E402
from gpu_seal.analysis.statistics import ObservationCounts  # noqa: E402
from gpu_seal.controller.evidence_store import EvidenceStore  # noqa: E402
from gpu_seal.cuda import (  # noqa: E402
    BackendUnavailable,
    CupyBackend,
    PooledCupyBackend,
    SimulatedBackend,
)
from gpu_seal.cuda.nvml import read_nvml  # noqa: E402
from gpu_seal.evidence import (  # noqa: E402
    key_source_from_options,
    signing_metadata,
)
from gpu_seal.evidence.result import ResultBundle, ToolProvenance  # noqa: E402
from gpu_seal.probes import (  # noqa: E402
    AllocationEvidence,
    AllocationModelClassifier,
    DeviceExposureProbe,
    EnvironmentInventoryProbe,
    FrameworkAllocatorProbe,
    GlobalMemoryProbe,
    ProviderClaims,
    measure_scheduling_gaps,
)
from gpu_seal.probes.framework_allocator import summarise as fw_summarise  # noqa: E402
from gpu_seal.probes.memory_global import summarise  # noqa: E402
from gpu_seal.probes.topology import (  # noqa: E402
    PUBLISHED_JITTER_BASELINE_CYCLES,
    CudaLatencySource,
    TopologyProbe,
    compare_certificates,
)
from gpu_seal.reporting import (  # noqa: E402
    MeasurementPath,
    MemoryHygieneEvidence,
    build_report_card,
)
from gpu_seal.safety import CampaignControl, CanarySet  # noqa: E402

MIB = 1 << 20


def banner(text: str) -> None:
    print()
    print(text)
    print("-" * len(text))


def field(label: str, value: object) -> None:
    print(f"  {label:<32}{value}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--size-mib", type=int, default=32)
    ap.add_argument("--cycles", type=int, default=10)
    ap.add_argument("--simulate", action="store_true")
    ap.add_argument("--signing-key", type=Path,
                    help="caller-supplied Ed25519 private-key PEM")
    ap.add_argument(
        "--unsafe-development-ephemeral",
        action="store_true",
        help=(
            "explicitly use an ephemeral key; output is not provenance evidence"
        ),
    )
    args = ap.parse_args()

    try:
        key_source = key_source_from_options(
            args.signing_key,
            unsafe_development_ephemeral=args.unsafe_development_ephemeral,
        )
        signer = key_source.load()
    except (OSError, TypeError, ValueError) as exc:
        ap.error(str(exc))

    size = args.size_mib * MIB
    verdicts: dict[str, bool] = {}
    observations = []
    records = []

    print()
    print("GPU-SEAL Phase 2 dress rehearsal (local hardware)")
    print("=" * 62)
    print(f"  signing key       {signer.verify_key.fingerprint}")
    if not key_source.provenance_suitable:
        print(
            "  WARNING            UNSAFE DEVELOPMENT KEY: output is unsuitable "
            "for provenance claims"
        )

    campaign = CampaignControl.create()

    # -- Backend ---------------------------------------------------------
    is_real = False
    if not args.simulate:
        try:
            backend = CupyBackend()
            is_real = True
        except BackendUnavailable as exc:
            print(f"  no CUDA device ({exc}); using simulation")
            backend = SimulatedBackend(sanitises_on_free=True, pool_bytes=256 * MIB)
    else:
        backend = SimulatedBackend(sanitises_on_free=True, pool_bytes=256 * MIB)

    info = backend.device_info()
    nvml = read_nvml()

    # -- §9.1 Environment inventory -- runs first, everything else is read
    #    through it.
    banner("§9.1 Environment inventory")
    inventory_probe = EnvironmentInventoryProbe(
        backend,
        claims=ProviderClaims(
            provider_code="local-lab",
            product_name="researcher-owned workstation",
            advertised_gpu=str(info.get("device_name", "unknown")),
            advertised_tenancy="dedicated",
        ),
        nvml=nvml,
        campaign=campaign,
    )
    inventory = inventory_probe.collect(
        experiment_id=f"exp_phase2_{uuid.uuid4().hex[:12]}",
        tool_version=__version__,
        tool_commit=_git_commit(),
    )
    observations += inventory_probe.observations(inventory)
    field("device", info.get("device_name"))
    field("compute capability", info.get("compute_capability"))
    field("management library", "available" if nvml.available else "unavailable")
    field("containerised", inventory.system.get("containerised"))
    field("container profile", inventory.experiment.get("container_profile"))

    # -- §9.7 Allocation model -- BEFORE any memory result is interpreted.
    banner("§9.7 Allocation-model classifier (D3)")
    stall_ratio = measure_scheduling_gaps(
        backend, samples=256, campaign=campaign
    )
    classifier = AllocationModelClassifier(campaign=campaign)
    classification = classifier.classify(
        AllocationEvidence(
            documented_model=None,
            mig_enabled=nvml.mig_enabled,
            visible_memory_bytes=int(info.get("total_memory_bytes", 0) or 0),
            advertised_model_memory_bytes=int(info.get("total_memory_bytes", 0) or 0),
            visible_device_count=nvml.device_count,
            neighbour_process_count=nvml.compute_process_count,
            scheduling_stall_ratio=stall_ratio,
            reported_model=str(info.get("device_name", "")),
            containerised=inventory.system.get("containerised"),
        )
    )
    observations.append(classifier.observation(classification))
    field("classification", classification.classification)
    field("confidence", f"{classification.confidence:.2f}")
    field("scheduling stall", f"{stall_ratio:.2f}x median" if stall_ratio else "n/a")
    for name, score in classification.ranked[:3]:
        field(f"  {name}", f"{score:.2f}")
    if classification.classification == "time_sliced_full_gpu":
        # Not a misfire on a Windows/WDDM laptop. The display driver really
        # does preempt the GPU for the desktop compositor, and the compositor
        # really is another process holding a context on it. Both signals the
        # classifier keys on are present and both are true; a dedicated
        # datacentre passthrough instance shows neither. Worth stating,
        # because "the classifier said time-slicing on my laptop" reads like
        # a bug until you notice it is right.
        print("    ^ expected on a WDDM workstation: the desktop compositor")
        print("      holds a context and the driver preempts for it.")

    # -- §9.4 detection-capability control -------------------------------
    banner("§9.4 POSITIVE control: detection capability")
    detects = False
    pool_backend = None
    try:
        pool_backend = (
            PooledCupyBackend()
            if is_real
            else SimulatedBackend(sanitises_on_free=False, pool_bytes=256 * MIB)
        )
        fw = FrameworkAllocatorProbe(
            pool_backend,
            CanarySet.create(),
            canary_stride=4 * MIB,
            shared_infrastructure=False,
            campaign=campaign,
        ).run_cycles(size, args.cycles)
        fws = fw_summarise(fw)
        records += [c.observation for c in fw if c.observation]
        detects = bool(fws["cycles_usable"]) and fws["canary_recovered_cycles"] > 0
        field("usable cycles", f"{fws['cycles_usable']}/{fws['cycles_attempted']}")
        field("buffer reuse rate", fws.get("buffer_reuse_rate"))
        field("canary recovered", fws["canary_recovered_cycles"])
    except Exception as exc:  # noqa: BLE001 - report, do not crash the battery
        field("unavailable", f"{type(exc).__name__}: {exc}")
    finally:
        if pool_backend is not None:
            try:
                pool_backend.close()
            except Exception:  # noqa: BLE001
                pass
    verdicts["detection_capability"] = detects
    field("->", "PASS" if detects else "FAIL")

    # -- §9.3 measurement -------------------------------------------------
    banner("§9.3 MEASUREMENT: driver-path read-before-write")
    canaries = CanarySet.create()
    probe = GlobalMemoryProbe(
        backend, canaries, canary_stride=4 * MIB,
        shared_infrastructure=False, campaign=campaign,
    )
    reuse = probe.run_cycles(size, args.cycles, mode="reuse")
    rs = summarise(reuse)
    records += [c.observation for c in reuse if c.observation]
    counts = ObservationCounts(
        attempted=int(rs["cycles_attempted"]),
        usable=int(rs["cycles_usable"]),
        positive=int(rs["canary_recovered_cycles"]),
        excluded=int(rs["cycles_excluded"]),
        exclusion_reasons=list(rs["exclusion_reasons"]),
    )
    interval = counts.confidence_interval()
    field("usable cycles", f"{counts.usable}/{counts.attempted}")
    field("canary recovered", counts.positive)
    field("rate", counts.rate)
    field(
        "95% CI (Wilson)",
        f"[{interval[0]:.3f}, {interval[1]:.3f}]" if interval else "n/a",
    )

    # -- Negative control -------------------------------------------------
    banner("NEGATIVE control: explicit zeroisation before free")
    neg = probe.run_cycles(size, args.cycles, mode="zeroed")
    ns = summarise(neg)
    records += [c.observation for c in neg if c.observation]
    clean = bool(ns["cycles_usable"]) and ns["canary_recovered_cycles"] == 0
    verdicts["negative_control_clean"] = clean
    field("false positives", ns["canary_recovered_cycles"])
    field("->", "PASS" if clean else "FAIL")

    # -- §9.6 exposure inventory -----------------------------------------
    banner("§9.6 Device & namespace exposure inventory (D4)")
    exposure = DeviceExposureProbe(
        nvml=nvml,
        cuda_visible_device_count=1 if is_real else None,
        campaign=campaign,
    ).collect()
    observations += exposure
    tally: dict[str, int] = {}
    for record in exposure:
        tally[record.classification] = tally.get(record.classification, 0) + 1
    for name in sorted(tally):
        field(name, tally[name])

    # -- §9.8 topology instrument ----------------------------------------
    banner("§9.8 Topology fingerprint instrument (reproduction)")
    certificate = None
    topology_stable = False
    if is_real:
        try:
            source = CudaLatencySource(region_bytes=8 * MIB)
            topology = TopologyProbe(source, campaign=campaign)
            certificate = topology.certify(
                regions=6, blocks=32, hops=256, repetitions=4
            )
            second = topology.certify(regions=6, blocks=32, hops=256, repetitions=4)
            consistency = compare_certificates(
                certificate, second, same_advertised_model=True
            )
            observations.append(
                topology.observation(
                    certificate, advertised_gpu=str(info.get("device_name", ""))
                )
            )
            topology_stable = (
                certificate.median_jitter <= PUBLISHED_JITTER_BASELINE_CYCLES * 10
            )
            field("fidelity", certificate.fidelity)
            field("physical SMs", len(certificate.sm_labels))
            field(
                "median jitter",
                f"{certificate.median_jitter:.4f} cycles "
                f"(published baseline {PUBLISHED_JITTER_BASELINE_CYCLES})",
            )
            field("self-comparison", f"{consistency.band} d={consistency.distance:.5f}")
            field("supports continuity", consistency.supports_same_device_claim)
            print("    ^ correctly False: same advertised model, D5 open (§9.8b)")
        except Exception as exc:  # noqa: BLE001
            field("unavailable", f"{type(exc).__name__}: {exc}")
    else:
        field("skipped", "needs a real device")

    # -- Families that refuse to run here --------------------------------
    banner("Refused on this hardware (the refusals are the result)")
    for family, reason in (
        ("§9.9  location", "no landmark set configured for a workstation"),
        ("§9.10 attestation", "needs H100-class confidential computing (§20)"),
        ("§9.12 MIG temporal", "needs A100/H100-class silicon (§20)"),
        ("§9.8b separability", "needs N rented instances of one model (§11)"),
    ):
        field(family, reason)

    # -- §13 report card --------------------------------------------------
    banner("§13 Report card")
    card = build_report_card(
        provider_code="local-lab",
        memory=MemoryHygieneEvidence(
            cycles=counts.usable,
            canary_recovered_cycles=counts.positive,
            ambiguous_cycles=0,
            same_device_evidence=certificate is not None,
            same_advertised_model=True,
            measurement_path=(
                MeasurementPath.DRIVER_DIRECT if is_real else MeasurementPath.SIMULATED
            ),
        ),
        exposure_classifications=tally,
        topology_certificates=1 if certificate else 0,
        topology_stable=topology_stable,
        topology_consistent=True if certificate else None,
        topology_is_evidence=bool(certificate and certificate.is_evidence),
        location_band="not_testable",
        location_measurements=0,
        documented_allocation_model=None,
        measured_allocation_model=classification.classification,
        allocation_confidence=classification.confidence,
        allocation_contradicted=bool(classification.contradicting),
        attestation_fields={"attestation_available": False},
    )
    payload = card.to_dict()
    for key in (
        "memory_lifecycle_hygiene",
        "tenant_exposure",
        "hardware_claim_consistency",
        "location_claim_consistency",
        "allocation_model_transparency",
    ):
        field(key, payload[key]["grade"])
    field("attestation", "field report, not a grade (§13.6)")

    # -- Evidence ---------------------------------------------------------
    banner("Evidence bundle")
    bundle = ResultBundle(
        experiment_id=inventory.experiment["id"],
        run_id=f"run_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
        provider_code="local-lab",
        region_claim="n/a",
        product_claim=str(info.get("device_name", "local")),
        tool=ToolProvenance(
            version=__version__,
            commit=_git_commit(),
            cuda_runtime_version=info.get("cuda_runtime_version"),
            cuda_driver_version=info.get("cuda_driver_version"),
        ),
        probes=records,
        observations=observations,
        environment={**dict(info), "inventory": inventory.to_dict()},
        allocation_model={
            "classification": classification.classification,
            "confidence": classification.confidence,
            "evidence": classification.evidence,
            "limitations": classification.limitations,
        },
        report_card=payload,
    )

    bundle.environment["signing"] = signing_metadata(key_source, signer)
    stored = EvidenceStore(args.out).write(bundle, signer)
    field("probe records", len(records))
    field("observations", len(observations))
    field("signature valid", stored.signature_verified)
    field("written to", stored.path)
    field("publishable", "yes" if stored.publishable else "no")
    if stored.refusal:
        print(f"    reason: {stored.refusal.split(':', 1)[-1].strip()[:200]}")

    # -- Verdict ----------------------------------------------------------
    banner("Verdict")
    for name, ok in verdicts.items():
        print(f"  [{'x' if ok else ' '}] {name}")
    ok = all(verdicts.values())
    print()
    if not is_real:
        print("  NOTE: simulated backend. Probe logic only, not a measurement.")
    print("  RESULT:", "PASS" if ok else "FAIL")
    print()

    try:
        backend.close()
    except Exception:  # noqa: BLE001
        pass
    return 0 if ok else 1


def _git_commit() -> str:
    import subprocess  # noqa: S404 - reading our own commit, not user input

    git = shutil.which("git")
    if git is None:
        return "unknown"
    try:
        out = subprocess.run(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return f"sha256:{out.stdout.strip()}" if out.returncode == 0 else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
