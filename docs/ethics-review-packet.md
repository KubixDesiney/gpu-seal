# GPU-SEAL ethics review packet

**Purpose:** request peer or supervisor review before any named-provider
measurement begins.

**Prepared:** 2026-08-03 · **Status checked:** 2026-09-02
**Project:** GPU-SEAL (internal codename: GHOSTMETER)
**Phase:** Phase 0 exit / Phase 2 pilot readiness  
**Decision requested:** approve, approve with conditions, or defer the pilot

This packet is an operational research review, not a legal opinion or a
substitute for an institution's formal ethics process. The pilot remains
blocked until a reviewer records a decision below.

## 1. Research question and scope

GPU-SEAL measures whether a GPU allocation rented by the researcher behaves
consistently with the provider's advertised isolation and memory-hygiene
guarantees. It is an assurance measurement, not an exploitation exercise.

The planned pilot is four pseudonymous provider slots: one hyperscaler, one
specialist GPU cloud, one marketplace or reseller, and one EU-sovereign
provider. Per provider, the pre-registration specifies one product, one
region, ten allocation cycles, and five probe families. Provider names remain
pseudonymous in study outputs until the publication gates are satisfied.

No provider measurement run is recorded or claimed. Local controls and the
software safety contract use researcher-owned hardware or simulation only; a
local result is not provider validation.

## 2. People, systems, and data in scope

### People and organisations

- The researcher/operator, who owns the experiment key and rented accounts.
- Cloud providers whose own rented instances are measured.
- Other tenants are not research subjects and are never contacted or profiled.
- Provider security or disclosure teams are contacted privately only if a
  validated result requires it.

### Systems

- A provider instance rented under the researcher's account.
- The GPU runtime and container visible from that instance.
- The local evidence store and signed result bundles.

### Data

The only bytes intentionally written are random, non-semantic, experiment-
bound canaries containing a nonce and keyed MAC. Unknown GPU memory is never
rendered, decoded, classified, uploaded, retained, or published. Retained
outputs are aggregate statistics, owned-canary metadata, hashes, timing,
environment metadata, and error or exclusion codes.

Account IDs, unnecessary public IPs, stable GPU UUIDs, hostnames,
provider-internal IDs, exact server coordinates, and raw unknown memory are
excluded from publication.

## 3. Activities that are allowed

- Run only on instances explicitly rented by the researcher.
- Use ordinary customer permissions and documented runtime APIs.
- Inventory the assigned environment and device exposure.
- Run pre-registered allocation, canary, timing, topology, and memory probes
  only when the provider policy permits them or written permission is attached.
- Use ten cycles per pilot cell, with explicit time and spend limits.
- Stop immediately on an unexpected non-owned observation or policy mismatch.
- Report observations separately from interpretations, with denominators and
  95% Wilson intervals.

## 4. Activities that are prohibited

GPU-SEAL will not:

- exploit a provider, escape a VM or container, access the host OS, or bypass
  authentication, quotas, billing, or network controls;
- scan infrastructure that is not rented by the researcher;
- read another tenant's files, processes, traffic, API data, or secrets;
- search for arbitrary strings, prompts, credentials, model weights, images,
  or natural-language content;
- attempt privilege escalation, Rowhammer, denial of service, saturation of
  shared infrastructure, or destructive resets;
- publish an uncoordinated accusation or rank providers by name;
- continue testing when the provider policy is unclear or permission is
  missing.

These constraints are product requirements in [`ETHICS.md`](../ETHICS.md) and
are enforced by the safety suite and provider-policy gate.

## 5. Main risks and mitigations

| Risk | Mitigation | Stop condition |
|---|---|---|
| Unexpected third-party bytes are observed | Canary-only authenticated search; unknown bytes remain inside `SafeBuffer`; aggregate-only egress | Automatic `sensitive_observation` stop; no automatic publication |
| Provider terms prohibit or limit testing | Read AUP, security-testing policy, and disclosure policy first; classify each slot; obtain written permission when unclear | No probe runs for `awaiting-review`, `needs-written-permission`, or `prohibited` |
| Shared infrastructure is affected | Small fixed allocations, ten cycles, no saturation, no cross-customer testing, ordinary customer APIs | Stop on throttling, instability, unexpected impact, or provider instruction |
| A false positive becomes a public allegation | Positive and negative controls, signed evidence, same-device gates, pre-registered thresholds, private disclosure first | Result is quarantined until methodology and disclosure review complete |
| Spend exceeds the approved amount | Set a per-provider budget ceiling before launch; use automatic shutdown and short-lived instances | Stop before the ceiling; no automatic retry after quota or billing errors |
| Credentials or identifiers leak into evidence | Store only necessary metadata; redact account, host, UUID, and location details from publication | Quarantine bundle and review before any transfer |
| A run is interrupted with a live allocation or canary | Use bounded runtime and cleanup paths; do not force-kill a probe mid-cycle | Mark run aborted, clean up the allocation, exclude it from statistics |

## 6. Safety and validity controls

Every provider cell must pass these gates before interpretation:

1. Environment inventory and allocation-model classification run first.
2. The §9.4 framework-cache positive control recovers a canary planted by the
   researcher. If it fails, the provider result is uninterpretable.
3. The explicit-zeroisation negative control produces zero false positives.
4. The measurement path is identified; only `driver_direct` observations can
   support a memory-hygiene grade.
5. Exclusions retain their reason and are not silently counted as negatives.
6. The signed bundle passes schema, integrity, and publication checks.

Current repository validation is recorded in [`docs/STATUS.md`](STATUS.md):
the measured local Python suite is 408 passed with no skips, and the mutation
battery catches 38/38 injected violations across 15 safety files. The current release gate is
not releasable because the worktree is dirty; its content and policy checks
pass. Local control findings validate the instrument boundary only, not any
provider.

## 7. Disclosure and publication

An anomalous result is reproduced internally before leaving the project. The
team then prepares a minimal technical report containing method, sample size,
uncertainty, environment, hashes, and container digest, but never raw unknown
memory or speculation about another tenant.

The provider is contacted privately through its published security or
disclosure channel. The default remediation window is 90 days, extendable by
agreement. Publication waits for coordination or documented non-response and
includes the provider's response. Verified facts, probable interpretations,
and unresolved uncertainty remain separate.

## 8. Provider-policy status

The runtime matrix currently has two complete provider records and two slots
awaiting written permission. The two awaiting slots remain blocked. No policy
record is treated as permission merely because an account or instance exists,
and the two complete records do not waive the ethics, ownership, budget, or
shared-provider safety gates.

Before each run, the operator must confirm that the relevant policy record is
reviewed, current, scoped to the planned probe family, and backed by written
permission where required. The policy check is run again immediately before
launch.

## 9. Reviewer checklist and decision

The reviewer should confirm:

- [ ] The research question is proportionate to the proposed activity.
- [ ] The canary-only and no-raw-memory policy adequately protects other
      tenants and provider data.
- [ ] The prohibited-activity list rules out exploitation and service impact.
- [ ] The provider-policy and written-permission gate is sufficient.
- [ ] The sample size, controls, exclusion rules, and uncertainty reporting
      are fixed before provider data collection.
- [ ] The disclosure and publication process is adequate.
- [ ] The per-provider spend ceiling and cleanup plan are filled in before
      launch.
- [ ] The reviewer has no additional conditions.

**Decision:** `pending` / `approved` / `approved-with-conditions` / `deferred`

**Conditions or required changes:**

______________________________________________________________________________

**Reviewer name and role:** _________________________________________________

**Signature or written approval reference:** _________________________________

**Date:** __________________

## 10. Launch gate after approval

Approval alone does not authorize a provider run. The operator must still
complete the provider-policy record, written permission, budget ceiling,
language-port gate from ADR-001, and the pre-launch checklist. Until all are
complete, the controller must continue to refuse named-provider testing.
