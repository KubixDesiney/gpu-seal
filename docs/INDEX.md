# Documentation index

GPU-SEAL's documentation is written for several different readers who each
need a different path through it. This page is that map — grouped by who
you are, not by directory structure.

For the full flat list of documents by content, see the table at the bottom
of [`README.md`](../README.md#documentation).

---

## 1. Start here — new to the project

Read in this order:

1. [`README.md`](../README.md) — what GPU-SEAL measures, what it refuses to
   do, platform quickstarts, and first verification.
2. [`STATUS.md`](STATUS.md) — the dated authoritative measured status and
   release scorecard.
3. [`CHARTER.md`](../CHARTER.md) — the governing research and implementation
   charter everything else in this list answers to.
4. [`ETHICS.md`](../ETHICS.md) — the one-sentence version of the project's
   ethical basis, and where each rule is enforced in code.
5. [`docs/PROGRESS.md`](PROGRESS.md) — what is actually built and verified,
   graded per category with no composite score.
6. [`docs/REMAINING.md`](REMAINING.md) — what is left, ordered by what
   actually unblocks the project rather than by what is most interesting to
   build.

## 2. Run locally — engineer setting up the probe

1. [`README.md` — Quickstarts](../README.md#quickstarts)
   — install, run the test suite, run the safety-suite negative control.
2. [`lab/docker/README.md`](../lab/docker/README.md) — full local lab setup
   (RTX 3050 / Docker Desktop / WSL2 target), dev vs. release image, and
   troubleshooting.
3. [`docs/architecture.md`](architecture.md) — component map, the
   `SafeBuffer` minimal usage example, and where the repo layout deviates
   from `CHARTER.md` §15.
4. [`docs/PROVIDER-ADAPTER.md`](PROVIDER-ADAPTER.md) — the provider runtime
   contract, deterministic fake, and owner inputs required before a concrete
   adapter can exist.
5. Verification scripts, runnable directly:
   - [`lab/verify-safety-suite.sh`](../lab/verify-safety-suite.sh) — proves
     the safety suite can fail (38 injected violations, all must be caught)
   - [`lab/scorecard.py`](../lab/scorecard.py) — executes shell syntax,
     probe-import, battery-preflight, and provider-matrix liveness checks;
     appends JSONL history by default
   - [`lab/check-provider-policy.py`](../lab/check-provider-policy.py) —
      reports the two complete and two awaiting provider records
   - [`lab/local-runner/run_phase1.py`](../lab/local-runner/run_phase1.py) and
     [`lab/local-runner/run_phase2_local.py`](../lab/local-runner/run_phase2_local.py)
     — the control battery and full local probe run, on real hardware
6. Example inputs and output: [`examples/`](../examples/) —
   [`experiment-local.yaml`](../examples/experiment-local.yaml),
   [`experiment-cloud.yaml`](../examples/experiment-cloud.yaml),
   [`sample-safe-result.json`](../examples/sample-safe-result.json).
7. [`TRUST-MODEL.md`](TRUST-MODEL.md) — dashboard inspection versus
   cryptographic verification with an external key.

## 3. Understand the safety model — security reviewer

1. [`ETHICS.md`](../ETHICS.md) — the enforceable rules, each with its
   enforcement point named (canary-only search, no rendering/retaining
   unknown memory, allowlisted egress, automatic safety stop).
2. [`docs/threat-model.md`](threat-model.md) — the tenant's actual position,
   what is and is not modelled as adversarial, and the hard boundaries with
   their enforcement points.
3. [`docs/data-handling.md`](data-handling.md) — exactly what is held, for
   how long, what is never published, and the publication gate.
4. [`SECURITY.md`](../SECURITY.md) — how to report a vulnerability in
   GPU-SEAL itself (a safety-layer bypass), separate from a finding about a
   provider.
5. [`DISCLOSURE.md`](../DISCLOSURE.md) — the responsible-disclosure process
   for findings *about* a provider.
6. Architecture decision records behind the safety-relevant design choices:
   [ADR-002 (canary wire format)](adr/002-canary-wire-format.md) and
   [ADR-003 (measurement path declared by the backend)](adr/003-measurement-path-declared-by-the-backend.md).
7. [`TRUST-MODEL.md`](TRUST-MODEL.md) — what a signature does and does not
   establish.

## 4. Understand the research methodology — academic reviewer

1. [`docs/methodology.md`](methodology.md) — how a measurement is taken, in
   order, and what each step is allowed to conclude; the positive/negative
   control design; statistics (Wilson intervals, seeded bootstrap).
2. [`docs/scoring.md`](scoring.md) — the report card's five independently
   graded categories, why there is no composite score, and why grade U means
   unproven rather than failing.
3. [`docs/pre-registration.md`](pre-registration.md) — hypotheses,
   thresholds, and interpretation rules fixed before any named-provider data
   is collected.
4. [`docs/prior-art.md`](prior-art.md) — the literature sweep, the
   incumbent instrument GPU-SEAL builds on, and where the project's actual
   delta lands.
5. [`docs/findings/2026-07-31-rtx3050-baseline.md`](findings/2026-07-31-rtx3050-baseline.md)
   — the one real-hardware result set so far, and the reasoning that
   produced it.
6. [ADR-001 (implementation language)](adr/001-implementation-language.md)
   — why the memory-touching slice is native while policy and orchestration
   remain in Python, and what must happen before provider use.
7. [`CITATION.cff`](../CITATION.cff) — citation metadata for Aziz Bargaoui.

## 5. Prepare for provider testing — project operator

1. [`docs/provider-policy-review/README.md`](provider-policy-review/README.md)
   — the Phase 0 gate itself: the four provider-policy classifications, the
   review procedure, and why this is operator work that cannot be automated
   or guessed.
2. [`controller/README.md`](../controller/README.md) — what the controller
   refuses before any probe runs (unreviewed policy, prohibited
   classification, stale review, missing ownership confirmation, budget
   caps), and where operator-facing configuration lives.
3. [ADR-001 (implementation language)](adr/001-implementation-language.md)
   — the native-path/conformance precondition that must pass before Phase 2.
4. [`DISCLOSURE.md`](../DISCLOSURE.md) — the process to follow if a
   measurement against a real provider produces a finding.
5. Check the gate at any time:
   [`lab/check-provider-policy.py`](../lab/check-provider-policy.py).
6. [`OWNER-ACTION-CHECKLIST.md`](OWNER-ACTION-CHECKLIST.md) — decisions and
   external inputs that cannot be automated.
7. [`OWNER-DIFF-MAP.md`](OWNER-DIFF-MAP.md) — file-by-file inclusion and owner
   review map for the current dirty tree.

## 6. Release checklist — the existing gates

`lab/check-release-readiness.py` is the release gate itself; everything
below is what it checks, in the same order:

1. **`CITATION.cff` author metadata** — complete for Aziz Bargaoui. See
   [`CITATION.cff`](../CITATION.cff).
2. **Container lock file** — hash-pinned dependencies for the reproducible
   release image. See
   [`lab/docker/README.md` §4](../lab/docker/README.md#4-dev-vs-release-image-this-matters).
3. **Provider policy matrix completeness** — the current checker measures two
   complete records and two awaiting written permission. No named-provider
   data may be published from this tree. See
   [`docs/provider-policy-review/README.md`](provider-policy-review/README.md).
4. **Quarantined evidence stays explained** — any bundle in `out/` with a
   canary recovery must be accounted for in `out/MISLABELLED-README.md`.
   Background: [ADR-003](adr/003-measurement-path-declared-by-the-backend.md).
5. **Measurement pre-registration** — scoring fixed before named-provider
   results exist. See [`docs/pre-registration.md`](pre-registration.md).
6. **Built artifact integrity** — release CI inspects the actual wheel for all
   runtime schemas and the dashboard `dist/client` manifest and assets. Run
   `lab/check-release-readiness.py --wheel <wheel> --dashboard-dist
   dashboard/dist/client` after building both artifacts.

Run it directly:

```bash
python lab/check-release-readiness.py
```

Related gates enforced elsewhere, not by this script:

- [`lab/verify-safety-suite.sh`](../lab/verify-safety-suite.sh) — the safety
  suite's own negative control (38 injected violations, all must be caught)
- [`docs/PROGRESS.md`](PROGRESS.md) — implementation progress and the human
  and external gates that `check-release-readiness.py` cannot decide.

## 7. Project operations

- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — contribution workflow and
  required checks.
- [`../SECURITY.md`](../SECURITY.md) — private reporting for safety-layer
  vulnerabilities.
- [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) — participation standards.
- [`RELEASE.md`](RELEASE.md) — release process and what the automated gate
  does not decide.
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — common setup and platform
  failures.
