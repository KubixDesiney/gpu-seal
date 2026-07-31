# ADR-002 — Canary wire format

- **Status:** Accepted
- **Date:** 2026-07-29
- **Charter reference:** §7.1, §23 immediate task 5
- **Implementation:** `probe/gpu_seal/safety/canary.py`

## Context

Charter §7.1 requires a canary that is randomly generated, unique per
experiment, non-semantic, cryptographically identifiable, bound to an
experiment ID, and free of personal information, real secrets, copyrighted
content, and realistic prompts.

The charter sketches a logical structure but leaves the encoding open. The
encoding has to satisfy three constraints simultaneously:

1. **Ownership must be cryptographically checkable**, or "we only searched for
   our own data" is a promise rather than a claim.
2. **The marker must be harmless if it surfaces in someone else's memory.**
   We are writing data into infrastructure other people also use. If our
   marker ever appeared in a third party's dump, it must leak nothing and
   alarm nobody.
3. **It must survive partial overwrite informatively.** A half-scrubbed buffer
   is a different finding from a fully-scrubbed one, and the format should let
   us measure that.

## Decision

A fixed **128-byte** binary record, 16-byte aligned:

```
offset  size  field          notes
------  ----  -------------  --------------------------------------------
0       8     magic          b'GPUSEALC' — the only ASCII in the record
8       2     version        uint16 LE
10      2     boundary_id    uint16 LE, see Boundary enum
12      4     flags          uint32 LE, reserved for probe-specific bits
16      16    experiment_id  UUID bytes
32      16    allocation_id  UUID bytes
48      32    nonce          os.urandom(32)
80      16    reserved       zeros
96      32    mac            BLAKE2b-256(key=experiment_key, msg=bytes[0:96])
------  ----
        128
```

### Rationale, field by field

**128 bytes, 16-byte aligned.** Aligns with GPU allocation granularity and
vector load widths, so a canary is unlikely to straddle a boundary in a way
that complicates interpretation.

**Magic first, and it is the only ASCII.** A recognisable prefix makes scanning
cheap. Putting it first also means that a *foreign* canary — one minted by a
different experiment or a different researcher running GPU-SEAL — can collide
with ours on at most the first 16 bytes, because everything identifying
(experiment ID onward) begins at offset 16. That property is asserted in
`test_search_does_not_find_another_experiments_canary`.

**Boundary in the record, not just in a log.** A recovered marker states which
isolation boundary it was written across. Correlating against an external log
would be fragile when the two allocations are on different machines.

**32-byte random nonce.** Makes each canary globally unique without a counter,
and gives a strong unique substring for partial-survival detection.

**Keyed BLAKE2b-256 MAC over the whole header.** This is the ownership proof.
Without the experiment key you cannot forge a canary that GPU-SEAL will
accept, so `authenticate()` is a real gate rather than a formality. BLAKE2b
over HMAC-SHA256 for native keying and speed; the security margin is
equivalent for this purpose.

**Reserved 16 bytes of zeros.** Room to extend without a version bump for
purely additive fields, and it keeps the MAC on a clean 96-byte boundary.

### Non-semantic by construction

Everything after the 8-byte magic is either a UUID, random bytes, a small
integer, or a MAC. There is no readable text anywhere. This is asserted, not
assumed: `test_canary_contains_no_readable_text` mints 50 canaries and fails
if any contains a printable run longer than 11 bytes.

This matters for a reason that is easy to miss. We are writing markers into
shared infrastructure. If a canary ever surfaced in another tenant's memory
dump, or in a provider's incident investigation, it must be self-evidently
inert — not a sentence, not a credential-shaped string, nothing that would
read as an intrusion attempt to someone who found it without context.

## Partial survival

`CanarySet.search` reports, per canary, the longest prefix present in the
buffer, via binary search over prefix length (~7 substring scans for a
128-byte needle rather than 128).

Interpretation:

| Recovered | Meaning |
|---|---|
| 128 bytes, MAC verifies | Full survival. Strong signal; investigate privately per §7.5. |
| 16–127 bytes | Partial survival — the region was overwritten part-way. Itself a measurement. |
| ≤ 16 bytes | Header collision only. Not evidence of anything; a foreign canary can produce this. |
| 0 bytes | No survival. |

## Consequences

- The experiment key must be generated per experiment and never committed.
  Losing it means previously-written canaries can no longer be authenticated —
  acceptable, since an experiment that lost its key cannot make claims anyway.
- 128 bytes is large enough that writing many canaries across a multi-GiB
  buffer is cheap, and small enough to survive in a partially-reused block.
- A future v2 format must bump `version`; the matcher rejects unknown versions
  rather than attempting to interpret them.

## Rejected alternatives

**Plain random bytes, no structure.** Simplest, but then "is this ours?" is
answered by a lookup table rather than cryptography, and a truncated marker
cannot say which boundary or allocation it came from.

**Readable structured text (JSON, key=value).** Trivially debuggable, and
disqualifying. A readable marker in shared infrastructure is exactly what
§7.1 forbids, and would look alarming to anyone who found it.

**HMAC-SHA256 instead of keyed BLAKE2b.** Equivalent security, marginally
slower, requires an extra import. No reason to prefer it here.
