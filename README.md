# GPU-SEAL

*Internal codename: Ghost Meter*

> Measures the GPU you rented, using only ordinary customer privileges, under
> a strict canary-only data policy. An assurance and measurement framework —
> **not** an exploitation toolkit.

[![status](https://img.shields.io/badge/status-pre--alpha%20(Phase%200%E2%80%931)-orange)]()
[![tests](https://img.shields.io/badge/tests-289%20passing-brightgreen)]()
[![mutations caught](https://img.shields.io/badge/injected%20violations%20caught-36%2F36-brightgreen)]()
[![probe families](https://img.shields.io/badge/probe%20families-13%2F13%20implemented-brightgreen)]()
[![licence](https://img.shields.io/badge/licence-Apache--2.0-blue)]()

**GPU-SEAL is a tenant-side, canary-only framework that lets GPU-cloud
customers independently measure memory sanitisation, hardware consistency,
and isolation controls without accessing other tenants’ data.**

**Primary audience:** security engineers and GPU-cloud decision-makers.
**Secondary audience:** academic and independent security reviewers.

New to the project, or looking for a specific role's path through the docs
(engineer, security reviewer, academic reviewer, operator)? Start at the
[documentation index](docs/INDEX.md).

---

## The problem

A GPU-cloud tenant pays for a clean chip, a specific model, a specific
region, and isolation from other tenants — and receives an invoice, not
evidence. Nothing in that commercial relationship lets the customer check any
of those claims from where they're actually sitting: inside the rented
instance, with no special access.

The gap is not hypothetical. NVIDIA's own CUDA documentation states that
memory returned by `cudaMalloc`, `cuMemAlloc`, `cudaMallocManaged`, and
`cuMemAllocManaged` **"is not cleared,"** and NVIDIA ships an administrative
`--clear-memory` tool precisely because clearing isn't the default.
Confidential Computing scrubs memory at Function Level Reset, not within a
session. MIG's documentation covers *runtime* isolation in detail and says
nothing about what happens when an instance is destroyed and handed to the
next tenant.

Nobody measures any of this in the wild, across providers, from the tenant's
own seat. That's the gap GPU-SEAL targets: turning "everyone knows GPUs might
leak" into a reproducible, signed, per-provider dataset — or into evidence
that they don't.

## What it measures

Thirteen probe families ([`CHARTER.md`](CHARTER.md) §9):

- **Memory residue** — device-global VRAM and shared memory, read before any
  write of our own
- **Detection-capability control** — a framework-level allocator canary that
  proves the probe *can* recover a marker when one exists, independent of
  what the driver does
- **Isolation & exposure** — device/namespace visibility, allocation-model
  classification (dedicated vs. shared vs. time-sliced), MIG temporal
  isolation
- **Hardware identity** — a topology fingerprint, reproduced from external
  published research, checked for consistency with an advertised chip class
- **Location & attestation** — coarse network-location consistency,
  confidential-computing attestation and channel binding

Every measurement leaves the probe as a signed, schema-validated JSON
bundle — never as raw memory.

## What it absolutely does not do

GPU-SEAL will never: exploit a provider, escape a VM or container, access
the host OS, circumvent authentication or billing, read another tenant's
files, processes, traffic, or data, recover natural-language text from
memory it didn't write, classify unknown memory content, retain raw unknown
VRAM, attempt Rowhammer / privilege escalation / denial of service, or
publish an uncoordinated accusation.

It searches only for cryptographic canaries it minted itself — there is no
API that accepts a caller-supplied search pattern, and static analysis
(`tests/safety/test_static_analysis.py`) rejects source that tries. Full
policy, with an enforcement point named for every rule: [`ETHICS.md`](ETHICS.md).

---

## Status — 2026-08-01

No cloud testing has occurred. No provider has been measured. No measurement
study exists yet.

**Verified locally**

- 289/289 tests passing; 36/36 injected policy violations caught by the
  negative-control mutation battery (`lab/verify-safety-suite.sh`) — a green
  safety suite that cannot be shown to fail is decoration, so this is run
  every time, not assumed
- Framework-allocator control (§9.4): **10/10** canary recovery on the lab
  RTX 3050 — proves the probe can detect a marker it planted, independent of
  driver behaviour
- Global VRAM read-before-write (§9.3) on the same GPU: **0/10** recovered —
  this platform's driver zeroes memory on free; see
  [Finding 001](docs/findings/2026-07-31-rtx3050-baseline.md)
- Topology fingerprint (§9.8) reproduced on real silicon: 16 physical SMs,
  median jitter 0.047–0.096 cycles across three runs (published baseline
  0.09, measured on different hardware under different load — an
  order-of-magnitude comparison only)

**Implemented but hardware-blocked** (built and tested; cannot be exercised
on hardware available to this project)

- Attestation + channel binding (§9.10/§9.11) — needs H100-class
  confidential-computing silicon
- MIG temporal isolation (§9.12) — correctly refuses on the consumer GPU in
  the lab; needs A100/H100-class silicon
- Same-model die separability (§9.8b) — evaluator built and tested against
  synthetic ground truth; needs *N* rented instances of one advertised model
- Self-vs-self sequential canary (§9.5) — needs two separate rentals of the
  same instance type
- Coarse location consistency (§9.9) — needs a rented instance with a region
  claim to check against

**Not yet proven**

- Allocation-model classifier (§9.7) confidences are documented-behaviour
  priors — ranked, not calibrated against ground truth
- Whether the RTX-3050/WSL2 zero-on-free result generalises to Linux,
  datacentre silicon, or any actual provider. It is one consumer platform,
  measured once, and is not treated as more than that anywhere in this repo

**Blocked before provider testing** (Phase 0 gate, enforced by CI, not a
to-do list)

- Provider policy matrix: **0 of 4** providers reviewed. No named-provider
  probing may begin until this is filled in — enforced by
  `lab/check-provider-policy.py`
- The probe agent is still Python; [ADR-001](docs/adr/001-implementation-language.md)
  makes a port to a lower-level language a precondition for Phase 2
- Ethics review sign-off is outstanding (the measurement pre-registration
  itself is [written and dated](docs/pre-registration.md))
- `CITATION.cff` now identifies Aziz Bargaoui; public release still depends on
  the remaining policy and ethics gates

Full grading, per-category rationale, and the running list of bugs found
along the way: [`docs/PROGRESS.md`](docs/PROGRESS.md).

---

## Five-minute quickstart

```bash
git clone <this-repo-url> gpu-seal && cd gpu-seal
pip install -e ".[dev]"

pytest tests -q                        # 289 tests
bash lab/verify-safety-suite.sh        # proves the safety suite can fail: 36 injected violations, all must be caught
python3 lab/check-provider-policy.py   # confirms the Phase 0 gate is still enforced
python3 lab/local-runner/smoke.py      # reports what this machine can actually measure
```

With a real NVIDIA GPU:

```bash
python3 lab/local-runner/run_phase1.py --out ./out        # §9.3 / §9.4 controls
python3 lab/local-runner/run_phase2_local.py --out ./out  # every local probe family + report card
```

A run outside the pinned container can't supply the container digest
CHARTER.md §10 requires, so publication is correctly refused — that's the
safeguard working, not a bug. Build the pinned image first:
[`lab/docker/README.md`](lab/docker/README.md).

Minimal Python usage example (the `SafeBuffer` API): see
[`docs/architecture.md`](docs/architecture.md#minimal-usage-example).

---

## Example output (trimmed)

```json
{
  "provider_code": "local-lab",
  "product_claim": "NVIDIA GeForce RTX 3050 Laptop GPU",
  "probes": [
    {
      "probe_name": "framework_allocator_reuse",
      "measurement_path": "framework_pooled",
      "zero_fraction": 0.9999748,
      "owned_canary_match": true,
      "owned_canary_exact_matches": 8
    },
    {
      "probe_name": "memory_global_read_before_write",
      "measurement_path": "driver_direct",
      "zero_fraction": 1.0,
      "owned_canary_match": false,
      "owned_canary_exact_matches": 0
    }
  ],
  "report_card": {
    "note": "Independent category grades, no composite score. U means unproven, not failing.",
    "memory_lifecycle_hygiene": {
      "grade": "U",
      "basis": "No canaries recovered, but same-model die separation (§9.8b) is not yet validated — a clean result cannot distinguish sanitisation from a different physical chip."
    },
    "hardware_claim_consistency": {
      "grade": "A",
      "basis": "Topology certificate strongly consistent with the advertised class."
    },
    "allocation_model_transparency": {
      "grade": "C",
      "basis": "Undocumented by the provider; inferred as time_sliced_full_gpu at confidence 0.80."
    }
  },
  "safety": {
    "raw_unknown_memory_retained": false,
    "unknown_memory_rendered": false,
    "canary_only_search": true
  }
}
```

`memory_lifecycle_hygiene` grading **U** next to `hardware_claim_consistency`
grading **A**, in the same bundle, is intentional: grades are independent per
category, and **U means the evidence doesn't support a claim yet — not that
anything failed.** Real, untrimmed bundle:
[`examples/sample-safe-result.json`](examples/sample-safe-result.json).

---

## Architecture

```
 rented GPU instance
        │
        ▼
┌────────────────────────────┐
│ Controller                 │  provider allowlist · ownership attestation
│ gpu_seal.controller        │  duration ceiling · budget · disclosure gate
└──────────────┬─────────────┘
               │ deploys
               ▼
┌────────────────────────────┐
│ Probe agent                │  13 families, §9.1–§9.12
│ gpu_seal.probes            │
└──────────────┬─────────────┘
               │ all unknown memory passes through here
               ▼
┌────────────────────────────┐
│ Enforced-safe layer        │  SafeBuffer: fill_via() is the only write
│ gpu_seal.safety            │  door, aggregate() the only read door
└──────────────┬─────────────┘
               │ allowlisted statistics only
               ▼
┌────────────────────────────┐
│ Signed evidence bundle     │  Ed25519 + SHA-256, schema-validated,
│ gpu_seal.evidence          │  report card, no composite score
└────────────────────────────┘
```

Full component map and the reasoning behind each boundary:
[`docs/architecture.md`](docs/architecture.md).

---

## Roadmap — CHARTER.md §17

- [x] Wk 1–2 Foundation — threat model, ethics/disclosure policy, schemas,
      prior-art sweep
- [x] Wk 3–4 Local probe core — built, run on real silicon, §9.4 control
      validated
- [x] Wk 5–6 Exposure & container tests — §9.1 / §9.6 running, NVML wired in
- [x] Wk 7–8 Topology + allocation classifier — §9.8 reproduced on silicon,
      §9.7 classifier built
- [ ] Wk 9–10 Provider pilot — blocked on the policy gate and the ADR-001
      language port
- [~] Wk 11 Attestation module — built and tested; needs H100-class CC
      hardware to exercise
- [~] Wk 12 Release + preprint — tooling and docs ready; blocked on citation
      metadata and on having any provider data to report

**Next concrete steps:** review the first provider's policy
(`docs/provider-policy-review/`), port the probe agent off Python (ADR-001),
get ethics sign-off, and rent *N* same-model instances to validate same-model
die separation (§9.8b).

---

## Standing on prior work

GPU-SEAL reuses, rather than reinvents,
[Alpay & Alpay (2026), *Unprivileged Topology Certificates for Cloud GPU
Attestation*](https://arxiv.org/abs/2606.24934) for hardware-class and
coarse-location attestation. Their instrument answers *which chip did I get,
and roughly where is it?* GPU-SEAL asks the question they leave open: *what
was left on it, and does the provider's isolation model match what they sold
you?* Their paper explicitly leaves same-model die separation unresolved
(§12); the report card refuses grade A on memory hygiene until that's
closed, and CI enforces the refusal. Details: [`docs/prior-art.md`](docs/prior-art.md).

---

## Documentation

Role-based navigation (start here, run locally, safety model, methodology,
provider testing, release checklist): [`docs/INDEX.md`](docs/INDEX.md).

Full flat list, by content:

| Document | Contents |
|---|---|
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Full status, per-category grades, what is done |
| [`docs/REMAINING.md`](docs/REMAINING.md) | What is left, ordered by what actually unblocks the project |
| [`CHARTER.md`](CHARTER.md) | Governing research and implementation charter |
| [`ETHICS.md`](ETHICS.md) | Ethics policy, with the enforcement point named for every rule |
| [`docs/threat-model.md`](docs/threat-model.md) | Tenant position, adversary model, hard boundaries |
| [`docs/methodology.md`](docs/methodology.md) | How a measurement is taken, and what it may conclude |
| [`docs/scoring.md`](docs/scoring.md) | The report card, and why there is no composite score |
| [`docs/pre-registration.md`](docs/pre-registration.md) | Hypotheses and thresholds, fixed before any provider data |
| [`docs/architecture.md`](docs/architecture.md) | Full component map and design principles |
| [`docs/data-handling.md`](docs/data-handling.md) | What is held, for how long, and what is refused outright |
| [`DISCLOSURE.md`](DISCLOSURE.md) | Responsible disclosure process |
| [`docs/provider-policy-review/`](docs/provider-policy-review/) | The Phase 0 gate: no reviewed record, no probing |
| [`docs/adr/`](docs/adr/) | Architecture decision records |
| [`SECURITY.md`](SECURITY.md) | Reporting vulnerabilities in GPU-SEAL itself |

---

## Licence & citation

Apache-2.0 — see [`LICENSE`](LICENSE). Citation metadata is in
[`CITATION.cff`](CITATION.cff).
