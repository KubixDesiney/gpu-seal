#!/usr/bin/env python3
"""Phase 1 control battery — CHARTER.md §11, §17 weeks 3-4.

Runs Memory Probe B (§9.3) through its positive and negative controls and
emits a signed result bundle.

    python3 lab/local-runner/run_phase1.py --out ./out

Exit criterion for weeks 3-4 (CHARTER.md §17):

    positive + negative local controls pass; no raw unknown data in logs or
    files.

This script decides pass/fail against that criterion and exits non-zero if it
is not met. The point of the positive control is unglamorous but load-bearing:
if the probe cannot detect a canary it planted itself in memory it knows was
reused, then a clean result from a cloud provider means nothing at all.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "probe"))

from gpu_seal import __version__  # noqa: E402
from gpu_seal.cuda import (  # noqa: E402
    BackendUnavailable,
    CupyBackend,
    PooledCupyBackend,
    SimulatedBackend,
)
from gpu_seal.evidence import ResultBundle, SigningKey  # noqa: E402
from gpu_seal.evidence.result import ToolProvenance  # noqa: E402
from gpu_seal.probes import (  # noqa: E402
    FrameworkAllocatorProbe,
    GlobalMemoryProbe,
    summarise,
)
from gpu_seal.probes.framework_allocator import summarise as fw_summarise  # noqa: E402
from gpu_seal.safety import CanarySet, EgressViolation  # noqa: E402

MIB = 1 << 20


def banner(text: str) -> None:
    print()
    print(text)
    print("-" * len(text))


def open_backend(force_sim: bool, leaky: bool):
    if not force_sim:
        try:
            return CupyBackend(), True
        except BackendUnavailable as exc:
            print(f"  no CUDA device ({str(exc).split('.')[0]}); using simulation")
    return SimulatedBackend(sanitises_on_free=not leaky, pool_bytes=256 * MIB), False


def open_pooled_backend(force_sim: bool, leaky: bool):
    """Backend for the §9.4 detection-capability control.

    A caching allocator, so free() returns the block to a pool rather than to
    the driver. On the simulated path this is modelled by a non-sanitising
    pool, which is what a caching allocator is.
    """
    if not force_sim:
        return PooledCupyBackend()
    return SimulatedBackend(sanitises_on_free=False, pool_bytes=256 * MIB)


def main() -> int:
    ap = argparse.ArgumentParser(description="GPU-SEAL Phase 1 control battery")
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--size-mib", type=int, default=64,
                    help="allocation size per cycle")
    ap.add_argument("--cycles", type=int, default=10,
                    help="repetitions per control (CHARTER.md §12)")
    ap.add_argument("--simulate", action="store_true",
                    help="force the simulated backend even if a GPU exists")
    ap.add_argument("--simulate-leaky", action="store_true",
                    help="simulated backend models a NON-sanitising allocator")
    args = ap.parse_args()

    size = args.size_mib * MIB
    args.out.mkdir(parents=True, exist_ok=True)

    print()
    print("GPU-SEAL Phase 1 control battery")
    print("=" * 62)
    print(f"  allocation size   {args.size_mib} MiB")
    print(f"  cycles / control  {args.cycles}")

    backend, is_real = open_backend(args.simulate, args.simulate_leaky)
    info = backend.device_info()
    print(f"  backend           {info['backend']} (real={info['backend_is_real']})")
    if is_real:
        print(f"  device            {info.get('device_name')} "
              f"cc{info.get('compute_capability')}")

    canaries = CanarySet.create()
    # shared_infrastructure=False: this is the researcher's own workstation.
    # Any residue here is our own from a previous kernel, so the entropy safety
    # stop would fire on every baseline read and measure nothing. On a RENTED
    # instance this must stay True -- see CHARTER.md §7.3.
    probe = GlobalMemoryProbe(
        backend, canaries, canary_stride=4 * MIB, shared_infrastructure=False
    )
    records = []
    verdicts = {}

    # -- Baseline ---------------------------------------------------------
    banner("Baseline: fresh cudaMalloc, read before write")
    print("  What does a brand-new allocation actually contain on this device?")
    fresh = probe.run_cycles(size, args.cycles, mode="fresh")
    fs = summarise(fresh)
    zeros = [c.observation.zero_fraction for c in fresh if c.usable]
    print(f"  usable cycles     {fs['cycles_usable']}/{fs['cycles_attempted']}")
    if zeros:
        print(f"  zero fraction     min={min(zeros):.6f} max={max(zeros):.6f}")
        ent = [c.observation.entropy_estimate for c in fresh if c.usable]
        print(f"  entropy           min={min(ent):.6f} max={max(ent):.6f}")
    print(f"  safety stops      {fs['safety_stop_cycles']}")
    records += [c.observation for c in fresh if c.observation]

    # -- Detection capability (§9.4) --------------------------------------
    #
    # This is the positive control CHARTER.md §11 requires, and it lives here
    # rather than in §9.3 for a reason found on real hardware: the RTX 3050
    # driver zeroes memory on free, so §9.3's own reuse cycle can never
    # recover a canary on this platform. A caching allocator never calls
    # cudaFree, so the driver is never given the chance -- which isolates
    # "can the harness see a marker it planted?" from "does this driver
    # scrub?". See docs/findings/2026-07-31-rtx3050-baseline.md.
    banner("POSITIVE control (§9.4): detection capability")
    print("  Plant a canary, free to a caching allocator's pool, reallocate,")
    print("  read before writing. The pool never calls cudaFree, so the driver")
    print("  is never told the memory was released and cannot scrub it.")
    print("  The canary MUST be recoverable. If it is not, the harness is")
    print("  blind and no result from any probe means anything.")

    detects = None
    pool_backend = None
    try:
        pool_backend = open_pooled_backend(args.simulate, args.simulate_leaky)
        fw_probe = FrameworkAllocatorProbe(
            pool_backend, CanarySet.create(),
            canary_stride=4 * MIB, shared_infrastructure=False,
        )
        fw = fw_probe.run_cycles(size, args.cycles)
        fws = fw_summarise(fw)
        print(f"  usable cycles     {fws['cycles_usable']}/{fws['cycles_attempted']}")
        print(f"  buffer reuse rate {fws.get('buffer_reuse_rate')}")
        print(f"  canary recovered  {fws['canary_recovered_cycles']}")
        print(f"  recovery rate     {fws['recovery_rate']}")
        if fws["exclusion_reasons"]:
            print(f"  exclusions        {fws['exclusion_reasons']}")
        records += [c.observation for c in fw if c.observation]
        detects = bool(fws["cycles_usable"]) and fws["canary_recovered_cycles"] > 0
    except Exception as exc:  # noqa: BLE001 - report, do not crash the battery
        print(f"  §9.4 control unavailable: {type(exc).__name__}: {exc}")
        detects = False
    finally:
        if pool_backend is not None:
            try:
                pool_backend.close()
            except Exception:  # noqa: BLE001
                pass

    verdicts["detection_capability"] = detects
    print(f"  -> {'PASS' if detects else 'FAIL'}: harness "
          f"{'can' if detects else 'CANNOT'} detect a canary it planted")

    # -- §9.3 driver behaviour (measurement, not a control) ---------------
    banner("MEASUREMENT (§9.3): does the driver return reused memory?")
    print("  Same cycle through the raw runtime API, so cudaFree IS called and")
    print("  the driver DOES get the chance to sanitise. Unlike the control")
    print("  above, a clean result here is a finding rather than a failure.")
    pos = probe.run_cycles(size, args.cycles, mode="reuse")
    ps = summarise(pos)
    print(f"  usable cycles     {ps['cycles_usable']}/{ps['cycles_attempted']}")
    print(f"  canary recovered  {ps['canary_recovered_cycles']}")
    print(f"  recovery rate     {ps['recovery_rate']}")
    if ps["exclusion_reasons"]:
        print(f"  exclusions        {ps['exclusion_reasons']}")
    records += [c.observation for c in pos if c.observation]

    if ps["cycles_usable"] and ps["canary_recovered_cycles"] == 0:
        print("  -> observation: no residue across the driver boundary")
        print("     Interpretable ONLY because the §9.4 control above passed.")
    elif ps["canary_recovered_cycles"]:
        print("  -> observation: canary survived the driver boundary")
        print("     CHARTER.md §7.5 applies before this leaves the machine.")

    # -- Negative control -------------------------------------------------
    banner("NEGATIVE control: explicit zeroisation before free")
    print("  Same cycle, but the allocation is memset to zero first.")
    print("  The canary must NOT be recovered. Any recovery is a false positive.")
    neg = probe.run_cycles(size, args.cycles, mode="zeroed")
    ns = summarise(neg)
    print(f"  usable cycles     {ns['cycles_usable']}/{ns['cycles_attempted']}")
    print(f"  false positives   {ns['canary_recovered_cycles']}")
    if ns["exclusion_reasons"]:
        print(f"  exclusions        {ns['exclusion_reasons']}")
    records += [c.observation for c in neg if c.observation]

    clean = bool(ns["cycles_usable"]) and ns["canary_recovered_cycles"] == 0
    verdicts["negative_control_clean"] = clean
    print(f"  -> {'PASS' if clean else 'FAIL'}: "
          f"{ns['canary_recovered_cycles']} false positive(s)")

    # -- Evidence ---------------------------------------------------------
    banner("Evidence bundle")
    bundle = ResultBundle(
        experiment_id=f"exp_phase1_{uuid.uuid4().hex[:12]}",
        run_id=f"run_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
        provider_code="local-lab",
        region_claim="n/a",
        product_claim=info.get("device_name", "local"),
        tool=ToolProvenance(
            version=__version__,
            commit=_git_commit(),
            container_digest=os.environ.get("GPU_SEAL_CONTAINER_DIGEST"),
            cuda_runtime_version=info.get("cuda_runtime_version"),
            cuda_driver_version=info.get("cuda_driver_version"),
        ),
        probes=records,
        environment=dict(info),
        allocation_model={
            "classification": "local_workstation",
            "confidence": 1.0,
            "evidence": ["researcher-owned hardware, not a rented allocation"],
        },
    )

    # clear_for_publication() must run BEFORE sign(): automatic_publication_
    # allowed is baked into the signed, hashed payload at sign() time, so
    # clearing afterwards would leave that field permanently false on disk
    # regardless of what this script prints. CHARTER.md's "publication is
    # gated, not defaulted" only holds if the gate is checked before the
    # bundle is sealed -- see ResultBundle.clear_for_publication's docstring
    # and tests/safety/test_egress_and_publication.py::
    # test_clean_bundle_can_be_cleared_for_publication for the intended order.
    publish_error: str | None = None
    try:
        bundle.clear_for_publication()
    except EgressViolation as exc:
        publish_error = str(exc).split(":", 1)[-1].strip().split(".")[0]

    signed = bundle.sign(SigningKey.generate())
    path = args.out / f"{bundle.run_id}.result.json"
    path.write_text(json.dumps(signed, indent=2), encoding="utf-8")

    print(f"  probes recorded   {len(records)}")
    print(f"  signature valid   {ResultBundle.verify(signed)}")
    print(f"  written to        {path}")
    if publish_error is None:
        print("  publishable       yes")
    else:
        print(f"  publishable       no -- {publish_error}")

    # -- Verdict ----------------------------------------------------------
    banner("Week 3-4 exit criterion")
    print("  'positive + negative local controls pass; no raw unknown data")
    print("   in logs or files' (CHARTER.md §17)")
    print()
    print("  The positive control is §9.4 (detection capability), not §9.3.")
    print("  §9.3 is the measurement being validated, not a control -- a")
    print("  platform that sanitises correctly would fail it by design.")
    print()
    for name, ok in verdicts.items():
        print(f"  [{'x' if ok else ' '}] {name}")

    ok = all(verdicts.values())
    print()
    if not is_real:
        print("  NOTE: simulated backend. This exercises probe logic only.")
        print("  The exit criterion is not satisfied until it passes on the GPU.")
    print("  RESULT:", "PASS" if ok else "FAIL")
    print()

    try:
        backend.close()
    except Exception:  # noqa: BLE001
        pass
    return 0 if ok else 1


def _git_commit() -> str:
    import subprocess  # noqa: S404 - reading our own commit, not user input

    try:
        out = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return f"sha256:{out.stdout.strip()}" if out.returncode == 0 else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
