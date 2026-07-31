# Progress checklist

**Assessed:** 2026-07-30 · **Version:** 0.1.0.dev0 · **Phase:** 0 complete, 1 built-but-unverified

Graded per category with no composite score, per [`CHARTER.md`](../CHARTER.md) §13.
**U means unproven, not failing** — it is the grade for a claim the evidence
cannot yet support. That distinction is the whole point of the rubric, and it
applies to the project as much as to a provider.

---

## Assurance grades

| Category | Grade | Basis |
|---|:---:|---|
| Ethics enforcement | **A** | Canary-only, no-render, no-retain locked in code *and* CI. Every rule in `ETHICS.md` names its enforcement point. |
| Test rigour | **A** | 131 tests, and a working negative control: 20 injected violations, 20 detected. |
| Research grounding | **A** | Prior art swept, incumbent identified, delta narrowed honestly, one fabricated citation caught and corrected. |
| Reproducibility | **B** | Signed schema-validated bundles and a pinned container — but the lock file is placeholder, so only the dev profile builds. |
| Probe coverage | **D** | 1 of 13 probe families. The right one first, still one. |
| Hardware validation | **U** | Zero GPU runs. Controls pass against a host-side allocator model. |
| Provider readiness | **U** | No policy matrix. CI gate actively blocks provider names in probe source. |

---

## Roadmap — CHARTER.md §17

- [x] **Wk 1–2 Foundation** — repo, threat model, ethics + disclosure policy, schemas, ADR-001/002, prior-art sweep
- [~] **Wk 3–4 Local probe core** — built, controls pass in simulation, **not verified on silicon**
- [ ] **Wk 5–6 Exposure & container tests** — container done; `/dev/nvidia*` and namespace inventory outstanding
- [ ] **Wk 7–8 Topology instrument + allocation classifier**
- [ ] **Wk 9–10 Provider pilot** — *blocked on the ethics/policy gate*
- [ ] **Wk 11 Attestation module**
- [ ] **Wk 12 Release + arXiv preprint**

---

## Built

- [x] Enforced-safe layer — `SafeBuffer`, allowlisted egress, automatic safety stop
- [x] Authenticated canary format — 128-byte, keyed BLAKE2b MAC ([ADR-002](adr/002-canary-wire-format.md))
- [x] Signed evidence bundles — Ed25519 + SHA-256, JSON Schema validated
- [x] Report-card grader with the D5 gate wired in
- [x] CUDA backend abstraction — real (CuPy) + simulated, with a publication guard on the latter
- [x] **Memory Probe B (§9.3)** — read-before-write, positive/negative/baseline modes
- [x] Reproducible container — pinned + dev profiles, WSL2 documented
- [x] Phase 1 control battery with pass/fail verdict and non-zero exit
- [x] 17/17 §16 safety rules present; mutation battery proves each detectable
- [x] CI: safety matrix, mutation batches, lint, Phase 0 provider-name gate

## Probe families — 1 of 13

- [x] §9.3 Device-global VRAM read-before-write
- [~] §9.1 Environment inventory *(partial — `device_info()` only)*
- [ ] §9.2 Local/shared memory · §9.4 Framework allocator · §9.5 Self-vs-self canary
- [ ] §9.6 Device exposure · §9.7 Allocation-model classifier
- [ ] §9.8 Topology instrument · §9.9 Coarse location · §9.11 Channel binding
- [ ] §9.8b Same-model die separation — *needs N rented instances*
- [ ] §9.10 CC attestation — *needs H100+*
- [ ] §9.12 MIG temporal isolation — *needs A100/H100-class*

## Contributions — CHARTER.md §2.1

| | Contribution | State |
|---|---|---|
| D1 | Cross-provider memory sanitisation | Probe built, no provider data |
| D2 | MIG temporal isolation | Not started — needs hardware |
| D3 | Allocation-model classifier | Not started |
| D4 | Device exposure census | Not started |
| D5 | Same-model die separation | Not started; **gate enforced in code** |
| D6 | Longitudinal signed evidence | Not started |
| D7 | EU sovereignty framing | In charter, not in code |

---

## Gates before Phase 2

Each of these is a precondition, not a nice-to-have.

- [ ] **Run the controls on the RTX 3050.** Everything green so far is green
      against a *model* of an allocator, not an allocator. Install the CUDA
      toolkit, then `bash lab/docker/run.sh --gpu phase1`.
- [ ] **Same-model die separation (D5).** §9.5's headline result caps at grade
      U until this lands. Enforced by CI test 16, not by anyone remembering.
- [ ] **Provider policy matrix.** Four providers classified
      `full-probe-ok` / `self-canary-only` / `needs-written-permission` /
      `prohibited` before any named testing. A CI job fails the build while
      `docs/provider-policy-review/` is empty.
- [ ] **Port the probe agent off Python.** [ADR-001](adr/001-implementation-language.md)
      makes this a precondition for Phase 2. If Phase 2 arrives first, delay
      Phase 2 — do not run the Python agent "just for the pilot."
- [ ] **Generate real lock file hashes.** Until then only the dev image builds,
      and its output is not publishable evidence.
- [ ] **Ethics review sign-off** and measurement pre-registration, including
      the §9.2 expected-negative.

---

## Known issues

| Issue | Impact | Where |
|---|---|---|
| Canary search is O(canaries ever minted) | Fine at pilot scale; will bite on a 20-cycle campaign over 64 MiB buffers | `safety/canary.py::search` |
| §16 rules 11, 13, 14 have no runtime enforcement | Policy constants are defined and tested; the controller that would enforce them does not exist | `safety/policy.py` |
| `requirements-lock.txt` is placeholder | Release container cannot build — by design, the refusal is the mechanism working | `infrastructure/containers/` |
| `CITATION.cff` author fields empty | Must be populated before any public release or preprint | `CITATION.cff` |
| Refs 7–12 cited from a secondary compilation | Read each in the original before it enters the paper; the compiler is a GPU host with a commercial interest in the conclusion | [`prior-art.md`](prior-art.md) |

---

## Two bugs worth remembering

**The entropy safety stop was armed unconditionally.** Found by running the
Phase 1 battery rather than by reading the code — it produced five safety stops
on the baseline measurement, which would have made GPU-SEAL unable to take its
own primary measurement. NVIDIA documents that `cudaMalloc` does not clear
memory, so high-entropy content in a fresh allocation is the *expected*
phenomenon, not an incident. Now split into two independently-armed triggers.

**A citation was fabricated.** The first prior-art draft attributed
arXiv:2606.24934 to "Miller et al." — an invented name. The real authors are
Faruk Alpay and Taylan Alpay. `CHARTER.md` §23 now carries a standing rule
against citing by unverified author name.

---

## Verify any of this yourself

```bash
pytest tests -q                       # 131 tests
bash lab/verify-safety-suite.sh       # 20 injected violations, all must be caught
python3 lab/local-runner/smoke.py     # what can this machine actually measure?
```
