# Project GHOSTMETER  ·  a.k.a. GPU-SEAL
### A tenant-side isolation & security-assurance harness for GPU clouds

*Two working names, one project. **GHOSTMETER** ("ghost" = residue left in the machine, "meter" = you measure it) is the punchy internal codename. **GPU-SEAL** — "Tenant-Observable **S**ecurity and **I**solation **A**ssurance for GPU C**L**ouds" — is the better name for a paper and a public repo. Pick whichever you want as the canonical one; the charter uses GHOSTMETER in prose and GPU-SEAL in the repo/paper examples.*

**Status:** pre-Phase-0 (nothing built yet)
**Document type:** governing research + implementation charter
**Purpose:** the shared plan you and Claude execute against in Cowork. Read top to bottom once; after that, live in the Roadmap, the Ethics model, and the First-Week section.
**Last updated:** July 2026

---

## 0. What changed in this merge (read once)

This charter merges the original GHOSTMETER kickoff doc with the fuller GPU-SEAL brief. The upgrades worth knowing:

- **Ethics is now enforced as product requirements, not prose.** The governing rule is **canary-only**: the harness searches memory *only* for cryptographic canaries the researcher created, and never interprets, classifies, decodes, retains, or publishes unknown memory. This supersedes the original "characterize, don't retain" wording.
- **Probe A no longer detects "structured content."** The original idea of flagging float/ASCII/token-ID patterns in returned buffers is **removed** — it edges toward interpreting another tenant's data. Replaced with safe aggregate statistics (zero fraction, entropy, byte histogram, repeated-block count) plus exact/prefix matching against owned canaries only.
- **"Escape surface" is renamed "device & namespace exposure inventory"** and reframed as passive observation — not every restriction is a provider failure, and nothing is actively exploited.
- **New:** signed reproducible evidence bundles (Ed25519 + SHA-256 + Sigstore), CI safety tests that reject policy-violating code, positive *and* negative controls, an allocation-model classifier, a framework-allocator probe, an application-channel-binding lab, ten formal research questions, and a per-category letter-grade report card (no single "62/100" score).
- **Tool orientation neutralised.** The brief was written for "ChatGPT Work"; this version targets Claude Cowork (or any disciplined coding assistant) and is otherwise tool-neutral.

---

## 1. One-paragraph thesis

A GPU-cloud tenant pays for isolation, for a specific chip, for a specific region, and for a clean machine — and receives an invoice, not evidence. That was acceptable when "cloud" meant three mature hyperscalers with audited isolation. It is not acceptable now that the market has filled with GPU providers, hosting companies, resellers, marketplaces, and fractional-GPU platforms (several of them recent crypto-mining pivots) renting out shared silicon that holds other people's model weights and inference traffic. The isolation gap on GPUs is *documented and vendor-admitted* — NVIDIA's own docs say time-slicing gives no memory isolation, and multiple 2024–2026 CVEs show uninitialised GPU memory leaking prior tenants' data — but **nobody measures it in the wild across providers.** GHOSTMETER / GPU-SEAL is an open-source probe suite you deploy as an ordinary paying customer, plus a measurement study that turns "everyone knows GPUs leak" into a reproducible, signed, per-provider dataset. It is an **assurance and measurement framework, not an exploitation toolkit.** You are not attacking anyone. You are auditing what *you* rented.

**The central research question:**

> Can an ordinary GPU-cloud customer independently verify memory sanitisation, workload isolation, hardware identity, coarse location, device exposure, and confidential-computing attestation — without trusting provider claims alone?

Five research areas feed that question: (1) GPU memory lifecycle and sanitisation; (2) tenant-visible isolation and management interfaces; (3) physical-GPU and hardware-class consistency; (4) coarse-location consistency; (5) confidential-computing attestation availability and correctness.

---

## 2. Why this is novel (and not "another scanner")

Almost every "cloud security project" collapses into the posture-management bucket: scan config, map to a benchmark, print findings. That space is fully saturated, including AI-flavoured variants that map misconfigurations to the OWASP LLM/Agentic Top 10. If a project can be described as "CSPM but for X," it already exists.

GHOSTMETER lives somewhere else — **independent tenant-side verification of provider claims:**

| Saturated space | This project |
|---|---|
| Audits *your* configuration (IAM, network, storage, logging, K8s) | Audits the *provider's* delivery of the rented accelerator |
| Reads cloud APIs and config files | Measures the actual silicon you rented |
| Opinion mapped to a framework | Empirical measurement with signed evidence and statistics |
| Runs against your own account settings | Produces a cross-provider dataset that does not currently exist |

Customers routinely receive claims that are hard to verify independently: "Dedicated GPU," "Isolated instance," "H100," "Confidential GPU," "Deployed in region X," "Secure multi-tenancy," "MIG-isolated," "Enterprise-grade." GHOSTMETER asks the empirical question underneath all of them:

> Does the underlying rented accelerator behave in a way consistent with the provider's isolation, hardware, location, and attestation claims?

"The person who built the tenant-side GPU-cloud isolation benchmark" is a real, durable professional identity. That is the prize.

---

## 3. Research motivation (the grounding)

### 3.1 GPU memory can expose sensitive computation
**LeftoverLocals** (Trail of Bits; CVE-2023-4969) showed GPU local memory could remain insufficiently cleared between kernel executions on affected platforms, and demonstrated recovery of data from an interactive LLM session. Do **not** use "LeftoverLocals" as a generic label for every GPU-memory test — the project must distinguish kernel-local/shared memory, device-global VRAM, framework-allocator reuse, partially-initialised tensors, and cross-process / cross-container / cross-VM / cross-MIG / sequential-cloud-allocation behaviour, each precisely.

### 3.2 Uninitialised GPU memory remains relevant
**CVE-2026-53923** (vLLM, GGUF dequantisation): integer truncation meant a full output tensor was allocated with uninitialised memory but only partly written — the unfilled section could retain stale GPU memory containing prior activations/weight fragments. Not identical to LeftoverLocals, but it reinforces the need to test whether buffers are fully initialised, whether allocator reuse exposes stale values, and whether cloud deployments correctly isolate reused GPU memory.

### 3.3 Physical-GPU identity is becoming measurable without privileged access
*Unprivileged Topology Certificates for Cloud GPU Attestation* (June 2026, arXiv:2606.24934) proposes software-only CUDA-timing measurements supporting claims about physical accelerator identity, hardware class, multi-die topology, and coarse network location — no firmware access or vendor serials required. Early research; **not** a universal serial-number replacement. A related 2026 paper explores GPU fingerprinting for location verification (arXiv:2605.01930). Treat all hardware claims probabilistically.

### 3.4 Attestation evidence is not automatically bound to the intended connection
**CVE-2026-33697** concerns relay/diversion risk in an attested-TLS design; the related *Intra-handshake.fail* work argues some intra-handshake attestation lacks strong application-traffic binding. Do **not** claim "all remote attestation is broken." Instead report independently: is evidence available; does the chain verify; do measurements match reference; is there a fresh nonce; is debug mode disabled; is the attested entity demonstrably bound to the application connection; was relay resistance actually tested.

### 3.5 MIG and fractional GPUs create different isolation boundaries
NVIDIA MIG partitions supported GPUs into hardware-isolated instances (separate L2 banks, memory controllers, DRAM address paths). But "fractional GPU" is not one architecture — a provider may use MIG, time-slicing, MPS, vGPU, full-device passthrough, software interception, custom scheduling, or undocumented combinations. **A valid benchmark must classify the allocation model before interpreting results.**

---

## 4. Goals, secondary goals, non-goals

### 4.1 Primary goals
1. Build a reproducible tenant-side GPU assurance harness.
2. Run with ordinary customer privileges — no provider/host/firmware access.
3. Measure only infrastructure the researcher rents.
4. Create a controlled canary-based memory-sanitisation methodology.
5. Inventory tenant-visible GPU device and management exposure.
6. Assess whether observed hardware is consistent with advertised hardware.
7. Assess whether coarse observed location is consistent with advertised region.
8. Verify available GPU confidential-computing attestation evidence.
9. Produce signed, reproducible result bundles.
10. Run a repeated measurement campaign across several providers.

### 4.2 Secondary goals
Public longitudinal dataset; provider-neutral assurance schema; local-lab validation path; support for multiple NVIDIA GPU generations where practical; let providers reproduce/respond; publishable paper; establish maintainer as a GPU-cloud-tenant-isolation specialist.

### 4.3 Non-goals (hard boundaries)
GPU-SEAL must **not**: exploit a provider; escape a VM/container; access the host OS; circumvent auth or billing; scan infrastructure it doesn't rent; read another tenant's files/processes/traffic/API data; recover natural-language text from unknown memory; classify unknown memory as weights/prompts/activations; save raw unknown VRAM; attempt GPU Rowhammer, privilege escalation, or DoS; saturate shared infrastructure beyond normal workload behaviour; publish an uncoordinated accusation; or present uncertain measurements as proof of malicious provider behaviour.

---

## 5. Core research questions

- **RQ1 — Memory sanitisation.** Do tenant-observable memory regions contain only expected initial values, or can the researcher's own canary survive across defined isolation boundaries?
- **RQ2 — Boundary strength.** How does observable memory behaviour differ across kernels, CUDA contexts, processes, containers, VMs, MIG instances, and sequential allocations?
- **RQ3 — Tenant-visible exposure.** Which device nodes, process metadata, profiling interfaces, management libraries, counters, sockets, and namespaces are visible?
- **RQ4 — Hardware consistency.** Are timing/topology measurements consistent with the advertised GPU model and class?
- **RQ5 — Physical-device continuity.** Can repeated topology fingerprints give evidence that two sequential allocations are consistent with the same physical accelerator?
- **RQ6 — Location consistency.** Are network/topology measurements consistent with the advertised region?
- **RQ7 — Attestation availability.** Does the provider expose GPU / confidential-computing attestation to the tenant?
- **RQ8 — Attestation correctness.** Does the evidence chain verify, contain freshness, match reference measurements, and indicate a non-debug configuration?
- **RQ9 — Connection binding.** Is the attested environment meaningfully bound to the tenant's application channel, or is this untested/ambiguous?
- **RQ10 — Market variation.** How do observable assurance properties differ among hyperscalers, specialist GPU clouds, marketplaces, resellers, and bare-metal services?

---

## 6. Threat model

**Tenant position.** The researcher is an ordinary authenticated customer with legitimate access: shell inside the rented VM/container, permission to run CUDA kernels and ordinary CUDA APIs, inspect the local filesystem/process namespace available to the tenant, make normal network requests, and destroy/recreate owned instances. The researcher does **not** assume host root, provider admin, firmware access, hidden provider telemetry, vendor signing keys, a neighbour's cooperation, access to neighbouring workloads, or physical server access.

**Failures being measured (observable evidence consistent with):** incomplete memory sanitisation; framework/allocator reuse; excessive device exposure; cross-process/cross-container visibility; unexpected management access; misdescribed hardware; undocumented sharing; region inconsistency; invalid/unavailable/stale attestation; debug-mode deployment; weak connection binding; ambiguous isolation.

**Adversary assumptions.** For some RQs the provider or reseller may be modelled as potentially inaccurate, misconfigured, or dishonest about GPU model/class, dedicated-vs-shared tenancy, region, confidential-computing status, or isolation guarantees. **This is a research model, not an accusation.**

**Out-of-scope adversaries (explicitly not modelled/tested):** physical chip attacks, malicious firmware implants, power/EM analysis, GPU Rowhammer, DMA attacks, IOMMU bypass, host-kernel or hypervisor exploitation, supply-chain implant detection, destructive fault injection.

---

## 7. Ethical & legal safety model (mandatory — implement as requirements)

This section is a set of **product requirements**, not a disclaimer. The clean, loudly-stated ethics posture is what makes the project publishable and you credible. It goes in the README, the paper, and the disclosure emails.

### 7.1 Canary-only memory policy
GPU-SEAL may search **only** for canaries the operator generated. A canary must be randomly generated, unique per controlled experiment, non-semantic, cryptographically identifiable, bound to an experiment ID, and free of personal information, real secrets, copyrighted content, and realistic prompts/messages.

Logical structure (the *actual* canary is a structured binary format with a random payload and authenticated checksum — never a readable sentence):
```text
GPU-SEAL-CANARY
experiment_id
allocation_id
boundary_id
random_nonce
checksum
```

### 7.2 Unknown-memory handling
The system must **never**: print unknown bytes; render unknown bytes as text; attempt UTF-8 decoding; search unknown bytes for natural-language patterns, credentials, or keys; classify unknown bytes as prompts/weights/activations/images/files; upload unknown bytes to an LLM; store raw unknown buffers; or include raw unknown buffers in logs or crash dumps.

It may retain only **safe aggregate information**: zero-byte percentage; fixed-pattern percentage; byte-frequency histogram; estimated entropy; repeated-block count; exact match against owned canaries; longest owned-canary prefix match; measurement hash; probe version; driver/environment metadata; error codes; timing measurements.

### 7.3 Automatic safety stop
If a probe detects unknown content inconsistent with expected allocation behaviour, it must: stop further memory analysis; not render/decode the bytes; delete the in-memory raw buffer where practical; preserve only an aggregate statistical record + cryptographic digest; mark the result `sensitive_observation`; block automatic publication; require manual disclosure review.

### 7.4 Provider terms & permission
Before testing a provider: review its AUP, security-testing policy, and vulnerability-disclosure programme; request written permission where policy is unclear; keep tests within owned instances and normal tenant privileges; avoid disruptive workloads; record permission and policy versions in study metadata. **Some providers prohibit security benchmarking without permission — resolve this per provider before probing.** Where prohibited, restrict to self-canary experiments that only ever touch your own marker data.

### 7.5 Responsible disclosure
Internally reproduce → eliminate methodology errors → confirm only owned canaries matched → prepare a minimal technical report → contact the provider privately → offer source/logs/hashes/environment → allow a reasonable remediation window (default 90 days) → re-test after response → publish only after coordination or documented non-response → clearly separate verified facts, probable interpretations, and unresolved uncertainty.

### 7.6 Naming policy
No public ranking by name until methodology is validated, positive/negative controls exist, measurements are repeated, provider responses are considered, uncertainty is represented, and ethical/legal review has passed. During the pilot, providers are **Provider A / B / C**. (Precedent for provider pushback: CVE-2023-48022 / ShadowRay was never fixed because the maintainer called it a feature. Measure against the provider's *own advertised guarantees* and let the report card speak.)

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

**Design principles:** safety is centralised (all buffer handling passes through one enforced-safe layer; only statistics leave a probe); everything is a signed structured result with full provenance; provider adapters isolate the messy provisioning; controls (a known-clean local baseline) run alongside every provider so you can separate "provider scrubbed" from "runtime zeroed."

---

## 9. Probe families

The full battery below subsumes the original GHOSTMETER A–E probes. Build in order; the inventory + memory + self-canary probes alone are enough to have a project.

> **Mapping from the original charter:** old *Probe A (residue)* → **9.2 + 9.3**; old *Probe B (self-canary)* → **9.5**; old *Probe C (identity/topology)* → **9.8 + 9.9**; old *Probe D (attestation)* → **9.10 + 9.11**; old *Probe E (escape surface)* → **9.6 (device & namespace exposure)**. The old *structured-content scoring* in Probe A is **deleted** per §7.2.

### 9.1 Environment inventory
Collects the minimum context needed to interpret everything else. Sensitive/stable identifiers are hashed or removed before publication.
```yaml
experiment: { id, timestamp, tool_version, tool_commit, container_digest, researcher_account_id_hash }
provider:   { provider_code, product_name, advertised_region, advertised_gpu, advertised_tenancy, advertised_confidential_mode }
system:     { operating_system, kernel_version, containerised, virtualisation_indicators, cgroup_mode, pid_namespace, ipc_namespace, network_namespace }
gpu:        { cuda_runtime_version, cuda_driver_version, visible_device_count, reported_model, total_memory, mig_mode, mig_profile, gpu_uuid_hash, pci_information_reduced, nvml_available, dcgm_available }
```

### 9.2 Memory Probe A — local / shared memory sanitisation
Tests whether kernel-local / workgroup-shared memory begins in an expected state (the LeftoverLocals class), measuring **only controlled canaries**. Variants: same kernel sequence, separate launch, separate stream, separate context, separate process, separate container (researcher-controlled). Classify the affected region and boundary precisely; a positive result is **not** automatically "LeftoverLocals."
```json
{ "probe": "local_memory_sanitisation", "boundary": "separate_process",
  "owned_canary_match": false, "zero_fraction": 0.9999, "entropy_estimate": 0.0012,
  "unknown_raw_retained": false, "confidence": "medium" }
```

### 9.3 Memory Probe B — device-global VRAM allocation
Allocate large device-global buffers with a **non-zeroing** allocator (`cudaMalloc`, `torch.empty`); measure returned bytes *before* writing app data; determine whether owned canaries survive across controlled boundaries. **Limitations (record the boundary every time):** runtime/driver may initialise allocations; caching allocators may return process-local reused memory; a non-zero buffer does **not** prove cross-tenant residue; an all-zero buffer does **not** prove provider sanitisation. Tests: allocate→write canary→free→reallocate in (1) same process, (2) new context, (3) new process, (4) new container, (5) after VM destroy/recreate, (6) after release/re-rent of the cloud allocation, (7) across researcher-controlled MIG instances where permitted.

### 9.4 Memory Probe C — framework allocator behaviour
Distinguishes GPU-driver behaviour from framework-level caching (e.g. PyTorch's caching allocator returning process-local stale buffers). Primarily a **local / dedicated-lab** test — do **not** send malformed requests to a provider-managed inference endpoint without explicit permission. Frameworks: PyTorch, CUDA runtime API, CUDA driver API; optional lab-only vLLM / TensorFlow. Metrics: allocation source/size, buffer-reuse rate, owned-canary recovery rate, boundary type, framework version, sanitisation option, allocator config.

### 9.5 Self-vs-self sequential canary
The clean, fully-ethical isolation test: does a canary written in Allocation A appear in a later Allocation B controlled by the same researcher? **Must not assume two rentals use the same physical GPU** — pair with topology fingerprints.
```text
Allocation A: collect env → topology F1 → write random canary → release → destroy
Allocation B: collect env → topology F2 → estimate F1≈F2 consistency → safe canary match → aggregate only
```
Interpretation: positive match = strong signal, investigate privately; negative + inconsistent fingerprints = inconclusive; negative + highly-consistent fingerprints = useful but not absolute proof; uncertain fingerprint = inconclusive. Report *"the two allocations were consistent with the same physical accelerator under the project's classifier"* — **never** *"proved both allocations used the same physical GPU."*

### 9.6 Device & namespace exposure inventory  *(was "escape surface")*
Passive observation only — no active exploitation. Inventory `/dev/nvidia*` (ownership, permissions, major/minor), visible GPU count, MIG IDs, CUDA IPC, NVML/DCGM availability, `nvidia-smi` process visibility, profiling/debugging interfaces, host-management sockets, Linux capabilities, seccomp profile, AppArmor/SELinux context, privileged-container indicators, host PID/IPC namespace indicators, mounted host paths, NVIDIA container driver capabilities (`NVIDIA_VISIBLE_DEVICES`, `NVIDIA_DRIVER_CAPABILITIES`). **Not every unavailable interface is a failure** — some restricted counters/DCGM functions correctly require privilege. Classify each finding: `secure_restriction` / `expected_visibility` / `unexpected_visibility` / `ambiguous` / `not_testable`.

### 9.7 Allocation-model classifier
Classify (with confidence + evidence) before interpreting anything: `dedicated_physical_passthrough`, `dedicated_virtual_gpu`, `time_sliced_full_gpu`, `mps`, `mig_instance`, `mig_backed_vgpu`, `software_fractional_gpu`, `shared_unknown`, `dedicated_unknown`, `undocumented`. Evidence: provider docs, MIG mode, GPU IDs, visible memory size, scheduling/timing behaviour, device count, virtualisation indicators, provider support response. Never present inference as provider-confirmed fact.

### 9.8 Topology fingerprint & hardware-class consistency
Unprivileged timing → topology certificate/fingerprint → compare repeated runs → assess consistency with the advertised class. Measurements: SM-to-memory latency matrix, cache-bypassing sweeps, multi-die latency asymmetry, memory-domain structure, stable shape features, repeated-run jitter, kernel code hash, compiler/driver metadata. Start by reproducing arXiv:2606.24934. Limitations: early results may not generalise; driver version, thermal state, load, and provider scheduling add noise; a signature is not a unique immutable serial. Express hardware claims probabilistically.
```json
{ "advertised_gpu": "NVIDIA H100 SXM", "observed_class": "hopper_high_bandwidth_class",
  "consistency": "consistent", "classifier_confidence": 0.91, "physical_continuity_score": 0.87,
  "limitations": ["no vendor serial", "shared-host load unknown"] }
```

### 9.9 Coarse location consistency
Is the observed network location consistent with the advertised region? **Do not** claim precise geolocation or infer fraud from latency alone. Data: RTT to public landmarks, RIPE Atlas, permitted traceroute-derived info, path stability, provider ASN, public-region endpoints, repeated measurements. Output a consistency band: `consistent` / `probably_consistent` / `ambiguous` / `probably_inconsistent` / `inconsistent` / `not_testable`. Acknowledge anycast, tunnelling, backbone routing, congestion, traffic engineering, reseller infra, region-border ambiguity, landmark error. Never publish exact server coordinates.

### 9.10 Attestation availability & verification
Determine whether GPU / CC attestation is available, verify what's independently verifiable, and **don't reduce assurance to one Boolean.** Checks: can a report be obtained; nonce matches; certificate chain verifies; revocation checked; firmware measurements match reference; driver measurements match; debug mode disabled; report identifies expected GPU model; evidence is fresh; CC mode actually enabled.
```json
{ "attestation_available": true, "evidence_signature_valid": true, "certificate_chain_valid": true,
  "revocation_status_checked": true, "nonce_matches": true, "measurements_match_reference": true,
  "debug_mode_disabled": true, "gpu_model_claim_consistent": true,
  "application_channel_binding": "not_established", "relay_resistance_tested": false }
```

### 9.11 Application-channel binding lab
Initially a **controlled lab module**, not a public-cloud attack — must not redirect/intercept a real provider's customer traffic. Tests whether valid attestation evidence is cryptographically tied to the client's application connection; compares intra-handshake vs post-handshake designs; reproduces relay scenarios only between researcher-owned endpoints. Distinguish these related-but-distinct properties: `evidence_valid`, `evidence_fresh`, `transport_authenticated`, `application_channel_bound`, `relay_resistance_demonstrated`.

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
**Reproducibility fields:** git commit, build timestamp, container digest, CUDA/compiler/driver versions, kernel source hash, probe config, provider product, advertised GPU/region, test boundary, allocation timestamps, repetition count, error/exclusion reason.
**Never published:** account IDs, unnecessary public IPs, stable GPU UUIDs, hostnames, provider-internal IDs, sensitive raw traceroutes (unless reviewed), exact server coordinates, raw unknown GPU memory.

---

## 11. Experimental methodology & phases

**Phase 0 — Literature & policy review.** Bibliography, threat model, ethical protocol, **provider policy matrix**, disclosure template, measurement pre-registration, exclusion criteria. Also: prior-art sweep (GitHub, USENIX/NDSS/S&P/CCS, arXiv cs.CR, vendor blogs) to confirm nobody has shipped this in the last few months. **No cloud testing yet;** peer/supervisor ethics review completed.

**Phase 1 — Controlled local lab.** A local CUDA GPU is valuable for validation — the researcher's **GTX 1650** supports kernel dev, global-memory experiments, same/cross-process tests, container tests, canary logic, signing, and stats. It **cannot** reproduce H100 CC, modern attestation, MIG, H200/B200 topology, provider scheduling, or cross-provider isolation. **Positive controls** (canary *should* survive): same-process allocator reuse, deliberately uninitialised output buffer, controlled framework-cache reuse, kernel that leaves part of a buffer untouched. **Negative controls** (canary should *not* survive): explicit zeroisation, verified-reset new process, buffer overwrite, freshly-initialised allocation, clean container/VM boundary. *Without positive controls you cannot prove a negative cloud result means the probe could detect a leak.*

**Phase 2 — Three-provider pilot.** One hyperscaler, one specialist GPU cloud, one marketplace/reseller/fractional service. Scope: 3 providers × 1 product × 1 region × 10 allocation cycles × 4 initial probe families (inventory, device exposure, global VRAM canary, topology). Goals: validate deployment automation, surface ambiguous results, estimate cost, measure fingerprint stability, refine classifications, validate disclosure workflow, detect false-positive sources. **No public ranking.**

**Phase 3 — Expanded campaign.** Provider × GPU class × region × tenancy model × repeated cycles. Target ~5–10 providers, 1–3 products each, 1–2 regions, ~20 cycles for core configs, smaller samples for expensive products. Record per cycle: creation/destruction time, product, model, allocation mode, fingerprint, memory/exposure/attestation/network results, cost, errors, exclusion reason.

**Phase 4 — Longitudinal retesting.** Re-test after driver/CUDA upgrades, platform announcements, security disclosures, new GPU releases, architecture changes, CC updates. Longitudinal value may become a primary differentiator.

---

## 12. Statistical & scientific requirements

Don't overinterpret one allocation. For each conclusion report sample/success/failure/error/exclusion counts, confidence interval (bootstrap CIs where appropriate), variance, fingerprint stability, classifier confidence. **Separate observation from interpretation**, e.g. — *Observation:* "In 3 of 20 sequential allocations, 0.08% of the measured buffer matched an earlier owned canary." *Interpretation:* "Consistent with incomplete sanitisation across the measured boundary, subject to confirming same-physical-device and no client-side cache." Avoid provider-wide conclusions from one product/region/driver/date. **Pre-register scoring** before examining named-provider results.

---

## 13. Assurance report card (independent categories, no single score)

Avoid `62/100`. Grade each category A/B/C/D/U:

**13.1 Memory lifecycle hygiene** — A: no owned canaries recovered across tested boundaries, with repeated valid same-device evidence · B: none recovered but some non-zero/ambiguous behaviour · C: varies by boundary/product/run · D: owned canary recovered where it should have been sanitised · U: insufficient evidence / unsupported.

**13.2 Tenant exposure** — A: minimal expected exposure · B: extra visibility with plausible justification · C: ambiguous/excessive metadata exposure · D: cross-boundary visibility of researcher-controlled neighbour metadata · U: not testable.

**13.3 Hardware claim consistency** — A: strongly consistent with advertised class · B: mostly consistent, limited confidence · C: ambiguous · D: repeatedly inconsistent · U: unsupported by classifier.

**13.4 Location claim consistency** — A: strongly consistent · B: probably consistent · C: ambiguous · D: repeatedly inconsistent · U: not testable.

**13.5 Attestation assurance** — report separate fields (not a grade): availability, signature validity, chain validity, revocation status, nonce freshness, measurement verification, debug status, hardware-model consistency, application-channel binding, relay-resistance evidence.

---

## 14. Technology stack

**Recommended (disciplined target):** probe agent in **C++ / CUDA** for low-level probes + **Rust or Go** for orchestration and safe result handling; minimal Python only for analysis / provider-SDK glue; static/tightly-controlled deps; reproducible containers. Controller in Go or Python with provider adapters, Terraform/OpenTofu, optional K8s jobs, budget/quota controls, run-state DB, signed-result ingestion. Data: PostgreSQL (metadata), object storage (signed safe bundles), Parquet (research datasets), **no raw unknown GPU-memory storage.** Integrity: Ed25519 signatures, SHA-256+ digests, Sigstore/Cosign container signing, SBOM, reproducible-build metadata. Analysis: Python, pandas, NumPy, SciPy, statsmodels, Jupyter, Matplotlib. Optional dashboard: Next.js, static provider-neutral reports, uncertainty visualisation, public data only post-disclosure.

**Architecture decision to make in Phase 0 (ADR-worthy):** the original charter suggested a Python-first prototype (CuPy/PyTorch/PyCUDA) for speed to first data point. That's fine for **local positive/negative-control validation in weeks 3–4** — but the cloud-facing agent that touches unknown memory should move to the disciplined stack **before any provider testing**, and the safety-critical buffer handling must live behind the enforced-safe layer regardless of language. Decide and record this trade-off explicitly.

---

## 15. Repository structure

```text
gpu-seal/
├── README.md  SECURITY.md  ETHICS.md  DISCLOSURE.md  LICENSE  CITATION.cff
├── docs/        architecture · threat-model · methodology · scoring · data-handling · provider-policy-review
├── schemas/     experiment.schema.json · result.schema.json · report-card.schema.json
├── probe/       inventory · memory-local · memory-global · framework-allocator · device-exposure · topology · location · attestation
├── controller/  providers · scheduler · budget · evidence · disclosure
├── lab/         positive-controls · negative-controls · docker · local-runner
├── analysis/    notebooks · statistics · figures · report-generator
├── infrastructure/ terraform · containers · kubernetes
├── tests/       unit · integration · safety · reproducibility
└── examples/    experiment-local.yaml · experiment-cloud.yaml · sample-safe-result.json
```

---

## 16. Safety tests required in CI (reject non-compliant changes)

1. No code path prints raw probe buffers. 2. No code path writes raw unknown VRAM to disk. 3. No network upload of raw probe buffers. 4. No automatic UTF-8/text decoding. 5. No regex search for credentials/secrets. 6. Canary matcher accepts only experiment-owned authenticated canaries. 7. Public report generator rejects `sensitive_observation` runs. 8. Stable provider IDs redacted when configured. 9. Result signatures verify. 10. Tool + kernel hashes included. 11. Max experiment duration enforced. 12. Max allocation size enforced. 13. Provider allowlists enforced. 14. Owned-account confirmation enforced. 15. Destructive/privilege-escalation test names prohibited.

---

## 17. Roadmap

### Twelve-week initial roadmap
- **Wk 1–2 Foundation.** Repo, threat model, ethics + disclosure policy, result/experiment schemas, provider-policy template, literature review. *Exit:* safety rules documented, no cloud testing, ethics review done.
- **Wk 3–4 Local probe core.** CUDA inventory, safe canary generator, global memory probe, same/cross-process experiments, safe aggregation, signed JSON, raw-buffer destruction. *Exit:* positive+negative local controls pass; no raw unknown data in logs/files.
- **Wk 5–6 Exposure & container tests.** `/dev/nvidia*` + namespace inventory, NVML visibility, `nvidia-smi` process visibility, driver-capability inventory, Docker matrix, interpretation categories. *Exit:* reproducible local container tests; expected restrictions distinguished from failures.
- **Wk 7–8 Topology & sequential allocation.** Timing probe, fingerprint schema, repeated-run stability, Allocation A/B workflow, confidence-based continuity. *Exit:* fingerprint stability characterised; no binary same-GPU claim.
- **Wk 9–10 Provider pilot.** 3 providers, 1 product+region each, 10 cycles where affordable; collect inventory/memory/exposure/fingerprints/errors/cost. *Exit:* pilot dataset; methodology revision; no public ranking.
- **Wk 11 Attestation module.** Evidence collection, nonce validation, chain verification, measurement comparison, debug-status check, structured limitations. *Exit:* ≥1 controlled/rented supported platform tested.
- **Wk 12 Release & research draft.** GPU-SEAL v0.1, reproducible pilot dataset, technical report, 5-min demo, public methodology, redacted sample results, paper outline.

### Extended version roadmap
- **v0.1** inventory · safe canary framework · local+global memory probes · exposure inventory · signed evidence · local controls.
- **v0.2** topology fingerprint · hardware-class consistency · sequential-allocation workflow · initial location.
- **v0.3** NVIDIA attestation · freshness/certificate checks · measurement verification · controlled channel-binding lab.
- **v0.5** three-provider pilot · reproducible analysis notebooks · provider-response workflow.
- **v1.0** multi-provider study · public provider-neutral dataset · coordinated named results · paper · dashboard · longitudinal retest plan.

---

## 18. Evaluation metrics

**Probe correctness:** positive-control detection rate, negative-control false-positive rate, canary precision/recall, buffer coverage, probe error rate. **Fingerprint quality:** intra-device temporal variance, inter-device separation, class-classification accuracy, confidence calibration, sensitivity to driver/temperature/load. **Cloud campaign:** #providers/products/regions, successful vs excluded cycles, cost per valid observation, reproduction rate. **Attestation:** evidence-availability/signature/chain/nonce/measurement-match/debug-disabled rates, channel-binding level. **Safety (hard targets):** raw unknown buffers retained = 0; unknown buffers rendered = 0; unauthorised targets = 0; out-of-policy provider complaints → 0; findings disclosed before publication = 100%.

---

## 19. Expected challenges & mitigations

- **Proving physical-device continuity** — a negative canary is weak if Allocation B used a different GPU. *Mitigate:* topology fingerprints, repeated allocations, report uncertainty, seek provider-assisted controlled placement for validation.
- **Provider terms differ** — some prohibit benchmarking without permission. *Mitigate:* policy matrix, request permission, start with providers publishing clear research policies.
- **GPU cost** — H100/H200/B200 is expensive. *Mitigate:* three-provider pilot first, short jobs, automated destruction, hard budget limits, research credits, sponsorship *without surrendering publication independence.*
- **Quotas & availability** — instances may need approval. *Mitigate:* multiple providers, async scheduling, separate cheap probes from expensive attestation tests.
- **False positives** — non-zero memory can come from runtime init, local allocator reuse, own-process reuse, driver behaviour, measurement bugs, compiler optimisation. *Mitigate:* positive+negative controls, boundary-specific probes, repeat runs, owned canaries only, require independent reproduction.
- **Fingerprint overclaiming** — topology may not uniquely identify every GPU. *Mitigate:* confidence scores, "consistent with" not "proved", validate across known devices, publish classifier limits.
- **Provider reputation risk** — a badly framed report could unfairly harm a provider. *Mitigate:* pre-register scoring, coordinate disclosure, include provider responses, separate product-level from provider-wide claims, publish uncertainty.

---

## 20. Hardware & budget

**No datacentre hardware required.** Minimum: existing laptop/desktop, Linux dev env, cloud accounts, payment method or research credits, secure storage for code + safe aggregate results. **Useful existing hardware:** a GTX 1650 covers CUDA dev, basic global-memory experiments, same/cross-process testing, Docker validation, canary logic, stats. **Rented specialised hardware** needed for: MIG, H100 CC, H200/B200 topology, NVIDIA attestation, provider-specific virtualisation, cross-provider measurements. **Do not** buy an H100, a GPU server, a rack, multiple physical GPUs, an HSM, or special networking gear.

**Budget:** a pilot may be a few hundred £/$ or cloud credits; a rigorous multi-provider campaign on premium GPUs costs more. Controls: per-run max duration, per-provider spend limit, automatic shutdown, quota monitoring, failed-deployment cleanup, cost recorded in each result, daily + campaign caps. Staged: *Stage 1* local validation (near-zero) → *Stage 2* three-provider pilot (limited budget) → *Stage 3* expanded study (credits/sponsorship) → *Stage 4* premium confidential GPUs (targeted short experiments). Don't promise a fixed budget before checking real prices/availability.

---

## 21. Publication strategy

**Open-source release:** probe source, schemas, safe example results, reproducible container, ethics policy, methodology, analysis notebooks, signed release artifacts.
**Paper structure:** abstract → introduction → GPU-cloud background → threat model → ethical methodology → probe design → local validation → provider campaign → results → limitations → responsible disclosure → related work → conclusion.
**Target venues:** fwd:cloudsec (its 2026 theme is literally "the neocloud" — near-perfect fit), USENIX Security / NDSS, or a strong technical blog + arXiv preprint.
**Candidate titles:** *GPU-SEAL: Tenant-Observable Isolation Assurance for Public GPU Clouds* · *Can You Trust the GPU You Rented? A Tenant-Side Measurement Study of Cloud GPU Isolation.*
**Portfolio line:** "Designed and implemented a tenant-side GPU-cloud assurance framework that measures memory sanitisation, device exposure, physical-hardware consistency, coarse location, and confidential-computing attestation using only ordinary customer privileges and a strict canary-only data policy."

---

## 22. Success criteria

**Initial project succeeds when:** (1) a safe probe suite runs on a normal rented CUDA instance; (2) raw unknown VRAM is never stored/rendered; (3) positive local controls are detected; (4) negative controls produce no false canary matches; (5) result bundles are signed and reproducible; (6) ≥3 providers tested in a pilot; (7) allocation boundaries explicitly classified; (8) hardware conclusions include confidence + limitations; (9) attestation results separate evidence validity from channel binding; (10) methodology is strong enough for independent reproduction.

**Expanded project succeeds when:** the dataset covers multiple provider categories; results include repeated allocation cycles; findings are responsibly disclosed; ≥1 provider reproduces or responds; the project yields a paper/dissertation/workshop submission/industry report; the tool becomes reusable by other legitimate GPU-cloud customers.

---

## 23. Operating rules for the Cowork / AI-assistant session

Use this charter as the governing brief. **Required operating rules:** never generate code intended to read or reconstruct another tenant's data; never implement host escape, privilege escalation, Rowhammer, or destructive tests; never save or display raw unknown GPU memory; never search unknown memory for credentials, text, prompts, weights, or personal information; restrict all cloud tests to accounts/instances the researcher controls; prefer controlled canary matching and aggregate statistics; preserve scientific uncertainty; treat provider-facing findings as confidential until disclosure review; keep each milestone independently testable; add safety tests before expanding probe capability.

**Immediate tasks:** (1) detailed literature map; (2) convert ethical rules into technical acceptance tests; (3) design the JSON schemas; (4) write an ADR for the implementation language; (5) design the safe binary canary format; (6) design positive+negative controls; (7) create the first repo scaffold; (8) implement local environment inventory; (9) implement a safe same-process VRAM experiment; (10) implement signed result output; (11) **do not begin named-provider testing until the ethics + policy checklist is complete.**

**First implementation milestone:**
> A local, reproducible CUDA probe that writes an authenticated researcher-owned binary canary, exercises controlled allocation reuse, reports only aggregate statistics and exact canary matches, signs the resulting JSON, and demonstrably never prints or stores unknown raw memory.

### First week in Cowork — concrete tasks
1. **Prior-art sweep** (half day): GitHub + USENIX/NDSS/S&P/CCS + arXiv cs.CR + vendor blogs → short "who's near this" doc. If someone shipped it, pivot to the delta.
2. **Repo skeleton + result schema + enforced-safe layer** (half day): lock the canary-only / no-render / no-retain rules in code *and* CI *before* the first probe exists.
3. **Set up the local GTX 1650 lab** (1–2 hrs): CUDA toolchain, reproducible container.
4. **Safe canary generator + Memory Probe B (global read-before-write) + safe aggregation + signed JSON** (~a day): first real local data point.
5. **Positive + negative controls** wired into the safety test suite.
6. **Draft the Ethics/ToS matrix** for the first 3–4 target providers (`full-probe-ok` / `self-canary-only` / `needs-written-permission`).

**Definition of week-one success:** positive controls detected, negative controls clean, one signed reproducible JSON result from the local lab, and a demonstrable guarantee that no unknown raw memory was ever printed or stored.

---

## 24. References

1. Sorensen & Khlaaf — *LeftoverLocals: Listening to LLM Responses Through Leaked GPU Local Memory* — https://arxiv.org/abs/2401.16603
2. Trail of Bits — *LeftoverLocals* (blog) — https://blog.trailofbits.com/2024/01/16/leftoverlocals-listening-to-llm-responses-through-leaked-gpu-local-memory/
3. vLLM — GGUF dequantize integer-truncation advisory GHSA-5jv2-g5wq-cmr4 — https://github.com/vllm-project/vllm/security/advisories/GHSA-5jv2-g5wq-cmr4
4. Red Hat — CVE-2026-53923 — https://access.redhat.com/security/cve/cve-2026-53923
5. *Unprivileged Topology Certificates for Cloud GPU Attestation* — https://arxiv.org/abs/2606.24934
6. *GPU Fingerprinting for Location Verification* — https://arxiv.org/abs/2605.01930
7. NVD — CVE-2026-33697 (attested-TLS relay) — https://nvd.nist.gov/vuln/detail/CVE-2026-33697
8. IETF Internet-Draft — *Intra-handshake.fail* — https://datatracker.ietf.org/doc/draft-intra-handshake-fail/
9. NVIDIA — Multi-Instance GPU User Guide — https://docs.nvidia.com/datacenter/tesla/mig-user-guide/latest/
10. NVIDIA — Hopper Single GPU Attestation Example — https://docs.nvidia.com/attestation/quick-start-guide/latest/attestation-examples/hopper_single_gpu.html
11. NVIDIA — GPU Claims Guide — https://docs.nvidia.com/attestation/advanced-documentation/latest/claims-guide/gpu_claims.html
12. NVIDIA — Container Toolkit Specialised Configurations — https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html
13. NVIDIA GPU Operator docs — GPU sharing (time-slicing has no memory/fault isolation) — https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/gpu-sharing.html
14. Oligo — ShadowRay 2.0 (precedent for "disputed" / unfixed provider behaviour) — https://www.oligo.security/blog/shadowray-2-0-attackers-turn-ai-against-itself-in-global-campaign-that-hijacks-ai-into-self-propagating-botnet
15. fwd:cloudsec — 2026 CFP, theme "the neocloud" (target venue) — https://fwdcloudsec.org/

---

## 25. Final note

The primary innovation is **not** a new exploit. The value is a **safe, repeatable, provider-neutral assurance methodology** that lets ordinary customers test the GPU infrastructure they rent. Always present the project as:

> *A tenant-side assurance and measurement framework for evaluating observable GPU-cloud isolation controls.*

Never as:

> *A toolkit for extracting residue from other tenants or escaping GPU-cloud isolation.*

*Codenames GHOSTMETER / GPU-SEAL are placeholders — rename freely. Everything here is a starting position, not a contract; we revise as Phase 0 tells us what's real.*
