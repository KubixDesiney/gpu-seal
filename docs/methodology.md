# Methodology

**Charter:** §9 (probe families), §11 (phases), §12 (statistics), §18 (metrics)

How a GPU-SEAL measurement is taken, in the order it is taken, and what each
step is allowed to conclude.

---

## The order is the method

1. **§9.1 Environment inventory.** Runs first. Everything downstream is
   interpreted through it. Claims (what was advertised) are recorded
   separately from measurements (what was observed), because collapsing them
   makes §13.3 and §13.5 unanswerable.
2. **§9.7 Allocation-model classification.** Runs *before* any memory result is
   interpreted. NVIDIA's GPU Operator documentation states that time-slicing
   provides no memory or fault isolation; the same canary outcome therefore
   means opposite things under MIG and under a time-slice.
3. **§9.4 Detection-capability control.** Proves the harness can find a marker
   it planted. If this fails, nothing else measured on that platform means
   anything.
4. **§9.3 / §9.2 / §9.12 measurements.** Read-before-write, always.
5. **§9.6 exposure inventory, §9.8 topology, §9.9 location, §9.10 attestation.**
6. **§13 report card.** Graded last, from evidence, with the gates applied.

---

## Why §9.4 is the positive control and §9.3 is not

This was learned on hardware, not from the design.

§9.3 goes to the raw CUDA runtime API on purpose, so a recovered canary says
something about the **driver**. On the RTX 3050 under WSL2/WDDM the driver
zeroes memory on free — confirmed by `instrument_check.py`, where the
write/read path passed 16/16 with nothing freed in between, and the
free/realloc path recovered nothing. So §9.3's own reuse cycle can *never*
produce a positive control on that platform.

Using it as one was a category error: a platform that sanitises correctly
fails §9.3's reuse cycle **by design**.

§9.4 supplies the control instead. It allocates through a caching allocator
(`cupy.cuda.MemoryPool`) which never calls `cudaFree`, so the driver is never
told the memory was released and has no opportunity to scrub it. A canary
recovered there proves detection capability independent of driver behaviour.

**The two produce numerically identical evidence.** Only the measurement path
separates a working control from an accusation, which is why
`MeasurementPath` gates every §13.1 grade *before* the D branch and defaults to
`unknown`.

See [Finding 001](findings/2026-07-31-rtx3050-baseline.md).

---

## Controls, per CHARTER.md §11

**Positive** (marker *should* survive): same-process allocator reuse;
deliberately uninitialised output buffer; controlled framework-cache reuse; a
kernel that leaves part of a buffer untouched (the CVE-2026-53923 class).

**Negative** (marker should *not* survive): explicit zeroisation; verified-reset
new process; buffer overwrite; freshly-initialised allocation; clean container
boundary.

Without positive controls you cannot prove a negative cloud result means the
probe could have detected a leak.

**Independent validation:** NVIDIA Compute Sanitizer `--tool initcheck` detects
uninitialised global memory reads after `cudaMalloc`. Cross-checking the
positive controls with a vendor tool strengthens the methodology section
considerably. *Status: not yet run — Compute Sanitizer ships with the CUDA
toolkit, which is not installed on the lab machine (the probe path uses CuPy's
bundled runtime libraries instead). Open.*

---

## Statistics — §12

Every conclusion reports sample / usable / positive / errored / excluded
counts, carried together in `ObservationCounts` so a rate cannot be quoted
without its denominator.

Proportions use the **Wilson** interval, not the normal approximation. The
headline results here are proportions near zero over small samples — zero
canaries in ten cycles — where the normal approximation returns the degenerate
interval [0, 0]. Claiming a 95% CI of exactly zero from ten observations is the
precise overclaim §12 exists to prevent. Wilson gives about [0, 0.28].

`rate` returns `None`, not `0.0`, when no cycle was usable. A run where
everything errored has an *unknown* positive rate; reporting it as zero would
turn a failed measurement into a clean result.

Bootstrap intervals are seeded. An interval that moves between runs of the same
analysis is not a reproducible result.

---

## Instrument reproduction — §9.8

Success criterion is **fidelity, not novelty**. Alpay & Alpay (2026) published
the topology certificate; GPU-SEAL consumes it.

Reproduction status on the local RTX 3050 (Ampere GA107, CC 8.6):

| Target | Published | Reproduced here |
|---|---|---|
| Physical SM labelling via `%smid` | yes | **yes — 16 SMs resolved** |
| Median temporal jitter | 0.09 cycles (RTX 5090, 6 h full load) | **0.047 – 0.096 cycles**, n=3 runs (4 repetitions each, idle) |
| Stable per-SM structure | yes | yes — a repeatable alternating pattern across SM indices |
| Same-device shape distance | — | 0.0004 – 0.0006 mean absolute, row-normalised |
| Cross-*product* separation | 100% LOO across Blackwell dies | not testable — one GPU available |
| Same-*model* die separation | **explicitly deferred** | **open — contribution D5** |

**Report the range, not the best run.** Three short runs gave 0.047, 0.061,
and 0.096 cycles — a factor of two, on an idle machine, within one hour. The
first draft of this table quoted 0.047 alone, which is the most favourable
observation presented as though it were the result: exactly the overinterpretation
of a single sample that §12 exists to prevent, committed in the document that
describes §12.

Nor is the range directly comparable to the published figure. Theirs is a
6-hour full-load run on a different architecture; ours is four repetitions on
an idle laptop GPU whose clocks are free to move. The honest statement is
"the same order of magnitude, on this hardware, under these conditions" — and
the spread is itself a result: it says a single short certificate on a
consumer part is not a precision instrument, and that §9.8b will need many
repetitions per instance rather than one.

Comparison is on **row-normalised shape**, not absolute latency, matching the
source paper's shape-only classification. Absolute cycles track clock speed and
thermal state; comparing them would separate a warm chip from a cold one rather
than one die from another.

---

## What a result may say

| Observation | May be reported as | May **not** be reported as |
|---|---|---|
| No canary recovered, same-model pair, D5 open | inconclusive | evidence of sanitisation |
| No canary recovered, same-device evidence valid | useful evidence, not absolute proof | proof of sanitisation |
| Canary recovered via §9.4 pool | detection capability confirmed | provider residue |
| Canary recovered via §9.3 driver path | a finding; §7.5 applies | a public accusation |
| Topology matches advertised class | consistent with the class | confirmation of the model |
| Two certificates agree | "consistent with the same physical accelerator under the project's classifier" | "proved both allocations used the same physical GPU" |
| RTT places us near the claimed region | consistent at metropolitan-to-continental resolution | a datacentre, campus, or rack |

---

## Known methodological gaps

Stated here rather than discovered by a reviewer.

- **Compute Sanitizer cross-validation not yet run.** Requires the CUDA
  toolkit on the lab machine.
- **Scheduler duration enforcement is post-hoc.** A run that overruns is marked
  aborted and excluded; it is not pre-emptively killed. Interrupting a probe
  mid-measurement risks leaving a device allocation alive and a canary planted
  with nothing to read it back. Bounding cost is the operator's
  automatic-shutdown control (§20). Pre-emptive cancellation is a probe-layer
  change and is open.
- **Allocation classifier is uncalibrated.** Weights are documented-behaviour
  priors, not fitted to ground truth; §18 requires accuracy against ground
  truth on researcher-configured hardware, which needs MIG-capable silicon.
  Confidences rank hypotheses; they are not probabilities, and every result
  says so.
- **§9.6 omits host-management socket inventory** by design — see
  `probes/device_exposure.py` for why the census is deliberately one row poorer.
- **Neighbour-visibility grade D is unreachable from a single instance.** It
  needs a controlled two-instance experiment, which is Phase 2 work.
