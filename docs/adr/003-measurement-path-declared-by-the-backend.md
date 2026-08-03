# ADR-003 — The backend declares the measurement path, not the probe

**Status:** accepted · **Date:** 2026-07-31 · **Supersedes:** nothing ·
**Charter:** §9.3, §9.4, §13.1, §16 test 16

## Context

§9.3 (device-global read-before-write) and §9.4 (framework allocator
behaviour) produce **numerically identical evidence**. Both plant an
authenticated owned canary, free the allocation, reallocate, and read before
writing. Both report the same fields: cycles, recoveries, zero fraction,
entropy.

They mean opposite things.

§9.3 allocates through the raw CUDA runtime API. `cudaFree` is called, so the
driver is told the memory was released and *had the opportunity to sanitise
it*. A canary recovered there is a statement about the platform.

§9.4 allocates through a caching allocator (`cupy.cuda.MemoryPool`). `free()`
returns the block to the pool's own free list and `cudaFree` is **never
called**. The driver never learns the memory was released. A canary recovered
there proves the harness can detect a marker it planted — the
detection-capability control §11 requires — and says nothing about the driver,
the provider, or anybody else's data.

This became urgent rather than theoretical when §9.4 was promoted onto the
Phase 1 critical path. Feeding the control's counts into the §13.1 grader
returned grade **D — "pending private disclosure and provider response"**. A
control succeeding had been turned into an accusation against a provider, by a
grader doing exactly what it was told.

Two failures were involved, and they are worth separating:

1. **The grader had no way to tell them apart.** Counts alone cannot.
2. **The records were mislabelled.** `FrameworkAllocatorProbe` composes
   `GlobalMemoryProbe` for the read-before-write mechanics — the right design —
   but inherited its *identity* along with its mechanics. Ten §9.4 control
   records were written into two signed evidence bundles under §9.3's probe
   name. Read literally, those bundles assert that §9.3 recovered canaries in
   10 of 40 cycles: a residue finding that did not happen. Both bundles are
   quarantined; see `out/MISLABELLED-README.md`.

## Decision

**The measurement path is a property of the backend, and the backend declares
it.**

`CudaBackend.measurement_path` is one of `driver_direct`,
`framework_pooled`, or `simulated`. `CupyBackend` declares `driver_direct`;
`PooledCupyBackend` declares `framework_pooled`; `SimulatedBackend` declares
`simulated`. Every probe stamps the backend's declaration into
`driver_metadata` on every record.

`MemoryHygieneEvidence.measurement_path` gates **every** §13.1 grade *before*
the D branch, and defaults to `MeasurementPath.UNKNOWN`.

Composing probes override the identity stamped on the record they produce.
`GlobalMemoryProbe.read_before_write` takes `probe_name` / `probe_version`
arguments for exactly this, and `FrameworkAllocatorProbe` passes its own.

## Rationale

**Why the backend and not the probe.** It is the *allocator* that determines
whether the driver is ever told the memory was released. A probe declaring its
own path is a probe asserting something about a component it does not own —
and a probe pointed at the wrong backend would then assert it confidently. The
backend cannot be wrong about its own allocator.

`FrameworkAllocatorProbe` additionally refuses to construct against a backend
with `pooled = False`, so §9.4 cannot be run against the raw runtime API and
mislabelled as driver-independent.

**Why the default is `unknown` and not `driver_direct`.** Forgetting to state
the path must yield **U** (unproven), never **D** (a provider failed). The
asymmetry is the point: the cost of a spurious U is a weaker paper, and the
cost of a spurious D is an unfounded public accusation against a company.

**Why the gate precedes the D branch.** If it followed, a control run would be
graded D and only *then* explained away. Grading first and filtering afterwards
means the accusation exists, in a signed artefact, before anything catches it.

## Consequences

- §13.1 can only be graded from `driver_direct` measurements. §9.4 data is a
  control and is reported as one.
- Any future backend must declare a path, or its results are ungradeable —
  which is the safe failure.
- Composition remains the right structure for probes that share safety-relevant
  mechanics; inheriting the label was the error, not inheriting the code.
- Four mutations in `lab/verify-safety-suite.sh` pin this: removing the gate,
  moving it below the D branch, flipping the default to `driver_direct`, and
  removing the probe-identity override. Each must turn the suite red.

## Alternatives rejected

**Separate grader entry points per probe family.** Would work until someone
called the wrong one. The gate travels with the evidence instead.

**Never running §9.4 on the critical path.** This was the status quo, and it
left §9.3 with no working positive control on any platform whose driver zeroes
on free — which is the platform the project actually has. Removing the hazard
by removing the control would have removed the ability to interpret any §9.3
result.

**Inferring the path from the probe name.** A string comparison standing in
for a structural property, which fails silently the first time a probe is
renamed.
