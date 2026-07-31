# Prior Art Sweep — "Who's Near This"

**Project:** GPU-SEAL (codename GHOSTMETER)
**Phase:** 0 — Literature & policy review
**Date:** 2026-07-29
**Charter task:** §23 First Week, Task 1
**Status:** Complete. **Verdict: PROCEED, with a mandatory reframe.**

---

## 0. Executive summary

Nobody has shipped GPU-SEAL. There is no cross-provider, tenant-side, canary-based GPU-cloud isolation
measurement study or harness in the public record. The core idea survives the sweep.

But three findings change the project materially, and one of them is load-bearing:

1. **🔴 Probe families 9.8 (topology fingerprint) and 9.9 (location consistency) are no longer novel.**
   arXiv:2606.24934 (22 June 2026) does both, better than the charter anticipated, with published
   validation. The charter said "start by reproducing" it — correct instinct, wrong framing. It is not
   a contribution, it is now an **instrument** GPU-SEAL consumes. This is a *gift*: it solves the
   charter's own #1 expected challenge (§19, physical-device continuity).

2. **🔴 The charter's flagship motivation partly does not apply to the charter's own target platform.**
   NVIDIA GPUs were **confirmed not affected** by LeftoverLocals (CVE-2023-4969). The affected vendors
   were AMD, Apple, Qualcomm, and Imagination. GPU-SEAL targets NVIDIA GPU clouds. §3.1 needs rewriting
   or a reviewer kills the paper in the first round.

3. **🟠 The related-work section is ~10 years thin.** The charter cites LeftoverLocals and nothing else
   from the GPU memory residue literature. There are at least six major peer-reviewed papers
   (S&P 2014 → USENIX Sec 2024) directly on this topic. Submitting without them is not survivable.

Plus one strategic opportunity the charter missed entirely — see §6, **EU digital sovereignty**.

---

## 1. Citation verification

All four of the charter's load-bearing 2026 citations are real and say what the charter claims.

| Charter ref | Status | Note |
|---|---|---|
| arXiv:2606.24934 — Unprivileged Topology Certificates | ✅ Real, 22 Jun 2026 | **Much stronger than charter implies.** See §2. |
| CVE-2026-53923 — vLLM GGUF int truncation | ✅ Real | Affects vLLM 0.5.5 → 0.23.1rc0. Root cause: an `int` that should have been `int64_t`. Charter's description is accurate. |
| CVE-2026-33697 — attested-TLS relay | ✅ Real, CVSS 7.5 | Nuance: NVD/SentinelOne scope it to Cocos AI v0.4.0–v0.8.2; the *research* claim is broader (7 binding mechanisms tested, none relay-resistant). Real-world impact named: Meta Private Processing (WhatsApp), Edgeless Contrast. Formal proof repo: `CCC-Attestation/formal-spec-KBS`. |
| arXiv:2605.01930 — GPU Fingerprinting for Location Verification | ✅ Real | **Important distinction:** requires a *registration phase before chips are sold* plus a trusted verifying server. That is a **provider-side / vendor-side** scheme. A tenant cannot use it. Not competitive with GPU-SEAL; cite as contrast. |

**Action:** charter §24 reference list is accurate but incomplete. See §3 for what must be added.

---

## 2. The big one: arXiv:2606.24934 overlaps RQ4, RQ5, RQ6

Its abstract framing is close to verbatim GPU-SEAL:

> "Cloud GPU tenants are asked to trust provider claims that are hard to inspect from inside a rented
> job. The accelerator should be the same physical machine over time, it should match the billed
> hardware class, and it should run at the advertised site."

That is charter RQ4 (hardware consistency), RQ5 (physical continuity), and RQ6 (location) — stated by
someone else, five weeks ago.

**What it already delivers:**

| Claim | Their result |
|---|---|
| Per-SM latency map is a stable physical fingerprint | 6-hour full-load RTX 5090 run, median temporal jitter **0.09 cycles** |
| Distinct dies are separable | Shape-only leave-one-out classification, **100.0% accuracy** on Blackwell dies |
| Hardware-class topology recovery | Volta V100 unified domain; Hopper H200 two-way L2 split; Blackwell B200 two-die NV-HBI package |
| Coarse location binding | 169 RIPE Atlas probes place a B200 within **44 km** of claimed DC, **rejects all 11 decoy sites** |
| Verifier needs no GPU | Certificate = sufficient statistics + config + code hashes + network evidence + SHA-256 |

They also ship the certificate concept — which overlaps charter §10's signed evidence bundle.

**Authors:** Faruk Alpay (Bahçeşehir University, Istanbul) and Taylan Alpay (University of Turkish
Aeronautical Association, Ankara). Correspondence: `alpay@lightcap.ai`. CC BY 4.0, arXiv:2606.24934v1,
22 Jun 2026. Cite as **Alpay & Alpay (2026)**.

### 🟢 Their stated limitations are our contribution surface

Read §12 of their paper closely — it hands us back more than the abstract suggests:

| Their limitation (verbatim sense) | What it means for GPU-SEAL |
|---|---|
| *"The cross-die identity experiment separates two different Blackwell **products**. **Same-model die separation is left to prior GPU fingerprinting.**"* | 🔴 **This is the big one.** They can tell a B200 from a 5090. They have **not** shown they can tell *your* H100 from *another* H100. Charter §9.5 depends on exactly that. |
| *"Across **five rented GPUs** and three generations"* | Tiny N. Their campaign is a demonstration, not a census. GPU-SEAL's repeated multi-provider campaign is a different scale of claim. |
| *"B200 measurement was taken on a rental instance with limited tenure… bootstrap CI on the cut conductance **awaits a longer multi-seed campaign**."* | They explicitly leave the statistical/longitudinal campaign open. That is charter Phase 3 + Phase 4. |
| *"The network alibi localises to **metropolitan-to-continental scale**, not to a rack."* | Sufficient for sovereignty (EU vs US is continental). Insufficient for anything finer. Bounds the §6 framing honestly. |
| *"Instances do not answer ICMP, so it uses TCP-reachable ports."* | Practical methodology note to inherit directly. |
| *"The certificate proves consistency of the measured evidence; it does not prove firmware integrity, prevent refusal to run, or replace vendor attestation."* | Clean separation of concerns — their instrument does not overlap §9.10 attestation. |

**Consequence for §9.5 (self-vs-self sequential canary).** The design assumed a working same-physical-
device classifier. The published instrument gives us *temporal stability on one device* (0.09-cycle
jitter over 6 h) and *cross-product class separation* (100%), but **not same-model die
re-identification**. So either:

- **(a)** GPU-SEAL contributes same-model die separation — a genuine, well-scoped open problem with an
  obvious evaluation (rent N instances of one model, test pairwise separability); or
- **(b)** GPU-SEAL reports `inconclusive` whenever two allocations share a model, which guts the
  strongest memory result.

**(a) is now a top-tier delta candidate — promote it.** It is narrow, measurable, directly enables the
memory work, and the authors have publicly flagged it as unfinished.

### What this means (this is the reframe)

**Do not compete. Consume.**

The charter's §19 lists as expected challenge #1:

> *"Proving physical-device continuity — a negative canary is weak if Allocation B used a different GPU."*

That was the methodological weak point of the entire self-vs-self canary design (§9.5). A published,
validated, unprivileged, software-only instrument for exactly that problem now exists. GPU-SEAL should
implement it as a **dependency and control**, cite it, and spend its novelty budget elsewhere.

**Revised positioning:**

> Topology certificates tell you *which chip you got*. GPU-SEAL asks *what was left on it* — and does
> so across providers, repeatedly, over time, under a canary-only ethics policy.

Reduce §9.8/§9.9 from "probe families" to "**§9.8 Physical-continuity instrument (reproduction and
extension of Alpay & Alpay 2026)**." Report reproduction fidelity as a validation result; report
same-model die separation (§2 above) as the contribution.

**Risk to watch:** if that group extends into memory sanitisation, GPU-SEAL's remaining delta shrinks
fast. Recommend monitoring the authors and considering early contact — collaboration beats collision.

---

## 3. Prior art the charter is missing (must be added to §24)

A decade of peer-reviewed GPU memory residue work exists. Currently uncited:

| Work | Venue | Finding |
|---|---|---|
| Lee et al., *Stealing Webpages Rendered on Your Browser* | IEEE S&P **2014** | First deep GPU memory security analysis. NVIDIA **and** AMD do not initialise newly allocated GPU pages. Recovered rendered webpages, 95.4% identification accuracy. |
| Maurice et al., *Confidentiality Issues on a GPU in a Virtualized Environment* | FC **2014** | Cross-VM GPU data recovery. GPU global memory is zeroed only in some configs — and then as a **side effect of ECC**, not for security. |
| Zhou et al., *Vulnerable GPU Memory Management* | PoPETs **2017** | Recovered credit card numbers, email contents, credentials from residue left by Chrome, Adobe Reader, GIMP, Matlab. No special privileges needed. |
| Naghibijouybari et al., *Rendered Insecure: GPU Side Channel Attacks are Practical* | ACM CCS **2018** | First general GPU side channels; ~90% website fingerprinting; derived NN model parameters from another CUDA app. → CVE-2018-6260. |
| Pustelnik et al., *Whispering Pixels* | IEEE EuroS&P **2024** | Uninitialised **register** accesses. Leaked CNN intermediates and reconstructed LLM output. Apple/NVIDIA/Qualcomm affected. AMD → CVE-2024-21969. |
| Guo et al., *GPU Memory Exploitation for Fun and Profit* | USENIX Sec **2024** | Code injection/reuse on Volta+; tampered DNN params **persisting in GPU memory** to poison future inference. |

**Also add — 2026 adjacent work (different lane, but reviewers will ask):**

- *Behind Bars: A Side-Channel Attack on NVIDIA MIG Cache Partitioning Using Memory Barriers* — USENIX Security **2026**
- *Exploiting TLBs in Virtualized GPUs for Cross-VM Side-Channel Attacks* — NDSS **2026**
- *Blueprint, Bootstrap, and Bridge: A Security Look at NVIDIA GPU Confidential Computing* — MLSys **2026** (arXiv:2507.02770, IBM Research + Ohio State). Directly relevant to §9.10/§9.11.
- *The Serialized Bridge: LLM Serving Performance under Blackwell GPU CC* — arXiv:2606.23969

**Distinguish clearly in the paper:** all of the above are **attacks**. GPU-SEAL is **tenant-side
assurance measurement**. That distinction is the ethical and scientific identity of the project — make
the reviewer see it in the related-work table, not just the ethics section.

---

## 4. 🔴 The LeftoverLocals problem

Charter §3.1 leads with LeftoverLocals as motivation. But:

> **NVIDIA confirmed their devices were not affected by LeftoverLocals (CVE-2023-4969).** Affected:
> AMD, Apple, Qualcomm, Imagination. Trail of Bits noted NVIDIA had likely already addressed these
> patterns due to prior academic work (the CUDA Leaks paper).

GPU-SEAL targets NVIDIA GPU clouds — CUDA, MIG, H100 CC, nvtrust. So:

- **Probe family §9.2 (local/shared memory sanitisation, "the LeftoverLocals class") should be
  hypothesised negative on NVIDIA before we run it.** That is fine — a well-designed negative with
  working positive controls is a publishable result. But it must be *pre-registered as expected*,
  otherwise it looks like we went looking for a known-absent bug.
- The honest motivating chain for NVIDIA is **not** LeftoverLocals. It is:
  1. `cudaMalloc()` documentation states verbatim: **"The memory is not cleared."** Same language in
     `cuMemAlloc`, `cudaMallocManaged`, `cuMemAllocManaged`.
  2. No NVIDIA documentation guarantees zeroing between processes or CUDA contexts in non-CC operation.
  3. NVIDIA's own `gpu-admin-tools` ships an explicit `--clear-memory` flag — proving clearing is *not*
     default.
  4. CC on H100 scrubs **only at FLR** (tenant handoff). Within a session, `cudaMalloc` still returns
     uncleared memory. CC addresses inter-tenant, not intra-session.
  5. MIG documents **runtime** isolation (separate L2 banks, memory controllers, DRAM address buses) but
     is **silent on temporal isolation** — i.e. scrubbing when instances are destroyed and recreated for
     a new tenant.
  6. CVE-2026-53923 shows the framework layer independently reintroducing the exposure.

**Rewrite §3.1 around points 1–6. Demote LeftoverLocals to related work with an explicit
"NVIDIA not affected" note.** This makes the project *more* credible, not less — it shows we read the
advisory rather than the headline.

---

## 5. Where the defensible delta actually is

Ranked by novelty × feasibility on an RTX 3050 + modest cloud budget:

| # | Delta | Why it holds | Confidence |
|---|---|---|---|
| **D1** | **Cross-provider memory-sanitisation measurement in the wild** | No such dataset exists, at all. Topology paper doesn't touch memory. Academic residue work is single-machine/lab, never a provider census. This is the core. | **High** |
| **D2** | **MIG temporal isolation** | NVIDIA documents runtime isolation and is explicitly silent on destroy/recreate scrubbing. Nobody has measured it. Clean, bounded, self-canary-safe, publishable on its own. | **High** |
| **D3** | **Tenant-side allocation-model classifier (§9.7)** | "Fractional GPU" means MIG *or* time-slicing *or* MPS *or* vGPU *or* software interception. Providers rarely say which. Time-slicing has *no* memory isolation per NVIDIA's own GPU Operator docs. Telling them apart from inside a rented job is genuinely unsolved and commercially useful. | **High** |
| **D4** | **Post-NVIDIAScape device/namespace exposure census (§9.6)** | Three container-escape CVEs in 18 months (CVE-2024-0132, CVE-2025-23359, CVE-2025-23266 "NVIDIAScape" — Wiz measured 37% of cloud environments vulnerable). `NVIDIA_DRIVER_CAPABILITIES` / OCI hook posture across providers is unmeasured. | **Medium-High** |
| **D5** | **Same-model physical die re-identification** | **Explicitly left open by Alpay & Alpay §12.** Narrow, measurable, and it is the *precondition* for D1's strongest result. Rent N of one model, test pairwise separability. | **High** |
| **D6** | **Longitudinal + signed reproducible evidence** | Nobody re-tests providers over driver/CUDA upgrade cycles. Alpay & Alpay defer the multi-seed campaign explicitly. Slow-burn differentiator, matches charter Phase 4. | **Medium** |
| **D7** | **EU sovereignty verification** | See §6. Possibly the strongest *framing*, even if technically built on D1 + reproduced 9.8/9.9. | **High** |
| ~~D8~~ | ~~Cross-*product* hardware class + coarse location~~ | **Claimed by Alpay & Alpay (2026).** Reproduce as instrument, do not claim. | — |

**Minimum viable novel paper:** D1 + D2 + D3. That is a real contribution with or without everything
else. **D5 is the highest-leverage addition** — it is small, it is flagged as open by the incumbent
authors, and D1's headline result is weak without it.

---

## 6. 🟢 Strategic opportunity the charter missed: EU digital sovereignty

fwd:cloudsec **Europe 2026** CFP explicitly solicits:

- "data sovereignty, relevant regulations, European-specific technical challenges"
- "real-world impacts and experiences working to comply with … **NIS2, DORA, the AI Act** and the Cyber
  Resiliency Act"
- "security research related to Europe-based providers such as **STACKIT, UpCloud, Scaleway, Exoscale**"
- (under *Tales from Turing's Hut*) "security of emerging application architectures (**confidential
  compute**, edge computing) training and inference engines"

GPU-SEAL's §9.9 location-consistency probe stops being "a reproduction of a fingerprinting paper" and
becomes **an independent instrument for verifying a regulatory claim**. "Can an EU AI Act / GDPR /
NIS2-bound organisation independently verify that the GPU running its model is physically in the EU?"
is a sharper, more fundable, more publishable question than a generic isolation census — and it is a
question a *customer* asks, which fits the charter's tenant-side identity perfectly.

**Recommendation:** adopt sovereignty verification as a first-class framing alongside memory hygiene.
Add a European provider (Scaleway / Exoscale / STACKIT) to the Phase 2 pilot's three.

---

## 7. Tooling landscape

No competitor found. What exists and how it relates:

| Tool | What it is | Relation to GPU-SEAL |
|---|---|---|
| **NVIDIA Compute Sanitizer** (`--tool initcheck`) | Detects uninitialised global memory reads after `cudaMalloc` | **Use it.** Validates our positive controls independently. Vendor-supplied confirmation that residue is real. |
| **NVIDIA `nvtrust`** + Attestation SDK (Python) | Official GPU/NVSwitch attestation | **Dependency for §9.10.** Do not rebuild. |
| **NVIDIA `gpu-admin-tools`** (`--clear-memory`) | Admin memory clearing | **Evidence artifact** — its existence proves clearing isn't default. Cite it. |
| **Azure `az-cgpu-onboarding`** | Confidential GPU onboarding | Reference implementation for a CC-enabled test target. |
| **Intel Trust Authority** (`tdx+nvgpu`) | Composite TDX + H100 attestation | Alternate verifier for §9.10 cross-checking. |
| **Phala** | Commercial confidential AI cloud, GPU TEE + attestation | Potential *test target*, and a competitor for the "verifiable GPU" narrative — but they verify *their own* cloud. GPU-SEAL is provider-neutral and tenant-operated. |
| `memtestG80`, `cuda-unified-memory-analyzer` | GPU diagnostics | Unrelated (correctness/perf, not security). |

**Nothing in this list is a tenant-side, cross-provider, canary-based isolation harness.** The niche is open.

---

## 8. Venue timing (revised — charter §21 is now out of date)

| Venue | Status as of 2026-07-29 |
|---|---|
| **fwd:cloudsec NA 2026** | ❌ **Held 1–2 June 2026.** Schedule reviewed: **no GPU/neocloud isolation talk was delivered.** The "neocloud" theme was announced and nobody filled it. Strong signal the slot is genuinely open. |
| **fwd:cloudsec EU 2026** (London) | ❌ Closed. Final round 13 Jun, acceptances sent 3 Jul 2026. |
| **fwd:cloudsec NA 2027** | 🎯 **Primary target.** CFP historically opens ~Dec–Jan. A 12-week roadmap from now lands v0.1 + pilot data in ~Oct 2026 — comfortable. |
| **fwd:cloudsec EU 2027** | 🎯 Secondary, with the sovereignty framing (§6). CFP historically opens ~March. |
| **USENIX Sec / NDSS** | Longer lead; needs full Phase 3 campaign. |
| **arXiv preprint** | ⚡ Available immediately, and given how fast this area is moving (a directly-overlapping paper appeared 5 weeks ago), **preprint early to establish priority**. |

Two useful CFP facts: fwd:cloudsec **explicitly encourages first-time speakers** and offers mentoring;
and its disclosure policy is Project-Zero-shaped (90 days + 30 to coordinate) — which matches the
charter's §7.5 default exactly. Good alignment.

---

## 9. Required charter amendments

| § | Change | Priority |
|---|---|---|
| §3.1 | Rewrite. Lead with NVIDIA's own `cudaMalloc` "memory is not cleared" documentation + `--clear-memory` tool + MIG temporal-isolation silence. Demote LeftoverLocals to related work, explicitly noting **NVIDIA not affected**. | 🔴 Critical |
| §3.3 | Upgrade. The topology paper is stronger than described (0.09-cycle jitter, 100% die separation, 44 km / 11 decoys). Reclassify as **instrument, not target**. | 🔴 Critical |
| §9.8, §9.9 | Demote from "probe family / contribution" to "reproduction + instrument." Report reproduction fidelity as validation. | 🔴 Critical |
| §24 | Add the six historical papers (§3 above) + the three 2026 adjacent papers. | 🟠 High |
| §19 | Expected-challenge #1 (physical-device continuity) is **substantially solved** by arXiv:2606.24934. Rewrite as an integration task. | 🟠 High |
| §9.7 | Promote. The allocation-model classifier is a **top-3 novelty**, not a preliminary step. | 🟠 High |
| New §9.12 | Add **MIG temporal isolation** as an explicit probe family (D2). Currently only implicit in §9.3 test 7. | 🟠 High |
| §1, §21 | Add EU digital-sovereignty framing and a European provider to the pilot. | 🟡 Medium |
| §21 | Update venue timing per §8 above. Add "arXiv preprint early" as a priority action. | 🟡 Medium |
| §20 | Hardware corrected: **RTX 3050 (Ampere, CC 8.6)**, not GTX 1650. Ampere ⇒ closer arch generation to A100; still no MIG, no CC, no NVLink. | 🟡 Medium |

---

## 10. Verdict

**Proceed.** The central thesis holds: no cross-provider tenant-side GPU isolation dataset exists, the
venue theme was announced and went unfilled, and the tooling niche is empty.

But the project is now **narrower and sharper** than the charter describes. Hardware identity and
location were claimed by someone else in June 2026. What remains — and what nobody has done — is:

> **What is left in the memory of the GPU you rented, does the provider's isolation model actually
> match what they sold you, and can you tell from inside the box?**

Measured across providers, repeatedly, over time, under a canary-only policy, with signed reproducible
evidence — and, if we take the sovereignty framing, in a form that answers a regulatory question a real
customer is already being asked by their auditor.

That is still a durable professional identity. It is just a more specific one.

---

## Sources

- [Unprivileged Topology Certificates for Cloud GPU Attestation (arXiv:2606.24934)](https://arxiv.org/abs/2606.24934)
- [GPU Fingerprinting for Location Verification (arXiv:2605.01930)](https://arxiv.org/pdf/2605.01930)
- [CVE-2026-53923 — vLLM GGUF dequantize advisory](https://advisories.gitlab.com/pypi/vllm/CVE-2026-53923/)
- [Intra-handshake.fail / CVE-2026-33697 — formal proof repo](https://github.com/CCC-Attestation/formal-spec-KBS)
- [The Register — Confidential computing's trust mechanism is broken](https://www.theregister.com/security/2026/07/04/confidential-computings-trust-mechanism-is-broken-the-fix-may-not-exist/5266056)
- [Barrack AI — NVIDIA's CUDA Never Clears GPU Memory (decade-of-research compilation)](https://blog.barrack.ai/nvidia-cuda-never-clears-gpu-memory/)
- [Blueprint, Bootstrap, and Bridge: A Security Look at NVIDIA GPU Confidential Computing (arXiv:2507.02770)](https://arxiv.org/abs/2507.02770)
- [LeftoverLocals (arXiv:2401.16603)](https://arxiv.org/abs/2401.16603)
- [NVIDIA nvtrust](https://github.com/NVIDIA/nvtrust) · [NVIDIA Compute Sanitizer](https://developer.nvidia.com/compute-sanitizer) · [Azure az-cgpu-onboarding](https://github.com/Azure/az-cgpu-onboarding)
- [fwd:cloudsec NA 2026 schedule](https://pretalx.com/fwd-cloudsec-2026/schedule/) · [fwd:cloudsec EU 2026 CFP](https://fwdcloudsec.org/conference/europe/cfp.html)

*Note on the Barrack AI source: Barrack AI sells GPU hosting, and the post recommends single-tenant
instances — which they sell. Treated as a bibliography, not an authority; every claim drawn from it
above traces to a primary source (NVIDIA docs, named CVEs, named peer-reviewed papers) that should be
independently confirmed before it enters the paper.*
