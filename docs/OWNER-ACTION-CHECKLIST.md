# Owner action checklist

This list deliberately records decisions for the project owner. It is not a
recommendation to choose any particular option, and checking an item requires
the owner to record the decision or evidence outside the automated test suite.

## Working baseline approved 2026-09-02

The owner approved the current working direction: GPU-SEAL as the public name,
GHOSTMETER as the internal codename, the tenant-side assurance and measurement
category, an integrity-plus-external-key trust model, and a pre-alpha platform
posture centered on the exercised Windows CUDA path. Linux/WSL2 remains a
documented target path; provider, MIG, H100 CC, and same-model claims remain
experimental. This approval does not authorize provider testing, publication,
deployment, disclosure, or a commit.

Use [`OWNER-DIFF-MAP.md`](OWNER-DIFF-MAP.md) for the file-by-file inclusion
recommendation before staging the dirty tree.

- [ ] Approve the binding unknown-memory security guarantee.
- [ ] Review and commit or discard the current dirty-tree changes.
- [x] Engineering implementation: campaign-wide terminal safety, explicit
      signing sources/fingerprints, provider runtime boundary with deterministic
      fake, cleanup/timeout handling, action pin policy, dependency fixes, and
      coverage/license gates are in the repository; this does not authorize a
      provider run or make simulated output evidence.
- [ ] Select a concrete provider and approve its exact adapter permission
      scope, credentials, spending ceiling, billing alerts, and kill switch.
- [x] Choose the primary public name and product category. Working baseline:
      GPU-SEAL and tenant-side GPU-cloud assurance and measurement framework.
- [x] Choose supported platforms and the formal trust model. Working baseline:
      exercised Windows CUDA path, documented Linux/WSL2 target path, and
      integrity-plus-external-key verification without a provider-attestation
      claim.
- [ ] Sign the ethics protocol.
- [ ] Obtain written permission for unresolved providers.
- [ ] Supply cloud accounts, credentials, budget, billing alerts, and provider kill switches.
- [ ] Authorize real Linux, MIG A100/H100, H100 confidential-computing, and same-model experiments.
- [x] Approve deploying the pre-alpha dashboard to a public, unindexed
      `workers.dev` URL. Recorded 2026-09-20 on the owner's direction; evidence
      is the [deployment record](../dashboard/README.md#deployment-record) and
      the [STATUS section](STATUS.md#dashboard-deployment). This covers that
      deployment only, not the decisions in the next item.
- [ ] Approve disclosure, domain, and public-release decisions.
- [ ] Arrange an independent usability/accessibility review.

Until the relevant decisions and external evidence exist, keep provider-facing
execution disabled and treat local/simulated output as development evidence
only.
