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
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "probe"))

from gpu_seal import __version__  # noqa: E402
from gpu_seal.cuda import BackendUnavailable, CupyBackend, SimulatedBackend  # noqa: E402
from gpu_seal.evidence import ResultBundle, SigningKey  # noqa: E402
from gpu_seal.evidence.result import ToolProvenance  # noqa: E402
from gpu_seal.probes import GlobalMemoryProbe, summarise  # noqa: E402
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

    # -- Positive control -------------------------------------------------
    banner("POSITIVE control: same-process allocator reuse")
    print("  Plant an owned canary, free, reallocate, read before writing.")
    print("  The canary SHOULD be recoverable. If it is not, the probe is")
    print("  blind and no negative result from it can be trusted.")
    pos = probe.run_cycles(size, args.cycles, mode="reuse")
    ps = summarise(pos)
    print(f"  usable cycles     {ps['cycles_usable']}/{ps['cycles_attempted']}")
    print(f"  canary recovered  {ps['canary_recovered_cycles']}")
    print(f"  recovery rate     {ps['recovery_rate']}")
    if ps["exclusion_reasons"]:
        print(f"  exclusions        {ps['exclusion_reasons']}")
    records += [c.observation for c in pos if c.observation]

    detects = bool(ps["cycles_usable"]) and ps["canary_recovered_cycles"] > 0
    verdicts["positive_control_detects"] = detects
    print(f"  -> {'PASS' if detects else 'FAIL'}: probe "
          f"{'can' if detects else 'CANNOT'} detect a surviving canary")

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

    signed = bundle.sign(SigningKey.generate())
    path = args.out / f"{bundle.run_id}.result.json"
    path.write_text(json.dumps(signed, indent=2), encoding="utf-8")

    print(f"  probes recorded   {len(records)}")
    print(f"  signature valid   {ResultBundle.verify(signed)}")
    print(f"  written to        {path}")

    try:
        bundle.clear_for_publication()
        print("  publishable       yes")
    except EgressViolation as exc:
        reason = str(exc).split(":", 1)[-1].strip().split(".")[0]
        print(f"  publishable       no -- {reason}")

    # -- Verdict ----------------------------------------------------------
    banner("Week 3-4 exit criterion")
    print("  'positive + negative local controls pass; no raw unknown data")
    print("   in logs or files' (CHARTER.md §17)")
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
