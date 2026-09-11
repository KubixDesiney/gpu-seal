# Provider runtime boundary

GPU-SEAL now owns the campaign orchestration boundary, but it does not ship a
real provider adapter. `CampaignOrchestrator` sequences bounded runs through
the small `ProviderRuntime` contract in
[`probe/gpu_seal/controller/native_runner.py`](../probe/gpu_seal/controller/native_runner.py).
Each logical campaign supplies one root-owned `CampaignControl` to every
runner. A missing context is a fail-closed error for shared-infrastructure
execution.

The contract has three operations:

- `launch(plan)` creates only the operator's authorized allocation;
- `execute(allocation, command, timeout_s)` runs the pinned native command and
  returns typed stdout/status information;
- `terminate(allocation)` destroys the allocation and returns explicit cleanup
  and billing reconciliation state, including unknown state.

`DeterministicFakeRuntime` is the repository-owned contract test double. Its
output is deliberately marked simulated and is not provider or hardware
evidence. The CLI campaign command uses this runtime only; it has no cloud
SDK, provider credentials, or spending path.

Selecting a concrete provider requires an owner decision about the provider,
authorized credentials, permitted API operations, budget, kill-switch, and
written permission where applicable. After that decision, an adapter can be
added behind `ProviderRuntime` and tested against the existing fake-runtime
contract without changing the safety layer. Until then, provider-facing
execution remains unavailable by design.
