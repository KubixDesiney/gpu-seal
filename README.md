# GPU-SEAL

*Internal codename: GHOSTMETER*

> Measures the GPU you rented, using only ordinary customer privileges, under
> a strict canary-only data policy. An assurance and measurement framework —
> **not** an exploitation toolkit.

[![status](https://img.shields.io/badge/status-pre--alpha%20(Phase%200%E2%80%931)-orange)]()
[![mutations caught](badges/mutation-battery.svg)](https://github.com/KubixDesiney/gpu-seal/actions/workflows/safety.yml)
[![licence](https://img.shields.io/badge/licence-Apache--2.0-blue)]()
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22725005.svg)](https://doi.org/10.5281/zenodo.22725005)

**GPU-SEAL is a tenant-side, canary-only framework that lets GPU-cloud
customers independently measure memory sanitisation, hardware consistency,
and isolation controls without accessing other tenants’ data.**

**Live dashboard:** <https://gpu-seal-dashboard.gpu-seal.workers.dev> ·
Repository: <https://github.com/KubixDesiney/gpu-seal> · DOI:
[10.5281/zenodo.22725005](https://doi.org/10.5281/zenodo.22725005) · Current
measured status: [`docs/STATUS.md`](docs/STATUS.md)

**First result** ([F-001](docs/findings/F-001-linux-driver-residue.md)): across
two independent Linux hosts (a Tesla T4 each) and 20 driver-direct reuse
cycles, **0/20 owned canaries were recovered** — and on each host the
detection-capability control recovered its canary 10/10 times, so the harness
is shown able to see a canary it planted.

> **What this does not establish.**
>
> - **No provider has been measured.** Both hosts are ad-hoc runs on notebook
>   platforms, not a provider study. No provider study has been run or
>   validated, and shared-provider use remains blocked.
> - **It is not a clean bill of health.** Memory-lifecycle hygiene is graded
>   **U** on both hosts, because same-model die separation (contribution D5)
>   is not yet validated: a clean result on a chip that may not be the same one
>   is not evidence of sanitisation. **U means unproven, not failing** — and it
>   is not an A either.
> - **Two hosts, one run each.** It says nothing about MIG temporal isolation,
>   H100 confidential computing, same-model physical-die continuity, or
>   provider isolation and policy compliance; each is an open claim boundary in
>   [`docs/STATUS.md`](docs/STATUS.md#open-claim-boundaries).
> - **Pre-alpha, not a release.** The dashboard is a public viewer, and its
>   structural inspection is not cryptographic verification — verify with the
>   CLI and a trusted public key ([`TRUST-MODEL.md`](docs/TRUST-MODEL.md)).

**Verify it yourself:** [`REPRODUCE.md`](REPRODUCE.md) is the ten-minute,
no-GPU verification path. The mutation badge above is **40/40** injected safety
violations caught — see [Prove the tests can fail](#prove-the-tests-can-fail).

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

## Current status

No provider measurement study has been run or validated. The current checkout
has a green local Python contract and a real local RTX 3050 smoke result, but
it is not a provider result and is not a release candidate. The policy matrix
has two complete records and two records awaiting written permission. Ethics
sign-off, Linux/MIG/H100/same-model validation, and owner decisions remain
open. See the dated [status snapshot](docs/STATUS.md) for the measured counts
and exact gate outcomes.

## Prove the tests can fail

A green safety suite means nothing on its own — a suite that always passes,
even against broken code, isn't testing anything. [`lab/verify-safety-suite.sh`](lab/verify-safety-suite.sh)
injects 40 known policy violations, one at a time, into a scratch copy of the
repo and asserts that each one turns the suite red; CI additionally checks
that every injected case is actually wired into a batch it runs, so a new
case can't be added and silently skipped (see the `negative-control-coverage`
and `mutation-summary` jobs in [`.github/workflows/safety.yml`](.github/workflows/safety.yml)).
The badge above is generated from that run's own `mutation-battery-summary.json`
artifact, not hand-typed — download it from the latest `main` run of the
[safety workflow](https://github.com/KubixDesiney/gpu-seal/actions/workflows/safety.yml)
for the full per-case breakdown.

Don't want to trust any of this? [`REPRODUCE.md`](REPRODUCE.md) is a
ten-minute, no-GPU-required, copy-paste checklist that runs the install, the
test suite, this mutation battery, the release/policy gates, and a signed
evidence-bundle verification yourself, with the exact command and expected
output for each.

---

## Quickstarts

The commands below separate software verification, simulated runs, and real
CUDA observations. A simulated result is a test fixture: it is always marked
`backend_is_real=false` and cannot be published as hardware or provider
evidence.

### Linux or WSL2

From a Bash shell in a fresh checkout:

```bash
git clone https://github.com/KubixDesiney/gpu-seal.git
cd gpu-seal
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --no-build-isolation -e ".[dev]"
python -m pytest tests -q
python lab/check-provider-policy.py
python lab/local-runner/smoke.py
```

Validation note for this snapshot: the PowerShell quickstart and Git Bash
negative control were run on Windows. WSL2 was unavailable in the managed
session (`E_ACCESSDENIED`), so Linux/WSL2 hardware evidence still needs a
supported Linux or WSL2 host run.

For the safety negative control, use a working Bash installation:

```bash
PYTHON_BIN="$(command -v python)" bash lab/verify-safety-suite.sh
```

Real CUDA work in WSL2 additionally requires the Windows NVIDIA driver, WSL2
GPU integration, Docker Desktop WSL integration if using containers, and the
NVIDIA Container Toolkit. Do not install a Linux NVIDIA driver inside WSL2.
The full container setup is in [`lab/docker/README.md`](lab/docker/README.md).

### Windows PowerShell

From the repository root, use Python 3.10 or newer in an isolated environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --no-build-isolation -e ".[dev]"
python -m pytest tests -q
python lab/check-provider-policy.py
python lab/local-runner/smoke.py
```

The safety battery needs Bash. Run it from WSL2 or Git Bash with the Python
interpreter selected for that shell. PowerShell itself is sufficient for the
unit/safety suite, the policy check, simulated runs, and the local smoke check.

For a real CUDA backend on bare metal, install the CUDA extra as well:

```powershell
python -m pip install --no-build-isolation -e ".[dev,cuda]"
```

The `cuda` extra provides CuPy and the Python CUDA runtime/compiler components
used by the probes. Native compilation still requires a compatible CUDA
toolkit/compiler or the pinned CUDA container; the extra does not establish
native conformance.

### First successful verification

1. Run `python -m pytest tests -q`; the checkout measured 430 passed as of the
   2026-09-11 run recorded in [`docs/STATUS.md`](docs/STATUS.md).
2. Run `python lab/check-provider-policy.py`; expect 2 complete, 2 awaiting,
   and `GATE: lifted`. This does not authorize all providers.
3. Run `python lab/local-runner/run_phase1.py --simulate --size-mib 1
   --cycles 2 --unsafe-development-ephemeral --out ./out-simulated`; expect
   exit 0 and a non-publishable result with `backend_is_real=false`. For any
   provenance-suitable bundle, replace the explicit development flag with
   `--signing-key <caller-supplied-ed25519.pem>`.
4. Run `python lab/local-runner/smoke.py`. Only a `CupyBackend` report with
   `backend_is_real=true` is a real local CUDA observation; it is still not
   provider validation.

To verify a signed bundle, obtain the expected public key through an
independent trusted channel and use the CLI with that external key:

```bash
gpu-seal verify ./out/<run-id>.result.json --public-key ./trusted-ed25519.pem
```

See [`docs/TRUST-MODEL.md`](docs/TRUST-MODEL.md) for the distinction between
dashboard inspection and cryptographic verification. A non-pinned local run
does not satisfy the publication provenance gate; use the pinned CUDA image
for evidence intended for publication.

The repository-owned campaign harness is also available without a provider:

```bash
python -m gpu_seal campaign run \
  --ownership-confirmation "local deterministic validation" \
  --confirmed-by researcher \
  --unsafe-development-ephemeral
```

This command uses only the deterministic fake runtime. It exercises campaign
sequencing, timeouts, cleanup reconciliation, and signed storage; it does not
contact a provider or produce hardware evidence. The provider adapter boundary
and its owner inputs are documented in [`docs/PROVIDER-ADAPTER.md`](docs/PROVIDER-ADAPTER.md).

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
- [ ] Wk 9–10 Provider pilot — blocked on ethics approval, provider
      permissions, pinned native conformance, and owner launch decisions
- [~] Wk 11 Attestation module — built and tested; needs H100-class CC
      hardware to exercise
- [~] Wk 12 Release + preprint — tooling and docs are present; public release
      remains blocked by the dirty-tree gate and unresolved human/external
      validation decisions

**Next concrete steps:** review the current dirty tree, obtain the two
outstanding written permissions, get ethics sign-off, and schedule the pinned
native/Linux and same-model validation work. Do not start provider testing from
this quickstart.

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
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Implementation progress, category assessment, and boundaries |
| [`docs/REMAINING.md`](docs/REMAINING.md) | What is left, ordered by what actually unblocks the project |
| [`docs/STATUS.md`](docs/STATUS.md) | Dated measured release-readiness snapshot |
| [`REPRODUCE.md`](REPRODUCE.md) | Ten-minute, no-GPU independent verification checklist |
| [`docs/OWNER-ACTION-CHECKLIST.md`](docs/OWNER-ACTION-CHECKLIST.md) | Human decisions and external inputs |
| [`docs/TRUST-MODEL.md`](docs/TRUST-MODEL.md) | Dashboard inspection and cryptographic verification |
| [`docs/RELEASE.md`](docs/RELEASE.md) | Release process and automated-gate limits |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Setup, platform, and evidence FAQ |
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
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution workflow and required checks |
| [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) | Participation standards |
| [`CHANGELOG.md`](CHANGELOG.md) | Release notes and change policy |

---

## Licence & citation

Apache-2.0 — see [`LICENSE`](LICENSE). Machine-readable citation metadata is
in [`CITATION.cff`](CITATION.cff).

### How to cite

**GPU-SEAL (this software):**

> Bargaoui, A. (2026). *GPU-SEAL: Tenant-Observable Security and Isolation
> Assurance for GPU Clouds* (Version 0.1.0-alpha.2) [Computer software].
> Zenodo. https://doi.org/10.5281/zenodo.22725006

Cite the version DOI above for the exact release you used, or
[10.5281/zenodo.22725005](https://doi.org/10.5281/zenodo.22725005) (the
concept DOI) to always point at the latest version.

**The physical-continuity / coarse-location instrument GPU-SEAL reuses**
(cite this alongside GPU-SEAL if you rely on that capability):

> Alpay, F., & Alpay, T. (2026). *Unprivileged Topology Certificates for
> Cloud GPU Attestation*. arXiv:2606.24934.
