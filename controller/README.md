# controller/

Operator-facing configuration for the GPU-SEAL controller.

**The controller code is not here.** It lives at
`probe/gpu_seal/controller/`, imported as `gpu_seal.controller`. The reason is
in [`docs/architecture.md`](../docs/architecture.md#deviations-from-chartermd-15):
a second distribution root would need the test suite, the §16 static analysis,
and the Phase 0 provider-name CI gate each taught about it separately, and
controller code being held to the same static analysis as probe code matters
more than matching the charter's directory sketch.

This directory keeps the layout §15 describes and holds the things an operator
edits rather than the things a reviewer audits.

| Subdirectory | Holds | Code that reads it |
|---|---|---|
| `providers/` | provider adapters and per-provider deployment config | `gpu_seal.controller.policy_matrix` reads the *policy* records from `docs/provider-policy-review/` |
| `scheduler/` | experiment definitions (see `examples/`) | `gpu_seal.controller.scheduler` |
| `budget/` | spend caps per campaign | `gpu_seal.controller.budget` |
| `evidence/` | signed bundle output, when not written to `out/` | `gpu_seal.controller.evidence_store` |
| `disclosure/` | disclosure records and correspondence | `gpu_seal.controller.disclosure` |

All five are empty. They fill during Phase 2, which is blocked on the provider
policy matrix — see [`docs/provider-policy-review/`](../docs/provider-policy-review/).

## What the controller refuses

Before any probe runs against any provider:

- **No reviewed policy record** → `ProviderNotReviewed`
- **Provider classified `prohibited`** → `ProviderProhibited` (raised, not
  returned, so a caller who forgot to check a boolean cannot proceed)
- **`self-canary-only` and the probe is not self-canary-safe** → refused
- **`needs-written-permission` with no permission on record** → refused
- **Policy review older than 365 days** → refused as stale
- **No ownership confirmation on the plan** → `OwnershipNotConfirmed`
- **Estimated cost over any cap** → `BudgetExceeded`, before the instance exists
- **Run exceeds `max_duration_s`** → marked aborted and excluded from statistics

Check the current state with:

```bash
python3 lab/check-provider-policy.py
```
