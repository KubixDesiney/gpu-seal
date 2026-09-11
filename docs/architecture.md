# Architecture

**Charter:** §8, §15

```text
┌───────────────────────────────────────────────────────────┐
│ Controller            gpu_seal.controller                  │
│  policy_matrix   §7.4 provider allowlist  (§16 test 13)    │
│  scheduler       duration + ownership     (§16 tests 11,14)│
│  budget          per-run/provider/day/campaign caps  (§20) │
│  orchestrator    one campaign context + runtime contract   │
│  fake_runtime    deterministic local contract validation   │
│  evidence_store  gate → sign → write → verify        (§10) │
│  disclosure      the §7.5 state machine                    │
└───────────────────────────┬───────────────────────────────┘
                            │ deploy
┌───────────────────────────▼───────────────────────────────┐
│ Tenant probe agent    gpu_seal.probes                      │
│  environment §9.1   memory_local §9.2   memory_global §9.3 │
│  framework_allocator §9.4   self_canary §9.5               │
│  device_exposure §9.6   allocation_model §9.7              │
│  topology §9.8   location §9.9   attestation §9.10/§9.11   │
│  mig_temporal §9.12                                        │
├───────────────────────────────────────────────────────────┤
│ Enforced-safe layer   gpu_seal.safety                      │
│  SafeBuffer · canary · aggregation · policy · metadata     │
└───────────────────────────┬───────────────────────────────┘
                            │ signed safe results
┌───────────────────────────▼───────────────────────────────┐
│ Evidence              gpu_seal.evidence                    │
│  AggregateRecord · ObservationRecord · ResultBundle        │
│  Ed25519 signing sources · public fingerprints · schemas   │
└───────────────────────────┬───────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────┐
│ Analysis              gpu_seal.analysis                    │
│  statistics (Wilson, bootstrap) · separability (D5)        │
│  reporting.report_card §13                                 │
└───────────────────────────────────────────────────────────┘
```

## Design principles, and where each is enforced

**Safety is centralised.** All handling of memory GPU-SEAL did not write passes
through `gpu_seal.safety`. `SafeBuffer` has exactly two doors — `fill_via` in,
`aggregate()` out — and `tests/safety/test_static_analysis.py` proves by
parsing every module under `probe/` that no other module calls `_unsafe_view`,
materialises bytes, prints, decodes, or imports a regex engine.

The exemption lists (`SAFE_LAYER_MODULES`, `LOW_LEVEL_MEMORY_MODULES`) are
capped in size by a test, so widening them requires a deliberate decision and a
bumped number rather than a quiet append.

**Everything is a signed structured result.** No probe returns bytes; no probe
prints. `ResultBundle` carries the measurement, its provenance, a machine-
payload.

**A campaign has one terminal safety state.** The campaign root creates one
`CampaignControl` and passes it to every shared-memory probe and provider
runner. The object retains only the first redacted stop record, uses instance
locking rather than process-global state, and is checked before allocation,
native execution, and device-to-host copying. Shared-infrastructure
constructors refuse to invent a private fallback context.

**Provider execution is an adapter boundary, not an invented integration.**
`CampaignOrchestrator` owns sequencing, bounded failure handling, and cleanup
reconciliation through `ProviderRuntime`. The deterministic fake is explicitly
simulated. A real adapter remains pending provider selection, authorized
credentials, permission constraints, and spending approval; no provider result
is inferred from the fake runtime.

**Two egress doors, because there are two hazards.** `AggregateRecord` guards
statistics over unknown memory. `ObservationRecord` guards description of the
rented environment, which is where §10's never-published identifiers would
otherwise leak. Both are allowlists that refuse rather than filter.

**Controls run alongside every measurement**, so "provider scrubbed" can be
separated from "runtime zeroed". §9.4 is the detection-capability control;
§9.3 is the measurement it makes interpretable.

**Backends declare their own measurement path.** It is the *allocator* that
determines whether the driver is ever told memory was released, so the backend
declares `driver_direct` / `framework_pooled` / `simulated` and the probe
inherits it. A probe declaring its own path is how §9.4 control data ended up
graded as a §9.3 provider failure.

## Deviations from CHARTER.md §15

**`controller/` code lives in the package.** §15 draws `controller/` as a
top-level directory; the code is at `probe/gpu_seal/controller/` instead. The
alternative is a second distribution root that the test suite, the static
analysis, and the Phase 0 provider-name CI gate would each need teaching about
separately. Controller code being held to the same static analysis as probe
code is worth more than the directory layout. The top-level `controller/`
directory holds operator-facing configuration; see `controller/README.md`.

**`analysis/` math lives in the package too**, at `probe/gpu_seal/analysis/`,
so that every figure in the paper is produced by code the test suite exercises.
A number that exists only inside a notebook cell is a number nobody can
reproduce. `analysis/` at the top level holds notebooks and figures that import
it.

## Minimal usage example

```python
from gpu_seal.safety import SafeBuffer, CanarySet, Boundary, aggregate

canaries = CanarySet.create()
marker = canaries.mint(Boundary.SEQUENTIAL_ALLOCATION)

with SafeBuffer.acquire(4 << 20, provenance="cudaMalloc:device_global") as buf:
    buf.fill_via(lambda view: copy_device_to_host(view, device_ptr))
    record = aggregate(
        buf, canaries,
        probe_name="memory_global_read_before_write",
        probe_version="0.1.0",
        expect_zeroed=False,
    )
# buffer zeroed here, unconditionally

print(record.owned_canary_match, record.zero_fraction)
# print(buf)  ← raises UnknownMemoryRenderError
```

`fill_via` is the only write door onto unknown memory; `aggregate()` is the
only read door, and it returns allowlisted statistics, never bytes.
