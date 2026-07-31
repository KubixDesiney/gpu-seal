# GPU-SEAL — Project Charter v2
### Tenant-Observable Security and Isolation Assurance for GPU Clouds
*Internal codename: **GHOSTMETER**. Canonical name for repo, package namespace, schema IDs, and paper: **GPU-SEAL**.*

**Status:** Phase 0 — prior-art sweep complete, ethics/policy checklist outstanding
**Document type:** governing research + implementation charter
**Supersedes:** `ghostmeter-project-charter.md` (v1, July 2026)
**Last updated:** 29 July 2026
**Purpose:** the shared plan executed against in Cowork. Read top to bottom once; after that live in §17 Roadmap, §7 Ethics, and §23 First Week.

---

## 0. What changed in v2 (read once)

v2 applies the ten amendments from [`docs/prior-art.md`](docs/prior-art.md). The Phase 0 prior-art sweep
found no competitor — but it found that the market moved under two of our research questions, and that
our lead citation was pointed at the wrong vendor.

| # | Change | Was |
|---|---|---|
| **A1** | **§3.1 rewritten.** NVIDIA was **confirmed not affected** by LeftoverLocals. Motivation now leads with NVIDIA's own documentation. | LeftoverLocals as flagship motivation |
| **A2** | **§3.3 upgraded, §9.8/§9.9 demoted.** Alpay & Alpay (2026) already deliver hardware-class and coarse-location attestation. They are now an **instrument we consume**, not a target we build. | Topology/location as our contribution |
| **A3** | **§9.8 gains a real contribution: same-model die separation.** Alpay & Alpay explicitly leave it open, and §9.5 does not work without it. | Assumed solved |
| **A4** | **§24 expanded** with six historical papers (S&P 2014 → USENIX Sec 2024) and three 2026 adjacent works. | LeftoverLocals only |
| **A5** | **§19 challenge #1 substantially solved** by the topology certificate. Rewritten as an integration + extension task. | Open methodological risk |
| **A6** | **§9.7 allocation-model classifier promoted** to a top-three novelty. | Preliminary step |
| **A7** | **New §9.12 — MIG temporal isolation.** NVIDIA documents runtime isolation and is silent on destroy/recreate scrubbing. Nobody has measured it. | Implicit in §9.3 test 7 |
| **A8** | **EU digital-sovereignty framing added** (§1, §11, §21). Turns location consistency from reproduction into a regulatory instrument. | Absent |
| **A9** | **§21 venue timing corrected.** fwd:cloudsec NA and EU 2026 have both closed. NA 2027 is the target. **arXiv preprint early.** | Assumed 2026 CFP open |
| **A10** | **§20 hardware corrected: RTX 3050 (Ampere, CC 8.6).** | GTX 1650 (Turing, CC 7.5) |

**The one-line consequence:** the project is narrower and sharper. Hardware identity and coarse location
were claimed in June 2026. What remains unclaimed — and what nobody has measured — is *what is left in
the memory of the GPU you rented, and whether the provider's isolation model matches what they sold you*.

---

## 1. One-paragraph thesis

A GPU-cloud tenant pays for isolation, for a specific chip, for a specific region, and for a clean
machine — and receives an invoice, not evidence. That was acceptable when "cloud" meant three mature
hyperscalers with audited isolation. It is not acceptable now that the market has filled with GPU
providers, hosting companies, resellers, marketplaces, and fractional-GPU platforms (several of them
recent crypto-mining pivots) renting out shared silicon that holds other people's model weights and
inference traffic. The isolation gap on GPUs is *documented and vendor-admitted* — NVIDIA's own CUDA
documentation states that allocated memory **"is not cleared"**, NVIDIA ships an administrative
`--clear-memory` tool precisely because clearing is not default, MIG documents runtime isolation while
saying nothing about scrubbing between successive tenants, and 2024–2026 CVEs show uninitialised GPU
memory leaking prior tenants' data at the framework layer. **Nobody measures any of it in the wild
across providers.** GPU-SEAL is an open-source probe suite deployed as an ordinary paying customer, plus
a measurement study that turns "everyone knows GPUs leak" into a reproducible, signed, per-provider
dataset. It is an **assurance and measurement framework, not an exploitation toolkit.** You are not
attacking anyone. You are auditing what *you* rented.

**The central research question:**

> Can an ordinary GPU-cloud customer independently verify memory sanitisation, workload isolation,
> hardware identity, coarse location, device exposure, and confidential-computing attestation — without
> trusting provider claims alone?

**The regulatory corollary (new in v2):**

> Can an organisation bound by GDPR, NIS2, DORA, or the EU AI Act independently verify that the
> accelerator running its model is physically located, and isolated, as contracted?

Five research areas feed these questions: (1) GPU memory lifecycle and sanitisation; (2) tenant-visible
isolation and management interfaces; (3) physical-GPU and hardware-class consistency; (4) coarse-location
consistency; (5) confidential-computing attestation availability and correctness.

---

## 2. Why this is novel (and not "another scanner")

Almost every "cloud security project" collapses into the posture-management bucket: scan config, map to
a benchmark, print findings. That space is fully saturated, including AI-flavoured variants that map
misconfigurations to the OWASP LLM/Agentic Top 10. If a project can be described as "CSPM but for X," it
already exists.

GPU-SEAL lives somewhere else — **independent tenant-side verification of provider claims:**

| Saturated space | This project |
|---|---|
| Audits *your* configuration (IAM, network, storage, logging, K8s) | Audits the *provider's* delivery of the rented accelerator |
| Reads cloud APIs and config files | Measures the actual silicon you rented |
| Opinion mapped to a framework | Empirical measurement with signed evidence and statistics |
| Runs against your own account settings | Produces a cross-provider dataset that does not currently exist |

Customers routinely receive claims that are hard to verify independently: "Dedicated GPU," "Isolated
instance," "H100," "Confidential GPU," "Deployed in region X," "Secure multi-tenancy," "MIG-isolated,"
"Enterprise-grade." GPU-SEAL asks the empirical question underneath all of them:

> Does the underlying rented accelerator behave in a way consistent with the provider's isolation,
> hardware, location, and attestation claims?

### 2.1 The v2 delta, stated honestly

Alpay & Alpay (2026) answered *"which chip did I get, and roughly where is it?"* GPU-SEAL asks
**"what was left on it, and does the isolation model match the sale?"** — measured across providers,
repeatedly, over time, under a canary-only policy.

Ranked contributions:

| # | Contribution | Why it holds |
|---|---|---|
| **D1** | Cross-provider memory-sanitisation measurement in the wild | No such dataset exists. The topology work does not touch memory. Academic residue work is single-machine lab work, never a provider census. |
| **D2** | MIG temporal isolation | NVIDIA documents runtime isolation and is explicitly silent on destroy/recreate scrubbing. Unmeasured. |
| **D3** | Tenant-side allocation-model classifier | "Fractional GPU" may mean MIG, time-slicing, MPS, vGPU, or software interception. Time-slicing has *no* memory isolation per NVIDIA's own GPU Operator docs. Providers rarely say which. Unsolved from inside a rented job. |
| **D4** | Post-NVIDIAScape device/namespace exposure census | Three container-escape CVEs in 18 months; Wiz measured 37% of cloud environments vulnerable to CVE-2025-23266. Cross-provider posture unmeasured. |
| **D5** | **Same-model physical die re-identification** | **Explicitly left open by Alpay & Alpay §12** — they separate *products*, not two dies of one model. D1's strongest result is inconclusive without it. |
| **D6** | Longitudinal signed evidence | Nobody re-tests providers across driver/CUDA upgrades. The incumbents defer the multi-seed campaign explicitly. |
| **D7** | EU sovereignty verification framing | Turns coarse location from reproduction into an instrument answering a question auditors already ask. |
| ~~D8~~ | ~~Cross-product hardware class + coarse location~~ | **Claimed by Alpay & Alpay (2026). Reproduce as instrument; do not claim.** |

**Minimum viable novel paper: D1 + D2 + D3.** D5 is the highest-leverage addition.

"The person who built the tenant-side GPU-cloud isolation benchmark" is a real, durable professional
identity. That is the prize.

---

## 3. Research motivation (the grounding)

### 3.1 NVIDIA does not clear GPU memory, and says so *(rewritten in v2 — A1)*

> ⚠️ **v1 correction.** v1 led with LeftoverLocals. **NVIDIA GPUs were confirmed *not* affected by
> LeftoverLocals (CVE-2023-4969).** The affected vendors were AMD, Apple, Qualcomm, and Imagination
> Technologies. Trail of Bits noted NVIDIA had likely already addressed those patterns following earlier
> academic work. GPU-SEAL targets NVIDIA GPU clouds. Leading with LeftoverLocals would be rejected on
> first read. It belongs in related work (§3.6), not motivation.

The honest, NVIDIA-specific motivating chain is **stronger** than the headline vulnerability:

1. **NVIDIA documents the behaviour verbatim.** The CUDA Runtime API documentation for `cudaMalloc()`
   states: *"The memory is not cleared."* The identical sentence appears for `cuMemAlloc`,
   `cudaMallocManaged`, and `cuMemAllocManaged` across both the Runtime and Driver APIs.
2. **No guarantee exists across process or context boundaries.** No official NVIDIA documentation
   guarantees GPU memory is zeroed between processes or CUDA contexts in standard (non-CC) operation.
   `cudaFree()` does not specify whether freed memory is zeroed before reallocation.
3. **NVIDIA ships a tool that proves clearing is not default.** `gpu-admin-tools` includes a
   `--clear-memory` flag described as clearing GPU memory contents. Its existence as an explicit
   *administrative action* is the admission.
4. **Confidential Computing scrubs only at handoff.** H100 CC performs firmware-level scrubbing during
   Function Level Reset — memory is locked until scrubbed, mitigating cold-boot. But **within** a CC
   session, ordinary CUDA allocation behaviour applies and `cudaMalloc` still returns uncleared memory.
   CC addresses inter-tenant leakage, not intra-session reuse. It is also opt-in and requires Intel TDX,
   AMD SEV-SNP, or ARM CCA on the host.
5. **MIG documents runtime isolation and is silent on temporal isolation.** The MIG User Guide describes
   separate, isolated paths through the memory system — crossbar ports, L2 cache banks, memory
   controllers, DRAM address buses. It says nothing about whether memory is scrubbed when a MIG instance
   is destroyed and recreated for the next tenant. **Runtime isolation and temporal isolation are
   different properties.** This silence is a measurable gap → §9.12.
6. **The framework layer independently reintroduces the exposure.** See §3.2.
7. **Contrast with CPU behaviour.** The Linux kernel guarantees zeroed pages to userspace via
   `get_zeroed_page()`/`mmap()`, hardened further by `CONFIG_INIT_ON_ALLOC_DEFAULT_ON` since v5.3. No
   documented GPU equivalent exists.

**Working hypothesis to pre-register:** probe family §9.2 (kernel-local / shared memory, the
LeftoverLocals class) is **expected negative on NVIDIA**. Pre-registering this matters — a negative with
working positive controls is a publishable result; an unregistered negative looks like we went hunting
for a known-absent bug.

### 3.2 Uninitialised GPU memory remains live at the framework layer

**CVE-2026-53923** (vLLM, GGUF dequantisation; affects 0.5.5 → 0.23.1rc0): integer truncation of tensor
dimensions — a single `int` that should have been `int64_t` — meant the output tensor was allocated at
full size via `torch::empty` (uninitialised) while the dequantise kernel processed only a truncated
element count. The unfilled remainder retains whatever previously occupied that GPU memory. In shared
serving deployments that residue may contain tensor data from other users' inference requests.

Not identical to LeftoverLocals, and importantly **not a driver bug** — it reinforces that buffer
initialisation, allocator reuse, and correct isolation of reused GPU memory must each be tested
separately, at both driver and framework layers.

### 3.3 Physical-GPU identity is now a solved instrument, not an open problem *(upgraded in v2 — A2)*

**Alpay & Alpay (2026)**, *Unprivileged Topology Certificates for Cloud GPU Attestation*
(arXiv:2606.24934v1, 22 June 2026, CC BY 4.0) presents a software-only attestation primitive requiring no
firmware access or vendor serials. A CUDA probe measures an SM-by-memory-region latency matrix using
physical SM labels and dependent global loads; a streaming reducer commits sufficient statistics,
configuration, code hashes, and network evidence into a certificate a verifier checks **without a GPU**.

Published results:

| Claim | Result |
|---|---|
| Per-SM latency map is a stable physical fingerprint | 6-hour full-load RTX 5090 run, median temporal jitter **0.09 cycles** |
| Distinct dies separable | Shape-only leave-one-out classification, **100.0%** accuracy across Blackwell dies |
| Hardware-class topology recovery | Volta V100 unified memory domain; Hopper H200 two-way L2 split; Blackwell B200 two-die NV-HBI package |
| Coarse location binding | 169 RIPE Atlas probes place a B200 within **44 km** of claimed datacentre, **rejecting all 11 decoy sites** |

**This is a gift, not a threat.** v1 §19 listed "proving physical-device continuity" as expected
challenge #1 — the weak point of the entire self-vs-self canary design. A published, validated,
unprivileged instrument for it now exists. GPU-SEAL **consumes** it.

**But read their §12 Limitations.** They are candid, and the gaps are ours:

- *"The cross-die identity experiment separates two different Blackwell **products**. **Same-model die
  separation is left to prior GPU fingerprinting.**"* → They distinguish a B200 from a 5090. They have
  **not** shown they can distinguish *your* H100 from *another* H100. **§9.5 does not work without
  this.** → becomes contribution **D5**.
- *"Across **five rented GPUs** and three generations"* → a demonstration, not a census.
- *"…awaits a longer multi-seed campaign"* → the statistical/longitudinal campaign is explicitly open.
- *"The network alibi localises to **metropolitan-to-continental** scale, not to a rack."* → sufficient
  for EU-vs-US sovereignty, insufficient for anything finer. Bounds §9.9 honestly.
- *"…does not prove firmware integrity, prevent refusal to run, or replace vendor attestation."* → clean
  separation from §9.10.
- Instances did not answer ICMP, so TCP-reachable ports were used → inherit directly.

Related but **not** tenant-usable: *GPU Fingerprinting for Location Verification* (arXiv:2605.01930)
requires a registration phase before chips are sold plus a trusted verifying server. That is a
vendor/provider-side scheme. Cite as contrast, not competition.

**Recommended action:** contact the authors (`alpay@lightcap.ai`) once GPU-SEAL v0.1 exists.
Collaboration beats collision, and D5 is a natural joint extension.

### 3.4 Attestation evidence is not automatically bound to the intended connection

**CVE-2026-33697** (CVSS 7.5) concerns relay/diversion risk in an attested-TLS design. The associated
*Intra-handshake.fail* work tests seven mechanisms for cryptographically binding intra-handshake
attestation evidence to the underlying connection and finds **none** protect against relay — an attacker
able to extract the ephemeral TLS private key can relay or divert the attested session and impersonate
the legitimate attested service. Named real-world implementations include Meta's Private Processing
(WhatsApp) and Edgeless Systems' Contrast. Formal proof: `CCC-Attestation/formal-spec-KBS`.

> Scope note: NVD and vendor trackers scope the CVE identifier to Cocos AI v0.4.0–v0.8.2. The *research*
> claim is architectural and broader. Represent both, and do **not** claim "all remote attestation is
> broken."

Report independently: is evidence available; does the chain verify; do measurements match reference; is
there a fresh nonce; is debug mode disabled; is the attested entity demonstrably bound to the application
connection; was relay resistance actually tested.

### 3.5 MIG and fractional GPUs create different isolation boundaries

NVIDIA MIG partitions supported GPUs into hardware-isolated instances (separate L2 banks, memory
controllers, DRAM address paths). But "fractional GPU" is not one architecture — a provider may use MIG,
time-slicing, MPS, vGPU, full-device passthrough, software interception, custom scheduling, or
undocumented combinations. **NVIDIA's own GPU Operator documentation states time-slicing provides no
memory or fault isolation.** A valid benchmark must classify the allocation model before interpreting
results → §9.7, promoted to **D3**.

Emerging 2026 work indicates MIG's *runtime* isolation may also have cache and TLB side channels
(§24 refs 20–21). Those are attacks; GPU-SEAL measures assurance. Cite, distinguish, do not reproduce.

### 3.6 Related work: a decade of GPU memory residue research *(new in v2 — A4)*

This is where LeftoverLocals belongs, alongside the literature v1 omitted. See §24 refs 7–12 for the full
list. The single most important framing point for the paper:

> **All of that work describes attacks. GPU-SEAL performs tenant-side assurance measurement.** That
> distinction is the scientific and ethical identity of this project, and it must be visible in the
> related-work table — not buried in the ethics section.

---

## 4. Goals, secondary goals, non-goals

### 4.1 Primary goals

1. Build a reproducible tenant-side GPU assurance harness.
2. Run with ordinary customer privileges — no provider/host/firmware access.
3. Measure only infrastructure the researcher rents.
4. Create a controlled canary-based memory-sanitisation methodology.
5. Inventory tenant-visible GPU device and management exposure.
6. **Classify the allocation model** before interpreting any isolation result. *(promoted — A6)*
7. **Measure MIG temporal isolation** across destroy/recreate boundaries. *(new — A7)*
8. Reproduce the topology-certificate instrument, and **extend it to same-model die separation**. *(revised — A2/A3)*
9. Assess whether coarse observed location is consistent with advertised region — including as a
   **sovereignty-verification instrument**. *(revised — A8)*
10. Verify available GPU confidential-computing attestation evidence.
11. Produce signed, reproducible result bundles.
12. Run a repeated measurement campaign across several providers, **including at least one EU provider**.

### 4.2 Secondary goals

Public longitudinal dataset; provider-neutral assurance schema; local-lab validation path; support for
multiple NVIDIA GPU generations where practical; let providers reproduce and respond; publishable paper;
establish maintainer as a GPU-cloud-tenant-isolation specialist.

### 4.3 Non-goals (hard boundaries)

GPU-SEAL must **not**: exploit a provider; escape a VM/container; access the host OS; circumvent auth or
billing; scan infrastructure it doesn't rent; read another tenant's files/processes/traffic/API data;
recover natural-language text from unknown memory; classify unknown memory as weights/prompts/
activations; save raw unknown VRAM; attempt GPU Rowhammer, privilege escalation, or DoS; saturate shared
infrastructure beyond normal workload behaviour; publish an uncoordinated accusation; or present
uncertain measurements as proof of malicious provider behaviour.

---

## 5. Core research questions

*RQ4 and RQ6 are reframed in v2 as instrument-dependent. RQ5 now carries the open sub-problem.*

- **RQ1 — Memory sanitisation.** Do tenant-observable memory regions contain only expected initial
  values, or can the researcher's own canary survive across defined isolation boundaries?
- **RQ2 — Boundary strength.** How does observable memory behaviour differ across kernels, CUDA contexts,
  processes, containers, VMs, MIG instances, and sequential allocations?
- **RQ3 — Tenant-visible exposure.** Which device nodes, process metadata, profiling interfaces,
  management libraries, counters, sockets, and namespaces are visible?
- **RQ4 — Hardware consistency.** *(instrument-dependent)* Using the reproduced topology certificate, are
  timing/topology measurements consistent with the advertised GPU model and class?
- **RQ5 — Physical-device continuity.** *(carries D5)* Can repeated topology fingerprints give evidence
  that two sequential allocations used the same physical accelerator — **including when both allocations
  are the same advertised model?** This last clause is the open problem.
- **RQ6 — Location consistency.** *(instrument-dependent)* Are network/topology measurements consistent
  with the advertised region, at metropolitan-to-continental resolution, and is that sufficient to
  support or refute a jurisdictional claim?
- **RQ7 — Attestation availability.** Does the provider expose GPU / confidential-computing attestation
  to the tenant?
- **RQ8 — Attestation correctness.** Does the evidence chain verify, contain freshness, match reference
  measurements, and indicate a non-debug configuration?
- **RQ9 — Connection binding.** Is the attested environment meaningfully bound to the tenant's
  application channel, or is this untested/ambiguous?
- **RQ10 — Market variation.** How do observable assurance properties differ among hyperscalers,
  specialist GPU clouds, marketplaces, resellers, and bare-metal services?
- **RQ11 — Allocation model.** *(new — A6)* Can the allocation model (MIG / time-slicing / MPS / vGPU /
  passthrough / software-fractional) be inferred from inside a rented job, with calibrated confidence?
- **RQ12 — MIG temporal isolation.** *(new — A7)* Is GPU memory scrubbed when a MIG instance is destroyed
  and recreated?

---

## 6. Threat model

**Tenant position.** The researcher is an ordinary authenticated customer with legitimate access: shell
inside the rented VM/container, permission to run CUDA kernels and ordinary CUDA APIs, inspect the local
filesystem/process namespace available to the tenant, make normal network requests, and destroy/recreate
owned instances. The researcher does **not** assume host root, provider admin, firmware access, hidden
provider telemetry, vendor signing keys, a neighbour's cooperation, access to neighbouring workloads, or
physical server access.

**Failures being measured (observable evidence consistent with):** incomplete memory sanitisation;
framework/allocator reuse; excessive device exposure; cross-process/cross-container visibility;
unexpected management access; misdescribed hardware; undocumented sharing; region inconsistency;
invalid/unavailable/stale attestation; debug-mode deployment; weak connection binding; ambiguous
isolation; **undocumented MIG teardown behaviour**.

**Adversary assumptions.** For some RQs the provider or reseller may be modelled as potentially
inaccurate, misconfigured, or dishonest about GPU model/class, dedicated-vs-shared tenancy, region,
confidential-computing status, or isolation guarantees. **This is a research model, not an accusation.**

**Out-of-scope adversaries (explicitly not modelled/tested):** physical chip attacks, malicious firmware
implants, power/EM analysis, GPU Rowhammer, DMA attacks, IOMMU bypass, host-kernel or hypervisor
exploitation, supply-chain implant detection, destructive fault injection, **cache/TLB side channels**.

---

## 7. Ethical & legal safety model (mandatory — implement as requirements)

This section is a set of **product requirements**, not a disclaimer. The clean, loudly-stated ethics
posture is what makes the project publishable and the maintainer credible. It goes in the README, the
paper, and the disclosure emails. **Unchanged from v1 — it was already right.**

### 7.1 Canary-only memory policy

GPU-SEAL may search **only** for canaries the operator generated. A canary must be randomly generated,
unique per controlled experiment, non-semantic, cryptographically identifiable, bound to an experiment
ID, and free of personal information, real secrets, copyrighted content, and realistic prompts/messages.

Logical structure (the *actual* canary is a structured binary format with a random payload and
authenticated checksum — never a readable sentence):

```text
GPU-SEAL-CANARY
experiment_id
allocation_id
boundary_id
random_nonce
checksum
```

### 7.2 Unknown-memory handling

The system must **never**: print unknown bytes; render unknown bytes as text; attempt UTF-8 decoding;
search unknown bytes for natural-language patterns, credentials, or keys; classify unknown bytes as
prompts/weights/activations/images/files; upload unknown bytes to an LLM; store raw unknown buffers; or
include raw unknown buffers in logs or crash dumps.

It may retain only **safe aggregate information**: zero-byte percentage; fixed-pattern percentage;
byte-frequency histogram; estimated entropy; repeated-block count; exact match against owned canaries;
longest owned-canary prefix match; measurement hash; probe version; driver/environment metadata; error
codes; timing measurements.

### 7.3 Automatic safety stop

If a probe detects unknown content inconsistent with expected allocation behaviour, it must: stop further
memory analysis; not render/decode the bytes; delete the in-memory raw buffer where practical; preserve
only an aggregate statistical record + cryptographic digest; mark the result `sensitive_observation`;
block automatic publication; require manual disclosure review.

### 7.4 Provider terms & permission

Before testing a provider: review its AUP, security-testing policy, and vulnerability-disclosure
programme; request written permission where policy is unclear; keep tests within owned instances and
normal tenant privileges; avoid disruptive workloads; record permission and policy versions in study
metadata. **Some providers prohibit security benchmarking without permission — resolve this per provider
before probing.** Where prohibited, restrict to self-canary experiments that only ever touch your own
marker data.

### 7.5 Responsible disclosure

Internally reproduce → eliminate methodology errors → confirm only owned canaries matched → prepare a
minimal technical report → contact the provider privately → offer source/logs/hashes/environment → allow
a reasonable remediation window (default 90 days) → re-test after response → publish only after
coordination or documented non-response → clearly separate verified facts, probable interpretations, and
unresolved uncertainty.

> Alignment note: fwd:cloudsec's published disclosure policy is 90 days to patch plus 30 to coordinate.
> Our default already matches. Keep it.

### 7.6 Naming policy

No public ranking by name until methodology is validated, positive/negative controls exist, measurements
are repeated, provider responses are considered, uncertainty is represented, and ethical/legal review has
passed. During the pilot, providers are **Provider A / B / C / D**. (Precedent for provider pushback:
CVE-2023-48022 / ShadowRay was never fixed because the maintainer called it a feature. Measure against
the provider's *own advertised guarantees* and let the report card speak.)

---

## 8. Architecture

```text
┌──────────────────────────────────────────────┐
│                 Controller                    │
│  Experiment definitions · Provider adapters   │
│  Scheduling · Budget controls                 │
│  Result signing · Disclosure gating           │
└───────────────────┬──────────────────────────┘
                    │ deploy
                    ▼
┌──────────────────────────────────────────────┐
│             Tenant Probe Agent                │
│  Environment inventory · Memory probes        │
│  Canary writer/matcher · Device exposure      │
│  Allocation-model classifier · MIG teardown   │
│  Topology/timing · Network-location           │
│  Attestation collect/verify · Safe aggregation│
│  Raw-buffer destruction (enforced)            │
└───────────────────┬──────────────────────────┘
                    │ signed safe results
                    ▼
┌──────────────────────────────────────────────┐
│              Evidence Store                   │
│  Signed JSON bundles · No raw unknown VRAM    │
│  Tool & image digests · Provider policy meta  │
│  Reproduction status · Disclosure status      │
└───────────────────┬──────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────┐
│             Analysis & Reports                │
│  Statistics · Assurance grades · CIs          │
│  Provider-neutral comparison · Longitudinal   │
└──────────────────────────────────────────────┘
```

**Design principles:** safety is centralised (all buffer handling passes through one enforced-safe layer;
only statistics leave a probe); everything is a signed structured result with full provenance; provider
adapters isolate the messy provisioning; controls (a known-clean local baseline) run alongside every
provider so you can separate "provider scrubbed" from "runtime zeroed."

---

## 9. Probe families

Build in order. The inventory + memory + self-canary + allocation-classifier probes alone are enough to
have a project.

> **Mapping from v1:** old *Probe A (residue)* → **9.2 + 9.3**; old *Probe B (self-canary)* → **9.5**;
> old *Probe C (identity/topology)* → **9.8 + 9.9, now demoted to instrument**; old *Probe D
> (attestation)* → **9.10 + 9.11**; old *Probe E (escape surface)* → **9.6**. The old
> *structured-content scoring* in Probe A is **deleted** per §7.2. **New in v2: §9.12.**

### 9.1 Environment inventory

Collects the minimum context needed to interpret everything else. Sensitive/stable identifiers are hashed
or removed before publication.

```yaml
experiment: { id, timestamp, tool_version, tool_commit, container_digest, researcher_account_id_hash }
provider:   { provider_code, product_name, advertised_region, advertised_gpu, advertised_tenancy, advertised_confidential_mode }
system:     { operating_system, kernel_version, containerised, virtualisation_indicators, cgroup_mode, pid_namespace, ipc_namespace, network_namespace }
gpu:        { cuda_runtime_version, cuda_driver_version, visible_device_count, reported_model, total_memory, mig_mode, mig_profile, gpu_uuid_hash, pci_information_reduced, nvml_available, dcgm_available }
```

### 9.2 Memory Probe A — local / shared memory sanitisation

Tests whether kernel-local / workgroup-shared memory begins in an expected state (the LeftoverLocals
class), measuring **only controlled canaries**. Variants: same kernel sequence, separate launch, separate
stream, separate context, separate process, separate container (researcher-controlled). Classify the
affected region and boundary precisely; a positive result is **not** automatically "LeftoverLocals."

> **Pre-registered expectation (A1):** negative on NVIDIA. NVIDIA was confirmed unaffected by
> CVE-2023-4969. This probe exists to *demonstrate the harness can detect the class* (via positive
> controls) and to cover non-NVIDIA silicon later — not because we expect a finding.

```json
{ "probe": "local_memory_sanitisation", "boundary": "separate_process",
  "owned_canary_match": false, "zero_fraction": 0.9999, "entropy_estimate": 0.0012,
  "unknown_raw_retained": false, "confidence": "medium" }
```

### 9.3 Memory Probe B — device-global VRAM allocation  ⭐ **D1 core**

Allocate large device-global buffers with a **non-zeroing** allocator (`cudaMalloc`, `torch.empty`);
measure returned bytes *before* writing app data; determine whether owned canaries survive across
controlled boundaries.

**Limitations (record the boundary every time):** runtime/driver may initialise allocations; caching
allocators may return process-local reused memory; a non-zero buffer does **not** prove cross-tenant
residue; an all-zero buffer does **not** prove provider sanitisation.

Tests: allocate → write canary → free → reallocate in (1) same process, (2) new context, (3) new process,
(4) new container, (5) after VM destroy/recreate, (6) after release/re-rent of the cloud allocation,
(7) across researcher-controlled MIG instances where permitted.

**Independent validation:** cross-check positive controls with NVIDIA **Compute Sanitizer**
`--tool initcheck`, which detects uninitialised global memory reads after `cudaMalloc`. Vendor-supplied
confirmation that the phenomenon is real strengthens the methodology section considerably.

### 9.4 Memory Probe C — framework allocator behaviour

Distinguishes GPU-driver behaviour from framework-level caching (e.g. PyTorch's caching allocator
returning process-local stale buffers). Primarily a **local / dedicated-lab** test — do **not** send
malformed requests to a provider-managed inference endpoint without explicit permission. Frameworks:
PyTorch, CUDA runtime API, CUDA driver API; optional lab-only vLLM / TensorFlow. Metrics: allocation
source/size, buffer-reuse rate, owned-canary recovery rate, boundary type, framework version,
sanitisation option, allocator config.

> CVE-2026-53923 is the reference case: a framework can reintroduce exposure on a driver that behaved
> correctly. Reproducing its *class* of bug locally (partial kernel write into a `torch.empty` buffer) is
> an excellent **positive control**.

### 9.5 Self-vs-self sequential canary  ⭐ **D1 core, gated on D5**

The clean, fully-ethical isolation test: does a canary written in Allocation A appear in a later
Allocation B controlled by the same researcher? **Must not assume two rentals use the same physical
GPU** — pair with topology fingerprints.

```text
Allocation A: collect env → topology F1 → write random canary → release → destroy
Allocation B: collect env → topology F2 → estimate F1≈F2 consistency → safe canary match → aggregate only
```

Interpretation: positive match = strong signal, investigate privately; negative + inconsistent
fingerprints = inconclusive; negative + highly-consistent fingerprints = useful but not absolute proof;
uncertain fingerprint = inconclusive. Report *"the two allocations were consistent with the same physical
accelerator under the project's classifier"* — **never** *"proved both allocations used the same physical
GPU."*

> 🔴 **v2 dependency (A3).** This probe's strongest result requires distinguishing *the same H100* from
> *a different H100*. Alpay & Alpay demonstrate same-device temporal stability and cross-*product*
> separation, but explicitly defer **same-model die separation**. Until §9.8b delivers it, every
> negative result where both allocations share an advertised model must be reported `inconclusive`.
> **Do not ship §9.5 conclusions before §9.8b has a calibrated classifier.**

### 9.6 Device & namespace exposure inventory  ⭐ **D4**

Passive observation only — no active exploitation. Inventory `/dev/nvidia*` (ownership, permissions,
major/minor), visible GPU count, MIG IDs, CUDA IPC, NVML/DCGM availability, `nvidia-smi` process
visibility, profiling/debugging interfaces, host-management sockets, Linux capabilities, seccomp profile,
AppArmor/SELinux context, privileged-container indicators, host PID/IPC namespace indicators, mounted
host paths, NVIDIA container driver capabilities (`NVIDIA_VISIBLE_DEVICES`, `NVIDIA_DRIVER_CAPABILITIES`).

**Not every unavailable interface is a failure** — some restricted counters/DCGM functions correctly
require privilege. Classify each finding: `secure_restriction` / `expected_visibility` /
`unexpected_visibility` / `ambiguous` / `not_testable`.

> **Why this matters more in v2:** three NVIDIA Container Toolkit escape CVEs in 18 months —
> CVE-2024-0132 (TOCTOU, CVSS 9.0, ~35% of cloud environments), CVE-2025-23359 (incomplete patch),
> CVE-2025-23266 "NVIDIAScape" (CVSS 9.0, `enable-cuda-compat` OCI hook inheriting `LD_PRELOAD`,
> exploitable with a 3-line Dockerfile, 37% of cloud environments per Wiz). `NVIDIA_DRIVER_CAPABILITIES`
> posture across providers is a directly relevant, unmeasured number. **Inventory only — never attempt
> the escape.**

### 9.7 Allocation-model classifier  ⭐ **D3 — promoted to primary contribution (A6)**

Classify (with confidence + evidence) **before interpreting anything**:
`dedicated_physical_passthrough`, `dedicated_virtual_gpu`, `time_sliced_full_gpu`, `mps`, `mig_instance`,
`mig_backed_vgpu`, `software_fractional_gpu`, `shared_unknown`, `dedicated_unknown`, `undocumented`.

Evidence: provider docs, MIG mode, GPU IDs, visible memory size, scheduling/timing behaviour, device
count, virtualisation indicators, provider support response. Never present inference as provider-confirmed
fact.

> **Why this is now a headline contribution.** NVIDIA's GPU Operator documentation states plainly that
> **time-slicing provides no memory or fault isolation between replicas.** A customer told "fractional
> H100" cannot tell from the invoice whether they bought hardware-partitioned MIG or an unisolated
> time-slice. Distinguishing them from inside a rented job — with calibrated confidence — is both
> unsolved and commercially meaningful. It is also the *precondition* for interpreting every memory
> result: the same canary outcome means something completely different under MIG than under time-slicing.

### 9.8 Topology fingerprint — **instrument, reproduced** *(demoted from contribution — A2)*

Reproduce Alpay & Alpay (2026). Unprivileged timing → SM-by-memory-region latency matrix → topology
certificate → compare repeated runs → assess consistency with the advertised class.

Measurements: SM-to-memory latency matrix (physical SM labels, dependent global loads),
cache-bypassing HBM sweeps, multi-die latency asymmetry, memory-domain structure, stable shape features,
repeated-run jitter, kernel code hash, compiler/driver metadata.

**Success criterion is reproduction fidelity, not novelty.** Target: recover the documented topology
signatures on available hardware, and characterise per-SM jitter against their 0.09-cycle baseline.
Report as validation.

Limitations: driver version, thermal state, load, and provider scheduling add noise; a signature is not a
unique immutable serial. Express hardware claims probabilistically.

```json
{ "advertised_gpu": "NVIDIA H100 SXM", "observed_class": "hopper_high_bandwidth_class",
  "consistency": "consistent", "classifier_confidence": 0.91, "physical_continuity_score": 0.87,
  "same_model_separation_supported": false,
  "limitations": ["no vendor serial", "shared-host load unknown", "same-model die separation unvalidated"] }
```

### 9.8b Same-model physical die re-identification  ⭐ **D5 — new contribution (A3)**

**The open problem Alpay & Alpay handed us.** Their cross-die identity experiment separates two different
Blackwell *products*; same-model die separation is deferred to prior fingerprinting literature.

Research design: rent N instances of a *single* advertised model (cheapest viable class first — an
Ampere or Ada consumer/workstation tier before H100), collect topology certificates, test pairwise
separability. Deliverables: a separability metric, an ROC/confidence calibration, an explicit statement
of the conditions under which same-model continuity can and cannot be claimed, and the resulting
constraint on §9.5.

Report honestly if it fails. "Same-model die separation is not achievable at tenant privilege under
conditions X, Y, Z" is itself a publishable, useful negative that bounds the whole research area.

### 9.9 Coarse location consistency — **instrument, reproduced** *(demoted — A2; reframed — A8)*

Is the observed network location consistent with the advertised region? **Do not** claim precise
geolocation or infer fraud from latency alone. Data: RTT to public landmarks, RIPE Atlas, permitted
traceroute-derived info, path stability, provider ASN, public-region endpoints, repeated measurements.
Note that rented instances often do not answer ICMP — use TCP-reachable ports, per Alpay & Alpay.

Output a consistency band: `consistent` / `probably_consistent` / `ambiguous` / `probably_inconsistent` /
`inconsistent` / `not_testable`. Acknowledge anycast, tunnelling, backbone routing, congestion, traffic
engineering, reseller infra, region-border ambiguity, landmark error. Never publish exact server
coordinates.

**Resolution bound (inherited):** metropolitan-to-continental, not rack-level. State this every time.

> **Sovereignty reframing (A8).** At continental resolution this instrument cannot find a rack — but it
> *can* distinguish "in the EU" from "not in the EU." That is precisely the granularity GDPR, NIS2, DORA,
> and the EU AI Act care about. Reframed this way, §9.9 stops being a reproduction and becomes an
> independent verification instrument for a contractual and regulatory claim that organisations are
> already being audited against, and currently answer with nothing but the provider's word.

### 9.10 Attestation availability & verification

Determine whether GPU / CC attestation is available, verify what's independently verifiable, and
**don't reduce assurance to one Boolean.** Checks: can a report be obtained; nonce matches; certificate
chain verifies; revocation checked; firmware measurements match reference; driver measurements match;
debug mode disabled; report identifies expected GPU model; evidence is fresh; CC mode actually enabled.

**Build on NVIDIA `nvtrust` + Attestation SDK — do not reimplement.** Cross-check with Intel Trust
Authority (`tdx+nvgpu`) where available. `Azure/az-cgpu-onboarding` is a useful reference deployment for
a CC-enabled test target.

```json
{ "attestation_available": true, "evidence_signature_valid": true, "certificate_chain_valid": true,
  "revocation_status_checked": true, "nonce_matches": true, "measurements_match_reference": true,
  "debug_mode_disabled": true, "gpu_model_claim_consistent": true,
  "application_channel_binding": "not_established", "relay_resistance_tested": false }
```

> Recommended reading before building: *Blueprint, Bootstrap, and Bridge: A Security Look at NVIDIA GPU
> Confidential Computing* (MLSys 2026, arXiv:2507.02770) — reconstructs GPU-CC architecture, bootstrap,
> and CPU↔GPU transfer protection. Closest thing to a map of the territory.

### 9.11 Application-channel binding lab

Initially a **controlled lab module**, not a public-cloud attack — must not redirect/intercept a real
provider's customer traffic. Tests whether valid attestation evidence is cryptographically tied to the
client's application connection; compares intra-handshake vs post-handshake designs; reproduces relay
scenarios only between researcher-owned endpoints.

Distinguish these related-but-distinct properties: `evidence_valid`, `evidence_fresh`,
`transport_authenticated`, `application_channel_bound`, `relay_resistance_demonstrated`.

### 9.12 MIG temporal isolation  ⭐ **D2 — new probe family (A7)**

**The gap NVIDIA's documentation leaves open.** The MIG User Guide specifies runtime isolation in detail —
separate crossbar ports, L2 cache banks, memory controllers, DRAM address buses — and specifies nothing
about whether memory is scrubbed when a MIG instance is **destroyed and recreated** for a successive
tenant. Runtime isolation ≠ temporal isolation.

Design (all within researcher-owned hardware or a researcher-controlled MIG-capable rental):

```text
1. Create MIG instance M1 on a researcher-owned GPU
2. Write authenticated owned canary into M1's device-global memory
3. Destroy M1
4. Recreate a MIG instance M2 with the same profile (and separately, a different profile)
5. Read-before-write in M2 → safe aggregation → owned-canary match only
6. Repeat across: same profile, different profile, full GPU reset, driver reload, host reboot
```

Report per boundary. Distinguish MIG teardown behaviour from GPU-wide FLR behaviour from driver-reload
behaviour — these are three different mechanisms and conflating them would be the obvious methodological
error.

**Hardware note:** MIG requires A100/H100-class datacentre silicon. **The RTX 3050 cannot run this
probe.** It requires rented hardware and is therefore Phase 2+, not local-lab. Budget accordingly, and
scope it tightly — short jobs, immediate teardown.

**Ethics note:** entirely self-canary. Only ever touches the researcher's own marker data in the
researcher's own MIG instances. This makes §9.12 runnable even under `self-canary-only` provider
policies — a significant practical advantage.

---

## 10. Data collection & evidence format

Every measurement bundle is signed.

```json
{
  "schema_version": "gpu-seal-result-v1",
  "experiment_id": "exp_2026_000001", "run_id": "run_2026_000045",
  "timestamp_utc": "2026-07-29T12:00:00Z",
  "provider_code": "provider-a", "region_claim": "region-1", "product_claim": "gpu-product-x",
  "tool": { "version": "0.1.0", "commit": "sha256:...", "container_digest": "sha256:...", "kernel_bundle_hash": "sha256:..." },
  "environment": {}, "allocation_model": {}, "probes": [],
  "safety": { "raw_unknown_memory_retained": false, "unknown_memory_rendered": false, "canary_only_search": true, "automatic_publication_allowed": false },
  "integrity": { "payload_hash": "sha256:...", "signature_algorithm": "ed25519", "signature": "..." }
}
```

**Reproducibility fields:** git commit, build timestamp, container digest, CUDA/compiler/driver versions,
kernel source hash, probe config, provider product, advertised GPU/region, test boundary, allocation
timestamps, repetition count, error/exclusion reason.

**Never published:** account IDs, unnecessary public IPs, stable GPU UUIDs, hostnames, provider-internal
IDs, sensitive raw traceroutes (unless reviewed), exact server coordinates, raw unknown GPU memory.

---

## 11. Experimental methodology & phases

**Phase 0 — Literature & policy review.** *(prior-art sweep ✅ complete — `docs/prior-art.md`)*
Remaining: bibliography expansion per §24, threat model sign-off, ethical protocol, **provider policy
matrix**, disclosure template, measurement pre-registration (including the §9.2 expected-negative),
exclusion criteria, language ADR. **No cloud testing yet;** peer/supervisor ethics review completed.

**Phase 1 — Controlled local lab.** The **RTX 3050 (Ampere, GA10x, CC 8.6)** supports kernel dev,
global-memory experiments, same/cross-process tests, container tests, canary logic, signing, and stats.
Ampere is architecturally nearer the A100 generation than Turing was, so topology-timing work transfers
better than v1 assumed. It **cannot** reproduce H100 CC, modern attestation, **MIG (§9.12)**, H200/B200
topology, provider scheduling, or cross-provider isolation.

- **Positive controls** (canary *should* survive): same-process allocator reuse; deliberately
  uninitialised output buffer; controlled framework-cache reuse; kernel that leaves part of a buffer
  untouched (the CVE-2026-53923 class).
- **Negative controls** (canary should *not* survive): explicit zeroisation; verified-reset new process;
  buffer overwrite; freshly-initialised allocation; clean container boundary.
- **Independent validation:** confirm positive controls with Compute Sanitizer `--tool initcheck`.

*Without positive controls you cannot prove a negative cloud result means the probe could detect a leak.*

**Phase 2 — Four-provider pilot.** *(expanded from three — A8)* One hyperscaler, one specialist GPU
cloud, one marketplace/reseller/fractional service, **one EU-sovereign provider** (Scaleway / Exoscale /
STACKIT). Scope: 4 providers × 1 product × 1 region × 10 allocation cycles × 5 probe families (inventory,
device exposure, global VRAM canary, allocation-model classifier, topology instrument).

Goals: validate deployment automation, surface ambiguous results, estimate cost, measure fingerprint
stability, refine classifications, validate disclosure workflow, detect false-positive sources.
**No public ranking.**

**Phase 2b — Same-model separability study (D5).** N instances of one model, cheapest viable class,
pairwise separability. Gates §9.5 conclusions.

**Phase 3 — Expanded campaign.** Provider × GPU class × region × tenancy model × repeated cycles. Target
~5–10 providers, 1–3 products each, 1–2 regions, ~20 cycles for core configs, smaller samples for
expensive products. Add §9.12 MIG temporal isolation on rented A100/H100. Record per cycle:
creation/destruction time, product, model, allocation mode, fingerprint, memory/exposure/attestation/
network results, cost, errors, exclusion reason.

**Phase 4 — Longitudinal retesting.** Re-test after driver/CUDA upgrades, platform announcements,
security disclosures, new GPU releases, architecture changes, CC updates. Alpay & Alpay explicitly defer
the multi-seed longitudinal campaign — this is open ground and may become a primary differentiator.

---

## 12. Statistical & scientific requirements

Don't overinterpret one allocation. For each conclusion report sample/success/failure/error/exclusion
counts, confidence interval (bootstrap CIs where appropriate), variance, fingerprint stability, classifier
confidence.

**Separate observation from interpretation**, e.g. — *Observation:* "In 3 of 20 sequential allocations,
0.08% of the measured buffer matched an earlier owned canary." *Interpretation:* "Consistent with
incomplete sanitisation across the measured boundary, subject to confirming same-physical-device and no
client-side cache."

Avoid provider-wide conclusions from one product/region/driver/date. **Pre-register scoring** before
examining named-provider results — including the §9.2 expected-negative and the §9.5 gating on D5.

---

## 13. Assurance report card (independent categories, no single score)

Avoid `62/100`. Grade each category A/B/C/D/U:

**13.1 Memory lifecycle hygiene** — A: no owned canaries recovered across tested boundaries, with
repeated valid same-device evidence · B: none recovered but some non-zero/ambiguous behaviour · C: varies
by boundary/product/run · D: owned canary recovered where it should have been sanitised · U: insufficient
evidence / unsupported.

> **v2 constraint:** grade **A requires valid same-device evidence.** Until D5 lands, allocations sharing
> an advertised model cannot reach A — they cap at **U**. Be explicit about this in every report card
> rather than silently inflating grades.

**13.2 Tenant exposure** — A: minimal expected exposure · B: extra visibility with plausible
justification · C: ambiguous/excessive metadata exposure · D: cross-boundary visibility of
researcher-controlled neighbour metadata · U: not testable.

**13.3 Hardware claim consistency** *(instrument-dependent)* — A: strongly consistent with advertised
class · B: mostly consistent, limited confidence · C: ambiguous · D: repeatedly inconsistent · U:
unsupported by classifier. **Cite the reproduced instrument and its limitations with every grade.**

**13.4 Location claim consistency** *(instrument-dependent)* — A: strongly consistent ·
B: probably consistent · C: ambiguous · D: repeatedly inconsistent · U: not testable. **State the
metropolitan-to-continental resolution bound with every grade.**

**13.5 Allocation-model transparency** *(new — A6)* — A: provider documents the model and measurement
agrees · B: documented, measurement ambiguous · C: undocumented but inferable · D: documented claim
contradicted by measurement · U: not classifiable.

**13.6 Attestation assurance** — report separate fields (not a grade): availability, signature validity,
chain validity, revocation status, nonce freshness, measurement verification, debug status,
hardware-model consistency, application-channel binding, relay-resistance evidence.

---

## 14. Technology stack

**Decided (ADR-001, Phase 0):** **Python-first prototype, port before cloud.**

- **Weeks 3–4, local lab only:** Python + CuPy / PyCUDA / PyTorch for control validation and canary
  logic. Fastest path to a real data point on the RTX 3050.
- **Before *any* provider testing:** port the cloud-facing probe agent to **C++/CUDA** for low-level
  probes with **Rust or Go** for orchestration and safe result handling.
- **Regardless of language:** all safety-critical buffer handling lives behind the single enforced-safe
  layer, and the CI safety tests in §16 gate every change.

Rationale and trade-offs to be written up as `docs/adr/001-implementation-language.md`. The risk being
accepted: throwaway prototype code. The risk being avoided: shipping garbage-collected, hard-to-audit
memory handling into a probe that touches unknown VRAM.

**Controller:** Go or Python with provider adapters, Terraform/OpenTofu, optional K8s jobs, budget/quota
controls, run-state DB, signed-result ingestion.
**Data:** PostgreSQL (metadata), object storage (signed safe bundles), Parquet (research datasets),
**no raw unknown GPU-memory storage.**
**Integrity:** Ed25519 signatures, SHA-256+ digests, Sigstore/Cosign container signing, SBOM,
reproducible-build metadata.
**Analysis:** Python, pandas, NumPy, SciPy, statsmodels, Jupyter, Matplotlib.
**Optional dashboard:** Next.js, static provider-neutral reports, uncertainty visualisation, public data
only post-disclosure.

---

## 15. Repository structure

```text
gpu-seal/
├── README.md  SECURITY.md  ETHICS.md  DISCLOSURE.md  CHARTER.md  LICENSE  CITATION.cff
├── docs/        prior-art · architecture · threat-model · methodology · scoring · data-handling
│                provider-policy-review · adr/
├── schemas/     experiment.schema.json · result.schema.json · report-card.schema.json
├── probe/       inventory · memory-local · memory-global · framework-allocator · device-exposure
│                allocation-classifier · mig-temporal · topology · location · attestation
├── controller/  providers · scheduler · budget · evidence · disclosure
├── lab/         positive-controls · negative-controls · docker · local-runner
├── analysis/    notebooks · statistics · figures · report-generator
├── infrastructure/ terraform · containers · kubernetes
├── tests/       unit · integration · safety · reproducibility
└── examples/    experiment-local.yaml · experiment-cloud.yaml · sample-safe-result.json
```

---

## 16. Safety tests required in CI (reject non-compliant changes)

1. No code path prints raw probe buffers. 2. No code path writes raw unknown VRAM to disk. 3. No network
upload of raw probe buffers. 4. No automatic UTF-8/text decoding. 5. No regex search for
credentials/secrets. 6. Canary matcher accepts only experiment-owned authenticated canaries. 7. Public
report generator rejects `sensitive_observation` runs. 8. Stable provider IDs redacted when configured.
9. Result signatures verify. 10. Tool + kernel hashes included. 11. Max experiment duration enforced.
12. Max allocation size enforced. 13. Provider allowlists enforced. 14. Owned-account confirmation
enforced. 15. Destructive/privilege-escalation test names prohibited.
16. **(new)** Report generator refuses grade A on §13.1 when same-device evidence is absent.
17. **(new)** No probe attempts container escape, `LD_PRELOAD` injection, or OCI hook manipulation —
    §9.6 is inventory-only.

---

## 17. Roadmap

### Twelve-week roadmap *(revised)*

- **Wk 1–2 Foundation.** ✅ Prior-art sweep. Repo, threat model, ethics + disclosure policy,
  result/experiment schemas, provider-policy template, **ADR-001**, expanded bibliography.
  *Exit:* safety rules documented **and enforced in CI**, no cloud testing, ethics review done.
- **Wk 3–4 Local probe core.** CUDA inventory, safe canary generator, global memory probe (§9.3),
  same/cross-process experiments, safe aggregation, signed JSON, raw-buffer destruction.
  *Exit:* positive + negative local controls pass, cross-validated with Compute Sanitizer; no raw unknown
  data in logs or files.
- **Wk 5–6 Exposure & container tests.** `/dev/nvidia*` + namespace inventory, NVML visibility,
  `nvidia-smi` process visibility, driver-capability inventory, Docker matrix, interpretation categories.
  *Exit:* reproducible local container tests; expected restrictions distinguished from failures.
- **Wk 7–8 Topology instrument + allocation classifier.** *(revised — A2/A6)* **Reproduce** Alpay & Alpay
  on the RTX 3050; fingerprint schema; repeated-run stability vs their 0.09-cycle baseline; Allocation
  A/B workflow; first cut of the §9.7 allocation-model classifier.
  *Exit:* reproduction fidelity characterised and reported; no binary same-GPU claim; classifier
  taxonomy validated locally.
- **Wk 9–10 Provider pilot.** 4 providers incl. one EU-sovereign, 1 product + region each, 10 cycles
  where affordable. *Exit:* pilot dataset; methodology revision; no public ranking.
- **Wk 11 Attestation module.** Evidence collection via `nvtrust`, nonce validation, chain verification,
  measurement comparison, debug-status check, structured limitations.
  *Exit:* ≥1 controlled/rented supported platform tested.
- **Wk 12 Release & research draft.** GPU-SEAL v0.1, reproducible pilot dataset, technical report,
  5-min demo, public methodology, redacted sample results, **arXiv preprint outline**.

**Deferred to post-week-12 (require rented datacentre silicon):** §9.12 MIG temporal isolation,
§9.8b same-model separability, H100 CC attestation.

### Extended version roadmap

- **v0.1** inventory · safe canary framework · local + global memory probes · exposure inventory ·
  allocation-model classifier · signed evidence · local controls.
- **v0.2** topology instrument reproduced · hardware-class consistency · sequential-allocation workflow ·
  initial location · **same-model separability study (D5)**.
- **v0.3** NVIDIA attestation · freshness/certificate checks · measurement verification · controlled
  channel-binding lab · **MIG temporal isolation (D2)**.
- **v0.5** four-provider pilot · reproducible analysis notebooks · provider-response workflow.
- **v1.0** multi-provider study · public provider-neutral dataset · coordinated named results · paper ·
  dashboard · longitudinal retest plan.

---

## 18. Evaluation metrics

**Probe correctness:** positive-control detection rate, negative-control false-positive rate, canary
precision/recall, buffer coverage, probe error rate.
**Instrument reproduction:** topology signature recovery vs published reference, per-SM jitter vs the
0.09-cycle baseline, class-classification accuracy.
**Same-model separability (D5):** pairwise separability, ROC, confidence calibration, and the explicit
conditions under which the claim fails.
**Allocation classifier (D3):** classification accuracy against ground truth on researcher-configured
hardware, confidence calibration, `undocumented` rate in the wild.
**Cloud campaign:** #providers/products/regions, successful vs excluded cycles, cost per valid
observation, reproduction rate.
**Attestation:** evidence-availability/signature/chain/nonce/measurement-match/debug-disabled rates,
channel-binding level.
**Safety (hard targets):** raw unknown buffers retained = 0; unknown buffers rendered = 0; unauthorised
targets = 0; out-of-policy provider complaints → 0; findings disclosed before publication = 100%.

---

## 19. Expected challenges & mitigations

- **~~Proving physical-device continuity~~ → Integrating and extending the topology instrument.**
  *(rewritten — A5)* v1's #1 risk is substantially solved for the cross-*product* case by Alpay & Alpay
  (2026). What remains is (a) reproducing it faithfully and (b) closing same-model die separation (D5).
  *Mitigate:* budget Wk 7–8 for reproduction, treat D5 as a first-class research task with an honest
  negative result as an acceptable outcome, and gate §9.5 conclusions on it explicitly.
- **Incumbent extends into memory.** If the Alpay group adds memory sanitisation, the delta shrinks fast.
  *Mitigate:* preprint early to establish priority; consider contacting them (`alpay@lightcap.ai`) —
  collaboration beats collision, and D5 is a natural joint extension.
- **Provider terms differ** — some prohibit benchmarking without permission. *Mitigate:* policy matrix,
  request permission, start with providers publishing clear research policies. Note §9.12 is pure
  self-canary and survives `self-canary-only` policies.
- **GPU cost** — H100/H200/B200 is expensive, and D2 + D5 both require rented datacentre silicon.
  *Mitigate:* four-provider pilot first, short jobs, automated destruction, hard budget limits, research
  credits, sponsorship *without surrendering publication independence*. Run D5 on the cheapest model class
  that still has multiple instances available.
- **Quotas & availability** — instances may need approval. *Mitigate:* multiple providers, async
  scheduling, separate cheap probes from expensive attestation tests.
- **False positives** — non-zero memory can come from runtime init, local allocator reuse, own-process
  reuse, driver behaviour, measurement bugs, compiler optimisation. *Mitigate:* positive + negative
  controls, Compute Sanitizer cross-validation, boundary-specific probes, repeat runs, owned canaries
  only, require independent reproduction.
- **Fingerprint overclaiming** — topology may not uniquely identify every GPU, and **explicitly does not
  yet separate same-model dies**. *Mitigate:* confidence scores, "consistent with" not "proved", publish
  classifier limits, cap §13.1 grades when same-device evidence is absent (CI test 16).
- **Expected-negative misreading** — §9.2 is expected negative on NVIDIA; an unregistered negative looks
  like a fishing expedition. *Mitigate:* pre-register it in Phase 0.
- **Provider reputation risk** — a badly framed report could unfairly harm a provider. *Mitigate:*
  pre-register scoring, coordinate disclosure, include provider responses, separate product-level from
  provider-wide claims, publish uncertainty.

---

## 20. Hardware & budget

**No datacentre hardware required to start.** Minimum: existing laptop/desktop, Linux dev env (or
WSL2 + Docker Desktop), cloud accounts, payment method or research credits, secure storage for code and
safe aggregate results.

**Existing hardware — RTX 3050 (Ampere GA10x, compute capability 8.6)** *(corrected — A10)*. Covers CUDA
dev, global-memory experiments (§9.3), same/cross-process testing, Docker validation, canary logic,
signing, statistics, and topology-instrument reproduction (§9.8). Ampere is a nearer architectural
generation to A100 than Turing, so timing work transfers better than v1 assumed.

**Cannot run locally:** MIG (§9.12 — needs A100/H100-class), H100 Confidential Computing, NVIDIA
attestation (§9.10), H200/B200 topology, provider scheduling behaviour, cross-provider isolation,
same-model separability (§9.8b — needs N rented instances).

**Current setup gap:** CUDA toolkit not yet installed. Docker Desktop present. First lab task is
toolchain + reproducible container.

**Do not** buy an H100, a GPU server, a rack, multiple physical GPUs, an HSM, or special networking gear.

**Budget.** A pilot may be a few hundred £/$ or cloud credits; a rigorous multi-provider campaign on
premium GPUs costs more. Controls: per-run max duration, per-provider spend limit, automatic shutdown,
quota monitoring, failed-deployment cleanup, cost recorded in each result, daily + campaign caps.
Staged: *Stage 1* local validation (near-zero) → *Stage 2* four-provider pilot (limited budget) →
*Stage 3* expanded study + D5 (credits/sponsorship) → *Stage 4* premium confidential GPUs and MIG
(targeted short experiments). Don't promise a fixed budget before checking real prices and availability.

---

## 21. Publication strategy

**Open-source release:** probe source, schemas, safe example results, reproducible container, ethics
policy, methodology, analysis notebooks, signed release artifacts.

**Paper structure:** abstract → introduction → GPU-cloud background → threat model → ethical methodology →
probe design → local validation → provider campaign → results → limitations → responsible disclosure →
related work → conclusion.

### Venue timing *(corrected — A9)*

| Venue | Status |
|---|---|
| fwd:cloudsec **NA 2026** | ❌ Held 1–2 June 2026. Schedule reviewed: **the "neocloud" theme was announced and no GPU-isolation talk was delivered.** The slot is genuinely open. |
| fwd:cloudsec **EU 2026** (London) | ❌ Closed — final round 13 Jun, acceptances 3 Jul 2026. |
| **fwd:cloudsec NA 2027** | 🎯 **Primary target.** CFP historically opens ~Dec–Jan. The 12-week roadmap lands v0.1 + pilot data ~Oct 2026 — comfortable. |
| **fwd:cloudsec EU 2027** | 🎯 Secondary, with the sovereignty framing. CFP historically ~March. Track *Tales from Turing's Hut* explicitly names confidential compute and inference engines; the sovereignty track explicitly names NIS2, DORA, the AI Act, and EU providers. |
| USENIX Security / NDSS | Longer lead; requires full Phase 3 campaign. |
| **arXiv preprint** | ⚡ **Priority action.** A directly-overlapping paper appeared five weeks ago. Preprint early to establish priority. |

Two useful facts: fwd:cloudsec **explicitly encourages first-time speakers** and offers mentoring; its
disclosure policy (90 days + 30 to coordinate) already matches §7.5.

**Candidate titles:** *GPU-SEAL: Tenant-Observable Isolation Assurance for Public GPU Clouds* ·
*Can You Trust the GPU You Rented? A Tenant-Side Measurement Study of Cloud GPU Isolation* ·
*What's Left on the Card: Cross-Provider Measurement of GPU Memory Hygiene*

**Portfolio line:** "Designed and implemented a tenant-side GPU-cloud assurance framework that measures
memory sanitisation, allocation-model transparency, device exposure, physical-hardware consistency,
coarse location, and confidential-computing attestation using only ordinary customer privileges and a
strict canary-only data policy."

---

## 22. Success criteria

**Initial project succeeds when:** (1) a safe probe suite runs on a normal rented CUDA instance; (2) raw
unknown VRAM is never stored or rendered; (3) positive local controls are detected and cross-validated
with Compute Sanitizer; (4) negative controls produce no false canary matches; (5) result bundles are
signed and reproducible; (6) ≥4 providers tested in a pilot including one EU-sovereign; (7) allocation
boundaries **and allocation models** are explicitly classified; (8) hardware conclusions include
confidence, limitations, and an explicit same-model separability caveat; (9) attestation results separate
evidence validity from channel binding; (10) methodology is strong enough for independent reproduction.

**Expanded project succeeds when:** the dataset covers multiple provider categories; results include
repeated allocation cycles; MIG temporal isolation has been measured; same-model separability is resolved
either way; findings are responsibly disclosed; ≥1 provider reproduces or responds; the project yields a
paper/dissertation/workshop submission/industry report; the tool becomes reusable by other legitimate
GPU-cloud customers.

---

## 23. Operating rules for the Cowork / AI-assistant session

Use this charter as the governing brief. **Required operating rules:** never generate code intended to
read or reconstruct another tenant's data; never implement host escape, privilege escalation, Rowhammer,
or destructive tests; **never implement container-escape techniques even for §9.6 inventory**; never save
or display raw unknown GPU memory; never search unknown memory for credentials, text, prompts, weights,
or personal information; restrict all cloud tests to accounts/instances the researcher controls; prefer
controlled canary matching and aggregate statistics; preserve scientific uncertainty; treat
provider-facing findings as confidential until disclosure review; keep each milestone independently
testable; add safety tests before expanding probe capability; **never cite a source by invented author
name — verify the author list before it enters a document.**

**Immediate tasks:**

1. ✅ ~~Detailed literature map / prior-art sweep~~ → `docs/prior-art.md`
2. Convert ethical rules into technical acceptance tests *(§16, incl. new tests 16–17)*
3. Design the JSON schemas
4. Write **ADR-001** for the implementation language *(decision made: Python-first, port before cloud)*
5. Design the safe binary canary format
6. Design positive + negative controls *(incl. the CVE-2026-53923-class partial-write control)*
7. Create the first repo scaffold
8. Implement local environment inventory
9. Implement a safe same-process VRAM experiment
10. Implement signed result output
11. Expand §24 bibliography and read the six historical papers
12. Draft the Ethics/ToS matrix for the first four target providers
13. **Do not begin named-provider testing until the ethics + policy checklist is complete.**

**First implementation milestone:**

> A local, reproducible CUDA probe that writes an authenticated researcher-owned binary canary, exercises
> controlled allocation reuse, reports only aggregate statistics and exact canary matches, signs the
> resulting JSON, and demonstrably never prints or stores unknown raw memory.

### Next session in Cowork — concrete tasks

1. ✅ **Prior-art sweep** — complete, `docs/prior-art.md`.
2. **Repo skeleton + result schema + enforced-safe layer** (half day): lock the canary-only / no-render /
   no-retain rules in code *and* CI **before** the first probe exists.
3. **Set up the local RTX 3050 lab** (1–2 hrs): CUDA toolkit (absent), reproducible container via the
   installed Docker Desktop, GPU passthrough verified.
4. **Safe canary generator + Memory Probe B (global read-before-write) + safe aggregation + signed JSON**
   (~a day): first real local data point.
5. **Positive + negative controls** wired into the safety test suite, cross-validated with Compute
   Sanitizer.
6. **Draft the Ethics/ToS matrix** for the first four target providers
   (`full-probe-ok` / `self-canary-only` / `needs-written-permission`).

**Definition of next-session success:** positive controls detected, negative controls clean, one signed
reproducible JSON result from the local lab, and a demonstrable guarantee that no unknown raw memory was
ever printed or stored.

---

## 24. References *(expanded — A4)*

### Primary motivation — NVIDIA documentation

1. NVIDIA — CUDA Runtime API, `cudaMalloc` ("The memory is not cleared") — https://docs.nvidia.com/cuda/cuda-runtime-api/
2. NVIDIA — Compute Sanitizer (`--tool initcheck`) — https://developer.nvidia.com/compute-sanitizer
3. NVIDIA — `gpu-admin-tools` (`--clear-memory`) — https://github.com/NVIDIA/gpu-admin-tools
4. NVIDIA — Multi-Instance GPU User Guide — https://docs.nvidia.com/datacenter/tesla/mig-user-guide/latest/
5. NVIDIA — GPU Operator, GPU sharing (time-slicing has no memory/fault isolation) — https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/gpu-sharing.html
6. NVIDIA — Confidential Compute on Hopper H100 (WP-11459-001) + attestation quick-start — https://docs.nvidia.com/attestation/quick-start-guide/latest/attestation-examples/hopper_single_gpu.html

### GPU memory residue — the decade of prior work *(new in v2)*

7. Lee et al. — *Stealing Webpages Rendered on Your Browser by Exploiting GPU Vulnerabilities* — IEEE S&P 2014
8. Maurice et al. — *Confidentiality Issues on a GPU in a Virtualized Environment* — Financial Cryptography 2014
9. Zhou et al. — *Vulnerable GPU Memory Management: Towards Recovering Raw Data from GPU* — PoPETs 2017
10. Naghibijouybari et al. — *Rendered Insecure: GPU Side Channel Attacks are Practical* — ACM CCS 2018 (→ CVE-2018-6260)
11. Pustelnik et al. — *Whispering Pixels: Exploiting Uninitialized Register Accesses in Modern GPUs* — IEEE EuroS&P 2024 (→ CVE-2024-21969)
12. Guo et al. — *GPU Memory Exploitation for Fun and Profit* — USENIX Security 2024
13. Sorensen & Khlaaf — *LeftoverLocals* (CVE-2023-4969) — https://arxiv.org/abs/2401.16603 · **NVIDIA confirmed not affected**
14. Trail of Bits — *LeftoverLocals* blog — https://blog.trailofbits.com/2024/01/16/leftoverlocals-listening-to-llm-responses-through-leaked-gpu-local-memory/

### Framework-layer exposure

15. vLLM — GGUF dequantize integer-truncation advisory GHSA-5jv2-g5wq-cmr4 — https://github.com/vllm-project/vllm/security/advisories/GHSA-5jv2-g5wq-cmr4
16. Red Hat — CVE-2026-53923 — https://access.redhat.com/security/cve/cve-2026-53923

### Hardware identity, location, attestation

17. **Alpay, F. & Alpay, T.** — *Unprivileged Topology Certificates for Cloud GPU Attestation* — arXiv:2606.24934v1, 22 Jun 2026, CC BY 4.0 — https://arxiv.org/abs/2606.24934 · **primary instrument**
18. *GPU Fingerprinting for Location Verification* — arXiv:2605.01930 — **provider-side scheme, cite as contrast**
19. NVD — CVE-2026-33697 (attested-TLS relay) — https://nvd.nist.gov/vuln/detail/CVE-2026-33697
20. IETF Internet-Draft — *Intra-handshake.fail* — https://datatracker.ietf.org/doc/draft-intra-handshake-fail/ · formal proof: https://github.com/CCC-Attestation/formal-spec-KBS
21. NVIDIA — GPU Claims Guide — https://docs.nvidia.com/attestation/advanced-documentation/latest/claims-guide/gpu_claims.html
22. NVIDIA — `nvtrust` — https://github.com/NVIDIA/nvtrust
23. Azure — `az-cgpu-onboarding` — https://github.com/Azure/az-cgpu-onboarding

### 2026 adjacent work — attacks, not assurance *(new in v2)*

24. *Blueprint, Bootstrap, and Bridge: A Security Look at NVIDIA GPU Confidential Computing* — MLSys 2026, arXiv:2507.02770
25. *Behind Bars: A Side-Channel Attack on NVIDIA MIG Cache Partitioning Using Memory Barriers* — USENIX Security 2026
26. *Exploiting TLBs in Virtualized GPUs for Cross-VM Side-Channel Attacks* — NDSS 2026
27. *The Serialized Bridge: LLM Serving Performance under Blackwell GPU Confidential Computing* — arXiv:2606.23969

### Container & platform

28. Wiz — NVIDIA Container Toolkit escapes: CVE-2024-0132, CVE-2025-23359, CVE-2025-23266 "NVIDIAScape"
29. NVIDIA — Container Toolkit Specialised Configurations — https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html

### Venue & precedent

30. Oligo — ShadowRay 2.0 (precedent for "disputed"/unfixed provider behaviour) — https://www.oligo.security/blog/shadowray-2-0-attackers-turn-ai-against-itself-in-global-campaign-that-hijacks-ai-into-self-propagating-botnet
31. fwd:cloudsec — https://fwdcloudsec.org/

> **Bibliography hygiene:** refs 7–12 are currently cited from a secondary compilation
> ([Barrack AI](https://blog.barrack.ai/nvidia-cuda-never-clears-gpu-memory/), a GPU host with a
> commercial interest in the conclusion). **Each must be read in the original and independently verified
> before it enters the paper.** Refs 25–26 are titles observed in a secondary source; confirm venue and
> authors directly.

---

## 25. Final note

The primary innovation is **not** a new exploit. The value is a **safe, repeatable, provider-neutral
assurance methodology** that lets ordinary customers test the GPU infrastructure they rent.

v2 sharpens what that means. Hardware identity and coarse location were claimed by others in June 2026 —
so GPU-SEAL consumes those as instruments and spends its novelty where the ground is still open:

> **What is left in the memory of the GPU you rented, does the provider's isolation model actually match
> what they sold you, and can you tell from inside the box?**

Always present the project as:

> *A tenant-side assurance and measurement framework for evaluating observable GPU-cloud isolation
> controls.*

Never as:

> *A toolkit for extracting residue from other tenants or escaping GPU-cloud isolation.*

*Everything here is a starting position, not a contract. v1 → v2 took one prior-art sweep. Expect v3.*
