# Measurement pre-registration

**Registered:** 2026-08-01 · **Applies from:** GPU-SEAL v0.1.0.dev0 · **Charter:** §12, §19

Everything in this document is fixed **before** any named-provider data is
collected. That is the entire point. CHARTER.md §12 requires scoring to be
pre-registered before named-provider results are examined, and §19 names
"expected-negative misreading" as a specific risk: an unregistered negative
looks like a fishing expedition that came up empty.

Changing anything here after Phase 2 data exists requires a dated amendment
below, stating what changed and why. Silent edits defeat the mechanism.

---

## 1. Hypotheses, registered in advance

### H1 — §9.2 local / shared memory is **expected negative** on NVIDIA

NVIDIA GPUs were **confirmed not affected** by LeftoverLocals (CVE-2023-4969);
the affected vendors were AMD, Apple, Qualcomm, and Imagination. Trail of Bits
noted NVIDIA had likely already addressed these patterns following earlier
academic work.

We therefore expect to recover **no** owned marker from kernel-shared memory
across any boundary, on any NVIDIA product, at any provider.

- **If confirmed:** report as a registered negative with working positive
  controls. This is a publishable result — the literature does not currently
  contain a cross-provider negative for this class.
- **If contradicted:** it is a significant finding, and it must **not** be
  reported as "LeftoverLocals". §9.2 requires classifying the affected region
  and boundary precisely before naming anything. §7.5 disclosure applies before
  it leaves the machine.
- **Invalidation:** the positive control (plant and read within one launch
  sequence) must pass. A negative without it is not a result.

### H2 — §9.3 device-global residue is **not predicted either way**

No prediction is registered. This is the measurement the project exists to
take, and registering an expectation for it would be registering a conclusion.

What *is* registered is the interpretation rule, below in §3.

### H3 — §9.12 MIG temporal isolation is **not predicted either way**

NVIDIA documents runtime isolation and is silent on destroy/recreate scrubbing.
Silence is not a prediction. Registered instead: the six boundaries are
reported **separately** and never pooled, because MIG teardown, GPU-wide reset,
and driver reload are three different mechanisms.

### H4 — §9.8b same-model die separation may **fail**, and that is a result

Registered before any data: a failure to separate same-model dies at tenant
privilege is a publishable negative that bounds the research area, not a failed
experiment to be retried until it works. See §2 for the thresholds.

---

## 2. Pre-registered thresholds

Fixed now so they cannot be chosen after seeing the data.

| Quantity | Threshold | Where enforced |
|---|---|---|
| §9.8b leave-one-out accuracy for D5 validation | **≥ 0.95** | `analysis.separability.VALIDATION_ACCURACY_THRESHOLD` |
| §9.8b AUC for D5 validation | **≥ 0.98** | `analysis.separability.VALIDATION_AUC_THRESHOLD` |
| Minimum cycles before a §13.1 hygiene grade | **10** | `grade_memory_hygiene(minimum_cycles=10)` |
| Topology shape distance for "probably consistent" | **≤ 0.02** mean absolute, row-normalised | `compare_certificates(threshold=0.02)` |
| Scheduling-stall ratio suggesting time-slicing | **≥ 4.0** tail-to-median | `allocation_model.SCHEDULING_STALL_RATIO` |
| Minimum location measurements before grade D | **3** | `grade_location_claim` |
| Provider policy review validity | **365 days** | `policy_matrix.REVIEW_VALIDITY_DAYS` |
| Disclosure window before publication | **90 + 30 days** | `controller.disclosure` |
| Confidence level for all reported intervals | **95%**, Wilson for proportions | `analysis.statistics` |

---

## 3. Interpretation rules, fixed in advance

These are the rules that decide what a number *means*, and they are the ones
most vulnerable to being adjusted once a result is in hand.

1. **Measurement path gates every §13.1 grade.** A canary recovered through a
   caching allocator (§9.4) is the detection-capability control succeeding, not
   a provider failing. Only `driver_direct` measurements (§9.3) are gradeable.
   Enforced in `MeasurementPath`, defaulting to `unknown` so a forgotten path
   yields U rather than an accusation.

2. **Grade A on §13.1 requires valid same-device evidence.** Two allocations
   sharing an advertised model cap at **U** until D5 lands. A clean result on a
   possibly-different chip is not evidence of sanitisation.

3. **A non-zero buffer does not prove cross-tenant residue.** Uninitialised
   memory is uninitialised. Only an authenticated owned canary counts.

4. **An all-zero buffer does not prove sanitisation.** It may be a fresh page,
   a zeroing runtime, or luck.

5. **The allocation model is classified before any memory result is
   interpreted.** The same canary outcome means different things under MIG and
   under time-slicing.

6. **Observation is reported separately from interpretation**, in those words,
   in every result (§12).

7. **Hardware and location claims are reported as "consistent with", never as
   confirmation.** Both are instrument-dependent and both cite the instrument
   and its bounds with every grade.

8. **Exclusions are declared with a reason.** A cycle that errored is excluded
   from statistics and its reason is recorded; it is never silently dropped and
   never counted as a clean observation.

---

## 4. Exclusion criteria, fixed in advance

A measurement cycle is **excluded** when:

- the probe raised an error before producing an observation (`error_code` set);
- the run exceeded `max_duration_s` (§16 test 11);
- the backend was simulated (`backend_is_real: false`);
- the container profile was not `pinned` — the run is not reproducible;
- the §9.12 record has no `teardown_performed` statement;
- topology certificates being compared carry different kernel hashes.

A run carrying `sensitive_observation` is **not** excluded — it is retained,
blocked from automatic publication, and routed to manual disclosure review.

---

## 5. Sample sizes

Phase 2 pilot, per CHARTER.md §11: 4 providers × 1 product × 1 region ×
**10 allocation cycles** × 5 probe families. Phase 3 expands to ~20 cycles for
core configurations.

Ten cycles is small, and the Wilson interval says so: zero positives in ten
cycles gives a 95% interval of approximately **[0, 0.28]**. That interval, not
the point estimate, is what gets reported. A pilot cannot rule out a 1-in-20
effect and will not be written as though it can.

---

## 6. What would falsify the project's own claims

Registered so it cannot be quietly reframed later:

- If the §9.4 detection-capability control fails on a platform, **every** §9.3
  result from that platform is uninterpretable and must be reported as such.
- If the negative control produces a false canary match, all results are void
  until the cause is explained.
- If topology jitter on a rented instance is so large that same-device
  comparison is meaningless, §9.5 results from that provider are `inconclusive`
  regardless of canary outcome.
- If the allocation-model classifier's `undocumented` rate is high, that is
  reported as a limitation of the classifier as well as a finding about the
  market — not only the latter.

---

## Amendments

*None. Amendments are appended here with a date and a reason.*
