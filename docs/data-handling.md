# Data handling

**Charter:** §7.2 (unknown-memory handling), §7.3 (safety stop), §10 (never published)

This document says what GPU-SEAL holds, for how long, and what it refuses to
hold at all. Every rule here is enforced in code and tested; the citations are
to the enforcement point, not to a policy paragraph.

---

## Two kinds of data, two doors

| | Memory GPU-SEAL did not write | Description of the rented environment |
|---|---|---|
| Produced by | §9.2, §9.3, §9.4, §9.12 | §9.1, §9.6, §9.7, §9.8, §9.9, §9.10, §9.11 |
| Container | `SafeBuffer` | plain values |
| Egress door | `aggregate()` → `AggregateRecord` | `ObservationRecord.to_dict()` |
| Allowlist | `SAFE_AGGREGATE_KEYS` | `SAFE_OBSERVATION_KEYS` |
| Hazard | leaking another tenant's bytes | leaking §10 identifiers |

Both allowlists are enforced **on the way out** and both refuse rather than
filter. A field absent from the list raises `EgressViolation`; it is not
silently dropped, because a silent drop lets a contributor believe the field
was recorded.

---

## Unknown memory

**What may be retained** (§7.2, and nothing else): zero-byte percentage,
fixed-pattern percentage, byte-frequency histogram, estimated entropy,
repeated-block count, exact match against owned canaries, longest owned-canary
prefix match, measurement hash, probe version, driver/environment metadata,
error codes, timing measurements.

**What is never done, and is blocked by static analysis** (§16 tests 1, 4, 5,
enforced in `tests/safety/test_static_analysis.py`):

- printing unknown bytes — no `print()` anywhere under `probe/`
- decoding unknown bytes — no `.decode()` outside `safety/metadata.py`, which
  refuses any input over 256 bytes or containing non-printable ASCII
- pattern-searching unknown bytes — `re` cannot be imported in probe source
- classifying unknown bytes as prompts, weights, activations, images, or files
- storing raw unknown buffers — `pickle`/`marshal`/`shelve` cannot be imported

`SafeBuffer` refuses to be printed, formatted, indexed, iterated, copied,
pickled, or converted to bytes. Each raises rather than returning a redacted
placeholder, because a placeholder would let a caller believe the operation
succeeded. It is zeroed on scope exit, including on the exception path.

**Lifetime.** A `SafeBuffer` cannot outlive its `with` block.
`live_buffer_count()` is asserted to be zero between experiments.

---

## The automatic safety stop (§7.3)

Fires when a buffer holds content inconsistent with expected allocation
behaviour **and** no owned canary matched. On firing: analysis stops, the raw
buffer is destroyed, only the aggregate record survives, the run is marked
`sensitive_observation`, and automatic publication is blocked.

Two independently-armed triggers, and the distinction is load-bearing:

- **`expect_zeroed`** — we asserted this allocation should be clean and it is
  not. Armed whenever set, on any hardware.
- **`shared_infrastructure`** — high-entropy content on hardware that might
  hold someone else's data. **Armed only on rented infrastructure.**

The second condition was originally unconditional, which produced five safety
stops on the project's own baseline measurement. NVIDIA documents that
`cudaMalloc` does not clear memory, so high entropy in a fresh allocation is
the *expected* phenomenon, not an incident. Arming it everywhere made GPU-SEAL
unable to take its own primary measurement.

Note what the stop does **not** do: it never decides *what* the content is.
It decides that the content is not what we expected and not ours, and
therefore that we stop looking. Deciding what it is would be the §4.3
violation.

---

## Never published (§10)

Account IDs · unnecessary public IPs · stable GPU UUIDs · hostnames ·
provider-internal IDs · sensitive raw traceroutes · exact server coordinates ·
raw unknown GPU memory.

Enforcement: `ObservationRecord._refuse_unhashed_identifier` refuses any
observation whose `subject` names one of these, unless it is the `_hash` form
carrying a value produced by `stable_hash()`. Identifiers that are useful for
joining observations — GPU UUID, account ID — are hashed **at collection**, so
the clear value never reaches a field something else might serialise.

`stable_hash` is domain-separated: the same identifier hashed for two purposes
gives different digests, so one disclosed mapping does not leak another.

**It is not anonymisation and does not claim to be.** The input space for a GPU
UUID is small enough to enumerate if you hold the fleet. The guarantee is "not
published in the clear", not "unrecoverable by the provider who issued it", and
the paper says so.

---

## Retention and publication

| Artefact | Retained | Publishable |
|---|---|---|
| Raw unknown VRAM | never | never |
| Aggregate statistics | yes, signed | subject to the gate below |
| Environment observations | yes, signed | subject to the gate below |
| Canary keys | operator-held, never in a bundle | never |
| Signed bundles | indefinitely | subject to the gate below |

A bundle can be cleared for publication only when **all** of:

1. no probe carries `sensitive_observation` (§7.3, §16 test 7);
2. no probe ran on a simulated backend — publishing modelled residue would be
   fabrication;
3. every probe ran under container profile `pinned` — a `dev-unpinned` image
   resolves dependencies at build time, and a bare-metal run has no image at
   all, so neither can supply the container digest §10 requires;
4. any grade-D finding has been through the §7.5 disclosure sequence.

`clear_for_publication()` must be called **before** `sign()`. The flag is part
of the signed payload, so clearing afterwards changes an in-memory boolean and
nothing on disk. Every bundle this project wrote before 2026-07-31 carried
`automatic_publication_allowed: false` regardless of what the console printed,
for exactly that reason. `EvidenceStore.write` is now the supported path and
does the steps in the correct order, then reads the file back and verifies what
actually landed.

**Unpublishable is not the same as unusable.** Signed local control runs are
retained. Deleting inconvenient signed evidence is its own bad habit — the two
mislabelled GPU bundles in `out/` are quarantined with a README rather than
removed.
