# Provider policy review — CHARTER.md §7.4

> Some providers prohibit security benchmarking without permission — resolve
> this per provider **before** probing.

This directory is the gate. A provider that has no complete record here cannot
be probed: `gpu_seal.controller.policy_matrix` raises `ProviderNotReviewed`,
and the Phase 0 CI job keeps the no-named-provider rule in force.

The point is that "we checked the terms" becomes a reviewable artefact rather
than a memory.

---

## Status

**No provider has been reviewed yet.** The four files below are *slots* for the
Phase 2 pilot (CHARTER.md §11), each marked `"status": "awaiting-review"`. The
loader skips them and the runtime matrix is empty, which is the safe state:
everything is refused.

Filling them requires reading four providers' actual terms and, where those
terms are unclear, writing to the provider and waiting for an answer. That is
operator work with legal judgement in it. It cannot be done from inside the
repository, and inventing a classification would be worse than having none —
a fabricated `full-probe-ok` is how a research project ends up in breach of a
contract it never read.

| Slot | Pilot category (CHARTER.md §11 Phase 2) | State |
|---|---|---|
| `provider-a` | Hyperscaler | awaiting review |
| `provider-b` | Specialist GPU cloud | awaiting review |
| `provider-c` | Marketplace / reseller / fractional service | awaiting review |
| `provider-d` | EU-sovereign provider | awaiting review |

Codes are pseudonymous per §7.6 and stay that way until methodology is
validated, controls exist, measurements are repeated, provider responses are
considered, uncertainty is represented, and ethical review has passed.

---

## The four classifications (§7.4)

| Class | Meaning | What may run |
|---|---|---|
| `full-probe-ok` | A published research or security-testing policy covers what GPU-SEAL does on infrastructure the researcher rents. | All probe families. |
| `self-canary-only` | Benchmarking is restricted, but experiments touching only the researcher's own marker data are within terms. | `environment_inventory`, `device_exposure_inventory`, `self_sequential_canary`, `mig_temporal_isolation`. Note §9.12 is pure self-canary and survives this class — a real practical advantage. |
| `needs-written-permission` | The policy is unclear, or requires prior authorisation. | Nothing, until a permission reference is attached to the record. |
| `prohibited` | Testing is forbidden. | Nothing. The controller raises rather than returns, so it cannot be ignored. |

---

## Review procedure

For each provider, before any probe runs:

1. **Read the acceptable use policy.** Record the URL and the version or date
   stamp of the document as read (§7.4 requires the policy version in study
   metadata, not just the classification).
2. **Read the security-testing policy**, if one exists separately.
3. **Read the vulnerability-disclosure programme.** A provider with a
   published VDP and a 90-day norm is a different counterparty from one with
   neither.
4. **Decide the classification** from what the documents actually say, not
   from what would be convenient. When in doubt the answer is
   `needs-written-permission` — the cost of asking is an email.
5. **Where permission is needed, request it in writing** and record the
   reference in `permission_reference`. Describe what GPU-SEAL does honestly:
   tenant-side assurance measurement on instances we rent, canary-only data
   policy, no exploitation, coordinated disclosure.
6. **Set `status` to `"reviewed"`** and fill `reviewed_on` and `reviewed_by`.
7. Re-read annually. A record older than 365 days is refused as stale —
   provider terms change, and a classification from two years ago is a guess
   wearing a citation.

## Record format

See [`_template.json`](_template.json). Validated by
[`schemas/provider-policy.schema.json`](../../schemas/provider-policy.schema.json)
and loaded by `gpu_seal.controller.policy_matrix.load_policy_matrix`.

Check the directory at any time with:

```bash
python3 lab/check-provider-policy.py
```

That script is what the CI job runs. While no record is complete it reports
the Phase 0 gate as *enforced*, and no real provider name may appear in
`probe/` or `controller/` source.
