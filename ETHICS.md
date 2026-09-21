# Ethics Policy

**This is a set of product requirements, not a disclaimer.**

Every rule below is enforced somewhere in code or CI. Where a rule is
enforced, the enforcement point is named. If you find a rule here with no
enforcement, that is a bug — please open an issue.

Governing document: [`CHARTER.md`](CHARTER.md) §7.

---

## The one-sentence version

> GPU-SEAL searches memory **only** for cryptographic markers it created
> itself, and never interprets, decodes, classifies, retains, or publishes
> memory it did not write.

---

## 1. Canary-only search

GPU-SEAL may search only for canaries the operator generated. Each canary is
randomly generated, unique per experiment, non-semantic, cryptographically
authenticated, and bound to an experiment ID. It contains no personal
information, no real secrets, no copyrighted content, and no realistic
prompts or messages — the payload is a random nonce and a keyed MAC.

There is deliberately **no API that accepts a caller-supplied search pattern.**

| Enforcement | Where |
|---|---|
| Canaries authenticate under an experiment-specific key | `probe/gpu_seal/safety/canary.py` — `CanarySet.authenticate` |
| Foreign canaries are rejected | `tests/safety/test_canary_ownership.py::test_canary_from_another_experiment_is_rejected` |
| No general-purpose search method exists | `tests/safety/test_canary_ownership.py::test_there_is_no_arbitrary_pattern_search_api` |
| Canaries contain no readable text | `tests/safety/test_canary_ownership.py::test_canary_contains_no_readable_text` |

## 2. Unknown memory is never rendered or retained

The system must never print unknown bytes, render them as text, attempt UTF-8
decoding, search them for natural-language patterns or credentials, classify
them as prompts / weights / activations / images / files, upload them to an
LLM, or store them in logs, files, or crash dumps.

Unknown memory lives in a `SafeBuffer`, which refuses `repr()`, `str()`,
f-string interpolation, `print()`, `bytes()`, `memoryview()`, indexing,
slicing, iteration, membership testing, hashing, copying, pickling, JSON
serialisation, and the buffer protocol. Every refusal raises; none returns a
placeholder.

| Enforcement | Where |
|---|---|
| All refusals | `probe/gpu_seal/safety/buffer.py` |
| 26 containment tests | `tests/safety/test_buffer_containment.py` |
| Static: no `print()` in probe source | `tests/safety/test_static_analysis.py` |
| Static: no `.decode()`, no `codecs` | same |
| Static: no `re` / `regex` imports | same |
| Static: no `pickle` / `marshal` / `shelve` | same |

## 3. Only aggregate statistics leave a probe

What may be retained is an **allowlist**, not a denylist. A key absent from
`SAFE_AGGREGATE_KEYS` is refused, not filtered — so adding a field is a
deliberate, reviewable act.

Permitted: zero fraction · fixed-pattern fraction · byte histogram · entropy
estimate · repeated-block count · exact owned-canary matches · longest
owned-canary prefix · measurement hash · probe version · driver metadata ·
error codes · timing.

| Enforcement | Where |
|---|---|
| Allowlist | `probe/gpu_seal/safety/policy.py` — `SAFE_AGGREGATE_KEYS` |
| Egress check | `probe/gpu_seal/safety/aggregation.py` — `AggregateRecord.to_dict` |
| Schema `additionalProperties: false` | `schemas/result.schema.json` |

**Explicitly removed in charter v1→v2:** detection of "structured content"
(float / ASCII / token-ID patterns) in returned buffers. That edged toward
interpreting another tenant's data. It is not coming back.

## 4. Automatic safety stop

If a probe observes unknown content inconsistent with expected allocation
behaviour, and that content is not ours, analysis halts immediately. The raw
buffer is destroyed, only the aggregate record survives, the run is marked
`sensitive_observation`, automatic publication is blocked, and manual
disclosure review is required.

Note the ordering: GPU-SEAL never decides *what* the content is. It decides
only that the content is unexpected and not ours, and therefore that it stops
looking.

| Enforcement | Where |
|---|---|
| Stop logic | `probe/gpu_seal/safety/aggregation.py` — `_check_safety_stop` |
| Publication gate | `probe/gpu_seal/evidence/result.py` — `clear_for_publication` |
| Schema gate | `schemas/result.schema.json` — `safety.allOf` |

## 5. Provider terms and permission

Before testing any provider we review its AUP, security-testing policy, and
vulnerability-disclosure programme, and request written permission where the
policy is unclear. Every provider is classified `full-probe-ok`,
`self-canary-only`, `needs-written-permission`, or `prohibited` before a
single probe runs against it.

Under `self-canary-only`, only probes that touch exclusively our own marker
data may run — environment inventory, device-exposure inventory, self-vs-self
sequential canary, and MIG temporal isolation. Global VRAM read-before-write
is **not** on that list, because it reads memory we did not write.

| Enforcement | Where |
|---|---|
| Policy classes | `probe/gpu_seal/safety/policy.py` |
| Probe restriction set | same — `SELF_CANARY_ONLY_SAFE_PROBES` |
| Test | `tests/safety/test_operational_limits.py` |

## 6. Responsible disclosure

Reproduce internally → eliminate methodology error → confirm only owned
canaries matched → minimal technical report → private contact → offer source,
logs, hashes, environment → 90-day remediation window → re-test → publish only
after coordination or documented non-response.

Verified facts, probable interpretations, and unresolved uncertainty are
always presented separately. See [`DISCLOSURE.md`](DISCLOSURE.md).

## 7. Naming

No public ranking by provider name until the methodology is validated,
positive and negative controls exist, measurements are repeated, provider
responses are considered, uncertainty is represented, and ethical review has
passed. During the pilot, providers are Provider A / B / C / D.

## 8. What GPU-SEAL will never do

Exploit a provider · escape a VM or container · access the host OS ·
circumvent authentication or billing · scan infrastructure it does not rent ·
read another tenant's files, processes, traffic, or API data · recover
natural-language text from unknown memory · classify unknown memory · save raw
unknown VRAM · attempt GPU Rowhammer, privilege escalation, or denial of
service · saturate shared infrastructure · publish an uncoordinated accusation
· present uncertain measurements as proof of malicious provider behaviour.

Static analysis rejects source containing container-escape indicators,
privileged process calls, and offensively-named symbols — see
`tests/safety/test_static_analysis.py`.

---

## Verifying these claims yourself

```bash
pytest tests/safety -v          # every rule above, as executable tests
bash lab/verify-safety-suite.sh # proves the suite goes red when violated
```

The second command matters more than the first. A green safety suite proves
nothing unless it can be shown to fail. `verify-safety-suite.sh` injects the
current 39 known policy violations into a scratch copy of the repo and asserts
that each one turns the suite red. The authoritative measured result is in
[`docs/STATUS.md`](docs/STATUS.md).

---

## Reporting an ethics concern

If you believe GPU-SEAL has violated any rule on this page — in code, in a
published result, or in conduct toward a provider — report a code/safety issue
privately as described in [`SECURITY.md`](SECURITY.md). Concerns about a
specific provider interaction belong in [`DISCLOSURE.md`](DISCLOSURE.md), not a
public issue. An ethics concern that is not security-sensitive may be opened
as an issue with no provider-identifying details.
