# ADR-001 — Implementation language for the probe agent

- **Status:** Accepted
- **Date:** 2026-07-29
- **Charter reference:** §14, §23 immediate task 4
- **Deciders:** maintainer

## Context

The charter requires an architecture decision on implementation language
before any provider testing (§14):

> The original charter suggested a Python-first prototype (CuPy/PyTorch/PyCUDA)
> for speed to first data point. That's fine for local positive/negative-control
> validation in weeks 3–4 — but the cloud-facing agent that touches unknown
> memory should move to the disciplined stack before any provider testing, and
> the safety-critical buffer handling must live behind the enforced-safe layer
> regardless of language. Decide and record this trade-off explicitly.

Two forces pull in opposite directions.

**Toward Python.** The research questions are not yet stable. Control design
(§11 Phase 1) is exploratory: we do not know in advance which positive controls
will reliably reproduce allocator reuse on Ampere, nor how many variants of the
partial-write control we will need. Iteration speed dominates in that phase.
CuPy and PyCUDA also give direct access to the framework-allocator behaviour
that §9.4 exists to measure — PyTorch's caching allocator is a *subject* of the
research, not merely a tool.

**Toward C++/CUDA + Rust.** The cloud-facing agent handles memory belonging to
someone else. Python's memory model makes "this buffer is definitely gone" hard
to assert: `bytearray` contents can be copied by the interpreter, garbage
collection timing is not controlled, and there is no way to guarantee an
overwrite is not optimised away or that no intermediate copy was made. For a
project whose central ethical claim is *we never retained unknown memory*,
that is uncomfortable.

## Decision

**Python-first local prototype; native memory-touching path before any provider
testing.** The current source contains the C++/CUDA memory slice and retains
the Python controller for policy, ownership, budget, signing, and orchestration.
The native binary must pass the pinned-image conformance gate before provider
use.

1. **Weeks 3–4, local lab only.** Python + CuPy / PyCUDA / PyTorch. Control
   validation, canary logic, aggregation, signing, statistics. Runs only
   against the maintainer's own RTX 3050. No provider contact.
2. **Before the first provider run.** Use the C++/CUDA slice for the probe path
   that touches unknown memory. The Python controller remains acceptable for
   policy and orchestration because it does not touch unknown memory.
3. **Regardless of language and from day one.** All buffer handling passes
   through the single enforced-safe layer, and the §16 CI safety tests gate
   every change.

Point 3 is what makes point 1 acceptable. The safe layer is exercised by the
current Python test suite and mutation battery; the native conformance gate is
still required before the native path is used against a provider. See the
dated result in [`docs/STATUS.md`](../STATUS.md) rather than copying an old
test count into this ADR.

## Consequences

### Accepted costs

- **Throwaway code.** The Python probe agent will be rewritten. Estimated waste:
  1–2 weeks. Judged worth it against the risk of freezing control design
  prematurely in a language that is slow to iterate in.
- **Two implementations of the safe layer.** The Python one remains the
  contract reference, and the native implementation must pass the
  cross-language conformance vectors. Divergence between them is a real risk and needs a
  cross-language conformance suite at port time.
- **Weaker memory-hygiene guarantees during Phase 1.** Acceptable *only*
  because Phase 1 touches no provider infrastructure. This is the load-bearing
  condition and it must not erode.

### Rejected alternatives

**C++/CUDA + Rust from day one.** Strongest memory guarantees, no port, no
throwaway. Rejected because control design is genuinely exploratory right now
and native iteration cost would likely push first-data-point out by 3–4 weeks.
Reconsider immediately if Phase 1 converges faster than expected.

**C++/CUDA probe + Python controller, permanently.** Skips Rust/Go, keeps the
safety-critical path native throughout. This is the most likely *fallback* if
the Rust orchestration layer proves to be scope creep — the orchestration layer
does not touch unknown memory, so its language matters much less. Worth
revisiting at v0.2.

## The tripwire

This decision has a hard boundary, and it is easy to erode by accident, so it
is stated as an explicit gate:

> **No Python probe agent may be run against any provider-owned
> infrastructure.** The port is a precondition for Phase 2, not a follow-up
> task.

If Phase 2 arrives and the port is not done, the correct action is to delay
Phase 2 — not to run the Python agent "just for the pilot."

## Revisit when

- Phase 1 controls stabilise (then: consider porting early)
- The Rust orchestration layer starts looking like scope creep (then: fall back
  to C++/CUDA probe + Python controller)
- Before Phase 2 begins, unconditionally
