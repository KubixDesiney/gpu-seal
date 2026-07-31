# Responsible Disclosure

GPU-SEAL measures infrastructure the researcher rents. When a measurement
suggests a provider's delivery does not match its advertised guarantees, that
finding goes to the provider privately, first, with everything they need to
reproduce it.

Governing document: [`CHARTER.md`](CHARTER.md) §7.5.

---

## Process

### 1. Reproduce internally

A single anomalous allocation is not a finding. Before anything leaves the
project:

- Repeat the measurement across multiple allocation cycles
- Confirm positive controls still detect a known-planted canary
- Confirm negative controls produce no false matches
- Confirm the match was an **owned canary**, authenticated under this
  experiment's key — not an unexplained byte pattern
- Confirm same-physical-device evidence where the claim depends on it
  (see §9.8b; a clean or dirty result on a *different* chip means something
  else entirely)
- Rule out methodology error: runtime initialisation, local allocator reuse,
  own-process reuse, driver behaviour, measurement bug, compiler optimisation

### 2. Prepare a minimal report

Contains: what was measured, how, on what, how many times, what the
uncertainty is, and what it does and does not imply. Offers source, logs,
hashes, container digests, and environment metadata.

Does **not** contain: raw unknown memory, speculation about other tenants,
or any claim stronger than the statistics support.

### 3. Contact privately

Through the provider's published security contact or vulnerability-disclosure
programme. If neither exists, through the most senior technical contact
available, marked confidential.

### 4. Remediation window

**90 days** by default, from first contact, extendable by agreement where the
provider is engaging in good faith. Aligns with Project Zero practice and with
fwd:cloudsec's published disclosure policy (90 + 30 to coordinate).

### 5. Re-test

After a provider reports remediation, re-run the measurement and report the
result — including if it shows no change.

### 6. Publish

Only after coordination, or after documented non-response past the window.
Publication always separates:

- **Verified facts** — what was measured, with sample counts and confidence intervals
- **Probable interpretations** — what the measurement is consistent with
- **Unresolved uncertainty** — what it cannot distinguish

The provider's response is included, in full, if they provide one.

---

## What blocks publication automatically

A run flagged `sensitive_observation` — the §7.3 automatic safety stop fired —
can never be auto-published. This is enforced in three places:

| Gate | Where |
|---|---|
| `clear_for_publication()` refuses | `probe/gpu_seal/evidence/result.py` |
| Schema conditional | `schemas/result.schema.json` |
| CI test | `tests/safety/test_egress_and_publication.py` |

Clearing such a run requires manual review and, if it concerns a provider,
completion of this process.

---

## Naming policy

During the pilot, providers are **Provider A / B / C / D**. No public ranking
by name until:

- the methodology is validated
- positive and negative controls exist and pass
- measurements are repeated
- provider responses are considered
- uncertainty is represented in the published result
- ethical and legal review has passed

Measurements are always framed against the provider's **own advertised
guarantees**, never against an external ideal we invented.

---

## If a provider disputes a finding

Their response is published alongside ours. If we made a methodology error, we
say so plainly and prominently — a correction is cheaper than a reputation.

If a provider characterises measured behaviour as intended rather than
defective, we report that as their position and let the report card speak.
There is precedent for this: CVE-2023-48022 (ShadowRay) went unfixed for years
because the maintainer classified it as a feature. Measuring against advertised
guarantees, rather than arguing about intent, is how that impasse is avoided.

---

## Reporting a vulnerability *in GPU-SEAL itself*

See [`SECURITY.md`](SECURITY.md). A safety-layer bypass — any way to make
GPU-SEAL render, retain, or exfiltrate unknown memory — is the most serious
class of bug this project can have. Please report it privately.
