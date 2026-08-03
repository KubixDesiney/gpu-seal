# Threat model

**Charter:** §6, and §4.3 for the hard boundaries

The single most important sentence in this document is not about an adversary:

> **You are not attacking anyone. You are auditing what *you* rented.**

Everything below exists to keep that true under pressure.

---

## Position: ordinary paying customer

The researcher is an authenticated customer with legitimate access to an
instance they pay for. Specifically they have:

- a shell inside the rented VM or container
- permission to run CUDA kernels and ordinary CUDA APIs
- the ability to inspect the filesystem and process namespace the tenant is
  given
- the ability to make normal network requests
- the ability to destroy and recreate instances they own

They do **not** assume, request, or acquire: host root, provider admin,
firmware access, hidden provider telemetry, vendor signing keys, a neighbour's
cooperation, access to neighbouring workloads, or physical server access.

Every probe is written to work from this position. Where a probe would need
more, it reports `not_testable` with a reason rather than escalating — see
`DeviceExposureProbe`, most of whose findings on a well-configured host are
`secure_restriction`, which is the system working.

---

## What is being measured

Observable evidence *consistent with*: incomplete memory sanitisation ·
framework or allocator reuse · excessive device exposure · cross-process or
cross-container visibility · unexpected management access · misdescribed
hardware · undocumented sharing · region inconsistency · invalid, unavailable,
or stale attestation · debug-mode deployment · weak connection binding ·
ambiguous isolation · undocumented MIG teardown behaviour.

"Consistent with" is doing real work in that sentence. §12 requires observation
and interpretation to be reported separately, and the report card's grade D —
the only grade that asserts a failure — routes through the §7.5 disclosure
sequence before it can be published.

---

## Adversary assumption, and its limits

For some research questions the provider or reseller is modelled as
potentially **inaccurate, misconfigured, or dishonest** about GPU model or
class, dedicated-versus-shared tenancy, region, confidential-computing status,
or isolation guarantees.

**This is a research model, not an accusation.** It is the assumption that
makes the measurement worth taking — if provider claims were self-verifying
there would be nothing to measure. It is not a belief about any provider, and
nothing in a GPU-SEAL report may be phrased as though it were.

---

## Explicitly out of scope

Not modelled, not tested, not implemented:

physical chip attacks · malicious firmware implants · power and EM analysis ·
GPU Rowhammer · DMA attacks · IOMMU bypass · host-kernel or hypervisor
exploitation · supply-chain implant detection · destructive fault injection ·
**cache and TLB side channels**

The last one is worth spelling out, because 2026 work shows MIG's *runtime*
isolation may have cache and TLB side channels (§24 refs 25–26). Those are
attacks. GPU-SEAL measures assurance. The papers are cited and distinguished;
they are not reproduced.

The one timing measurement in the project — `measure_scheduling_gaps` — times
**only our own operations** and retains only their aggregate distribution. It
measures whether *we* were scheduled, not what anybody else did.

---

## Hard boundaries (§4.3), enforced not promised

GPU-SEAL must never: exploit a provider · escape a VM or container · access the
host OS · circumvent authentication or billing · scan infrastructure it does
not rent · read another tenant's files, processes, traffic, or API data ·
recover natural-language text from unknown memory · classify unknown memory as
weights, prompts, or activations · save raw unknown VRAM · attempt GPU
Rowhammer, privilege escalation, or denial of service · saturate shared
infrastructure beyond normal workload behaviour · publish an uncoordinated
accusation · present uncertain measurements as proof of malicious provider
behaviour.

| Boundary | Enforcement |
|---|---|
| No container escape, even for §9.6 inventory | `test_no_container_escape_constructs` rejects the constructs anywhere in `probe/`; §9.6 omits the host-socket census rather than name the paths |
| No privilege escalation | `test_no_privileged_subprocess_invocations` |
| No reading another tenant's data | canary-only search; there is no API taking a caller-supplied pattern |
| No text recovery or classification | no `.decode()` outside `metadata.py`; no `re`; the safety stop halts *before* deciding what content is |
| No raw VRAM retained | `SafeBuffer` zeroes on scope exit; no serialisation modules importable |
| No unauthorised targets | `ProviderNotReviewed` / `ProviderProhibited`; ownership attestation required |
| No uncoordinated accusation | grade D routes through `DisclosureGate` |
| No offensive naming | `test_no_destructive_or_offensive_symbol_names` — a repo containing `container_escape()` cannot be handed to a provider's security team, whatever the function does |

Each has at least one mutation in `lab/verify-safety-suite.sh` proving the
suite goes red when it is removed.

---

## Threats to the *research*, not from it

The failure modes most likely to actually occur are methodological.

| Threat | Mitigation |
|---|---|
| False positive from runtime init, local allocator reuse, or a measurement bug | positive + negative controls; boundary-specific probes; repeated runs; owned canaries only |
| A working control graded as a provider failure | `MeasurementPath` gates every §13.1 grade before the D branch (ADR-003) |
| A clean result on a chip we were never given twice | same-device gate; same-model pairs cap at U until D5 |
| Fingerprint overclaiming | confidence scores; "consistent with" never "proved"; published classifier limits |
| An unregistered negative reading as a fishing expedition | `docs/pre-registration.md`, dated before any provider data |
| A provider unfairly harmed by a badly framed report | pseudonymous codes; pre-registered scoring; coordinated disclosure; provider response included; product-level claims separated from provider-wide ones |
| Evidence that cannot be reproduced | signed bundles; pinned container; publication refused for any run that cannot name its image |
