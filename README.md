# GPU-SEAL

**Tenant-Observable Security and Isolation Assurance for GPU Clouds**

*Internal codename: GHOSTMETER*

> An assurance and measurement framework, **not** an exploitation toolkit.
> GPU-SEAL audits the accelerator *you rented*, using only ordinary customer
> privileges, under a strict canary-only data policy.

[![status](https://img.shields.io/badge/status-pre--alpha%20(Phase%200%E2%80%931)-orange)]()
[![tests](https://img.shields.io/badge/tests-131%20passing-brightgreen)]()
[![mutations caught](https://img.shields.io/badge/injected%20violations%20caught-20%2F20-brightgreen)]()
[![licence](https://img.shields.io/badge/licence-Apache--2.0-blue)]()

---

## The problem

A GPU-cloud tenant pays for isolation, for a specific chip, for a specific
region, and for a clean machine — and receives an invoice, not evidence.

The isolation gap is documented and vendor-admitted. NVIDIA's CUDA
documentation states plainly that allocated memory **"is not cleared."** The
same sentence appears for `cudaMalloc`, `cuMemAlloc`, `cudaMallocManaged`, and
`cuMemAllocManaged`. NVIDIA ships an administrative `--clear-memory` tool
precisely because clearing is not the default. Confidential Computing scrubs
memory only at Function Level Reset, not within a session. MIG documents
*runtime* isolation in detail and says nothing about scrubbing when an
instance is destroyed and recreated for the next tenant.

Nobody measures any of this in the wild, across providers.

## What this is

An open-source probe suite you deploy as an ordinary paying customer, plus a
measurement study that turns "everyone knows GPUs leak" into a reproducible,
signed, per-provider dataset.

**Central question:**

> Can an ordinary GPU-cloud customer independently verify memory sanitisation,
> workload isolation, hardware identity, coarse location, device exposure, and
> confidential-computing attestation — without trusting provider claims alone?

**Regulatory corollary:**

> Can an organisation bound by GDPR, NIS2, DORA, or the EU AI Act independently
> verify that the accelerator running its model is located, and isolated, as
> contracted?

## What this is not

GPU-SEAL does not exploit providers, escape containers, access host systems,
read other tenants' data, or recover text from unknown memory. It cannot: the
architecture forbids it and CI rejects code that tries. See
[`ETHICS.md`](ETHICS.md).

---

## Status

**Phase 0 — pre-alpha.** No cloud testing has occurred and none may begin
until the ethics and provider-policy checklist is complete.

| Component | State |
|---|---|
| Prior-art sweep | ✅ [`docs/prior-art.md`](docs/prior-art.md) |
| Charter v2 | ✅ [`CHARTER.md`](CHARTER.md) |
| Enforced-safe layer | ✅ `probe/gpu_seal/safety/` |
| Authenticated canary format | ✅ 128-byte, keyed BLAKE2b MAC ([ADR-002](docs/adr/002-canary-wire-format.md)) |
| Signed evidence bundles | ✅ Ed25519 + SHA-256, schema-validated |
| Test suite | ✅ 131 tests, all 17 charter rules |
| Suite negative control | ✅ 20/20 injected violations caught |
| Reproducible container | ✅ pinned + dev profiles, `lab/docker/` |
| **Memory Probe B (§9.3)** | ✅ read-before-write, positive + negative controls |
| Phase 1 control battery | ✅ `lab/local-runner/run_phase1.py` |
| Verified on real silicon | ⬜ **next** — needs CUDA toolkit on the RTX 3050 |
| Allocation-model classifier (§9.7) | ⬜ |
| Device exposure inventory (§9.6) | ⬜ |
| Provider policy matrix | ⬜ **required before any cloud run** |

---

## Architecture: safety is centralised

All unknown memory passes through exactly one layer. Only statistics leave it.

```
 device memory
      │
      ▼
 ┌─────────────────────────────────────────┐
 │ SafeBuffer                              │   refuses repr, str, bytes,
 │   fill_via()   ← the only write door    │   memoryview, indexing, iteration,
 │   _unsafe_view ← the only read door,    │   pickling, JSON, buffer protocol
 │                  one caller             │   zeroed on scope exit, always
 └──────────────────┬──────────────────────┘
                    │
                    ▼
 ┌─────────────────────────────────────────┐
 │ aggregate()                             │   allowlisted statistics only
 │   + owned-canary search (only search    │   automatic safety stop on
 │     that exists anywhere in GPU-SEAL)   │   unexpected content
 └──────────────────┬──────────────────────┘
                    ▼
              signed JSON bundle
```

---

## Quick start

```bash
pip install -e ".[dev]"

pytest tests -q                                    # 131 tests
bash lab/verify-safety-suite.sh                    # prove the suite goes red
python3 lab/local-runner/smoke.py                  # what can this machine measure?
python3 lab/local-runner/run_phase1.py --simulate --simulate-leaky
```

The second command is the important one. It injects twenty known policy
violations into a scratch copy of the repo and asserts each turns the suite
red — because a green safety suite that cannot fail is decoration.

On the RTX 3050 lab machine, via Docker Desktop / WSL2
(see [`lab/docker/README.md`](lab/docker/README.md)):

```bash
bash lab/docker/build.sh dev
bash lab/docker/run.sh --gpu smoke
bash lab/docker/run.sh --gpu phase1
```

### Minimal example

```python
from gpu_seal.safety import SafeBuffer, CanarySet, Boundary, aggregate

canaries = CanarySet.create()
marker = canaries.mint(Boundary.SEQUENTIAL_ALLOCATION)

with SafeBuffer.acquire(4 << 20, provenance="cudaMalloc:device_global") as buf:
    buf.fill_via(lambda view: copy_device_to_host(view, device_ptr))
    record = aggregate(
        buf, canaries,
        probe_name="memory_global_read_before_write",
        probe_version="0.1.0",
        expect_zeroed=False,
    )
# buffer zeroed here, unconditionally

print(record.owned_canary_match, record.zero_fraction)
# print(buf)  ← raises UnknownMemoryRenderError
```

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Status, per-category grades, gates before Phase 2 |
| [`CHARTER.md`](CHARTER.md) | Governing research and implementation charter |
| [`ETHICS.md`](ETHICS.md) | Ethics policy, with enforcement points named |
| [`DISCLOSURE.md`](DISCLOSURE.md) | Responsible disclosure process |
| [`SECURITY.md`](SECURITY.md) | Reporting vulnerabilities in GPU-SEAL itself |
| [`docs/prior-art.md`](docs/prior-art.md) | What exists, and where our delta is |
| [`docs/adr/`](docs/adr/) | Architecture decision records |

---

## Standing on other people's shoulders

GPU-SEAL **consumes** rather than duplicates
[Alpay & Alpay (2026), *Unprivileged Topology Certificates for Cloud GPU
Attestation*](https://arxiv.org/abs/2606.24934) for hardware-class and
coarse-location attestation. Their instrument answers *which chip did I get,
and roughly where is it?*

GPU-SEAL asks the question they did not: **what was left on it, and does the
provider's isolation model match what they sold you?**

We also intend to close one gap they explicitly flag in their §12: their
cross-die experiment separates two different Blackwell *products*, and
same-model die separation is left open. That precondition matters —
without it, a clean result across two allocations of the same advertised model
cannot distinguish "the provider sanitised the chip" from "the provider gave
you a different chip." Our report card refuses to award grade A until it is
resolved, and CI enforces that refusal.

---

## Licence

Apache-2.0. See [`LICENSE`](LICENSE).

## Citation

See [`CITATION.cff`](CITATION.cff).
