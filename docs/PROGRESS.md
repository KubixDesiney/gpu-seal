# Progress checklist

**Assessed:** 2026-08-01 · **Version:** 0.1.0.dev0 · **Phase:** 0–1 complete, 2 blocked on policy

Graded per category with no composite score, per [`CHARTER.md`](../CHARTER.md) §13.
**U means unproven, not failing** — it is the grade for a claim the evidence
cannot yet support. That distinction is the whole point of the rubric, and it
applies to the project as much as to a provider.

---

## Assurance grades

| Category | Grade | Basis |
|---|:---:|---|
| Ethics enforcement | **A** | Canary-only, no-render, no-retain locked in code *and* CI. Every rule in `ETHICS.md` names its enforcement point. §16 rules 11, 13, 14 now have a runtime enforcer, not just a constant. |
| Test rigour | **A** | 289 tests, and a working negative control: 36 injected violations, 36 detected. The battery now runs `tests/unit` as well as `tests/safety`, because several safety properties assert there. |
| Research grounding | **A** | Prior art swept, incumbent identified, delta narrowed honestly, one fabricated citation caught and corrected. |
| Reproducibility | **A** | Signed schema-validated bundles, and the lock file now carries **real hashes for 17 packages** resolved against the container's own platform. The pinned image is the only profile that can produce publishable evidence, and it now builds. |
| Probe coverage | **A** | **13 of 13 families implemented.** Seven produce evidence on the local RTX 3050; six refuse on hardware that cannot support them, which is the design working. |
| Hardware validation | **A** | Rewired battery re-run on the RTX 3050: §9.4 control 10/10, negative control clean, §9.3 measurement 0/10, and the §9.4 records now correctly stamped `framework_allocator_reuse`. The topology instrument reproduces on silicon — 16 physical SMs, median jitter **0.047–0.096 cycles over three runs** (published baseline 0.09, measured on different hardware under sustained load, so the comparison is order-of-magnitude only). |
| Provider readiness | **U** | Policy matrix has structure, procedure, schema, four pilot slots, and a CI gate that checks *completeness* — but **no provider has been reviewed**, so the runtime matrix is empty and everything is refused. Correct state; not a finished one. |

---

## Roadmap — CHARTER.md §17

- [x] **Wk 1–2 Foundation** — repo, threat model, ethics + disclosure policy, schemas, ADR-001/002/003, prior-art sweep
- [x] **Wk 3–4 Local probe core** — built, run on silicon, cause isolated, §9.4 built and wired in as the positive control. Exit criterion **met on real hardware**, and the mislabelling that quarantined the first two GPU bundles is fixed and re-run clean.
- [x] **Wk 5–6 Exposure & container tests** — §9.1 inventory and §9.6 device/namespace exposure built and running; NVML binding added; container profile now stamped by the pinned image.
- [x] **Wk 7–8 Topology instrument + allocation classifier** — §9.8 reproduced on the 3050 at full fidelity (16 physical SMs via `%smid`); §9.7 classifier built with calibrated-confidence reporting; §9.8b separability evaluator built and tested against synthetic ground truth.
- [ ] **Wk 9–10 Provider pilot** — *blocked on the ethics/policy gate and on ADR-001's language port. Both are stated blockers, not oversights.*
- [~] **Wk 11 Attestation module** — collector, the ten §9.10 fields, and the §9.11 channel-binding assessment are **built and tested**; cannot be *exercised* without H100-class CC silicon.
- [~] **Wk 12 Release + arXiv preprint** — tooling, schemas, docs, and a release gate are in place. Author metadata is complete; release of a measurement study remains blocked on provider data and the ethics/policy gates.

---

## Built

- [x] Enforced-safe layer — `SafeBuffer`, allowlisted egress, automatic safety stop
- [x] Authenticated canary format — 128-byte, keyed BLAKE2b MAC ([ADR-002](adr/002-canary-wire-format.md))
- [x] **Canary search rewritten** — was O(canaries ever minted × buffer); now scans once per boundary group. Proven equivalent to the naive scan by a randomised test against the reference implementation.
- [x] Signed evidence bundles — Ed25519 + SHA-256, JSON Schema validated, now carrying `observations` and `report_card`
- [x] **Second egress door** — `ObservationRecord` for probes that describe the environment rather than read unknown memory, with its own §10 allowlist and a refusal on unhashed identifiers
- [x] **Full §13 report card** — all five graded categories plus the §13.6 field report, with no composite score and no code path that emits one
- [x] CUDA backends — raw runtime, pooled caching allocator, simulated, each declaring its own `measurement_path` ([ADR-003](adr/003-measurement-path-declared-by-the-backend.md))
- [x] **Controller** — provider allowlist, ownership attestation, duration ceiling, budget reservation, evidence store, and the §7.5 disclosure state machine
- [x] **Statistics** — Wilson intervals, seeded bootstrap, and `ObservationCounts` so a rate cannot be quoted without its denominator
- [x] Reproducible container — pinned profile now stamps `container_profile=pinned` and has a real hash-locked dependency set
- [x] Phase 1 control battery and a Phase 2 dress rehearsal, both with pass/fail verdicts and non-zero exit
- [x] 17/17 §16 safety rules present; 36-case mutation battery proves each detectable
- [x] CI: safety matrix, mutation batches, lint, provider-policy completeness gate, release-readiness gate

## Probe families — 13 of 13 implemented

**Producing evidence on the local RTX 3050:**

- [x] §9.1 Environment inventory — four charter blocks, identifiers hashed at collection
- [x] §9.2 Local/shared memory — real shared-memory kernels, pre-registered expected-negative
- [x] §9.3 Device-global VRAM read-before-write
- [x] §9.4 Framework allocator behaviour — the detection-capability control
- [x] §9.6 Device & namespace exposure inventory — passive, five-way classification
- [x] §9.7 Allocation-model classifier — ten classes, ranked hypotheses, refuses near-ties
- [x] §9.8 Topology fingerprint — **reproduced on silicon**, 16 SMs, 0.047 cycles jitter

**Implemented; refuse on hardware that cannot support them:**

- [x] §9.5 Self-vs-self sequential canary — needs two rentals; gated on D5
- [x] §9.8b Same-model separability evaluator — needs N instances of one model
- [x] §9.9 Coarse location consistency — needs an instance with a region claim
- [x] §9.10 Attestation + §9.11 channel binding — need H100-class CC silicon
- [x] §9.12 MIG temporal isolation — needs A100/H100-class silicon

`MigTemporalProbe` raising `MigUnavailable` on a consumer card is the design
working, not a gap. A §9.12 record produced on non-MIG hardware would be a
§9.3 record wearing the wrong name — the exact class of error that quarantined
two evidence bundles.

## Contributions — CHARTER.md §2.1

| | Contribution | State |
|---|---|---|
| D1 | Cross-provider memory sanitisation | Probe built and validated on silicon; no provider data |
| D2 | MIG temporal isolation | **Built**, six boundaries reported separately, never pooled. Needs A100/H100 |
| D3 | Allocation-model classifier | **Built**, ten classes, ranked. Uncalibrated — needs MIG hardware for ground truth |
| D4 | Device exposure census | **Built**. Needs providers to census |
| D5 | Same-model die separation | **Evaluator built**, thresholds pre-registered, tested against synthetic ground truth. Needs N rented instances. Gate enforced in code |
| D6 | Longitudinal signed evidence | Bundle format and store built; needs time and providers |
| D7 | EU sovereignty framing | **In code** — §9.9 bands on jurisdiction, not just distance |

---

> Outstanding work, ordered by what unblocks the project, is in
> [`REMAINING.md`](REMAINING.md).

## Gates before Phase 2

- [x] ~~**Run the controls on the RTX 3050.**~~ Done. See [Finding 001](findings/2026-07-31-rtx3050-baseline.md).
- [x] ~~**Run `instrument_check.py` on the 3050.**~~ Done. The write path is proven sound; the driver genuinely zeroes on free.
- [x] ~~**Build §9.4 framework-allocator control.**~~ Done, 10/10.
- [x] ~~**Wire §9.4 into the Phase 1 battery as the positive control.**~~ Done.
- [x] ~~**Re-run the battery on the 3050 after the probe-identity fix.**~~ **Done** — `out/run_20260801T004446Z.result.json` carries 10 §9.4 records correctly stamped `framework_allocator_reuse` / `framework_pooled` and 30 §9.3 records `driver_direct` with no recovery. The two quarantined bundles are superseded, and retained rather than deleted.
- [x] ~~**Generate real lock file hashes.**~~ **Done** — 17 packages, transitive closure, resolved against `manylinux2014_x86_64` / Python 3.10 so the hashes match the wheels the *image* installs. `lab/regenerate-lock.py` regenerates them.
- [ ] **Same-model die separation (D5).** The evaluator, its metrics, and its pre-registered thresholds exist and are tested. **Needs N rented instances of one advertised model.** §13.1 grade A stays capped at U until then — enforced by CI, not by anyone remembering.
- [ ] **Provider policy matrix.** Structure, schema, procedure, four pilot slots, and a CI gate that checks completeness rather than directory existence — all in place. **No provider has been reviewed**, because that means reading four providers' actual terms and, where they are unclear, writing to them and waiting. Operator work with legal judgement in it; inventing a classification would be worse than having none.
- [ ] **Port the probe agent off Python.** [ADR-001](adr/001-implementation-language.md) makes this a precondition for Phase 2. Not started. It is a rewrite of the safety-critical layer that must then be re-validated against the same 36-mutation battery, and it needs a C++/CUDA and Rust-or-Go toolchain that is not on the lab machine. **If Phase 2 arrives first, delay Phase 2.**
- [ ] **Ethics review sign-off.** Measurement pre-registration is [written and dated](pre-registration.md), including the §9.2 expected-negative and every scoring threshold. Peer/supervisor sign-off is outstanding.
- [x] **`CITATION.cff` author metadata.** Aziz Bargaoui, Student, ORCID `0009-0005-0826-0450`.

---

## Known issues

| Issue | Impact | Where |
|---|---|---|
| §9.3's reuse cycle recovers nothing on this platform | **Resolved, not a defect.** The driver zeroes on free; §9.4 supplies the control and §9.3 is reported as a measurement | [Finding 001](findings/2026-07-31-rtx3050-baseline.md) |
| ~~Canary search is O(canaries ever minted)~~ | **Fixed.** One scan per boundary group; equivalence to the naive scan asserted by a randomised test, and a mutation pins it | `safety/canary.py::search` |
| ~~§16 rules 11, 13, 14 have no runtime enforcement~~ | **Fixed.** `gpu_seal.controller` enforces all three, with four mutations proving each detectable | `controller/` |
| ~~`requirements-lock.txt` is placeholder~~ | **Fixed.** 17 packages hash-pinned for the container's platform | `infrastructure/containers/` |
| ~~Publication gate only string-matches `dev-unpinned`~~ | **Fixed, and the policy call is made:** the gate is now an allowlist, and `unspecified` is *not* on it. A run that cannot name its image cannot supply the container digest §10 requires. Every local run is therefore correctly unpublishable | `evidence/result.py` |
| `CITATION.cff` author fields empty | **Fixed.** Aziz Bargaoui and ORCID are recorded; the release gate now checks the remaining blockers | `CITATION.cff` |
| Refs 7–12 cited from a secondary compilation | Read each in the original before it enters the paper; the compiler is a GPU host with a commercial interest in the conclusion | [`prior-art.md`](prior-art.md) |
| Allocation classifier is uncalibrated | Confidences rank hypotheses; they are not probabilities. Stated in every bundle that carries a classification | `probes/allocation_model.py` |
| Compute Sanitizer cross-validation not run | §9.3 asks for `--tool initcheck` confirmation of the positive controls. Needs the CUDA toolkit, which is not installed — the probe path uses CuPy's bundled runtime libraries | [`methodology.md`](methodology.md) |
| §9.6 omits host-management socket inventory | One row poorer by design: inventorying those interfaces means naming their paths in probe source, which §16 test 17 refuses. Recorded as a `not_testable` with the reason, not silently dropped | `probes/device_exposure.py` |
| Scheduler duration enforcement is post-hoc | An overrunning run is excluded, not pre-emptively killed. Interrupting a probe mid-measurement risks a live allocation and a planted canary with nothing to read it back | `controller/scheduler.py` |

---

## Bugs worth remembering

**The entropy safety stop was armed unconditionally.** Found by running the
Phase 1 battery rather than by reading the code — it produced five safety stops
on the baseline measurement, which would have made GPU-SEAL unable to take its
own primary measurement. NVIDIA documents that `cudaMalloc` does not clear
memory, so high-entropy content in a fresh allocation is the *expected*
phenomenon, not an incident. Now split into two independently-armed triggers.

**§9.4 control data could be graded as a provider failure.** Promoting §9.4
onto the critical path created a hazard that did not previously exist: feeding
the framework-allocator control's counts into the §13.1 grader returned grade
**D — "pending private disclosure and provider response"**. The pool never
called `cudaFree`, so recovering the canary was the control succeeding. §9.3
and §9.4 produce numerically identical evidence and only the measurement path
separates them. Now [ADR-003](adr/003-measurement-path-declared-by-the-backend.md).

**`run_phase1.py` signed and wrote the bundle before checking whether it could
be published.** `automatic_publication_allowed` is baked into the signed,
hashed payload at `sign()` time, so clearing afterwards changed an in-memory
flag and nothing on disk. Every bundle the script had written carried
`false` regardless of what the console said. Fixed by reordering — and now
structurally prevented: `EvidenceStore.write` is the supported path, does the
steps in the right order, and reads the file back to verify what actually
landed.

**A citation was fabricated.** The first prior-art draft attributed
arXiv:2606.24934 to "Miller et al." — an invented name. The real authors are
Faruk Alpay and Taylan Alpay. `CHARTER.md` §23 now carries a standing rule
against citing by unverified author name. GPU-SEAL's author metadata is now
filled from Aziz Bargaoui's verified details rather than guessed from a git
handle.

**The lint gate had been red for some time and nobody noticed.** CI runs
`ruff check probe tests` with an unpinned `ruff>=0.5`. Modern ruff enforces
PEP 585/604 annotations at `target-version = "py310"`, and the whole codebase
used `Dict`/`List`/`Optional` — 227 findings across every module, including
files nobody had touched in weeks. A required job that fails on a dependency
upgrade is a job people learn to ignore. Fixed by modernising the annotations
and pinning the deliberate exemptions in `pyproject.toml` with reasons.

**Identifying a recovered canary by its allocation id looked obviously right
and was wrong.** The rewritten search indexed anchor occurrences and then
looked the owner up by the allocation id at offset 32 — which works until a
marker is truncated *inside* that field, at which point there is no id to read
and the surviving prefix is under-reported. Caught within minutes by the
randomised equivalence test against the original implementation, which is the
argument for writing that test before trusting the optimisation.

**The mutation battery reported a false MISSED on a non-UTF-8 host.** Its
Python snippets used `read_text()` with the platform default encoding; the
mutations anchored on comment lines containing an em-dash failed to find their
anchor and reported the suite as having missed a violation it would have
caught. A negative control that can produce a false alarm undermines the thing
it exists to prove. All 60 file operations in the battery are now
encoding-explicit.

**The first draft of this file quoted the best of three jitter measurements.**
Three short topology runs on the same idle machine within an hour gave 0.047,
0.061, and 0.096 cycles. The reproduction was written up as "0.047 cycles,
below the published 0.09 baseline" — the most favourable observation, stated
as though it were the result, in a project whose §12 exists to stop exactly
that. Now reported as a range with its sample size. The spread is itself
useful: a single short certificate on a consumer part is not a precision
instrument, and §9.8b will need many repetitions per instance rather than one.

**A safety test had been flaky since the day it was written.**
`test_canary_contains_no_readable_text` minted 50 canaries and asserted no
12-byte printable-ASCII run in any of them. Printable bytes are ~37% of the
value space, so over ~5,450 candidate positions that assertion fails in about
**3% of runs** — and it duly failed once, mid-way through routine verification,
having passed dozens of times. A flaky safety test is worse than no safety
test: people learn to re-run it, and then they learn to re-run the one that
was telling the truth. Replaced with a deterministic structural assertion —
past the magic, the layout is UUIDs, an `os.urandom` nonce, reserved zeros,
and a MAC, with nowhere for author-chosen text to live — plus a run-length
smoke test at a threshold whose tail probability is written down.

**The publication-gate test passed with the gate completely broken.** The
mutation battery found it: `test_unpinned_container_probe_cannot_be_published`
used a *simulated* record, and the simulation guard fires first, so the test
stayed green with the container check removed. The guard had looked tested for
weeks. Now isolated by
`test_a_real_record_outside_a_pinned_container_cannot_be_published`, which
parametrises over `dev-unpinned`, `unspecified`, and `release`.

---

## Verify any of this yourself

```bash
pytest tests -q                                   # 289 tests
bash lab/verify-safety-suite.sh                   # 36 injected violations, all must be caught
python3 lab/check-provider-policy.py              # is the Phase 0 gate still enforced?
python3 lab/check-release-readiness.py            # what blocks a public release
python3 lab/local-runner/smoke.py                 # what can this machine actually measure?
python3 lab/local-runner/run_phase1.py --out ./out
python3 lab/local-runner/run_phase2_local.py --out ./out
```
