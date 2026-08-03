# Scoring

**Charter:** §13 (report card), §16 test 16

Five independently graded categories and one field report. **No composite
score**, ever.

---

## Why there is no total

CHARTER.md §13 opens with "Avoid `62/100`." A single number invites a league
table, and a league table built from five categories with different evidence
strengths is a fiction: it averages a measurement with ten repetitions against
one that could not be taken at all.

`ReportCard` has no `total` property and `to_dict()` emits no numeric
top-level value. Adding one should be treated as an ethics change, not a
feature request.

## U is not F

**U means unproven.** It is the grade for a claim the evidence cannot support —
often because the *method* cannot support it, not because the provider did
anything wrong. A provider can score U on §13.1 while behaving perfectly,
simply because same-model die separation is unsolved.

That distinction is the whole point of the rubric, and it applies to the
project as much as to a provider.

---

## The categories

### §13.1 Memory lifecycle hygiene

| Grade | Condition |
|---|---|
| A | no owned canaries recovered, with repeated valid same-device evidence |
| B | none recovered, some non-zero or ambiguous behaviour |
| C | behaviour varies by boundary, product, or run |
| D | owned canary recovered where sanitisation was expected |
| U | insufficient evidence, or the method cannot support a grade |

Two gates run **before** any of that:

1. **Measurement path.** Only `driver_direct` (§9.3) is gradeable. A canary
   recovered through a caching allocator (§9.4) is the control succeeding.
   Defaults to `unknown`, so forgetting to state the path yields U — never D.
2. **Same-device evidence.** Grade A requires it. Two allocations sharing an
   advertised model cap at **U** until D5 lands, because the topology
   instrument cannot distinguish the same H100 from a different H100. Enforced
   by CI test 16, not by anyone remembering.

### §13.2 Tenant exposure

A: minimal expected exposure · B: extra visibility with plausible
justification · C: ambiguous or excessive metadata exposure · D:
cross-boundary visibility of researcher-controlled neighbour metadata · U: not
testable.

`secure_restriction` counts are **good**. An interface that correctly requires
privilege and refuses us is the system working. A grader that treated every
restricted interface as a missing capability would rank the most locked-down
provider worst.

Grade D requires a controlled two-instance experiment. Inferring it from a bare
process count would convert an ambiguous observation into an accusation.

### §13.3 Hardware claim consistency *(instrument-dependent)*

A: strongly consistent with advertised class · B: mostly consistent, limited
confidence · C: ambiguous · D: repeatedly inconsistent · U: unsupported by the
classifier.

Every grade cites the instrument (Alpay & Alpay 2026, arXiv:2606.24934) and its
limitations, including that it does not separate two dies of one model. A
certificate from a model rather than silicon can never grade hardware.

### §13.4 Location claim consistency *(instrument-dependent)*

Maps directly from the §9.9 consistency band. Every grade restates the
**metropolitan-to-continental** resolution bound.

A single measurement cannot produce grade D — routing, congestion, and traffic
engineering all move on the timescale of one observation, so an apparent
inconsistency from one sample is downgraded to C.

### §13.5 Allocation-model transparency *(new in v2, amendment A6)*

| Grade | Condition |
|---|---|
| A | provider documents the model and measurement agrees |
| B | documented, measurement ambiguous |
| C | undocumented but inferable from inside the job |
| D | documented claim contradicted by measurement |
| U | not classifiable |

C is the grade that names the real commercial problem: a customer sold a
"fractional H100" cannot learn from the invoice whether they bought
hardware-partitioned MIG or an unisolated time-slice.

U feeds the §18 `undocumented` rate, which is itself a finding about the
market.

### §13.6 Attestation — **a field report, not a grade**

Ten fields, reported separately: availability · signature validity · chain
validity · revocation status · nonce freshness · measurement verification ·
debug status · hardware-model consistency · application-channel binding ·
relay-resistance evidence.

The refusal to grade is implemented, not just documented: no code path emits a
letter for this category. The reason is CVE-2026-33697 and the
*Intra-handshake.fail* result — evidence can be signed, chain-valid, fresh, and
measurement-matched while **not bound to the connection carrying your traffic**.
Any single value that averages those together hides exactly the property that
matters.

---

## Grade D is an accusation

D is the only grade that asserts a provider failed. Before a D leaves the
machine, CHARTER.md §7.5 requires the full disclosure sequence and §7.6 forbids
naming the provider. `ReportCard.requires_disclosure_before_publication`
returns true whenever any category is D, and
`controller.disclosure.DisclosureGate` refuses to release the finding until the
sequence is complete or the window has expired with documented non-response.
