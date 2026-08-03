# What remains

**Compiled:** 2026-08-03 from an independent scan (368 tests, 36/36 mutations,
13/13 probe families, 13 evidence bundles, runtime gates tested directly).

Companion to [`PROGRESS.md`](PROGRESS.md), which records what is *done*. This
file records only what is *not*, ordered by what actually unblocks the project.

**The honest summary:** the instrument is built and validated. It is now
substantially ahead of its evidence, and almost nothing on this list is solved
by writing more code.

---

## Priority 0 — the binding constraint

### 0.1 Review four provider policies

Nothing else on this page moves the project's state. Verified at runtime, not
just on disk:

```
reviewed providers in runtime matrix: [provider-a, provider-c]
  provider-a → complete
  provider-c → complete
  provider-b → awaiting written permission
  provider-d → awaiting written permission
```

Four `docs/provider-policy-review/provider-*.json` slots exist. Two are now
complete and two are safely held in `awaiting-review` because written
permission is required before testing. The runtime matrix contains two usable
policy records and still refuses the two providers awaiting consent.

For each provider, per CHARTER.md §7.4:

- [x] Read the AUP, the security-testing policy, and the vulnerability-disclosure programme
- [x] Classify: `full-probe-ok` / `self-canary-only` / `needs-written-permission` / `prohibited`
- [x] Record the source URLs and the date each policy was retrieved
- [ ] Receive written permission where the policy is unclear or silent (requests sent to Lambda and Scaleway on 2026-08-03)
- [x] Fill `reviewed_by` and `reviewed_on`; note `REVIEW_VALIDITY_DAYS` means reviews expire
- [x] Choose the four: one hyperscaler, one specialist GPU cloud, one marketplace/reseller, **one EU-sovereign** (the D7 framing needs it)

**Effort remaining:** waiting for two provider responses. **Unblocks:** the
remaining policy records; Phase 2 still requires the Priority 1 gates below.

> Under `self-canary-only`, only §9.1, §9.6, §9.5 and §9.12 may run — probes
> that touch nothing but our own marker data. §9.3 reads memory we did not
> write and can never be on that list.

---

## Priority 1 — before any provider run

### 1.1 Produce one bundle from the pinned container

The pinned release image is built and its publication gate is verified. The
canonical 64 MiB × 10-cycle battery now completes on the Windows/WSL2 path
after optimizing real-CUDA canary planting and exact block analysis.

- [x] Build the release image with a hash-pinned Python 3.10 dependency set
- [x] Run the battery inside it with `container_profile=pinned`
- [x] Confirm `clear_for_publication()` accepts a bundle carrying the image digest
- [x] Pin the CUDA base image by digest
- [x] Complete the canonical 64 MiB × 10-cycle battery after optimizing the
      small-transfer and block-analysis paths

The canonical result is recorded in
[`2026-08-03-pinned-container-phase1.md`](findings/2026-08-03-pinned-container-phase1.md)
as run `run_20260803T011804Z`. It clears the Phase 1 control gate; it does not
clear the separate provider-permission or ethics gates below.

### 1.2 Port the probe agent off Python

[ADR-001](adr/001-implementation-language.md) makes this a **precondition** for
Phase 2, with an explicit tripwire: if Phase 2 arrives first, delay Phase 2 —
do not run the Python agent "just for the pilot."

- [ ] Port the buffer-handling path to C++/CUDA
- [ ] Cross-language conformance suite: the port must reproduce all 365 tests, not approximate them
- [ ] Decide Rust/Go orchestration vs. keeping the Python controller (ADR-001 flags the latter as the likely fallback)

**This is the largest single item on the page.** It is also the one most
likely to be quietly skipped under schedule pressure, which is exactly why the
ADR states it as a gate.

### 1.3 Ethics review sign-off

- [x] ~~Pre-register scoring, thresholds, exclusion criteria, sample sizes~~ —
      [`pre-registration.md`](pre-registration.md), registered 2026-08-01
- [x] ~~Pre-register the §9.2 expected-negative~~ — H1, with its invalidation
      condition stated (the positive control must pass, or the negative is not
      a result)
- [ ] **Peer or supervisor ethics review** (CHARTER.md §11 Phase 0 exit) — the
      only part still outstanding, and the one no script can check.
      `check-release-readiness.py` explicitly does not verify it

> The pre-registration also records §6, *"what would falsify the project's own
> claims"* — worth re-reading before Phase 2 rather than after, since that is
> the section most likely to be quietly renegotiated once real provider data
> is inconvenient.

---

## Priority 2 — measurement gaps

### 2.1 Two safety files have no mutation

Tests grew 289 → 365 while the battery held at 36 cases. Two safety files are
not named as the expected catcher of any mutation:

| File | Tests | Mutation |
|---|---|---|
| `test_device_exposure_egress` | 5 | **none** |
| `test_operational_limits` | 8 | **none** |

They may be caught incidentally, but nothing demonstrates they *can* fail —
which is the only property the battery exists to establish.

- [ ] Add a mutation for each
- [ ] Track mutations-per-safety-file as a standing metric, not a one-off audit

> This matters more here than it would elsewhere: this project has already
> shipped a bug into a signed, publication-cleared bundle **with a green test
> asserting it**. Coverage was never the issue; the assertion was wrong.

### 2.2 Second platform — Linux

The entire memory-hygiene result rests on one platform, and it is the least
representative one available: a **Laptop** GPU on Windows via WSL2, where WDDM
manages memory rather than the Linux driver. Every provider runs Linux.

- [ ] Re-run §9.3 + §9.4 on Linux bare metal or a Linux VM with GPU passthrough
- [ ] If the Linux result differs, the OS/driver stack is a covariate and §9.1 must record it as one
- [ ] Fold the outcome into [Finding 001](findings/2026-07-31-rtx3050-baseline.md)

Cheapest meaningful experiment left. A single cheap Linux instance answers it.

### 2.3 Calibrate what is currently uncalibrated

Several components are built and tested against synthetic ground truth, which
proves the logic and not the instrument:

- [ ] **§9.7 allocation classifier** — needs MIG hardware for real ground truth
- [ ] **§9.8b separability (D5)** — needs N rented instances of one model; §13.1 caps at U until it lands
- [ ] **§9.8 topology** — reproduces at 16 SMs / 0.047 cycles, but against a published baseline measured on different hardware. Order-of-magnitude agreement only; do not present as replication
- [ ] **§9.12 MIG temporal isolation** — never exercised; needs A100/H100-class silicon
- [ ] **§9.10/§9.11 attestation** — never exercised; needs H100-class CC silicon

---

## Priority 3 — publication readiness

### 3.1 Bibliography hygiene

- [ ] Read refs 7–12 **in the original**. They currently trace to a secondary compilation published by a GPU host with a commercial interest in the conclusion
- [ ] Confirm venue and authors for refs 25–26 (titles observed in a secondary source)
- [ ] Keep the §23 rule in force: never cite by unverified author name

### 3.2 Charter amendment from Finding 001

- [ ] Amend §3.1 to distinguish *"the API guarantees no clearing"* from *"the memory contains prior data."* The first measurement showed those diverging, in the provider's favour. The paper is stronger for saying so plainly

### 3.3 Venue

- [ ] fwd:cloudsec **NA 2027** — CFP historically opens Dec–Jan
- [ ] fwd:cloudsec **EU 2027** with the sovereignty framing — CFP ~March
- [ ] **arXiv preprint early.** A directly-overlapping paper (Alpay & Alpay) appeared five weeks before this project started. Priority is worth establishing before the campaign completes
- [ ] Consider contacting `alpay@lightcap.ai` — D5 is a natural joint extension and collaboration beats collision

---

## Priority 4 — deferred by design

Not gaps. Recording them so they are not mistaken for oversights.

- **§9.5 self-vs-self canary** — gated on D5 by CI test 16. Correct.
- **Probes that refuse on this hardware** — `MigUnavailable` on a consumer card is the design working. A §9.12 record produced on non-MIG silicon would be a §9.3 record wearing the wrong name, which is the exact error that quarantined two bundles.
- **D6 longitudinal** — needs time and providers, nothing else.
- **Named provider results** — CHARTER.md §7.6 forbids ranking by name until methodology is validated, controls exist, measurements repeat, provider responses are in, and ethics review has passed.

---

## Sequencing

```
0.1 review four providers ──┬──> 1.1 pinned bundle ───┐
                            │                         ├──> Phase 2 pilot
                            ├──> 1.2 language port ────┤
                            └──> 1.3 ethics sign-off ──┘

2.2 Linux platform ─────────> independent of all of the above; do it while
                              the policy reading is in progress
```

**Fastest path to unblocking:** read four AUPs (0.1) and run one Linux
instance (2.2) in the same afternoon. Those two together convert the project
from *an instrument with one unrepresentative data point* into *an instrument
with a validated cross-platform baseline and permission to proceed*.

Everything else is downstream of those.

---

## What is NOT on this list

Building more probes. All thirteen families exist. The next probe added
before a provider is reviewed is the project's first genuinely wasted effort —
and given the pattern so far, the temptation to build one instead of reading
four policy documents is real.
