# Project progress

**Snapshot:** 2026-09-04 · **Version:** `0.1.0.dev0` · **Phase:** local
instrument validation; provider study not started

The dated, measured counts live in [`STATUS.md`](STATUS.md). This page is the
implementation roadmap and category-level interpretation; it intentionally
does not repeat historic test counts or use a completion percentage.

## Assurance categories

| Category | Current assessment | Boundary |
|---|---|---|
| Ethics enforcement | Implemented in source and exercised by the safety suite and mutation battery. | The owner still has to sign the protocol before provider work. |
| Test rigour | Current local Python suite, safety suite, mutation battery, and 77% branch floor are green; see `STATUS.md`. | CI's Python 3.10-3.12 matrix and a fresh release artifact still need to be the final release record. |
| Research grounding | Prior-art and pre-registration documents exist. | Independent review and any amendments remain human work. |
| Reproducibility | Hash-locked release inputs, signed schemas, and artifact gates exist. | A current pinned CUDA/container conformance run is not available on this Windows host. |
| Probe coverage | Thirteen probe families are represented; unsupported families fail closed when prerequisites are absent. | “Implemented” does not mean hardware-validated. |
| Hardware validation | A local Windows RTX 3050/CUDA smoke path is available. | Linux, MIG, H100 CC, and same-model multi-instance evidence are still open. |
| Provider readiness | Campaign orchestration, runtime contract, timeout handling, cleanup reconciliation, and deterministic fake validation are implemented. | No concrete provider adapter, provider measurement, or provider validation is claimed; selection and authorization remain open. |

## Implemented in code

- Safe-buffer containment, canary ownership, aggregate-only egress, automatic
  safety stop, schema validation, signed result bundles, and external-key
  verification.
- Controller enforcement for provider policy, ownership confirmation, budget
  reservations, duration limits, disclosure order, and publication gating.
- One root-owned campaign context shared by probes and provider runners, with
  fail-closed checks before allocation, native execution, and memory copying.
- Explicit PEM/OS-key-store/KMS signing extension points, public-key
  fingerprints, unsafe-development marking, provider-runtime orchestration,
  deterministic fake execution, timeout handling, and cleanup reconciliation.
- Explicit measurement-path labels so framework allocator controls cannot be
  misread as driver-direct provider findings.
- Local CUDA backends, a simulated backend for software-only checks, report-card
  grading, topology comparison, allocation-model classification, MIG refusal
  on unsupported hardware, and the C++/CUDA native memory-touching slice.
- CI and local checks for shell syntax, safety tests, mutation coverage, Python
  coverage, wheel contents, dashboard assets, provider policy, mutable-action
  rejection, dependency advisories, and release integrity.

## Current local evidence

The current host is Windows 11 with one researcher-owned NVIDIA RTX 3050 Laptop
GPU (compute capability 8.6). `lab/local-runner/smoke.py` reports a real CuPy
backend on that device. This establishes only that the local CUDA path can be
entered. It does not establish Linux-driver behaviour, provider isolation,
MIG temporal isolation, confidential computing, or same-model die continuity.

The local Phase 1 controls and topology findings recorded under `docs/findings/`
are historical, bounded development evidence. They must not be promoted to
provider evidence or generalized beyond their recorded platform and container
conditions.

## Probe-family state

| Family | State |
|---|---|
| Environment, local/shared memory, driver-direct VRAM, framework allocator, device exposure, allocation classifier, topology | Implemented; local execution is available where the host supports it. |
| Sequential self-canary | Implemented; requires separate owned rentals and D5 gating. |
| Same-model die separation (D5) | Implemented evaluator; no real same-model multi-instance validation. |
| Coarse location consistency | Implemented; requires a rented instance and a region claim. |
| H100 attestation and application-channel binding | Implemented reporting path; no H100 CC validation. |
| MIG temporal isolation | Implemented refusal/reporting path; requires A100/H100 MIG hardware. |

## Gates before provider work

- [x] Full local Python contract is green in the current snapshot.
- [x] The mutation inventory covers every safety file.
- [x] The policy loader distinguishes complete records from awaiting records.
- [x] The release checker rejects a dirty worktree and checks public-tree
      pseudonymisation.
- [x] Engineering-owned release-gap architecture is implemented and locally
      validated with a deterministic provider runtime; no real adapter is
      implied.
- [ ] Complete and record written permission for `provider-b` and `provider-d`.
- [ ] Obtain owner-signed ethics approval.
- [ ] Run the native conformance gate in the pinned CUDA build.
- [ ] Complete the Linux, MIG/H100, H100 CC, and D5 experiments that support
      the intended claims.
- [x] Owner approved the working name, product category, platform posture, and
      formal trust-model direction; budget, disclosure, deployment, and public-
      release decisions remain open.

The controller must remain fail-closed while any applicable gate is open. See
[`STATUS.md`](STATUS.md) and [`OWNER-ACTION-CHECKLIST.md`](OWNER-ACTION-CHECKLIST.md)
for the handoff.
