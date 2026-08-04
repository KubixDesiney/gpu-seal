# What remains

**Compiled:** 2026-08-04 from an independent scan — 376 tests, 38/38 mutations,
13/13 probe families, 13 evidence bundles, provider matrix and CI gates tested
at runtime rather than read from disk.

Companion to [`PROGRESS.md`](PROGRESS.md), which records what is *done*. This
file records only what is *not*, ordered by what actually unblocks the project.

**What changed since 2026-08-03:** P0 is closed. The four provider policy
records were reviewed correctly but published with the real provider named in
plaintext, and the CI gate meant to catch that was wired to stop checking the
moment any provider finished review. Both are fixed — see
[`PROGRESS.md`](PROGRESS.md) "Bugs worth remembering" for the full account —
and the binding constraint moves back to where it was before the leak: two
outstanding permissions and the language port.

---

## Priority 0 — closed this session

**0.1 The §7.6 pseudonymisation leak is closed.** Every
`docs/provider-policy-review/provider-*.json` is now pseudonymous; the real
name, source URLs, and contact addresses for each provider live only in
`docs/provider-policy-review/private/` (gitignored, never loaded by the
runtime matrix, which globs non-recursively). A new release-readiness check,
`check_no_named_providers` in `lab/check-release-readiness.py`, scans every
git-tracked file — not just `probe/` and `controller/` — for real provider
names, with tests proving it fires and proving it leaves the reviewed
design-space mentions in `CHARTER.md` and `prior-art.md` alone. The two
commits that had already reached the public remote were reconstructed with
the same diffs minus the leak and force-pushed; the two branches carrying the
granular unredacted history were deleted from the remote.

**What a git rewrite does not reach:** GitHub retains `refs/pull/N/head` and
`refs/pull/N/merge` for merged pull requests independent of branch state: they
are not something `git push` can delete. If this repository is ever treated
as needing a *complete* purge rather than "stop the leak from here forward,"
that requires a GitHub Support request, not another rewrite. The repository
had zero forks and zero stars when this was found, which limits realistic
exposure but is not the same as zero.

**0.2 The Phase 0 CI gate is re-keyed.** `no-cloud-testing-marker` no longer
skips the real-names check once any provider record is complete — that was
the mechanism that let the leak reach `main` while the job stayed green. The
check now runs unconditionally on every push, and calls the same
`check_no_named_providers` function `lab/check-release-readiness.py` uses, so
the two can't drift apart again.

---

## Priority 1 — before any provider run

### 1.1 Obtain the two outstanding permissions

Half the pilot cannot legally run today.

| Code | Category | Class | State |
|---|---|---|---|
| provider-a | hyperscaler | `full-probe-ok` | ✅ permitted |
| provider-c | marketplace | `full-probe-ok` | ✅ permitted |
| provider-b | specialist | `needs-written-permission` | request sent 2026-08-03, awaiting |
| provider-d | eu-sovereign | `needs-written-permission` | awaiting |

- [ ] Chase provider-b; record the scope reference when it arrives
- [ ] Send provider-d's request if not yet sent — it is the **EU-sovereign** slot
      and the D7 framing depends on it
- [ ] Record `permission_reference` and re-run the matrix loader to confirm the
      classification changes
- [ ] Note `REVIEW_VALIDITY_DAYS`: reviews expire. Two are dated 2026-08-03

**Not in your control.** Start the clock now; do other work while it runs.

### 1.2 Produce one bundle from the pinned container

**Third scan running.** 13 bundles: 4 `dev-unpinned`, 9 bare-metal
`unspecified`, **0 pinned**. The lock file is real (17 hashes, no placeholders)
and the image builds. It has simply never produced anything.

- [ ] `bash lab/docker/build.sh release`
- [ ] Run the Phase 1 battery inside it; confirm `container_profile=pinned`
- [ ] Confirm `clear_for_publication()` accepts the result
- [ ] Pin the base image by digest — the Dockerfile still resolves a tag

Until this is done, by your own guard, nothing measured so far is evidence.

### 1.3 Port the probe agent off Python

[ADR-001](adr/001-implementation-language.md) states this as a **precondition**
for Phase 2 with an explicit tripwire: if Phase 2 arrives first, delay Phase 2 —
do not run the Python agent "just for the pilot."

With two providers now permitted, that tripwire is live rather than theoretical.

- [ ] Port the buffer-handling path to C++/CUDA
- [ ] Cross-language conformance suite — the port must reproduce all 376 tests,
      not approximate them
- [ ] Decide Rust/Go orchestration vs. keeping the Python controller (ADR-001
      names the latter as the likely fallback)

**Largest remaining item, and the one most likely to be quietly skipped now that
a provider is available to test against.**

### 1.4 Ethics review sign-off

- [x] ~~Pre-register scoring, thresholds, exclusions, sample sizes~~ —
      [`pre-registration.md`](pre-registration.md)
- [x] ~~Pre-register the §9.2 expected-negative~~ — H1, with its invalidation
      condition stated
- [ ] **Peer or supervisor ethics review** — the only part outstanding, and the
      one `check-release-readiness.py` explicitly cannot verify

> Re-read §6 of the pre-registration, *"what would falsify the project's own
> claims,"* **before** Phase 2 rather than after. It is the section most likely
> to be quietly renegotiated once real provider data is inconvenient.

---

## Priority 2 — measurement gaps

### 2.1 Second platform — Linux

The whole memory-hygiene result rests on one platform, and it is the least
representative one available: a **Laptop** GPU on Windows via WSL2, where WDDM
manages memory rather than the Linux driver. Every provider runs Linux.

- [ ] Re-run §9.3 + §9.4 on Linux bare metal or a Linux VM with GPU passthrough
- [ ] If the result differs, the OS/driver stack is a covariate and §9.1 must
      record it as one rather than as noise
- [ ] Fold into [Finding 001](findings/2026-07-31-rtx3050-baseline.md)

Cheapest meaningful experiment left, and with provider-a permitted it can now
run on a real rented instance instead of a local VM.

### 2.2 Calibrate what is calibrated only against synthetic ground truth

Built and tested, but never exercised against reality:

- [ ] **§9.7 allocation classifier** — needs MIG hardware for ground truth
- [ ] **§9.8b separability (D5)** — needs N instances of one model; §13.1 caps
      at U until it lands, and that cap is firing on real bundles today
- [ ] **§9.8 topology** — reproduces at 16 SMs / 0.047 cycles, but against a
      baseline measured on different hardware. Order-of-magnitude agreement
      only; do not present as replication
- [ ] **§9.12 MIG temporal isolation** — needs A100/H100-class silicon
- [ ] **§9.10 / §9.11 attestation** — needs H100-class CC silicon

### 2.3 Keep the mutation ratio honest

Both files flagged in the 2026-08-01 scan now have mutations (36 → 38), which
is the right response. Worth making standing rather than reactive.

- [ ] Add a CI check: every file in `tests/safety/` must be named as the
      expected catcher of at least one mutation
- [ ] Track mutations-per-safety-file as a metric, not a periodic audit

> This project has already shipped a bug into a signed, publication-cleared
> bundle **with a green test asserting it**. Coverage was never the problem;
> the assertion was wrong. The §7.6 leak closed this session is the same
> lesson at repository scope: a green CI job is not proof of the property it
> was named after.

---

## Priority 3 — publication readiness

### 3.1 Bibliography hygiene

- [ ] Read refs 7–12 **in the original**. They currently trace to a secondary
      compilation published by a GPU host with a commercial interest in the
      conclusion
- [ ] Confirm venue and authors for refs 25–26 (titles seen in a secondary source)
- [ ] Keep the §23 rule in force: never cite by unverified author name

### 3.2 Venue and priority

- [ ] **arXiv preprint early.** A directly-overlapping paper (Alpay & Alpay)
      appeared five weeks before this project began. Priority is worth
      establishing before the campaign completes
- [ ] fwd:cloudsec **NA 2027** — CFP historically opens Dec–Jan
- [ ] fwd:cloudsec **EU 2027** with the sovereignty framing — CFP ~March;
      depends on provider-d
- [ ] Consider contacting `alpay@lightcap.ai` — D5 is a natural joint extension

---

## Priority 4 — deferred by design

Not gaps. Recorded so they are not mistaken for oversights.

- **§9.5 self-vs-self canary** — gated on D5 by CI test 16. Correct.
- **Probes that refuse on this hardware** — `MigUnavailable` on a consumer card
  is the design working. A §9.12 record from non-MIG silicon would be a §9.3
  record wearing the wrong name, which is the exact error that quarantined two
  bundles.
- **D6 longitudinal** — needs time and providers, nothing else.
- **Named provider results** — §7.6 forbids ranking by name until methodology
  is validated, controls exist, measurements repeat, provider responses are in,
  and ethics review has passed. P0.1 being closed is what makes this
  *possible* to honour later; it does not bring it any closer to now.

---

## Sequencing

```
0.1 close §7.6 leak ──────> done
0.2 re-arm CI gate  ──────> done

1.1 chase permissions ────> not in your control; start the clock now
                              │
1.2 pinned bundle ────────┐   │
1.3 language port ────────┼───┴──> Phase 2 pilot on provider-a / provider-c
1.4 ethics sign-off ──────┘

2.1 Linux platform ───────> independent; can now run on provider-a
```

**Fastest path:** the pinned bundle and the language port are the only things
standing between you and a pilot on the two already-permitted providers.
Provider-b and provider-d's permissions run on their own clock in parallel.

---

## What is NOT on this list

Building more probes. All thirteen families exist and six already refuse for
want of hardware, not code. With a provider now permitted, the temptation
shifts from *build another probe* to *skip the language port and just run it* —
which ADR-001 anticipated and explicitly forbids.
